import asyncio
import csv
import json
from datetime import datetime

import pytest
from telethon import errors
from telethon.sessions import SQLiteSession, StringSession

import tgdl.cuentas
import tgdl.web
from tgdl import cifrado, html_export, motor, registro
from tgdl.bd import BD
from tgdl.exportar import exportar


# ---- cifrado de sesiones ------------------------------------------------------
def test_cifrado_ida_y_vuelta():
    blob = cifrado.cifrar("sesión secreta", "clave1")
    assert b"secreta" not in blob
    assert cifrado.descifrar(blob, "clave1") == "sesión secreta"
    with pytest.raises(cifrado.ContrasenaIncorrecta):
        cifrado.descifrar(blob, "otra")
    with pytest.raises(cifrado.ContrasenaIncorrecta):
        cifrado.descifrar(blob[:-1] + bytes([blob[-1] ^ 1]), "clave1")  # manipulado


def test_sesion_plana_se_convierte_en_cifrada(tmp_path, monkeypatch):
    sesiones = tmp_path / "sesiones"
    sesiones.mkdir()
    monkeypatch.setattr(tgdl.cuentas, "SESIONES", sesiones)
    plana = SQLiteSession(str(sesiones / "principal"))
    plana.set_dc(2, "149.154.167.51", 443)
    from telethon.crypto import AuthKey
    plana.auth_key = AuthKey(b"k" * 256)
    plana.save()
    plana.close()
    copia = SQLiteSession(str(sesiones / "principal"))
    esperado = StringSession.save(copia)
    copia.close()  # en Windows un archivo abierto no se puede borrar

    gestor = tgdl.cuentas.GestorCuentas(12345, "0" * 32, contrasena="clave")
    assert not (sesiones / "principal.session").exists()
    assert gestor.nombres() == ["principal"]
    assert cifrado.descifrar((sesiones / "principal.session.enc").read_bytes(), "clave") == esperado
    cliente = gestor._crear_cliente("principal")
    assert isinstance(cliente.session, StringSession) and cliente.session.auth_key.key == b"k" * 256


# ---- exportar -----------------------------------------------------------------
def _bd_con_mensajes(tmp_path, n=3):
    bd = BD(tmp_path / "d.db")
    bd.guardar_canal(-1, "Canal", tmp_path / "c")
    for i in range(1, n + 1):
        bd.guardar_mensaje(-1, i, "texto", origen=-1, texto=f"mensaje {i} https://ejemplo.com/{i}",
                           fecha=f"2024-01-01T00:{i % 60:02d}:00+00:00", vistas=i * 10)
    bd.confirmar()
    return bd


