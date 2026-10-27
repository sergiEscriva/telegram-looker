"""Registro en archivo (registro.log junto al programa) de todo lo que se muestra en consola y panel.

Rota solo: como mucho 3 archivos de 2 MB, así que nunca ocupa más de ~8 MB.
"""
import logging
from logging.handlers import RotatingFileHandler

from .config import BASE

RUTA = BASE / "registro.log"
_NIVELES = {"info": logging.INFO, "ok": logging.INFO, "aviso": logging.WARNING, "error": logging.ERROR}
_log = logging.getLogger("tgdl.registro")
_log.propagate = False
_log.setLevel(logging.INFO)


def _preparar():
    if _log.handlers:
        return True
    try:
        manejador = RotatingFileHandler(RUTA, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8", delay=True)
    except OSError:
        return False
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    _log.addHandler(manejador)
    return True


def escribir(texto: str, nivel: str = "info"):
    """Añade una línea al registro. Nunca lanza errores: si no se puede escribir, se ignora."""
    try:
        if _preparar():
            _log.log(_NIVELES.get(nivel, logging.INFO), texto)
    except Exception:  # noqa: BLE001 - el registro nunca debe parar una descarga
        pass
