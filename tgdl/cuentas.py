"""Gestión de varias cuentas de Telegram (una sesión por cuenta en ./sesiones).

Las sesiones pueden guardarse sin cifrar (<nombre>.session, el formato normal de Telethon) o
cifradas con una contraseña (<nombre>.session.enc) si CIFRAR_SESIONES=si en el .env.
"""
import getpass
import re

from telethon import TelegramClient, errors
from telethon.sessions import SQLiteSession, StringSession

from .cifrado import ContrasenaIncorrecta, cifrar, descifrar
from .config import BASE, SESIONES, cargar_config

_NOMBRE_VALIDO = re.compile(r"^[\w-]{1,32}$")


def validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not _NOMBRE_VALIDO.match(nombre):
        raise ValueError("Nombre de cuenta no válido: usa letras, números, '-' o '_' (máx. 32).")
    return nombre


def _activado(valor) -> bool:
    return str(valor or "").strip().lower() in ("1", "si", "sí", "true", "yes", "s")


def hay_sesiones_cifradas() -> bool:
    return SESIONES.is_dir() and any(SESIONES.glob("*.session.enc"))


def pedir_contrasena(interactivo: bool = True):
    """Pide la contraseña de las sesiones si están (o se quieren) cifradas. None = sin cifrar."""
    if not (_activado(cargar_config().get("CIFRAR_SESIONES")) or hay_sesiones_cifradas()):
        return None
    if not interactivo:
        raise RuntimeError("Las sesiones están cifradas: hace falta la contraseña.")
    existente = next(iter(SESIONES.glob("*.session.enc")), None) if SESIONES.is_dir() else None
    while True:
        contrasena = getpass.getpass("🔒 Contraseña de las sesiones: ")
        if not contrasena:
            continue
        if existente is None:  # primera vez: se pide dos veces
            if getpass.getpass("   Repítela: ") != contrasena:
                print("   No coinciden, prueba otra vez.")
                continue
            print("   Guárdala bien: sin ella habrá que volver a iniciar sesión en cada cuenta.")
            return contrasena
        try:
            descifrar(existente.read_bytes(), contrasena)
            return contrasena
        except ContrasenaIncorrecta:
            print("   Contraseña incorrecta.")