def test_exportar_csv_y_json(tmp_path):
    bd = _bd_con_mensajes(tmp_path)
    ruta = exportar(bd, -1, "csv")
    with open(ruta, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    assert len(filas) == 3 and filas[0]["enlaces"] == "https://ejemplo.com/1" and filas[2]["vistas"] == "30"
    datos = json.loads(exportar(bd, -1, "json").read_text(encoding="utf-8"))
    assert datos[1]["texto"].startswith("mensaje 2")
    with pytest.raises(ValueError):
        exportar(bd, -1, "xml")
    bd.cerrar()


# ---- archivo HTML por partes ---------------------------------------------------------
def test_html_grande_se_parte(tmp_path, monkeypatch):
    monkeypatch.setattr(html_export, "PARTE", 2)
    bd = _bd_con_mensajes(tmp_path, n=5)
    ruta = html_export.generar_html(bd, -1)
    partes = sorted((ruta.parent / "archivo_datos").glob("parte-*.js"))
    assert [p.name for p in partes] == ["parte-0002.js", "parte-0003.js"]
    assert partes[0].read_text(encoding="utf-8").startswith("__parte([")
    html = ruta.read_text(encoding="utf-8")
    assert '"partes": ["archivo_datos/parte-0002.js", "archivo_datos/parte-0003.js"]' in html
    # Al regenerar con menos mensajes desaparecen las partes que sobran
    monkeypatch.setattr(html_export, "PARTE", 2000)
    html_export.generar_html(bd, -1)
    assert not (ruta.parent / "archivo_datos").exists()
    bd.cerrar()


# ---- panel: repetir y programadas ------------------------------------------------------
@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setattr(tgdl.cuentas, "SESIONES", tmp_path / "sesiones")
    monkeypatch.setattr(tgdl.web, "RUTA_BD", tmp_path / "datos.db")
    p = tgdl.web.Panel(12345, "0" * 32)
    (tmp_path / "sesiones" / "principal.session").touch()
    lanzados = []

    def lanzar(cuentas, canales, opciones, programada=None):
        t = tgdl.web.Trabajo(cuentas, canales, opciones, programada)
        lanzados.append(t)
        p.trabajos[t.id] = t
        return t
    p._lanzar = lanzar
    p.lanzados = lanzados
    yield p
    p.bd.cerrar()


def test_programada_se_lanza_una_vez_al_dia(panel):
    datos = {"cuentas": ["principal"], "canales": [{"id": "@canal", "nombre": "Canal"}], "opciones": {},
             "hora": "03:00", "dias": [0, 1, 2, 3, 4, 5, 6]}
    panel.bd.guardar_programada("abc", json.dumps(datos))
    assert panel.revisar_programadas(datetime(2026, 10, 27, 2, 59)) == []
    assert len(panel.revisar_programadas(datetime(2026, 10, 27, 3, 0))) == 1
    assert panel.revisar_programadas(datetime(2026, 10, 27, 9, 0)) == []  # ya se lanzó hoy
    assert len(panel.revisar_programadas(datetime(2026, 10, 28, 3, 1))) == 1
    assert panel.lanzados[0].programada == "abc" and panel.lanzados[0].objetivos == ["@canal"]


def test_programada_respeta_los_dias(panel):
    datos = {"cuentas": ["principal"], "canales": [{"id": 1, "nombre": "x"}], "opciones": {},
             "hora": "03:00", "dias": [5, 6]}  # solo fines de semana
    panel.bd.guardar_programada("finde", json.dumps(datos))
    assert panel.revisar_programadas(datetime(2026, 10, 27, 4, 0)) == []  # martes
    assert len(panel.revisar_programadas(datetime(2026, 10, 31, 4, 0))) == 1  # sábado


def test_repetir_relanza_lo_mismo(panel):
    original = tgdl.web.Trabajo(["principal"], [{"id": "@canal", "nombre": "Canal"}], {"tipos": ["videos"]})
    original.estado = "terminado"
    panel.trabajos[original.id] = original

    class Peticion:
        match_info = {"id": original.id}
    asyncio.run(panel.api_repetir(Peticion()))
    nuevo = panel.lanzados[0]
    assert nuevo.canales == original.canales and nuevo.opciones == {"tipos": ["videos"]}


# ---- takeout y registro -----------------------------------------------------------------
def test_takeout_sin_confirmar_sigue_en_modo_normal():
    class Cliente:
        def takeout(self, **kw):
            raise errors.TakeoutInitDelayError(request=None, capture=3600)

    class Informe:
        lineas = []

        def log(self, texto, nivel="info"):
            self.lineas.append(texto)

    async def principal():
        import contextlib
        async with contextlib.AsyncExitStack() as pila:
            c = Cliente()
            return c, await motor._entrar_takeout(pila, "principal", c, Informe())
    original, resultado = asyncio.run(principal())
    assert resultado is original
    assert any("confirmar" in t for t in Informe.lineas)


def test_registro_en_archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, "RUTA", tmp_path / "registro.log")
    for h in list(registro._log.handlers):
        registro._log.removeHandler(h)
        h.close()
    registro.escribir("hola registro", "aviso")
    for h in registro._log.handlers:
        h.flush()
    assert "WARNING hola registro" in (tmp_path / "registro.log").read_text(encoding="utf-8")
    for h in list(registro._log.handlers):
        registro._log.removeHandler(h)
        h.close()
