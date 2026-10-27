"""Informes de progreso: el motor emite eventos y cada interfaz (consola / panel web) los muestra."""
from tqdm import tqdm

from .utilidades import tamano_legible


class Informe:
    """Interfaz base (no hace nada). Claves: `clave` = canal+cuenta, `slot` = hueco de descarga."""

    def log(self, texto: str, nivel: str = "info"): ...
    def fase(self, nombre: str): ...
    def canal_inicio(self, clave, titulo, total, hechos, cuenta): ...
    def ampliar(self, clave, n=1): ...
    def avance(self, clave, n=1): ...
    def canal_fin(self, clave, stats: dict): ...
    def archivo_inicio(self, slot, nombre, total): ...
    def archivo_progreso(self, slot, recibido): ...
    def archivo_fin(self, slot): ...


def resumen_stats(stats: dict) -> str:
    return (f"{stats['ok']} descargados ({tamano_legible(stats['bytes'])}), {stats['duplicados']} duplicados, "
            f"{stats['fallos']} fallidos, {stats['omitidos']} omitidos por filtro")


class InformeConsola(Informe):
    _ICONOS = {"info": "", "aviso": "⚠️  ", "error": "❌ ", "ok": "✅ "}

    def __init__(self):
        self.barras, self.slots, self.titulos = {}, {}, {}
        self._libres, self._siguiente = [], 0

    def _posicion(self):
        if self._libres:
            return self._libres.pop(0)
        self._siguiente += 1
        return self._siguiente - 1

    def _soltar(self, barra):
        pos = barra.pos if barra.pos >= 0 else -barra.pos
        barra.close()
        self._libres.append(pos)
        self._libres.sort()

    def log(self, texto, nivel="info"):
        tqdm.write(f"{self._ICONOS.get(nivel, '')}{texto}")

    def fase(self, nombre):
        if nombre == "vigilando":
            tqdm.write("\n👀 Modo vigilancia activo: los mensajes nuevos se descargan al instante. Ctrl+C para salir.")

    def canal_inicio(self, clave, titulo, total, hechos, cuenta):
        self.titulos[clave] = f"{titulo} [{cuenta}]"
        etiqueta = (titulo[:22] + f" [{cuenta}]")[:30].ljust(30)
        self.barras[clave] = tqdm(total=total, initial=hechos, desc=etiqueta, unit="msg",
                                  position=self._posicion(), leave=False, dynamic_ncols=True)

    def ampliar(self, clave, n=1):
        if clave in self.barras:
            self.barras[clave].total += n
            self.barras[clave].refresh()

    def avance(self, clave, n=1):
        if clave in self.barras:
            self.barras[clave].update(n)

    def canal_fin(self, clave, stats):
        barra = self.barras.pop(clave, None)
        if barra:
            self._soltar(barra)
        tqdm.write(f"✅ {self.titulos.get(clave, clave)}: {resumen_stats(stats)}")

    def archivo_inicio(self, slot, nombre, total):
        self.slots[slot] = [tqdm(total=total, desc=("  ↳ " + nombre)[:30].ljust(30), unit="B", unit_scale=True,
                                 unit_divisor=1024, position=self._posicion(), leave=False, dynamic_ncols=True), 0]

    def archivo_progreso(self, slot, recibido):
        if slot in self.slots:
            barra, previo = self.slots[slot]
            barra.update(recibido - previo)
            self.slots[slot][1] = recibido

    def archivo_fin(self, slot):
        par = self.slots.pop(slot, None)
        if par:
            self._soltar(par[0])
