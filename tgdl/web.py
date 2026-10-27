"""Panel web local (http://127.0.0.1:8765): cuentas, nuevas descargas, progreso en vivo y archivo."""
import asyncio
import json
import secrets
import sys
import time
import uuid
import webbrowser
from collections import deque
from pathlib import Path

from aiohttp import WSMsgType, web
from telethon import errors

from .bd import BD
from .config import RUTA_BD, SALIDA_POR_DEFECTO, cargar_config, entero, obtener_credenciales
from .cuentas import GestorCuentas
from .html_export import generar_html_async
from .informes import Informe
from .motor import Opciones, ejecutar, listar_dialogos
from .utilidades import tamano_legible

ESTATICO = Path(__file__).resolve().parent / "estatico"
ESPERA_DETENER = 30  # segundos para terminar ordenadamente antes de cancelar a la fuerza

# Archivos descargados que el navegador puede mostrar sin riesgo. Cualquier otro tipo (html, svg,
# xml...) podría ejecutar código, así que se entrega como descarga.
_EN_LINEA = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "mp4", "webm", "mov", "mkv", "m4v",
             "mp3", "ogg", "oga", "opus", "m4a", "wav", "flac", "pdf", "txt"}


# --------------------------------------------------------------------------- #
# Informe para el panel
# --------------------------------------------------------------------------- #
class InformeWeb(Informe):
    def __init__(self):
        self.canales, self.archivos = {}, {}
        self.logs = deque(maxlen=400)
        self.fase_actual = "preparando"
        self.bytes = 0

    def log(self, texto, nivel="info"):
        self.logs.append({"t": time.time(), "n": nivel, "x": texto})

    def fase(self, nombre):
        self.fase_actual = nombre

    def canal_inicio(self, clave, titulo, total, hechos, cuenta):
        self.canales[clave] = {"titulo": titulo, "cuenta": cuenta, "total": total, "hechos": hechos,
                               "terminado": False, "stats": None}

    def ampliar(self, clave, n=1):
        if clave in self.canales:
            self.canales[clave]["total"] += n

    def avance(self, clave, n=1):
        if clave in self.canales:
            self.canales[clave]["hechos"] += n

    def canal_fin(self, clave, stats):
        if clave in self.canales:
            self.canales[clave].update(terminado=True, stats=dict(stats))

    def archivo_inicio(self, slot, nombre, total):
        self.archivos[slot] = {"nombre": nombre, "total": total, "recibido": 0}

    def archivo_progreso(self, slot, recibido):
        a = self.archivos.get(slot)
        if a:
            self.bytes += max(0, recibido - a["recibido"])
            a["recibido"] = recibido

    def archivo_fin(self, slot):
        self.archivos.pop(slot, None)


class Trabajo:
    def __init__(self, cuentas, objetivos, etiquetas, opciones: dict):
        self.id = uuid.uuid4().hex[:8]
        self.cuentas, self.objetivos, self.etiquetas, self.opciones = cuentas, objetivos, etiquetas, opciones
        self.estado = "iniciando"
        self.error = None
        self.inicio, self.fin = time.time(), None
        self.informe = InformeWeb()
        self.detener = asyncio.Event()
        self.tarea = None
        self.velocidad = 0.0
        self._bytes_prev, self._t_prev = 0, time.monotonic()

    def medir(self):
        ahora = time.monotonic()
        dt = ahora - self._t_prev
        if dt >= 0.5:
            instantanea = (self.informe.bytes - self._bytes_prev) / dt
            self.velocidad = instantanea if self.velocidad == 0 else self.velocidad * 0.6 + instantanea * 0.4
            self._bytes_prev, self._t_prev = self.informe.bytes, ahora

    def foto(self) -> dict:
        inf = self.informe
        estado = self.estado
        if estado == "en curso" and inf.fase_actual == "vigilando":
            estado = "vigilando"
        return {
            "id": self.id, "estado": estado, "error": self.error, "cuentas": self.cuentas,
            "etiquetas": self.etiquetas, "inicio": self.inicio, "fin": self.fin,
            "velocidad": self.velocidad, "bytes": inf.bytes, "bytes_txt": tamano_legible(inf.bytes),
            "canales": list(inf.canales.values()), "archivos": list(inf.archivos.values()),
            "logs": list(inf.logs)[-120:], "seguir": bool(self.opciones.get("seguir")),
        }


