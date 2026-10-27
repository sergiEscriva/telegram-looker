"""Un Telegram de mentira para probar el motor de descarga sin red."""
import asyncio
from datetime import datetime, timedelta, timezone

from telethon.tl import types
from telethon.tl.custom.message import Message

CANAL_ID = 1234567


def canal(titulo="Canal de prueba"):
    return types.Channel(id=CANAL_ID, title=titulo, photo=types.ChatPhotoEmpty(),
                         date=datetime(2024, 1, 1, tzinfo=timezone.utc), access_hash=99, broadcast=True)


def _fecha(i):
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def documento(doc_id, tamano, nombre="archivo.bin", mime="application/octet-stream"):
    return types.Document(id=doc_id, access_hash=1, file_reference=b"ref", date=_fecha(0), mime_type=mime,
                          size=tamano, dc_id=2, attributes=[types.DocumentAttributeFilename(nombre)])


def mensaje(msg_id, texto="", doc=None):
    media = types.MessageMediaDocument(document=doc) if doc is not None else None
    return Message(id=msg_id, peer_id=types.PeerChannel(CANAL_ID), date=_fecha(msg_id), message=texto, media=media)


def contenido(doc_id, tamano):
    """Bytes deterministas de un documento (para comprobar que se escriben en su sitio)."""
    patron = doc_id.to_bytes(4, "big") + b"telegram-looker"
    return (patron * (tamano // len(patron) + 1))[:tamano]


class _Lista(list):
    total = 0


class ClienteFalso:
    def __init__(self, mensajes, fallar_trozo=None):
        self.mensajes = mensajes
        self.trozos_pedidos = []       # offsets pedidos con iter_download
        self.fallar_trozo = fallar_trozo  # offset que falla una vez (simula un corte)
        self.enviados = []

    async def get_messages(self, entidad, limit=None, ids=None, **kw):
        if ids is not None:
            return next((m for m in self.mensajes if m.id == ids), None)
        r = _Lista(self.mensajes[-1:] if limit else [])
        r.total = len(self.mensajes)
        return r

    async def iter_messages(self, entidad, reverse=False, **kw):
        for m in sorted(self.mensajes, key=lambda m: m.id, reverse=not reverse):
            yield m

    async def iter_download(self, doc, offset=0, limit=None, request_size=None, file_size=None):
        await asyncio.sleep(0)
        if self.fallar_trozo is not None and offset == self.fallar_trozo:
            self.fallar_trozo = None
            raise ConnectionError("corte simulado")
        self.trozos_pedidos.append(offset)
        datos = contenido(doc.id, doc.size)
        yield datos[offset:offset + request_size]

    async def download_media(self, msg, file=None, progress_callback=None):
        datos = contenido(msg.document.id, msg.document.size)
        with open(file, "wb") as f:
            f.write(datos)
        if progress_callback:
            await progress_callback(len(datos), len(datos))
        return file

    async def send_message(self, destino, texto):
        self.enviados.append(texto)

    def add_event_handler(self, *a, **k):
        pass

    def remove_event_handler(self, *a, **k):
        pass
