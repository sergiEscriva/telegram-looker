"""Motor de descarga: recorre canales, aplica filtros, descarga en paralelo con una o varias cuentas."""
import asyncio
import contextlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from telethon import errors, events, utils
from telethon.tl.functions.messages import CheckChatInviteRequest, GetForumTopicsRequest
from telethon.tl.types import ChatInviteAlready, ChatInvitePeek, MessageService

from .bd import BD
from .config import RUTA_BD, SALIDA_POR_DEFECTO
from .html_export import generar_html_async
from .informes import Informe, resumen_stats
from .utilidades import (TIPOS, clasificar, clave_archivo, extension, limpiar, parse_fecha, parse_lista,
                         parse_tamano, tamano_legible)


# --------------------------------------------------------------------------- #
# Opciones
# --------------------------------------------------------------------------- #
@dataclass
class Opciones:
    salida: Path = SALIDA_POR_DEFECTO
    hilos: int = 3
    tipos: set = field(default_factory=lambda: set(TIPOS))
    desde: datetime = None
    hasta: datetime = None
    min_tamano: int = 0
    max_tamano: int = 0
    extensiones: set = field(default_factory=set)
    excluir_extensiones: set = field(default_factory=set)
    buscar: str = ""
    albumes: bool = True
    nombres: str = "original"          # "original" | "texto"
    comentarios: bool = False
    seguir: bool = False
    html: bool = True
    deduplicar: bool = True
    limite_velocidad: int = 0          # bytes/s, 0 = sin límite
    espacio_minimo: int = 1024 ** 3    # deja al menos 1 GB libre
    notificar: bool = True
    reparto: str = "canal"             # "canal" | "mensajes"
    conexiones: int = 4                # trozos que se piden a la vez de cada archivo grande
    takeout: bool = False              # modo exportación de Telegram (menos esperas en historiales enormes)

    def validar(self):
        self.salida = Path(self.salida)
        self.hilos = max(1, min(int(self.hilos), 10))
        self.conexiones = max(1, min(int(self.conexiones), 8))
        self.tipos = parse_lista(self.tipos) or set(TIPOS)
        malos = self.tipos - set(TIPOS)
        if malos:
            raise ValueError(f"Tipos no válidos: {', '.join(malos)}. Opciones: {', '.join(TIPOS)}")
        if self.nombres not in ("original", "texto"):
            raise ValueError("nombres debe ser 'original' o 'texto'")
        if self.reparto not in ("canal", "mensajes"):
            raise ValueError("reparto debe ser 'canal' o 'mensajes'")
        return self

    @classmethod
    def desde_dict(cls, d: dict) -> "Opciones":
        """Construye las opciones a partir de textos (CLI / panel web)."""
        o = cls()
        for clave in ("salida", "hilos", "albumes", "nombres", "comentarios", "seguir", "html",
                      "deduplicar", "notificar", "reparto", "buscar", "conexiones", "takeout"):
            if d.get(clave) not in (None, ""):
                setattr(o, clave, d[clave])
        o.tipos = parse_lista(d.get("tipos"))
        o.desde = parse_fecha(d.get("desde"))
        o.hasta = parse_fecha(d.get("hasta"), fin_de_dia=True)
        o.min_tamano = parse_tamano(d.get("min_tamano"))
        o.max_tamano = parse_tamano(d.get("max_tamano"))
        o.extensiones = parse_lista(d.get("extensiones"))
        o.excluir_extensiones = parse_lista(d.get("excluir_extensiones"))
        o.limite_velocidad = parse_tamano(d.get("limite_velocidad"))
        if d.get("espacio_minimo") not in (None, ""):
            o.espacio_minimo = parse_tamano(d["espacio_minimo"])
        return o.validar()


# Descarga por trozos: Telegram sirve como máximo 512 KB por petición, alineados a 4 KB.
TROZO = 512 * 1024
MIN_TROCEADO = 4 * 1024 * 1024  # los documentos de 4 MB o más se bajan por trozos (en paralelo y reanudables)


class SinEspacio(Exception):
    pass


class Detenido(Exception):
    """Se lanza dentro de una descarga en curso cuando el usuario pide detener."""


# Canales que se están descargando ahora mismo (en cualquier trabajo): evita que dos
# descargas del mismo canal escriban a la vez los mismos archivos.
_CANALES_ACTIVOS: set = set()


class Limitador:
    """Limita la velocidad total de descarga de un trabajo (compartido por todas sus cuentas y canales)."""

    def __init__(self, bytes_por_segundo: int):
        self.bps = bytes_por_segundo
        self._libre_en = time.monotonic()

    async def consumir(self, n: int):
        if not self.bps or n <= 0:
            return
        ahora = time.monotonic()
        self._libre_en = max(self._libre_en, ahora) + n / self.bps
        espera = self._libre_en - ahora - 0.5  # permite pequeñas ráfagas
        if espera > 0:
            await asyncio.sleep(espera)


