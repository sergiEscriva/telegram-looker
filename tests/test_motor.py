import asyncio
import logging

from tgdl import motor
from tgdl.bd import BD
from tgdl.informes import Informe


class InformeLista(Informe):
    def __init__(self):
        self.lineas = []

    def log(self, texto, nivel="info"):
        self.lineas.append((nivel, texto))


class Falsa:
    """Descarga de canal mínima para probar la orquestación."""

    def __init__(self, canal_id):
        self.canal_id, self.titulo = canal_id, f"canal {canal_id}"
        self.preparada = False

    async def preparar(self):
        self.preparada = True

    async def historial(self):
        pass


def _ctx(tmp_path, informe):
    return motor.Contexto(BD(tmp_path / "d.db"), motor.Opciones(html=False, notificar=False).validar(), informe,
                          motor.Limitador(0), asyncio.Event())


def test_no_descarga_dos_veces_el_mismo_canal(tmp_path):
    informe = InformeLista()
    ctx = _ctx(tmp_path, informe)
    a, b = Falsa(-1001), Falsa(-1001)

    async def principal():
        await motor._correr_grupo(ctx, [a])
        await motor._correr_grupo(ctx, [b])  # mismo canal mientras el trabajo sigue activo

    asyncio.run(principal())
    assert a.preparada and not b.preparada
    assert any("ya se está descargando" in t for _, t in informe.lineas)
    motor._CANALES_ACTIVOS.difference_update(ctx.canales)
    ctx.bd.cerrar()


def test_avisos_de_telethon_van_a_su_cuenta():
    uno, otro = InformeLista(), InformeLista()
    motor._LOG_TELETHON.destinos.update({"uno": [uno], "otro": [otro]})
    try:
        logging.getLogger("tgdl.cuenta.uno.client.users").info("Sleeping for 5s on flood wait")
        logging.getLogger("tgdl.cuenta.otro.network").info("Conectando")  # info normal: se ignora
    finally:
        motor._LOG_TELETHON.destinos.clear()
    assert len(uno.lineas) == 1 and "[uno]" in uno.lineas[0][1]
    assert otro.lineas == []


def test_limitador_sin_limite_no_espera():
    asyncio.run(motor.Limitador(0).consumir(10**9))
