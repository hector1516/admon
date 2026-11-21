"""Tests de la caché de respuestas GET.

El servidor de SQL está sin RAM: cachear unos segundos las respuestas repetidas
es lo que mantiene la app usable. Estos tests fijan las reglas que no se pueden
romper: aislamiento por usuario, invalidación en escrituras, nada de cachear
errores ni binarios, y tope de memoria.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from response_cache import ResponseCache, ResponseCacheMiddleware  # noqa: E402


class FakeURL:
    def __init__(self, path="/api/reportes", query=""):
        self.path = path
        self.query = query


class FakeRequest:
    def __init__(self, method="GET", path="/api/reportes", query="", token="Bearer a"):
        self.method = method
        self.url = FakeURL(path, query)
        self.headers = {"authorization": token} if token else {}


class FakeResponse:
    def __init__(self, body=b'{"ok":true}', status=200,
                 content_type="application/json"):
        self.status_code = status
        self.body = body
        self.headers = {"content-type": content_type}

    @property
    def body_iterator(self):
        async def gen():
            yield self.body
        return gen()


def correr(mw, request, call_next):
    return asyncio.run(mw.dispatch(request, call_next))


def test_segunda_llamada_sale_de_cache():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse()

    correr(mw, FakeRequest(), call_next)
    correr(mw, FakeRequest(), call_next)

    assert len(llamadas) == 1


def test_usuarios_distintos_no_comparten():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse()

    correr(mw, FakeRequest(token="Bearer uno"), call_next)
    correr(mw, FakeRequest(token="Bearer dos"), call_next)

    assert len(llamadas) == 2


def test_query_distinta_no_comparte():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse()

    correr(mw, FakeRequest(query="limit=10"), call_next)
    correr(mw, FakeRequest(query="limit=20"), call_next)

    assert len(llamadas) == 2


def test_post_limpia_la_cache():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse()

    correr(mw, FakeRequest(), call_next)          # cachea
    correr(mw, FakeRequest(method="POST"), call_next)  # limpia
    correr(mw, FakeRequest(), call_next)          # vuelve a consultar

    assert len(llamadas) == 3


def test_no_cachea_errores():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse(status=500)

    correr(mw, FakeRequest(), call_next)
    correr(mw, FakeRequest(), call_next)

    assert len(llamadas) == 2


def test_no_cachea_binarios():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse(body=b"\x89PNG", content_type="image/png")

    correr(mw, FakeRequest(path="/api/users/1/foto"), call_next)
    correr(mw, FakeRequest(path="/api/users/1/foto"), call_next)

    assert len(llamadas) == 2


def test_no_cachea_salud():
    mw = ResponseCacheMiddleware(app=None)
    llamadas = []

    async def call_next(_req):
        llamadas.append(1)
        return FakeResponse()

    correr(mw, FakeRequest(path="/api/health"), call_next)
    correr(mw, FakeRequest(path="/api/health"), call_next)

    assert len(llamadas) == 2


def test_ttl_expira():
    cache = ResponseCache(ttl=0.05)
    cache.set(("k",), b"x", "application/json")
    assert cache.get(("k",)) is not None
    import time
    time.sleep(0.08)
    assert cache.get(("k",)) is None


def test_lru_respeta_el_tope():
    cache = ResponseCache(ttl=60, max_items=2)
    cache.set(("a",), b"1", "application/json")
    cache.set(("b",), b"2", "application/json")
    cache.set(("c",), b"3", "application/json")

    assert cache.get(("a",)) is None
    assert cache.get(("b",)) is not None
    assert cache.get(("c",)) is not None
    assert cache.stats()["items"] == 2


def test_respuesta_cacheada_conserva_el_cuerpo():
    mw = ResponseCacheMiddleware(app=None)
    cuerpo = b'{"folio":"RS-1"}'

    async def call_next(_req):
        return FakeResponse(body=cuerpo)

    correr(mw, FakeRequest(), call_next)
    resp = asyncio.run(mw.dispatch(FakeRequest(), call_next))

    assert resp.body == cuerpo