@dataclass
class Contexto:
    bd: BD
    opc: Opciones
    informe: Informe
    limitador: Limitador
    detener: asyncio.Event
    descargas: list = field(default_factory=list)
    canales: set = field(default_factory=set)   # canales reservados en _CANALES_ACTIVOS por este trabajo
    reservado: list = field(default_factory=lambda: [0])  # bytes de descargas en curso (para el espacio libre)
    en_curso: dict = field(default_factory=dict)  # clave de archivo -> Event (descargas en marcha, para duplicados)
    reales: dict = field(default_factory=dict)  # cuenta -> cliente normal (si se usa Takeout, el cliente va envuelto)


class _LogTelethon(logging.Handler):
    """Reenvía los avisos de Telethon (sobre todo esperas por FloodWait) a los trabajos que usan esa cuenta.

    Cada cliente registra en "tgdl.cuenta.<nombre>" (ver cuentas.py), así que el aviso de una
    cuenta solo aparece en los trabajos que la usan.
    """

    def __init__(self):
        super().__init__(logging.INFO)
        self.destinos: dict = {}  # nombre de cuenta -> [informes]

    def emit(self, record):
        partes = record.name.split(".")
        cuenta = partes[2] if len(partes) > 2 else None
        informes = self.destinos.get(cuenta, ())
        if not informes:
            return
        texto = record.getMessage()
        if "flood wait" in texto.lower():
            mensaje, nivel = f"⏳ [{cuenta}] Telegram pide esperar: {texto}", "aviso"
        elif record.levelno >= logging.ERROR:
            mensaje, nivel = f"Telethon [{cuenta}]: {texto}", "error"
        else:
            return
        for informe in informes:
            informe.log(mensaje, nivel)


_LOG_TELETHON = _LogTelethon()
_log_cuentas = logging.getLogger("tgdl.cuenta")
_log_cuentas.setLevel(logging.INFO)
_log_cuentas.propagate = False  # que no se mezcle con las barras de progreso de la consola
_log_cuentas.addHandler(_LOG_TELETHON)


# --------------------------------------------------------------------------- #
# Resolución de canales
# --------------------------------------------------------------------------- #
async def resolver(cliente, objetivo):
    """@usuario, enlace t.me, enlace de invitación o ID numérico -> entidad."""
    texto = str(objetivo).strip()
    privado = re.search(r"t\.me/c/(\d+)", texto)  # enlace a un mensaje de canal privado
    if privado:
        texto = f"-100{privado.group(1)}"
    m = re.search(r"(?:t\.me/\+|t\.me/joinchat/|^\+)([\w-]+)", texto)
    if m:
        info = await cliente(CheckChatInviteRequest(m.group(1)))
        if isinstance(info, (ChatInviteAlready, ChatInvitePeek)):
            return info.chat
        raise ValueError("no eres miembro de ese canal privado (únete desde la app)")
    if re.fullmatch(r"-?\d+", texto):
        ident = int(texto)
        try:
            return await cliente.get_entity(ident)
        except (ValueError, TypeError):
            async for d in cliente.iter_dialogs():  # la cuenta aún no tiene el canal en caché
                if d.id == ident or getattr(d.entity, "id", None) == abs(ident) % 10**12:
                    return d.entity
            raise ValueError("esta cuenta no está en ese canal")
    return await cliente.get_entity(texto)


async def listar_dialogos(cliente) -> list:
    return [d async for d in cliente.iter_dialogs() if d.is_channel or d.is_group]


