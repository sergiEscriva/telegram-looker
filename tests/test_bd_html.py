import json
import re

from tgdl.bd import BD
from tgdl.html_export import generar_html


def _datos(html: str) -> dict:
    m = re.search(r"const D = (.*);\n", html)
    return json.loads(m.group(1))


def test_progreso_y_lotes(tmp_path):
    bd = BD(tmp_path / "d.db")
    bd.guardar_canal(-1001, "Canal", tmp_path / "c")
    bd.guardar_mensaje(-1001, 1, "ok", origen=-1001, tipo="fotos", tamano=10, fecha="2024-01-01T00:00:00+00:00")
    bd.guardar_mensaje(-1001, 2, "fallo", origen=-1001, tipo="videos", post_id=None)
    bd.guardar_mensaje(-2002, 7, "fallo", origen=-1001, post_id=1)
    assert bd.hechos(-1001) == {1}
    assert bd.posts_con_fallos(-1001) == {1}
    r = bd.resumen(-1001)
    assert (r["total"], r["archivos"], r["bytes"], r["fallos"]) == (3, 1, 10, 2)
    bd.cerrar()
    # Lo escrito por lotes se guarda al cerrar
    bd2 = BD(tmp_path / "d.db")
    assert bd2.hechos(-1001) == {1}
    bd2.cerrar()


def test_historial_trabajos(tmp_path):
    bd = BD(tmp_path / "d.db")
    bd.guardar_trabajo("a", '{"id": "a"}', 1.0)
    bd.guardar_trabajo("b", '{"id": "b"}', 2.0)
    assert [f["id"] for f in bd.trabajos_guardados()] == ["b", "a"]
    bd.borrar_trabajo("a")
    assert [f["id"] for f in bd.trabajos_guardados()] == ["b"]
    bd.cerrar()


def test_html_no_permite_inyeccion(tmp_path):
    bd = BD(tmp_path / "d.db")
    # Un título con el marcador de datos y un texto que intenta cerrar el <script>
    bd.guardar_canal(-1, '__DATOS__ "><b>x', tmp_path / "c")
    malo = '</script><img src=x onerror=alert(1)> "><svg onload=alert(2)> __TITULO__'
    bd.guardar_mensaje(-1, 1, "texto", origen=-1, texto=malo, fecha="2024-01-01T00:00:00+00:00")
    html = generar_html(bd, -1).read_text(encoding="utf-8")
    assert "<img src=x" not in html and "<svg" not in html and "<b>x" not in html
    assert html.count("</script>") == 1
    datos = _datos(html)
    assert datos["mensajes"][0]["t"] == malo  # el texto se conserva intacto dentro del JSON
    assert datos["titulo"] == '__DATOS__ "><b>x'
    bd.cerrar()


def test_html_titulo_vacio(tmp_path):
    bd = BD(tmp_path / "d.db")
    bd.guardar_canal(-1, None, tmp_path / "c")
    assert _datos(generar_html(bd, -1).read_text(encoding="utf-8"))["titulo"] == ""
    bd.cerrar()
