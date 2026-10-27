import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest


@pytest.fixture(autouse=True)
def _registro_temporal(tmp_path, monkeypatch):
    """Que los tests no escriban en el registro.log real del programa."""
    from tgdl import registro
    for h in list(registro._log.handlers):
        registro._log.removeHandler(h)
        h.close()
    monkeypatch.setattr(registro, "RUTA", tmp_path / "registro.log")
    yield
    for h in list(registro._log.handlers):
        registro._log.removeHandler(h)
        h.close()
