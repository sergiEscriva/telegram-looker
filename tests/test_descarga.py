import asyncio
from pathlib import Path

import pytest

from tgdl import motor
from tgdl.bd import BD
from tgdl.informes import Informe

from telegram_falso import ClienteFalso, canal, contenido, documento, mensaje

MB = 1024 * 1024


class InformeLista(Informe):
    def __init__(self):
        self.lineas = []

    def log(self, texto, nivel="info"):
        self.lineas.append((nivel, texto))


def _ejecutar(tmp_path, cliente, **opciones):
    bd = BD(tmp_path / "d.db")
    opc = motor.Opciones(salida=tmp_path / "descargas", html=False, notificar=False, espacio_minimo=0, **opciones)
    informe = InformeLista()

    async def principal():
        async def resolver(_cliente, _obj):
            return canal()
        original = motor.resolver
        motor.resolver = resolver
        try:
            await motor.ejecutar({"principal": cliente}, ["@prueba"], opc, informe, bd)
        finally:
            motor.resolver = original

    asyncio.run(principal())
    return bd, informe


@pytest.fixture(autouse=True)
def _limpiar_canales():
    yield
    motor._CANALES_ACTIVOS.clear()


def _archivos(tmp_path):
    return {p.name: p for p in (tmp_path / "descargas").rglob("*") if p.is_file()}


def test_descarga_completa_con_trozos_y_duplicados(tmp_path):
    grande = documento(10, 5 * MB + 123, "video.mp4", "video/mp4")
    pequeno = documento(11, 3000, "nota.pdf", "application/pdf")
    cliente = ClienteFalso([
        mensaje(1, "hola"),
        mensaje(2, "vídeo", grande),
        mensaje(3, "", pequeno),
        mensaje(4, "repetido", grande),  # mismo archivo de Telegram: no se vuelve a bajar
    ])
    bd, informe = _ejecutar(tmp_path, cliente, conexiones=3)
    archivos = _archivos(tmp_path)
    assert archivos["2_video.mp4"].read_bytes() == contenido(10, grande.size)
    assert archivos["3_nota.pdf"].read_bytes() == contenido(11, 3000)
    assert not [n for n in archivos if n.endswith((".part", ".ok"))]
    # 11 trozos de 512 KB pedidos una sola vez cada uno
    assert sorted(cliente.trozos_pedidos) == [i * motor.TROZO for i in range(11)]
    estados = {f["msg_id"]: f["estado"] for f in bd.mensajes_de(-1000000000000 - 1234567)}
    assert estados == {1: "texto", 2: "ok", 3: "ok", 4: "duplicado"}
    bd.cerrar()


def test_reanuda_un_archivo_a_medias(tmp_path):
    grande = documento(20, 4 * MB, "pelicula.mkv", "video/x-matroska")
    datos = contenido(20, grande.size)
    # Un intento anterior dejó 3 trozos buenos (y basura después, que debe sobrescribirse)
    carpeta = tmp_path / "descargas" / f"Canal de prueba [{1000000000000 + 1234567}]" / "documentos"
    carpeta.mkdir(parents=True)
    (carpeta / "1_pelicula.mkv.part").write_bytes(datos[:3 * motor.TROZO] + b"x" * 1000)
    (carpeta / "1_pelicula.mkv.part.ok").write_text("3")
    cliente = ClienteFalso([mensaje(1, "", grande)])
    bd, informe = _ejecutar(tmp_path, cliente)
    assert (carpeta / "1_pelicula.mkv").read_bytes() == datos
    assert sorted(cliente.trozos_pedidos) == [i * motor.TROZO for i in range(3, 8)]  # solo lo que faltaba
    assert any("se reanuda" in t for _, t in informe.lineas)
    bd.cerrar()


def test_reintenta_tras_un_corte_sin_empezar_de_cero(tmp_path, monkeypatch):
    async def sin_espera(_):
        pass
    monkeypatch.setattr(motor.asyncio, "sleep", sin_espera)
    grande = documento(30, 6 * MB, "copia.zip", "application/zip")
    cliente = ClienteFalso([mensaje(1, "", grande)], fallar_trozo=9 * motor.TROZO)
    bd, _ = _ejecutar(tmp_path, cliente, conexiones=1)
    assert _archivos(tmp_path)["1_copia.zip"].read_bytes() == contenido(30, grande.size)
    # Con una conexión los trozos 0-8 se guardan antes del corte y no se vuelven a pedir
    assert cliente.trozos_pedidos.count(0) == 1
    bd.cerrar()


def test_filtro_por_tipo_omite_documentos(tmp_path):
    cliente = ClienteFalso([mensaje(1, "", documento(40, 5000, "a.pdf", "application/pdf"))])
    bd, _ = _ejecutar(tmp_path, cliente, tipos={"fotos"})
    assert _archivos(tmp_path) == {}
    bd.cerrar()


def test_detener_conserva_lo_descargado_para_seguir(tmp_path):
    grande = documento(50, 8 * MB, "largo.mp4", "video/mp4")
    cliente = ClienteFalso([mensaje(1, "", grande)])
    detener = asyncio.Event()
    original = cliente.iter_download

    async def lento(doc, **kw):
        async for c in original(doc, **kw):
            if len(cliente.trozos_pedidos) >= 4:
                detener.set()  # el usuario pulsa Detener a mitad
            yield c
    cliente.iter_download = lento

    bd = BD(tmp_path / "d.db")
    opc = motor.Opciones(salida=tmp_path / "descargas", html=False, notificar=False, espacio_minimo=0, conexiones=1)

    async def principal():
        async def resolver(_c, _o):
            return canal()
        motor.resolver, previo = resolver, motor.resolver
        try:
            await motor.ejecutar({"principal": cliente}, ["@prueba"], opc, InformeLista(), bd, detener)
        finally:
            motor.resolver = previo
    asyncio.run(principal())
    archivos = _archivos(tmp_path)
    assert "1_largo.mp4" not in archivos
    assert "1_largo.mp4.part" in archivos and int(archivos["1_largo.mp4.part.ok"].read_text()) >= 1
    assert not bd.hechos(-1000000000000 - 1234567)  # no se marca como hecho: se seguirá la próxima vez
    bd.cerrar()


def test_vistas_se_guardan(tmp_path):
    m = mensaje(1, "con vistas")
    m.views = 321
    bd, _ = _ejecutar(tmp_path, ClienteFalso([m]))
    assert bd.mensajes_de(-1000000000000 - 1234567)[0]["vistas"] == 321
    bd.cerrar()


def test_trozos_hechos_ignora_marca_mayor_que_el_archivo(tmp_path):
    tmp, marca = tmp_path / "a.part", tmp_path / "a.part.ok"
    tmp.write_bytes(b"x" * (2 * motor.TROZO + 5))
    marca.write_text("9")
    assert motor.DescargaCanal._trozos_hechos(tmp, marca) == 2
    marca.write_text("basura")
    assert motor.DescargaCanal._trozos_hechos(tmp, marca) == 0
    assert motor.DescargaCanal._trozos_hechos(Path(tmp_path / "no"), marca) == 0
