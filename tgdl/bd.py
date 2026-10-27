"""Estado persistente en SQLite: progreso por mensaje, duplicados, canales e hilos de comentarios.

Todo el programa corre en un único hilo asyncio, así que una sola conexión basta y
varias cuentas pueden escribir a la vez sin pisarse. Las escrituras frecuentes (mensajes y
archivos) se confirman por lotes; si el programa se corta se pierde como mucho un segundo de
registro, y esos archivos se reconocen en la siguiente pasada porque ya están en disco.
"""
import sqlite3
import time
from datetime import datetime, timezone

# Estados que significan "no hace falta volver a procesarlo"
HECHOS = ("ok", "texto", "duplicado", "servicio")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensajes (
    canal_id   INTEGER NOT NULL,   -- chat real del mensaje (canal o grupo de comentarios)
    msg_id     INTEGER NOT NULL,
    origen     INTEGER,            -- canal descargado al que pertenece (para el archivo HTML)
    estado     TEXT NOT NULL,      -- ok | texto | duplicado | servicio | fallo
    tipo       TEXT,
    ruta       TEXT,
    tamano     INTEGER,
    fecha      TEXT,
    texto      TEXT,
    album      INTEGER,
    tema       TEXT,
    post_id    INTEGER,            -- si es un comentario: publicación del canal a la que responde
    cuenta     TEXT,
    actualizado TEXT,
    PRIMARY KEY (canal_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_mensajes_origen ON mensajes (origen, fecha);
CREATE TABLE IF NOT EXISTS archivos (
    clave  TEXT PRIMARY KEY,       -- id del archivo en Telegram (p<id> foto, d<id> documento)
    ruta   TEXT NOT NULL,
    tamano INTEGER
);
CREATE TABLE IF NOT EXISTS canales (
    canal_id INTEGER PRIMARY KEY,
    titulo   TEXT,
    carpeta  TEXT,
    actualizado TEXT
);
CREATE TABLE IF NOT EXISTS hilos (
    canal_id  INTEGER,
    post_id   INTEGER,
    ultimo_id INTEGER,
    PRIMARY KEY (canal_id, post_id)
);
CREATE TABLE IF NOT EXISTS trabajos (
    id    TEXT PRIMARY KEY,        -- historial de descargas del panel web
    datos TEXT NOT NULL,           -- JSON con el último estado del trabajo
    fin   REAL
);
"""

_LOTE = 200          # escrituras máximas sin confirmar
_LOTE_SEGUNDOS = 1.0 # tiempo máximo sin confirmar


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BD:
    def __init__(self, ruta):
        self.con = sqlite3.connect(str(ruta), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.executescript(_ESQUEMA)
        self.con.commit()
        self._sin_confirmar, self._ultimo_commit = 0, time.monotonic()

    def confirmar(self):
        """Guarda en disco las escrituras pendientes."""
        if self._sin_confirmar:
            self.con.commit()
        self._sin_confirmar, self._ultimo_commit = 0, time.monotonic()

    def _escrito(self):
        self._sin_confirmar += 1
        if self._sin_confirmar >= _LOTE or time.monotonic() - self._ultimo_commit >= _LOTE_SEGUNDOS:
            self.confirmar()

    # ---- mensajes ---------------------------------------------------------
    def hechos(self, canal_id: int) -> set:
        marcas = ",".join("?" * len(HECHOS))
        filas = self.con.execute(
            f"SELECT msg_id FROM mensajes WHERE canal_id=? AND estado IN ({marcas})", (canal_id, *HECHOS))
        return {f[0] for f in filas}

    def guardar_mensaje(self, canal_id, msg_id, estado, *, origen=None, tipo=None, ruta=None, tamano=None,
                        fecha=None, texto=None, album=None, tema=None, post_id=None, cuenta=None):
        self.con.execute(
            "INSERT OR REPLACE INTO mensajes (canal_id, msg_id, origen, estado, tipo, ruta, tamano, fecha, texto,"
            " album, tema, post_id, cuenta, actualizado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (canal_id, msg_id, origen, estado, tipo, ruta, tamano, fecha, texto, album, tema, post_id, cuenta, _ahora()))
        self._escrito()

    def mensajes_de(self, origen: int):
        return self.con.execute(
            "SELECT * FROM mensajes WHERE origen=? AND estado != 'servicio' ORDER BY fecha, msg_id", (origen,)).fetchall()

    def posts_con_fallos(self, origen: int) -> set:
        filas = self.con.execute(
            "SELECT DISTINCT post_id FROM mensajes WHERE origen=? AND post_id IS NOT NULL AND estado='fallo'", (origen,))
        return {f[0] for f in filas}

    def resumen(self, origen: int) -> dict:
        f = self.con.execute(
            "SELECT COUNT(*) total, SUM(estado IN ('ok','duplicado')) archivos, SUM(CASE WHEN estado='ok' THEN tamano END) bytes,"
            " SUM(estado='fallo') fallos, MAX(actualizado) actualizado FROM mensajes WHERE origen=?", (origen,)).fetchone()
        return {k: (f[k] or 0) for k in f.keys()}

    # ---- duplicados -------------------------------------------------------
    def buscar_archivo(self, clave):
        return self.con.execute("SELECT ruta, tamano FROM archivos WHERE clave=?", (clave,)).fetchone()

    def guardar_archivo(self, clave, ruta, tamano):
        if clave:
            self.con.execute("INSERT OR REPLACE INTO archivos VALUES (?,?,?)", (clave, str(ruta), tamano))
            self._escrito()

    # ---- canales ----------------------------------------------------------
    def guardar_canal(self, canal_id, titulo, carpeta):
        self.con.execute("INSERT OR REPLACE INTO canales VALUES (?,?,?,?)", (canal_id, titulo, str(carpeta), _ahora()))
        self.con.commit()

    def canal(self, canal_id):
        return self.con.execute("SELECT * FROM canales WHERE canal_id=?", (canal_id,)).fetchone()

    def canales(self):
        return self.con.execute("SELECT * FROM canales ORDER BY actualizado DESC").fetchall()

    # ---- hilos de comentarios --------------------------------------------
    def ultimo_hilo(self, canal_id, post_id) -> int:
        f = self.con.execute("SELECT ultimo_id FROM hilos WHERE canal_id=? AND post_id=?", (canal_id, post_id)).fetchone()
        return f[0] if f else 0

    def guardar_hilo(self, canal_id, post_id, ultimo_id):
        self.con.execute("INSERT OR REPLACE INTO hilos VALUES (?,?,?)", (canal_id, post_id, ultimo_id))
        self.con.commit()

    # ---- historial de trabajos del panel ----------------------------------
    def guardar_trabajo(self, trabajo_id, datos: str, fin):
        self.con.execute("INSERT OR REPLACE INTO trabajos VALUES (?,?,?)", (trabajo_id, datos, fin))
        self.con.commit()

    def trabajos_guardados(self, limite: int = 30):
        return self.con.execute("SELECT * FROM trabajos ORDER BY fin DESC LIMIT ?", (limite,)).fetchall()

    def borrar_trabajo(self, trabajo_id):
        self.con.execute("DELETE FROM trabajos WHERE id=?", (trabajo_id,))
        self.con.commit()

    def cerrar(self):
        self.confirmar()
        self.con.close()
