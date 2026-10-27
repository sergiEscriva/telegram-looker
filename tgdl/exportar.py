"""Exporta los mensajes de un canal descargado a CSV (para Excel) o JSON."""
import csv
import json
import os
import re
from pathlib import Path

_ENLACES = re.compile(r"https?://[^\s<>\"]+")
CAMPOS = ("id", "fecha", "tipo", "estado", "texto", "enlaces", "archivo", "tamano", "album", "tema",
          "comentario_de", "vistas")


def _filas(bd, canal_id: int, carpeta: Path):
    for f in bd.mensajes_de(canal_id):
        ruta = f["ruta"]
        if ruta:
            try:
                ruta = os.path.relpath(ruta, carpeta)
            except ValueError:  # otra unidad de disco
                pass
        yield {
            "id": f["msg_id"], "fecha": f["fecha"], "tipo": f["tipo"] or "texto", "estado": f["estado"],
            "texto": f["texto"] or "", "enlaces": " ".join(_ENLACES.findall(f["texto"] or "")),
            "archivo": ruta or "", "tamano": f["tamano"] or 0, "album": f["album"] or "", "tema": f["tema"] or "",
            "comentario_de": f["post_id"] or "", "vistas": f["vistas"] if f["vistas"] is not None else "",
        }


def exportar(bd, canal_id: int, formato: str = "csv") -> Path:
    """Escribe mensajes.csv o mensajes.json en la carpeta del canal y devuelve la ruta."""
    canal = bd.canal(canal_id)
    if canal is None:
        raise ValueError("Ese canal no está en la base de datos")
    if formato not in ("csv", "json"):
        raise ValueError("Formato no válido: usa csv o json")
    carpeta = Path(canal["carpeta"])
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"mensajes.{formato}"
    filas = list(_filas(bd, canal_id, carpeta))
    if formato == "json":
        ruta.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        # utf-8 con BOM y ";" para que Excel en español lo abra bien con doble clic
        with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
            escritor.writeheader()
            escritor.writerows(filas)
    return ruta