class GestorCuentas:
    def __init__(self, api_id: int, api_hash: str, contrasena: str = None):
        self.api_id, self.api_hash = api_id, api_hash
        self.contrasena = contrasena  # si hay contraseña, las sesiones se guardan cifradas
        self.clientes: dict = {}
        self.pendientes: dict = {}  # logins a medias desde el panel web
        self._info: dict = {}
        cfg = cargar_config()
        # Vacío = valores normales de Telethon (versión de la librería y sistema operativo real)
        self.dispositivo = {"modelo": cfg.get("NOMBRE_DISPOSITIVO") or "PC",
                            "sistema": cfg.get("SISTEMA_DISPOSITIVO") or None,
                            "version": cfg.get("VERSION_APP") or None}
        SESIONES.mkdir(exist_ok=True)
        self._migrar_sesion_antigua()
        if self.contrasena:
            self._cifrar_sesiones_planas()

    def _cifrar_sesiones_planas(self):
        """Convierte las sesiones sin cifrar en cifradas (y borra las originales)."""
        for plana in SESIONES.glob("*.session"):
            nombre = plana.stem
            sesion = SQLiteSession(str(SESIONES / nombre))
            try:
                texto = StringSession.save(sesion)
            finally:
                sesion.close()
            if texto:
                (SESIONES / f"{nombre}.session.enc").write_bytes(cifrar(texto, self.contrasena))
            for ext in (".session", ".session-journal"):
                (SESIONES / f"{nombre}{ext}").unlink(missing_ok=True)

    def _guardar(self, nombre: str, cliente):
        """Con cifrado, la sesión vive en memoria: se guarda cifrada tras conectar o iniciar sesión."""
        if self.contrasena and cliente is not None:
            texto = cliente.session.save()
            if texto:
                (SESIONES / f"{nombre}.session.enc").write_bytes(cifrar(texto, self.contrasena))

    def _existe(self, nombre: str) -> bool:
        return any((SESIONES / f"{nombre}{ext}").exists() for ext in (".session", ".session.enc"))

    @staticmethod
    def _migrar_sesion_antigua():
        antigua = BASE / "sesion_descargas.session"
        nueva = SESIONES / "principal.session"
        if antigua.exists() and not nueva.exists():
            antigua.rename(nueva)

    def nombres(self) -> list:
        """Cuentas guardadas (sin contar los inicios de sesión a medias del panel)."""
        nombres = {p.name.split(".", 1)[0] for p in SESIONES.iterdir()
                   if p.name.endswith((".session", ".session.enc"))}
        return sorted(n for n in nombres if n not in self.pendientes)

    def _sesion(self, nombre: str):
        if not self.contrasena:
            return str(SESIONES / nombre)
        cifrada = SESIONES / f"{nombre}.session.enc"
        return StringSession(descifrar(cifrada.read_bytes(), self.contrasena) if cifrada.exists() else None)

    def _crear_cliente(self, nombre: str) -> TelegramClient:
        return TelegramClient(
            self._sesion(validar_nombre(nombre)), self.api_id, self.api_hash,
            flood_sleep_threshold=3600,      # espera sola FloodWaits de hasta 1 h (se avisa en el log)
            connection_retries=10, retry_delay=5, request_retries=10,
            # Lo que aparece en Telegram > Ajustes > Dispositivos (configurable en el .env)
            device_model=self.dispositivo["modelo"], system_version=self.dispositivo["sistema"],
            app_version=self.dispositivo["version"],
            base_logger=f"tgdl.cuenta.{nombre}",  # permite saber de qué cuenta es cada aviso
        )

    def _borrar_archivos(self, nombre: str):
        for ext in (".session", ".session-journal", ".session.enc"):
            ruta = SESIONES / f"{nombre}{ext}"
            if ruta.exists():
                ruta.unlink()

    async def conectar(self, nombre: str):
        """Devuelve el cliente conectado y autorizado, o None si la sesión no es válida."""
        if nombre in self.pendientes:  # su sesión la tiene abierta el login en curso
            return None
        cliente = self.clientes.get(nombre)
        if cliente is None:
            if not self._existe(validar_nombre(nombre)):
                return None
            cliente = self._crear_cliente(nombre)
        if not cliente.is_connected():
            await cliente.connect()
        if not await cliente.is_user_authorized():
            await cliente.disconnect()
            self.clientes.pop(nombre, None)
            return None
        self.clientes[nombre] = cliente
        self._guardar(nombre, cliente)
        return cliente

    async def info(self, nombre: str) -> dict:
        if nombre not in self._info:
            cliente = await self.conectar(nombre)
            if cliente is None:
                return {"nombre": nombre, "conectada": False}
            me = await cliente.get_me()
            self._info[nombre] = {
                "nombre": nombre, "conectada": True, "id": me.id,
                "usuario": me.username, "nombre_mostrado": " ".join(filter(None, [me.first_name, me.last_name])),
                "telefono": f"+{me.phone[:4]}•••{me.phone[-2:]}" if me.phone else None,
            }
        return self._info[nombre]

    # ---- login por consola -----------------------------------------------
    async def login_interactivo(self, nombre: str) -> TelegramClient:
        cliente = self._crear_cliente(nombre)
        await cliente.start()  # pide teléfono, código y contraseña 2FA por consola
        self.clientes[nombre] = cliente
        self._guardar(nombre, cliente)
        return cliente

    # ---- login por pasos (panel web) --------------------------------------
    async def enviar_codigo(self, nombre: str, telefono: str):
        nombre = validar_nombre(nombre)
        await self.cancelar_login(nombre)  # un intento anterior sin terminar
        if nombre in self.nombres() and await self.conectar(nombre):
            raise ValueError(f"La cuenta '{nombre}' ya existe y está conectada.")
        cliente = self.clientes.pop(nombre, None) or self._crear_cliente(nombre)
        try:
            if not cliente.is_connected():
                await cliente.connect()
            r = await cliente.send_code_request(telefono)
        except BaseException:
            await cliente.disconnect()
            raise
        self.pendientes[nombre] = (cliente, telefono, r.phone_code_hash)

    async def cancelar_login(self, nombre: str):
        """Abandona un inicio de sesión a medias y borra su sesión sin autorizar."""
        pendiente = self.pendientes.pop(validar_nombre(nombre), None)
        if pendiente is None:
            return
        cliente = pendiente[0]
        try:
            autorizado = cliente.is_connected() and await cliente.is_user_authorized()
        except Exception:  # noqa: BLE001
            autorizado = False
        await cliente.disconnect()
        if not autorizado:
            self._borrar_archivos(nombre)

    async def verificar(self, nombre: str, codigo: str = None, password: str = None) -> str:
        """Devuelve 'ok' o 'password' (si la cuenta tiene verificación en dos pasos)."""
        nombre = validar_nombre(nombre)
        if nombre not in self.pendientes:
            raise ValueError("Primero solicita el código.")
        cliente, telefono, hash_codigo = self.pendientes[nombre]
        try:
            if password:
                await cliente.sign_in(password=password)
            else:
                await cliente.sign_in(telefono, codigo, phone_code_hash=hash_codigo)
        except errors.SessionPasswordNeededError:
            return "password"
        del self.pendientes[nombre]
        self.clientes[nombre] = cliente
        self._guardar(nombre, cliente)
        return "ok"

    async def eliminar(self, nombre: str, cerrar_sesion: bool = True):
        nombre = validar_nombre(nombre)
        await self.cancelar_login(nombre)
        if not self._existe(nombre) and nombre not in self.clientes:
            raise ValueError(f"No existe la cuenta '{nombre}'.")
        cliente = self.clientes.pop(nombre, None) or self._crear_cliente(nombre)
        try:
            if not cliente.is_connected():
                await cliente.connect()
            if cerrar_sesion and await cliente.is_user_authorized():
                await cliente.log_out()
        finally:
            await cliente.disconnect()
        self._info.pop(nombre, None)
        self._borrar_archivos(nombre)

    async def cerrar(self):
        for nombre in list(self.pendientes):
            try:
                await self.cancelar_login(nombre)
            except Exception:  # noqa: BLE001
                pass
        for nombre, cliente in list(self.clientes.items()):
            try:
                self._guardar(nombre, cliente)
            except Exception:  # noqa: BLE001
                pass
            try:
                await cliente.disconnect()
            except Exception:  # noqa: BLE001
                pass
