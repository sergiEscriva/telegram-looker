"""Rutas del proyecto, lectura/escritura del .env y asistente de credenciales."""
import os
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RUTA_ENV = BASE / ".env"
SESIONES = BASE / "sesiones"
RUTA_BD = BASE / "datos.db"
SALIDA_POR_DEFECTO = BASE / "descargas"

_CLAVES_ENTORNO = ("API_ID", "API_HASH", "CANAL", "CARPETA_DESTINO", "HILOS", "CUENTAS", "REPARTO", "PUERTO_PANEL")


def cargar_config() -> dict:
    """Lee el .env (CLAVE=valor). Las variables de entorno tienen prioridad."""
    cfg = {}
    if RUTA_ENV.exists():
        for linea in RUTA_ENV.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            cfg[clave.strip()] = valor.strip().strip('"').strip("'")
    for clave in _CLAVES_ENTORNO:
        if os.environ.get(clave):
            cfg[clave] = os.environ[clave]
    return cfg


def guardar_en_env(valores: dict):
    """Actualiza (o añade) claves en el .env conservando el resto del archivo."""
    lineas = RUTA_ENV.read_text(encoding="utf-8").splitlines() if RUTA_ENV.exists() else []
    pendientes = dict(valores)
    for i, linea in enumerate(lineas):
        clave = linea.split("=", 1)[0].strip()
        if clave in pendientes and not linea.lstrip().startswith("#"):
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    RUTA_ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def credenciales_validas(api_id: str, api_hash: str) -> bool:
    return str(api_id).isdigit() and bool(re.fullmatch(r"[0-9a-fA-F]{32}", api_hash or ""))


def asistente_credenciales() -> tuple:
    """Guía paso a paso para obtener y guardar API_ID / API_HASH."""
    print("\n=== Configuración inicial ===")
    print("1. Abre https://my.telegram.org e inicia sesión con tu teléfono.")
    print("2. Entra en 'API development tools' y crea una app (nombre cualquiera).")
    print("3. Copia aquí los datos que te muestra.\n")
    while True:
        api_id = input("API_ID (número): ").strip()
        if api_id.isdigit():
            break
        print("   El API_ID debe ser solo números.")
    while True:
        api_hash = input("API_HASH (32 caracteres): ").strip()
        if re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
            break
        print("   El API_HASH debe tener 32 caracteres hexadecimales.")
    guardar_en_env({"API_ID": api_id, "API_HASH": api_hash})
    print("✅ Credenciales guardadas en .env\n")
    return api_id, api_hash


def obtener_credenciales(interactivo: bool = True) -> tuple:
    cfg = cargar_config()
    api_id, api_hash = cfg.get("API_ID", ""), cfg.get("API_HASH", "")
    if not credenciales_validas(api_id, api_hash):
        if not interactivo:
            raise RuntimeError("Faltan API_ID / API_HASH en el archivo .env")
        api_id, api_hash = asistente_credenciales()
    return int(api_id), api_hash
