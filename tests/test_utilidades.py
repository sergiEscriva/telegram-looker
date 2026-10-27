import pytest

from tgdl.utilidades import limpiar, parse_fecha, parse_lista, parse_tamano, tamano_legible


@pytest.mark.parametrize("entrada, esperado", [
    ('a<b>c:"d"/e\\f|g?h*i', "a_b_c__d__e_f_g_h_i"),
    ("  hola   mundo  ", "hola mundo"),
    ("fin con punto.", "fin con punto"),
    ("fin con espacio . ", "fin con espacio"),
    ("", "archivo"),
    (None, "archivo"),
    ("CON", "_CON"),
    ("nul.txt", "_nul.txt"),
    ("com1.tar.gz", "_com1.tar.gz"),
    ("CONSOLA", "CONSOLA"),
])
def test_limpiar(entrada, esperado):
    assert limpiar(entrada) == esperado


def test_limpiar_conserva_extension_al_recortar():
    nombre = limpiar("x" * 300 + ".mp4", 50)
    assert len(nombre) <= 50 and nombre.endswith(".mp4")


def test_limpiar_limita_bytes_utf8():
    nombre = limpiar("ж" * 120 + ".pdf")  # 2 bytes por carácter
    assert len(nombre.encode("utf-8")) <= 200 and nombre.endswith(".pdf")


@pytest.mark.parametrize("entrada, esperado", [
    ("", 0), (None, 0), (0, 0), (1234, 1234), ("500", 500), ("1KB", 1024), ("1,5 mb", int(1.5 * 1024**2)),
    ("2GB", 2 * 1024**3), ("1t", 1024**4),
])
def test_parse_tamano(entrada, esperado):
    assert parse_tamano(entrada) == esperado


@pytest.mark.parametrize("entrada", ["abc", "10XB", "-5MB"])
def test_parse_tamano_invalido(entrada):
    with pytest.raises(ValueError):
        parse_tamano(entrada)


def test_parse_fecha():
    assert parse_fecha("") is None
    d = parse_fecha("2025-01-31", fin_de_dia=True)
    assert (d.year, d.month, d.day, d.hour, d.minute) == (2025, 1, 31, 23, 59)
    assert d.tzinfo is not None
    with pytest.raises(ValueError):
        parse_fecha("31/01/2025")


def test_parse_lista():
    assert parse_lista("MP4, .mkv,,pdf ") == {"mp4", "mkv", "pdf"}
    assert parse_lista(["Fotos", " videos "]) == {"fotos", "videos"}
    assert parse_lista(None) == set()


def test_tamano_legible():
    assert tamano_legible(0) == "0.0 B"
    assert tamano_legible(1536) == "1.5 KB"