class TrabajoGuardado:
    """Trabajo terminado en una sesión anterior del panel (solo se muestra)."""

    def __init__(self, datos: dict):
        self.datos = datos
        self.id, self.cuentas = datos["id"], datos.get("cuentas", [])
        self.estado = datos.get("estado", "terminado")
        self.tarea = None

    def medir(self):
        pass

    def foto(self) -> dict:
        return self.datos


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
class Panel:
    def __init__(self, api_id, api_hash):
        self.cuentas = GestorCuentas(api_id, api_hash)
        self.bd = BD(RUTA_BD)
        self.trabajos: dict = {}
        self.sockets: set = set()
        self.token = secrets.token_urlsafe(24)  # se pide en /api y /ws: otras webs no lo conocen
        self.puerto = None
        self._ultimo_envio = None
        for fila in reversed(self.bd.trabajos_guardados()):
            try:
                t = TrabajoGuardado(json.loads(fila["datos"]))
            except (ValueError, KeyError):
                continue
            self.trabajos[t.id] = t

    def origenes(self) -> set:
        return {f"127.0.0.1:{self.puerto}", f"localhost:{self.puerto}"}

    async def indice(self, request):
        html = (ESTATICO / "index.html").read_text(encoding="utf-8")
        html = html.replace("</head>", f'<meta name="tgdl-token" content="{self.token}">\n</head>', 1)
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})

    # ---- cuentas -----------------------------------------------------------
    async def api_cuentas(self, request):
        res = []
        for n in self.cuentas.nombres():
            try:
                res.append(await asyncio.wait_for(self.cuentas.info(n), 30))
            except Exception as e:  # noqa: BLE001
                res.append({"nombre": n, "conectada": False, "error": str(e)})
        return web.json_response(res)

    async def api_codigo(self, request):
        d = await request.json()
        await self.cuentas.enviar_codigo(d.get("nombre", ""), d.get("telefono", "").replace(" ", ""))
        return web.json_response({"ok": True})

    async def api_verificar(self, request):
        d = await request.json()
        nombre = str(d.get("nombre") or "").strip()
        r = await self.cuentas.verificar(nombre, d.get("codigo") or None, d.get("password") or None)
        info = await self.cuentas.info(nombre) if r == "ok" else None
        return web.json_response({"resultado": r, "cuenta": info})

    async def api_cancelar_login(self, request):
        d = await request.json()
        await self.cuentas.cancelar_login(str(d.get("nombre") or "").strip())
        return web.json_response({"ok": True})

    async def api_eliminar_cuenta(self, request):
        nombre = request.match_info["nombre"]
        if any(nombre in t.cuentas and t.estado in ("iniciando", "en curso") for t in self.trabajos.values()):
            raise ValueError("Esa cuenta se está usando en una descarga activa.")
        await self.cuentas.eliminar(nombre)
        return web.json_response({"ok": True})

    async def api_canales(self, request):
        cliente = await self.cuentas.conectar(request.match_info["nombre"])
        if cliente is None:
            raise ValueError("La cuenta no está conectada.")
        descargados = {c["canal_id"] for c in self.bd.canales()}
        dialogos = await listar_dialogos(cliente)
        return web.json_response([
            {"id": d.id, "nombre": d.name, "tipo": "grupo" if d.is_group else "canal",
             "sin_leer": d.unread_count, "descargado": d.id in descargados,
             "usuario": getattr(d.entity, "username", None)}
            for d in dialogos])

    # ---- trabajos ------------------------------------------------------------
    async def api_trabajos(self, request):
        return web.json_response([t.foto() for t in self.trabajos.values()])

    async def api_nuevo_trabajo(self, request):
        d = await request.json()
        cuentas = [c for c in d.get("cuentas", []) if c in self.cuentas.nombres()]
        if not cuentas:
            raise ValueError("Elige al menos una cuenta.")
        canales = d.get("canales") or []
        if not canales:
            raise ValueError("Elige al menos un canal.")
        objetivos = [c["id"] if isinstance(c, dict) else c for c in canales]
        etiquetas = [c.get("nombre", str(c["id"])) if isinstance(c, dict) else str(c) for c in canales]
        opciones = d.get("opciones") or {}
        Opciones.desde_dict(opciones)  # valida antes de arrancar
        trabajo = Trabajo(cuentas, objetivos, etiquetas, opciones)
        self.trabajos[trabajo.id] = trabajo
        trabajo.tarea = asyncio.create_task(self._correr(trabajo))
        return web.json_response({"id": trabajo.id})

    async def _correr(self, t: Trabajo):
        try:
            clientes = {}
            for n in t.cuentas:
                c = await self.cuentas.conectar(n)
                if c is None:
                    t.informe.log(f"La cuenta '{n}' no tiene sesión válida", "error")
                else:
                    clientes[n] = c
            t.estado = "en curso"
            await ejecutar(clientes, t.objetivos, Opciones.desde_dict(t.opciones), t.informe, self.bd, t.detener)
            t.estado = "detenido" if t.detener.is_set() else "terminado"
        except asyncio.CancelledError:
            t.estado = "detenido"
        except Exception as e:  # noqa: BLE001
            t.estado, t.error = "error", f"{type(e).__name__}: {e}"
            t.informe.log(t.error, "error")
        finally:
            t.fin = time.time()
            try:
                self.bd.guardar_trabajo(t.id, json.dumps(t.foto()), t.fin)
            except Exception:  # noqa: BLE001
                pass

    async def api_detener(self, request):
        t = self.trabajos.get(request.match_info["id"])
        if t and t.tarea and not t.tarea.done() and not t.detener.is_set():
            # Primero se pide parar con calma (se borran los archivos a medias, se guarda el progreso
            # y se genera el HTML); si no termina a tiempo, se cancela.
            t.detener.set()
            t.informe.log("Deteniendo...", "aviso")
            asyncio.get_running_loop().call_later(
                ESPERA_DETENER, lambda: None if t.tarea.done() else t.tarea.cancel())
        return web.json_response({"ok": True})

    async def api_quitar(self, request):
        t = self.trabajos.get(request.match_info["id"])
        if t and t.tarea and not t.tarea.done():
            raise ValueError("Detén la descarga antes de quitarla.")
        self.trabajos.pop(request.match_info["id"], None)
        self.bd.borrar_trabajo(request.match_info["id"])
        return web.json_response({"ok": True})

    # ---- archivo -----------------------------------------------------------
    async def api_archivo(self, request):
        res = []
        for c in self.bd.canales():
            r = self.bd.resumen(c["canal_id"])
            carpeta = Path(c["carpeta"])
            res.append({"id": c["canal_id"], "titulo": c["titulo"], "carpeta": str(carpeta),
                        "archivos": r["archivos"], "mensajes": r["total"], "fallos": r["fallos"],
                        "tamano": tamano_legible(r["bytes"]), "actualizado": c["actualizado"],
                        "html": (carpeta / "index.html").exists()})
        return web.json_response(res)

    async def api_regenerar(self, request):
        ruta = await generar_html_async(self.bd, int(request.match_info["canal_id"]))
        return web.json_response({"ok": True, "ruta": str(ruta)})

    async def ver(self, request):
        canal = self.bd.canal(int(request.match_info["canal_id"]))
        if canal is None:
            raise web.HTTPNotFound()
        base = Path(canal["carpeta"]).resolve()
        ruta = (base / request.match_info["ruta"]).resolve()
        permitidas = [Path(c["carpeta"]).resolve() for c in self.bd.canales()]
        if not ruta.is_file() or not any(ruta.is_relative_to(p) for p in permitidas):
            raise web.HTTPNotFound()
        # Todo lo de /ver/ viene de canales de terceros: se aísla del panel con "sandbox" para que
        # ningún archivo pueda usar la API aunque contenga código.
        cabeceras = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
        ext = ruta.suffix.lower().lstrip(".")
        if ruta == base / "index.html":
            cabeceras["Content-Security-Policy"] = "sandbox allow-scripts allow-popups allow-downloads"
        elif ext in _EN_LINEA:
            if ext != "pdf":  # el visor de PDF del navegador no funciona dentro de un sandbox
                cabeceras["Content-Security-Policy"] = "sandbox"
        else:
            cabeceras["Content-Security-Policy"] = "sandbox"
            cabeceras["Content-Disposition"] = "attachment"
        return web.FileResponse(ruta, headers=cabeceras)

    async def api_config(self, request):
        cfg = cargar_config()
        return web.json_response({"salida": cfg.get("CARPETA_DESTINO") or str(SALIDA_POR_DEFECTO),
                                  "hilos": entero(cfg, "HILOS", 3)})

    # ---- tiempo real -------------------------------------------------------
    async def ws(self, request):
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(request)
        self.sockets.add(sock)
        try:
            await sock.send_str(json.dumps({"trabajos": [t.foto() for t in self.trabajos.values()]}))
            async for msg in sock:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.sockets.discard(sock)
        return sock

    async def _enviar(self, sock, datos):
        try:
            await asyncio.wait_for(sock.send_str(datos), 5)
        except Exception:  # noqa: BLE001 - un navegador lento o cerrado no debe frenar a los demás
            self.sockets.discard(sock)

    async def difundir(self):
        while True:
            await asyncio.sleep(0.8)
            self.bd.confirmar()
            for t in self.trabajos.values():
                t.medir()
            if not self.sockets:
                self._ultimo_envio = None
                continue
            datos = json.dumps({"trabajos": [t.foto() for t in self.trabajos.values()]})
            if datos == self._ultimo_envio:  # nada ha cambiado
                continue
            self._ultimo_envio = datos
            await asyncio.gather(*(self._enviar(s, datos) for s in list(self.sockets)))

    async def cerrar(self):
        for t in self.trabajos.values():
            if t.tarea and not t.tarea.done():
                t.detener.set()
                t.tarea.cancel()
        await asyncio.gather(*(t.tarea for t in self.trabajos.values() if t.tarea), return_exceptions=True)
        await self.cuentas.cerrar()
        self.bd.cerrar()


