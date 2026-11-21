"""El origen tiene que comprimir: Cloudflare comprime al cliente, pero el
servidor manda el JSON y el JS sin comprimir hasta el borde.

Se prueba que el middleware está registrado y que va **por fuera** de la caché
de respuestas: si quedara por dentro, la caché guardaría el cuerpo ya comprimido
y un cliente sin gzip recibiría bytes ilegibles.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# `api.main` lee la config de la BD al importarse; para esta prueba alcanza con
# que exista (no se abre ninguna conexión).
os.environ.setdefault("HUB_DB_PASSWORD", "prueba")
os.environ.setdefault("HUB_DB_SERVER", "localhost")
os.environ.setdefault("HUB_DB_USER", "prueba")
os.environ.setdefault("HUB_DB_NAME", "prueba")

from api import main  # noqa: E402


def _nombres():
    return [m.cls.__name__ for m in main.app.user_middleware]


def test_gzip_registrado():
    nombres = _nombres()
    assert "GZipMiddleware" in nombres, nombres


def test_gzip_va_por_fuera_de_la_cache():
    # El índice menor es el middleware más externo. GZip tiene que comprimir
    # DESPUÉS de que la caché guarde el cuerpo, nunca antes.
    nombres = _nombres()
    assert nombres.index("GZipMiddleware") < nombres.index("ResponseCacheMiddleware"), nombres
