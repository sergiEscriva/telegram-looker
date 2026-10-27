import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

import tgdl.cuentas
import tgdl.web


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setattr(tgdl.cuentas, "SESIONES", tmp_path / "sesiones")
    monkeypatch.setattr(tgdl.web, "RUTA_BD", tmp_path / "datos.db")
    p = tgdl.web.Panel(12345, "0" * 32)
    yield p
    p.bd.cerrar()


def _correr(panel, prueba):
    async def principal():
        servidor = TestServer(tgdl.web.crear_app(panel), host="127.0.0.1")
        cliente = TestClient(servidor)
        await cliente.start_server()
        panel.puerto = servidor.port
        try:
            await prueba(cliente, f"127.0.0.1:{servidor.port}")
        finally:
            await cliente.close()
    asyncio.run(principal())


def test_api_exige_token(panel):
    async def prueba(c, host):
        r = await c.get("/api/trabajos")
        assert r.status == 403
        r = await c.get("/api/trabajos", headers={"X-Token": "malo"})
        assert r.status == 403
        r = await c.get("/api/trabajos", headers={"X-Token": panel.token})
        assert r.status == 200
    _correr(panel, prueba)


def test_rechaza_otra_web(panel):
    async def prueba(c, host):
        # Petición "simple" (text/plain) que otra web podría mandar sin preflight
        r = await c.post("/api/trabajos", data='{"cuentas":["principal"]}',
                         headers={"Origin": "https://malvado.example", "Content-Type": "text/plain",
                                  "X-Token": panel.token})
        assert r.status == 403
        r = await c.post("/api/cuentas/codigo", data="{}", headers={"Content-Type": "text/plain"})
        assert r.status == 403
    _correr(panel, prueba)


def test_rechaza_dns_rebinding(panel):
    async def prueba(c, host):
        r = await c.get("/", headers={"Host": "malvado.example"})
        assert r.status == 403
        r = await c.get("/")
        assert r.status == 200
        assert panel.token in await r.text()
    _correr(panel, prueba)


def test_websocket_exige_token(panel):
    async def prueba(c, host):
        r = await c.get("/ws")
        assert r.status == 403
        ws = await c.ws_connect(f"/ws?token={panel.token}", origin=f"http://{host}")
        msg = await ws.receive_json()
        assert "trabajos" in msg
        await ws.close()
    _correr(panel, prueba)


def test_ver_aisla_archivos(panel, tmp_path):
    carpeta = tmp_path / "Canal [1]"
    (carpeta / "documentos").mkdir(parents=True)
    (carpeta / "index.html").write_text("<html></html>", encoding="utf-8")
    (carpeta / "documentos" / "1_malo.html").write_text("<script>fetch('/api/cuentas')</script>", encoding="utf-8")
    (carpeta / "documentos" / "2_foto.jpg").write_bytes(b"\xff\xd8\xff")
    panel.bd.guardar_canal(-1001, "Canal", carpeta)

    async def prueba(c, host):
        r = await c.get("/ver/-1001/index.html")
        assert r.status == 200 and "sandbox allow-scripts" in r.headers["Content-Security-Policy"]
        r = await c.get("/ver/-1001/documentos/1_malo.html")
        assert r.headers["Content-Disposition"] == "attachment"
        assert r.headers["Content-Security-Policy"] == "sandbox"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        r = await c.get("/ver/-1001/documentos/2_foto.jpg")
        assert "Content-Disposition" not in r.headers
        r = await c.get("/ver/-1001/../../etc/passwd")
        assert r.status == 404
    _correr(panel, prueba)


def test_nombre_de_dispositivo_configurable(tmp_path, monkeypatch):
    monkeypatch.setattr(tgdl.cuentas, "SESIONES", tmp_path / "sesiones")
    monkeypatch.setenv("NOMBRE_DISPOSITIVO", "Portátil de casa")
    monkeypatch.setenv("VERSION_APP", "5.1")
    gestor = tgdl.cuentas.GestorCuentas(12345, "0" * 32)
    cliente = gestor._crear_cliente("prueba")
    assert cliente._init_request.device_model == "Portátil de casa"
    assert cliente._init_request.app_version == "5.1"
    monkeypatch.delenv("NOMBRE_DISPOSITIVO")
    monkeypatch.setattr(tgdl.cuentas, "cargar_config", lambda: {})
    assert tgdl.cuentas.GestorCuentas(12345, "0" * 32)._crear_cliente("otra")._init_request.device_model == "PC"