# --------------------------------------------------------------------------- #
# Descarga de un canal con una cuenta
# --------------------------------------------------------------------------- #
class DescargaCanal:
    def __init__(self, ctx: Contexto, cliente, cuenta: str, entidad, particion=(0, 1)):
        self.ctx, self.cliente, self.cuenta, self.entidad = ctx, cliente, cuenta, entidad
        self.real = ctx.reales.get(cuenta, cliente)  # para eventos y mensajes (fuera del modo Takeout)
        self.k, self.n = particion
        self.canal_id = utils.get_peer_id(entidad)
        self.titulo = getattr(entidad, "title", None) or getattr(entidad, "username", None) or str(self.canal_id)
        self.carpeta = self._carpeta_canal()
        self.clave = f"{self.canal_id}:{cuenta}"
        self.es_foro = bool(getattr(entidad, "forum", False))
        self.cola: asyncio.Queue = asyncio.Queue(maxsize=ctx.opc.hilos * 4)
        self.hechos: set = set()
        self._hechos_otros: dict = {}       # hechos de grupos de comentarios
        self.temas: dict = {}
        self.textos_album: dict = {}
        self.posts_comentarios: list = []
        self.hilos_vistos: dict = {}
        self.stats = {"ok": 0, "fallos": 0, "omitidos": 0, "duplicados": 0, "bytes": 0}
        self.cambios = False
        self.trabajadores: list = []
        self.manejador = None

    # ---- preparación ------------------------------------------------------
    def _carpeta_canal(self) -> Path:
        """Carpeta del canal: «Título [id]», para que dos canales con el mismo nombre no se mezclen.

        Si el canal ya se descargó antes en esta misma carpeta de destino, se reutiliza la que tenía.
        """
        salida = Path(self.ctx.opc.salida)
        previo = self.ctx.bd.canal(self.canal_id)
        if previo and previo["carpeta"]:
            anterior = Path(previo["carpeta"])
            if anterior.is_dir() and anterior.parent.resolve() == salida.resolve():
                return anterior
        return salida / f"{limpiar(self.titulo, 70)} [{abs(self.canal_id)}]"

    def _mio(self, msg_id: int) -> bool:
        return msg_id % self.n == self.k

    async def _rango_ids(self):
        """(primero, último) id de mensaje dentro del filtro de fechas, o None si no hay filtro."""
        o = self.ctx.opc
        if not (o.desde or o.hasta):
            return None
        primero = 1
        if o.desde:
            r = await self.cliente.get_messages(self.entidad, limit=1, offset_date=o.desde, reverse=True)
            if not r:
                return (1, 0)
            primero = r[0].id
        r = await self.cliente.get_messages(self.entidad, limit=1, **({"offset_date": o.hasta} if o.hasta else {}))
        return (primero, r[0].id if r else 0)

    async def preparar(self):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.ctx.bd.guardar_canal(self.canal_id, self.titulo, self.carpeta)
        self.hechos = self.ctx.bd.hechos(self.canal_id)
        if self.es_foro:
            await self._cargar_temas()
        total = (await self.cliente.get_messages(self.entidad, limit=0)).total
        rango = await self._rango_ids()
        if rango:  # con filtro de fechas el total es aproximado (los ids pueden tener huecos)
            total = min(total, max(0, rango[1] - rango[0] + 1))
            hechos = sum(1 for h in self.hechos if self._mio(h) and rango[0] <= h <= rango[1])
        else:
            hechos = sum(1 for h in self.hechos if self._mio(h))
        if self.n > 1:
            total = total // self.n + 1
        self.ctx.informe.canal_inicio(self.clave, self.titulo, total, min(hechos, total), self.cuenta)
        self.trabajadores = [asyncio.create_task(self._trabajador(i)) for i in range(self.ctx.opc.hilos)]

    async def _cargar_temas(self):
        offset_date, offset_id, offset_topic = None, 0, 0
        try:
            for _ in range(100):
                r = await self.cliente(GetForumTopicsRequest(
                    peer=self.entidad, offset_date=offset_date, offset_id=offset_id,
                    offset_topic=offset_topic, limit=100))
                for t in r.topics:
                    if hasattr(t, "title"):
                        self.temas[t.id] = t.title
                if len(r.topics) < 100 or len(self.temas) >= r.count:
                    break
                ultimo = r.topics[-1]
                offset_topic, offset_id = ultimo.id, getattr(ultimo, "top_message", 0)
                fechas = {m.id: m.date for m in r.messages}
                offset_date = fechas.get(offset_id)
        except errors.RPCError as e:
            self.ctx.informe.log(f"No se pudieron leer los temas del foro: {e}", "aviso")

    def _tema(self, msg):
        if not self.es_foro:
            return None
        rt = getattr(msg, "reply_to", None)
        tid = (rt.reply_to_top_id or rt.reply_to_msg_id) if rt and getattr(rt, "forum_topic", False) else 1
        return self.temas.get(tid) or ("General" if tid == 1 else f"tema_{tid}")

    # ---- recorrido del historial -------------------------------------------
    async def historial(self):
        o = self.ctx.opc
        kwargs = {"reverse": True}
        if o.desde:
            kwargs["offset_date"] = o.desde
        async for msg in self.cliente.iter_messages(self.entidad, **kwargs):
            if self.ctx.detener.is_set():
                break
            if o.hasta and msg.date and msg.date > o.hasta:
                break
            if getattr(msg, "grouped_id", None) and getattr(msg, "message", None):
                self.textos_album[msg.grouped_id] = msg.message
            if o.comentarios and self.k == 0:
                self._anotar_comentarios(msg)
            if not self._mio(msg.id) or msg.id in self.hechos:
                continue
            await self.procesar(msg)
        if o.comentarios and self.k == 0 and not self.ctx.detener.is_set():
            await self._descargar_comentarios()
        await self.cola.join()
        # Si se detuvo, parte de los comentarios recorridos no llegó a descargarse: no se marca el
        # hilo como visto para que se revisen otra vez la próxima vez.
        if not self.ctx.detener.is_set():
            for post_id, ultimo in self.hilos_vistos.items():
                self.ctx.bd.guardar_hilo(self.canal_id, post_id, ultimo)
        self.ctx.bd.confirmar()
        self.ctx.informe.canal_fin(self.clave, self.stats)

    def _registrar(self, msg, estado, **campos):
        canal_id = utils.get_peer_id(msg.peer_id)
        self.ctx.bd.guardar_mensaje(
            canal_id, msg.id, estado, origen=self.canal_id, cuenta=self.cuenta,
            fecha=msg.date.isoformat() if msg.date else None,
            texto=getattr(msg, "message", None) or None, album=getattr(msg, "grouped_id", None),
            vistas=getattr(msg, "views", None), **campos)
        if canal_id == self.canal_id and estado != "fallo":
            self.hechos.add(msg.id)
        self.cambios = True

    async def procesar(self, msg, carpeta_base: Path = None, post_id: int = None):
        o = self.ctx.opc
        if (o.desde and msg.date < o.desde) or (o.hasta and msg.date > o.hasta):
            return
        if post_id is not None:
            self.ctx.informe.ampliar(self.clave)
        if isinstance(msg, MessageService):
            self._registrar(msg, "servicio")
            self.ctx.informe.avance(self.clave)
            return
        tema = self._tema(msg) if post_id is None else None
        tipo = clasificar(msg)
        if tipo is None:  # solo texto, enlaces, encuestas...
            if getattr(msg, "message", None):
                self._registrar(msg, "texto", tema=tema, post_id=post_id)
            else:
                self._registrar(msg, "servicio")
            self.ctx.informe.avance(self.clave)
            return
        if not self._pasa_filtros(msg, tipo):
            self.stats["omitidos"] += 1
            self.ctx.informe.avance(self.clave)
            return
        await self.cola.put((msg, tipo, carpeta_base, post_id, tema))

    def _pasa_filtros(self, msg, tipo) -> bool:
        o = self.ctx.opc
        if tipo not in o.tipos:
            return False
        tamano = msg.file.size or 0
        if (o.min_tamano and tamano < o.min_tamano) or (o.max_tamano and tamano > o.max_tamano):
            return False
        ext = extension(msg)
        if (o.extensiones and ext not in o.extensiones) or ext in o.excluir_extensiones:
            return False
        if o.buscar:
            texto = " ".join(filter(None, [msg.message, self.textos_album.get(msg.grouped_id), msg.file.name]))
            if o.buscar.lower() not in texto.lower():
                return False
        return True

    # ---- comentarios -------------------------------------------------------
    def _anotar_comentarios(self, msg):
        r = getattr(msg, "replies", None)
        if r and r.comments and r.replies:
            ultimo = self.ctx.bd.ultimo_hilo(self.canal_id, msg.id)
            if (r.max_id or 0) > ultimo:
                self.posts_comentarios.append((msg.id, ultimo))

    async def _descargar_comentarios(self):
        con_fallos = self.ctx.bd.posts_con_fallos(self.canal_id)
        pendientes = {p: u for p, u in self.posts_comentarios}
        pendientes.update({p: 0 for p in con_fallos})
        if not pendientes:
            return
        self.ctx.informe.log(f"💬 {self.titulo}: revisando comentarios de {len(pendientes)} publicaciones...")
        for post_id, ultimo in pendientes.items():
            if self.ctx.detener.is_set():
                break
            base = self.carpeta / "comentarios" / str(post_id)
            maximo = ultimo
            try:
                async for c in self.cliente.iter_messages(self.entidad, reply_to=post_id, reverse=True, min_id=ultimo):
                    if self.ctx.detener.is_set():
                        break
                    maximo = max(maximo, c.id)
                    grupo = utils.get_peer_id(c.peer_id)
                    if grupo not in self._hechos_otros:
                        self._hechos_otros[grupo] = self.ctx.bd.hechos(grupo)
                    if c.id in self._hechos_otros[grupo]:
                        continue
                    if c.grouped_id and c.message:
                        self.textos_album[c.grouped_id] = c.message
                    await self.procesar(c, carpeta_base=base, post_id=post_id)
            except (errors.MsgIdInvalidError, errors.ChannelPrivateError) as e:
                self.ctx.informe.log(f"Comentarios de la publicación {post_id} no accesibles: {e}", "aviso")
            self.hilos_vistos[post_id] = maximo

    # ---- descarga de archivos ---------------------------------------------
    async def _trabajador(self, i: int):
        slot = f"{self.clave}:{i}"
        while True:
            item = await self.cola.get()
            try:
                if not self.ctx.detener.is_set():
                    await self._descargar_item(slot, *item)
            except SinEspacio as e:
                self.ctx.informe.log(str(e), "error")
                self.ctx.detener.set()
            except Detenido:
                pass  # no cuenta como fallo: se descargará la próxima vez
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - un fallo no debe parar el canal
                self.stats["fallos"] += 1
                self.ctx.informe.log(f"Mensaje {item[0].id}: {type(e).__name__}: {e}", "error")
                msg, tipo, _base, post_id, tema = item
                try:  # queda como fallo para reintentarlo (también si es un comentario)
                    self._registrar(msg, "fallo", tipo=tipo, tamano=msg.file.size, tema=tema, post_id=post_id)
                except Exception:  # noqa: BLE001
                    pass
            finally:
                self.ctx.informe.archivo_fin(slot)
                self.ctx.informe.avance(self.clave)
                self.cola.task_done()
                if self.cola.empty():
                    self.ctx.bd.confirmar()

    def _nombre(self, msg) -> str:
        f = msg.file
        ext = f.ext or ""
        if self.ctx.opc.nombres == "texto":
            texto = msg.message or self.textos_album.get(msg.grouped_id)
            if texto:
                return limpiar(f"{msg.id}_{texto[:60]}{ext}")
        if f.name:
            nombre = f.name if (not ext or "." in f.name) else f.name + ext
        else:
            nombre = msg.date.strftime("%Y-%m-%d_%H-%M-%S") + ext
        return limpiar(f"{msg.id}_{nombre}")

    def _ruta_destino(self, msg, tipo, base, tema) -> Path:
        base = base or self.carpeta
        if tema:
            base = base / "temas" / limpiar(tema, 60)
        if self.ctx.opc.albumes and msg.grouped_id:
            carpeta = base / "albumes" / f"{msg.date:%Y-%m-%d}_{msg.grouped_id}"
        else:
            carpeta = base / tipo
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = self._nombre(msg)
        if os.name == "nt":  # Windows limita la ruta completa a 260 caracteres (MAX_PATH)
            libre = 250 - len(str(carpeta.resolve())) - 1 - len(".part")
            if len(nombre) > libre:
                nombre = limpiar(nombre, max(libre, len(str(msg.id)) + 12))
        return carpeta / nombre

    @staticmethod
    def _enlazar(origen: Path, destino: Path) -> Path:
        """Enlace duro (no ocupa espacio extra). Si no se puede, se referencia el original."""
        try:
            if destino.exists():
                # Solo se reutiliza si ya es el mismo archivo; si es otro, se apunta al original.
                return destino if os.path.samefile(origen, destino) else origen
            os.link(origen, destino)
            return destino
        except OSError:
            return origen

    async def _descargar_item(self, slot, msg, tipo, base, post_id, tema):
        o = self.ctx.opc
        destino = self._ruta_destino(msg, tipo, base, tema)
        tamano = msg.file.size or 0
        clave = clave_archivo(msg)
        campos = {"tipo": tipo, "tamano": tamano, "tema": tema, "post_id": post_id}

        if destino.exists() and tamano and destino.stat().st_size == tamano:
            self._registrar(msg, "ok", ruta=str(destino), **campos)
            self.ctx.bd.guardar_archivo(clave, destino, tamano)
            self.stats["ok"] += 1
            return

        en_curso = self.ctx.en_curso
        if o.deduplicar and clave:
            while clave in en_curso:  # el mismo archivo se está bajando ahora por otro mensaje: se espera
                await en_curso[clave].wait()
            previo = self.ctx.bd.buscar_archivo(clave)
            if previo:
                ruta_prev = Path(previo["ruta"])
                if ruta_prev.exists() and ruta_prev.stat().st_size == (previo["tamano"] or tamano):
                    ruta = self._enlazar(ruta_prev, destino)
                    self._registrar(msg, "duplicado", ruta=str(ruta), **campos)
                    self.stats["duplicados"] += 1
                    return

        libre = shutil.disk_usage(destino.parent).free
        reservado = self.ctx.reservado
        if libre - reservado[0] - tamano < o.espacio_minimo:
            raise SinEspacio(f"Espacio insuficiente en disco ({tamano_legible(libre)} libres). Descarga detenida.")

        reservado[0] += tamano  # cuenta lo que ocuparán las descargas que ya están en marcha
        listo = en_curso[clave] = asyncio.Event() if clave else None
        try:
            correcto = await self._descargar(slot, msg, destino)
        finally:
            reservado[0] -= tamano
            if listo is not None:
                en_curso.pop(clave, None)
                listo.set()
        if correcto:
            self._registrar(msg, "ok", ruta=str(destino), **campos)
            self.ctx.bd.guardar_archivo(clave, destino, tamano)
            self.stats["ok"] += 1
            self.stats["bytes"] += tamano
        else:
            self._registrar(msg, "fallo", **campos)
            self.stats["fallos"] += 1
            self.ctx.informe.log(f"No se pudo descargar el mensaje {msg.id} (se reintentará la próxima vez)", "error")

    async def _descargar(self, slot, msg, destino: Path, intentos: int = 6) -> bool:
        tmp = destino.with_name(destino.name + ".part")
        marca = destino.with_name(destino.name + ".part.ok")  # trozos ya completos (para reanudar)
        informe = self.ctx.informe
        tamano = msg.file.size or 0
        troceado = getattr(msg, "document", None) is not None and tamano >= MIN_TROCEADO
        for intento in range(1, intentos + 1):
            try:
                informe.archivo_fin(slot)
                if troceado:
                    await self._descargar_troceado(slot, msg, tmp, marca, tamano)
                    os.replace(tmp, destino)
                    self._borrar(marca)
                    return True
                tmp.unlink(missing_ok=True)
                informe.archivo_inicio(slot, destino.name, tamano)
                ultimo = [0]

                async def progreso(recibido, _total):
                    if self.ctx.detener.is_set():
                        raise Detenido()
                    delta, ultimo[0] = recibido - ultimo[0], recibido
                    informe.archivo_progreso(slot, recibido)
                    await self.ctx.limitador.consumir(delta)

                if await self.cliente.download_media(msg, file=str(tmp), progress_callback=progreso) is None:
                    self._borrar(tmp)
                    return False
                os.replace(tmp, destino)
                return True
            except (Detenido, asyncio.CancelledError):
                if not troceado:  # lo troceado se conserva para seguir la próxima vez
                    self._borrar(tmp)
                raise
            except errors.FloodWaitError as e:
                informe.log(f"⏳ Telegram pide esperar {e.seconds}s (FloodWait)...", "aviso")
                await asyncio.sleep(e.seconds + 2)
            except (errors.FileReferenceExpiredError, errors.FileReferenceInvalidError):
                # La referencia del archivo caduca con el tiempo: se vuelve a pedir el mensaje.
                nuevo = await self.cliente.get_messages(await msg.get_input_chat(), ids=msg.id)
                if not nuevo or not nuevo.media:
                    return False
                msg = nuevo
            except (ConnectionError, asyncio.TimeoutError, OSError, errors.RPCError) as e:
                espera = min(60, 5 * intento)
                informe.log(f"Mensaje {msg.id}: {type(e).__name__}: {e} -> reintento {intento}/{intentos} en {espera}s",
                            "aviso")
                await asyncio.sleep(espera)
        if not troceado:
            self._borrar(tmp)
        return False

    @staticmethod
    def _trozos_hechos(tmp: Path, marca: Path) -> int:
        """Cuántos trozos del principio de un .part ya están bien descargados."""
        try:
            hechos = int(marca.read_text(encoding="utf-8").strip())
            return max(0, min(hechos, tmp.stat().st_size // TROZO))
        except (OSError, ValueError):
            return 0

    async def _descargar_troceado(self, slot, msg, tmp: Path, marca: Path, tamano: int):
        """Descarga un documento por trozos de 512 KB, varios a la vez, y reanudable.

        Los trozos se escriben en su posición dentro del .part; en `marca` se guarda cuántos
        trozos seguidos desde el principio están completos, así que si se corta (Detener, sin
        conexión, cierre del programa) la siguiente vez se sigue desde ahí.
        """
        informe, ctx = self.ctx.informe, self.ctx
        total = -(-tamano // TROZO)
        hechos = self._trozos_hechos(tmp, marca) if tmp.exists() else 0
        if hechos == 0:
            self._borrar(tmp)
        elif hechos < total:
            informe.log(f"↻ {tmp.name[:-5]}: se reanuda al {hechos * 100 // total}%")
        recibido = [min(tamano, hechos * TROZO)]
        informe.archivo_inicio(slot, tmp.name[:-5], tamano, recibido[0])
        pendientes = iter(range(hechos, total))
        completos, prefijo = set(), [hechos]
        documento = msg.document

        with open(tmp, "r+b" if tmp.exists() else "w+b") as f:
            def guardar_marca():
                f.flush()  # primero los datos y luego la marca: la marca nunca va por delante
                marca.write_text(str(prefijo[0]), encoding="utf-8")

            async def obrero():
                for i in pendientes:  # el iterador es compartido: cada trozo lo pide un solo obrero
                    if ctx.detener.is_set():
                        raise Detenido()
                    partes = [c async for c in self.cliente.iter_download(
                        documento, offset=i * TROZO, limit=1, request_size=TROZO, file_size=tamano)]
                    datos = b"".join(partes)
                    esperado = min(TROZO, tamano - i * TROZO)
                    if len(datos) != esperado:
                        raise ConnectionError(f"trozo {i} incompleto ({len(datos)} de {esperado} bytes)")
                    f.seek(i * TROZO)
                    f.write(datos)
                    completos.add(i)
                    avanzado = False
                    while prefijo[0] in completos:
                        completos.discard(prefijo[0])
                        prefijo[0] += 1
                        avanzado = True
                    if avanzado and prefijo[0] % 8 == 0:
                        guardar_marca()
                    recibido[0] += len(datos)
                    informe.archivo_progreso(slot, recibido[0])
                    await ctx.limitador.consumir(len(datos))

            tareas = [asyncio.create_task(obrero()) for _ in range(min(ctx.opc.conexiones, max(1, total - hechos)))]
            try:
                await asyncio.gather(*tareas)
            except BaseException:
                for t in tareas:
                    t.cancel()
                await asyncio.gather(*tareas, return_exceptions=True)
                raise
            finally:
                guardar_marca()
            f.truncate(tamano)
        if tmp.stat().st_size != tamano:
            raise OSError(f"tamaño final incorrecto ({tmp.stat().st_size} de {tamano} bytes)")

    @staticmethod
    def _borrar(ruta: Path):
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass

    # ---- vigilancia ---------------------------------------------------------
    def activar_seguimiento(self):
        async def manejador(event):
            msg = event.message
            if not self._mio(msg.id) or msg.id in self.hechos:
                return
            if msg.grouped_id and msg.message:
                self.textos_album[msg.grouped_id] = msg.message
            self.ctx.informe.ampliar(self.clave)
            self.ctx.informe.log(f"🆕 {self.titulo}: mensaje nuevo {msg.id}")
            await self.procesar(msg)

        self.manejador = manejador
        self.real.add_event_handler(manejador, events.NewMessage(chats=[self.entidad]))

    async def cerrar(self):
        if self.manejador:
            self.real.remove_event_handler(self.manejador)
            self.manejador = None
        for t in self.trabajadores:
            t.cancel()
        await asyncio.gather(*self.trabajadores, return_exceptions=True)
        self.trabajadores = []


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
async def _al_terminar_canal(ctx: Contexto, grupo: list):
    """Tras el historial de un canal (todas sus particiones): HTML + notificación."""
    principal = grupo[0]
    stats = {k: sum(d.stats[k] for d in grupo) for k in principal.stats}
    if ctx.opc.html:
        try:
            ruta = await generar_html_async(ctx.bd, principal.canal_id)
            ctx.informe.log(f"🌐 Archivo navegable: {ruta}")
        except Exception as e:  # noqa: BLE001
            ctx.informe.log(f"No se pudo generar el HTML: {e}", "aviso")
    if ctx.opc.notificar and not ctx.detener.is_set():
        try:
            await principal.real.send_message(
                "me", f"✅ Descarga terminada: «{principal.titulo}»\n{resumen_stats(stats)}\n📂 {principal.carpeta}")
        except Exception as e:  # noqa: BLE001
            ctx.informe.log(f"No se pudo enviar la notificación: {e}", "aviso")


async def _correr_grupo(ctx: Contexto, grupo: list):
    canal_id = grupo[0].canal_id
    if canal_id in _CANALES_ACTIVOS:
        ctx.informe.log(f"«{grupo[0].titulo}» ya se está descargando (en este u otro trabajo): se omite.", "aviso")
        return
    _CANALES_ACTIVOS.add(canal_id)  # se libera al terminar ejecutar() (también tras la vigilancia)
    ctx.canales.add(canal_id)
    ctx.descargas.extend(grupo)
    try:
        for d in grupo:
            await d.preparar()
        await asyncio.gather(*(d.historial() for d in grupo))
        await _al_terminar_canal(ctx, grupo)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - un canal roto no debe parar los demás
        ctx.informe.log(f"{grupo[0].titulo}: {type(e).__name__}: {e}", "error")


async def _por_canal(ctx: Contexto, clientes: dict, objetivos: list):
    """Cada canal lo descarga una cuenta; las cuentas trabajan en paralelo."""
    nombres = list(clientes)
    asignacion = {n: [] for n in nombres}
    for i, obj in enumerate(objetivos):
        orden = nombres[i % len(nombres):] + nombres[: i % len(nombres)]
        for n in orden:
            try:
                asignacion[n].append(await resolver(clientes[n], obj))
                break
            except Exception as e:  # noqa: BLE001
                ctx.informe.log(f"[{n}] no puede abrir {obj}: {e}", "aviso")
        else:
            ctx.informe.log(f"Ninguna cuenta tiene acceso a {obj}", "error")

    async def correr_cuenta(nombre, entidades):
        for ent in entidades:
            if ctx.detener.is_set():
                break
            await _correr_grupo(ctx, [DescargaCanal(ctx, clientes[nombre], nombre, ent)])

    await asyncio.gather(*(correr_cuenta(n, e) for n, e in asignacion.items() if e))


async def _por_mensajes(ctx: Contexto, clientes: dict, objetivos: list):
    """Todas las cuentas colaboran en cada canal repartiéndose los mensajes."""
    for obj in objetivos:
        if ctx.detener.is_set():
            break
        entidades = {}
        for n, cliente in clientes.items():
            try:
                entidades[n] = await resolver(cliente, obj)
            except Exception as e:  # noqa: BLE001
                ctx.informe.log(f"[{n}] no puede abrir {obj}: {e} (no participará)", "aviso")
        if not entidades:
            ctx.informe.log(f"Ninguna cuenta tiene acceso a {obj}", "error")
            continue
        total = len(entidades)
        grupo = [DescargaCanal(ctx, clientes[n], n, ent, (k, total)) for k, (n, ent) in enumerate(entidades.items())]
        await _correr_grupo(ctx, grupo)


async def _vigilar(ctx: Contexto):
    for d in ctx.descargas:
        d.activar_seguimiento()
    ctx.informe.fase("vigilando")
    while not ctx.detener.is_set():
        try:
            await asyncio.wait_for(ctx.detener.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass
        if ctx.opc.html:
            pendientes = {d.canal_id for d in ctx.descargas if d.cambios}
            for d in ctx.descargas:
                d.cambios = False
            ctx.bd.confirmar()
            for canal_id in pendientes:
                try:
                    await generar_html_async(ctx.bd, canal_id)
                except Exception as e:  # noqa: BLE001
                    ctx.informe.log(f"No se pudo actualizar el HTML: {e}", "aviso")


async def _entrar_takeout(pila: contextlib.AsyncExitStack, nombre: str, cliente, informe: Informe):
    """Abre una sesión Takeout (exportación de datos) para la cuenta; si no se puede, sigue sin ella."""
    pedir = dict(finalize=True, channels=True, megagroups=True, chats=True, files=True, max_file_size=4 * 1024 ** 3)
    for intento in range(2):
        try:
            envuelto = await pila.enter_async_context(cliente.takeout(**pedir))
            informe.log(f"[{nombre}] modo Takeout activo")
            return envuelto
        except errors.TakeoutInitDelayError as e:
            informe.log(f"[{nombre}] Telegram pide confirmar la exportación de datos: acéptala en el aviso que te ha "
                        f"llegado a la app (o espera {e.seconds // 3600} h) y vuelve a lanzar la descarga. "
                        "Mientras, se descarga en modo normal.", "aviso")
            return cliente
        except ValueError:
            if intento == 0:  # quedó una sesión Takeout abierta de una ejecución que se cortó
                try:
                    await cliente.end_takeout(success=False)
                except Exception:  # noqa: BLE001
                    cliente.session.takeout_id = None
                continue
            raise
        except errors.RPCError as e:
            informe.log(f"[{nombre}] no se pudo activar Takeout ({e}); se descarga en modo normal.", "aviso")
            return cliente
    return cliente


async def ejecutar(clientes: dict, objetivos: list, opc: Opciones, informe: Informe = None,
                   bd: BD = None, detener: asyncio.Event = None):
    """Punto de entrada del motor. `clientes` = {nombre_cuenta: TelegramClient conectado}."""
    if not clientes:
        raise ValueError("No hay ninguna cuenta conectada.")
    informe = informe or Informe()
    propia_bd = bd is None
    ctx = Contexto(bd or BD(RUTA_BD), opc.validar(), informe, Limitador(opc.limite_velocidad),
                   detener or asyncio.Event())
    for nombre in clientes:
        _LOG_TELETHON.destinos.setdefault(nombre, []).append(informe)
    informe.fase("descargando")
    ctx.reales = dict(clientes)
    pila = contextlib.AsyncExitStack()
    try:
        if opc.takeout:
            clientes = {n: await _entrar_takeout(pila, n, c, informe) for n, c in clientes.items()}
        if opc.reparto == "mensajes" and len(clientes) > 1:
            await _por_mensajes(ctx, clientes, objetivos)
        else:
            await _por_canal(ctx, clientes, objetivos)
        if opc.seguir and not ctx.detener.is_set() and ctx.descargas:
            await _vigilar(ctx)
    finally:
        for d in ctx.descargas:
            await d.cerrar()
        try:
            await pila.aclose()  # cierra las sesiones Takeout
        except Exception as e:  # noqa: BLE001
            informe.log(f"No se pudo cerrar el modo Takeout: {e}", "aviso")
        _CANALES_ACTIVOS.difference_update(ctx.canales)
        for nombre in clientes:
            lista = _LOG_TELETHON.destinos.get(nombre, [])
            if informe in lista:
                lista.remove(informe)
            if not lista:
                _LOG_TELETHON.destinos.pop(nombre, None)
        ctx.bd.confirmar()
        if propia_bd:
            ctx.bd.cerrar()
        informe.fase("terminado")
