import pytest

from tgdl.motor import Opciones
from tgdl.utilidades import TIPOS


def test_desde_dict_por_defecto():
    o = Opciones.desde_dict({})
    assert o.tipos == set(TIPOS) and o.hilos == 3 and o.espacio_minimo == 1024**3


def test_desde_dict_valores():
    o = Opciones.desde_dict({"tipos": "fotos,videos", "hilos": 50, "min_tamano": "1MB", "desde": "2024-05-01",
                             "extensiones": "MP4,.mkv", "reparto": "mensajes"})
    assert o.tipos == {"fotos", "videos"}
    assert o.hilos == 10  # se limita a 10
    assert o.min_tamano == 1024**2
    assert o.extensiones == {"mp4", "mkv"}
    assert o.desde.year == 2024


@pytest.mark.parametrize("d", [{"tipos": "fotos,gatos"}, {"nombres": "raro"}, {"reparto": "x"}, {"max_tamano": "mucho"}])
def test_desde_dict_invalido(d):
    with pytest.raises(ValueError):
        Opciones.desde_dict(d)


def test_seleccion_multiple():
    from descargar_canal import seleccion_multiple
    assert seleccion_multiple("1,3,5-7", 10) == [1, 3, 5, 6, 7]
    assert seleccion_multiple("0,2,99", 10) == [2]
    assert seleccion_multiple("@canal", 10) == []
