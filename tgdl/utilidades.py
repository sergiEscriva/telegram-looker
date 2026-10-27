"""Funciones auxiliares sin estado."""
import os
import re
from datetime import datetime, timezone

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

TIPOS = ("fotos", "videos", "audios", "documentos", "stickers")

_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_UNIDADES = {"": 1, "b": 1, "k": 1024, "kb": 1024, "m": 1024**2, "mb": 1024**2,
             "g": 1024**3, "gb": 1024**3, "t": 1024**4, "tb": 1024**4}


def limpiar(nombre: str, maximo: int = 120) -> str:
    """Convierte un texto en un nombre de archivo/carpeta válido en Windows."""
    nombre = re.sub(r"\s+", " ", _INVALIDOS.sub("_", nombre or "")).strip().rstrip(".")
    if len(nombre) > maximo:
        base, ext = os.path.splitext(nombre)
        if len(ext) > 10:
            base, ext = nombre, ""
        nombre = base[: maximo - len(ext)].rstrip() + ext
    return nombre or "archivo"


def parse_tamano(texto) -> int:
    """'1.5GB' -> bytes. Vacío/None -> 0."""
    if texto in (None, "", 0):
        return 0
    if isinstance(texto, (int, float)):
        return int(texto)
    m = re.fullmatch(r"\s*([\d.,]+)\s*([a-zA-Z]*)\s*", str(texto))
    if not m or m.group(2).lower() not in _UNIDADES:
        raise ValueError(f"Tamaño no válido: {texto!r} (ejemplos: 500MB, 2GB)")
    return int(float(m.group(1).replace(",", ".")) * _UNIDADES[m.group(2).lower()])


def parse_fecha(texto, fin_de_dia: bool = False):
    """'2025-01-31' -> datetime UTC. Vacío -> None."""
    if not texto:
        return None
    if isinstance(texto, datetime):
        return texto if texto.tzinfo else texto.replace(tzinfo=timezone.utc)
    try:
        d = datetime.strptime(str(texto).strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Fecha no válida: {texto!r} (formato AAAA-MM-DD)") from None
    if fin_de_dia:
        d = d.replace(hour=23, minute=59, second=59)
    return d.replace(tzinfo=timezone.utc)


def parse_lista(texto) -> set:
    if not texto:
        return set()
    if isinstance(texto, (list, tuple, set)):
        return {str(x).strip().lower().lstrip(".") for x in texto if str(x).strip()}
    return {x.strip().lower().lstrip(".") for x in str(texto).split(",") if x.strip()}


def tamano_legible(n) -> str:
    n = float(n or 0)
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} PB"


def clasificar(msg):
    """Tipo de contenido descargable del mensaje, o None."""
    media = getattr(msg, "media", None)
    if media is None or getattr(msg, "file", None) is None:
        return None
    if isinstance(media, MessageMediaPhoto):
        return "fotos"
    if isinstance(media, MessageMediaDocument):
        if msg.sticker:
            return "stickers"
        if msg.video or msg.gif or msg.video_note:
            return "videos"
        if msg.audio or msg.voice:
            return "audios"
        return "documentos"
    return None  # enlaces, encuestas, ubicaciones...


def extension(msg) -> str:
    """Extensión real del archivo (sin punto, minúsculas). Prioriza el nombre original sobre el tipo MIME."""
    f = msg.file
    if f.name and "." in f.name:
        return f.name.rsplit(".", 1)[1].lower()
    return (f.ext or "").lower().lstrip(".")


def clave_archivo(msg):
    """Identificador único del archivo en Telegram (sirve para detectar duplicados)."""
    if getattr(msg, "photo", None) is not None:
        return f"p{msg.photo.id}"
    if getattr(msg, "document", None) is not None:
        return f"d{msg.document.id}"
    return None
