"""Gestión de varias cuentas de Telegram (una sesión por cuenta en ./sesiones)."""
import re

from telethon import TelegramClient, errors

from .config import BASE, SESIONES

_NOMBRE_VALIDO = re.compile(r"^[\w-]{1,32}$")


def validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not _NOMBRE_VALIDO.match(nombre):
        raise ValueError("Nombre de cuenta no válido: usa letras, números, '-' o '_' (máx. 32).")
    return nombre


class GestorCuentas:
    def __init__(self, api_id: int, api_hash: str):
        self.api_id, self.api_hash = api_id, api_hash
        self.clientes: dict = {}
        self.pendientes: dict = {}  # logins a medias desde el panel web
        self._info: dict = {}
        SESIONES.mkdir(exist_ok=True)
        self._migrar_sesion_antigua()

    @staticmethod
    def _migrar_sesion_antigua():
        antigua = BASE / "sesion_descargas.session"
        nueva = SESIONES / "principal.session"
        if antigua.exists() and not nueva.exists():
            antigua.rename(nueva)

    def nombres(self) -> list:
        return sorted(p.stem for p in SESIONES.glob("*.session"))

    def _crear_cliente(self, nombre: str) -> TelegramClient:
        return TelegramClient(
            str(SESIONES / validar_nombre(nombre)), self.api_id, self.api_hash,
            flood_sleep_threshold=3600,      # espera sola FloodWaits de hasta 1 h (se avisa en el log)
            connection_retries=10, retry_delay=5, request_retries=10,
            device_model="TG Downloader", app_version="2.0",
        )

    async def conectar(self, nombre: str):
        """Devuelve el cliente conectado y autorizado, o None si la sesión no es válida."""
        cliente = self.clientes.get(nombre)
        if cliente is None:
            if not (SESIONES / f"{validar_nombre(nombre)}.session").exists():
                return None
            cliente = self._crear_cliente(nombre)
        if not cliente.is_connected():
            await cliente.connect()
        if not await cliente.is_user_authorized():
            await cliente.disconnect()
            self.clientes.pop(nombre, None)
            return None
        self.clientes[nombre] = cliente
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
        return cliente

    # ---- login por pasos (panel web) --------------------------------------
    async def enviar_codigo(self, nombre: str, telefono: str):
        nombre = validar_nombre(nombre)
        if nombre in self.nombres() and await self.conectar(nombre):
            raise ValueError(f"La cuenta '{nombre}' ya existe y está conectada.")
        cliente = self._crear_cliente(nombre)
        await cliente.connect()
        r = await cliente.send_code_request(telefono)
        self.pendientes[nombre] = (cliente, telefono, r.phone_code_hash)

    async def verificar(self, nombre: str, codigo: str = None, password: str = None) -> str:
        """Devuelve 'ok' o 'password' (si la cuenta tiene verificación en dos pasos)."""
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
        return "ok"

    async def eliminar(self, nombre: str, cerrar_sesion: bool = True):
        nombre = validar_nombre(nombre)
        cliente = self.clientes.pop(nombre, None) or self._crear_cliente(nombre)
        try:
            if not cliente.is_connected():
                await cliente.connect()
            if cerrar_sesion and await cliente.is_user_authorized():
                await cliente.log_out()
        finally:
            await cliente.disconnect()
        self._info.pop(nombre, None)
        for ext in (".session", ".session-journal"):
            ruta = SESIONES / f"{nombre}{ext}"
            if ruta.exists():
                ruta.unlink()

    async def cerrar(self):
        for cliente in list(self.clientes.values()) + [p[0] for p in self.pendientes.values()]:
            try:
                await cliente.disconnect()
            except Exception:  # noqa: BLE001
                pass