def seguridad(panel: Panel):
    """Bloquea las peticiones que no vienen del propio panel.

    - Host: solo 127.0.0.1/localhost con nuestro puerto (evita el "DNS rebinding").
    - /api y /ws: exigen el token del panel y, si el navegador manda Origin, que sea el nuestro.
      Así otra web abierta en el navegador no puede lanzar descargas ni leer nada.
    """

    @web.middleware
    async def middleware(request, handler):
        if request.host not in panel.origenes():
            raise web.HTTPForbidden(text="Host no permitido")
        if request.path.startswith(("/api/", "/ws")):
            origen = request.headers.get("Origin")
            if origen is not None and origen not in {f"http://{h}" for h in panel.origenes()}:
                raise web.HTTPForbidden(text="Origen no permitido")
            token = request.headers.get("X-Token") or request.query.get("token", "")
            if not secrets.compare_digest(token, panel.token):
                raise web.HTTPForbidden(text="Token no válido: recarga la página del panel")
        return await handler(request)

    return middleware


@web.middleware
async def errores_json(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except errors.FloodWaitError as e:
        return web.json_response({"error": f"Telegram pide esperar {e.seconds}s antes de reintentar."}, status=429)
    except (ValueError, errors.RPCError) as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=500)


def crear_app(panel: Panel) -> web.Application:
    app = web.Application(middlewares=[seguridad(panel), errores_json])
    r = app.router
    r.add_get("/", panel.indice)
    r.add_static("/estatico/", ESTATICO)
    r.add_get("/ws", panel.ws)
    r.add_get("/api/config", panel.api_config)
    r.add_get("/api/cuentas", panel.api_cuentas)
    r.add_post("/api/cuentas/codigo", panel.api_codigo)
    r.add_post("/api/cuentas/verificar", panel.api_verificar)
    r.add_post("/api/cuentas/cancelar", panel.api_cancelar_login)
    r.add_delete("/api/cuentas/{nombre}", panel.api_eliminar_cuenta)
    r.add_get("/api/cuentas/{nombre}/canales", panel.api_canales)
    r.add_get("/api/trabajos", panel.api_trabajos)
    r.add_post("/api/trabajos", panel.api_nuevo_trabajo)
    r.add_post("/api/trabajos/{id}/detener", panel.api_detener)
    r.add_delete("/api/trabajos/{id}", panel.api_quitar)
    r.add_get("/api/archivo", panel.api_archivo)
    r.add_post("/api/archivo/{canal_id}/html", panel.api_regenerar)
    r.add_get("/ver/{canal_id}/{ruta:.*}", panel.ver)
    return app


async def _servir(api_id, api_hash, puerto):
    panel = Panel(api_id, api_hash)
    runner = web.AppRunner(crear_app(panel))
    await runner.setup()
    for p in range(puerto, puerto + 20):
        try:
            await web.TCPSite(runner, "127.0.0.1", p).start()
            puerto = panel.puerto = p
            break
        except OSError:
            continue
    else:
        raise SystemExit("No hay ningún puerto libre para el panel.")
    url = f"http://127.0.0.1:{puerto}"
    print(f"\n✨ Panel de TG Downloader en {url}\n   (deja esta ventana abierta; Ctrl+C para cerrar)\n")
    webbrowser.open(url)
    difusor = asyncio.create_task(panel.difundir())
    try:
        await asyncio.Event().wait()
    finally:
        difusor.cancel()
        await panel.cerrar()
        await runner.cleanup()


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    api_id, api_hash = obtener_credenciales()
    puerto = entero(cargar_config(), "PUERTO_PANEL", 8765)
    try:
        asyncio.run(_servir(api_id, api_hash, puerto))
    except KeyboardInterrupt:
        print("\nPanel cerrado.")
