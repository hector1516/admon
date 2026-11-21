"""Caché TTL para el prefetch offline de Admon (Fase B, B2).

`/api/sync/pull` cuesta 43-756 ms (mediana ~160 ms) y lo pide el shell en cada
carga de página. Su carga útil es la misma para todos los usuarios con acceso y
el cliente ya tolera desfase (es un prefetch), así que se cachea unos segundos.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from cache import TTLCache, debe_invalidar_prefetch  # noqa: E402


def test_devuelve_el_valor_dentro_del_ttl():
    cache = TTLCache(ttl=60)
    assert cache.get("sync") is None
    cache.set("sync", {"cotizaciones": [1, 2]})
    assert cache.get("sync") == {"cotizaciones": [1, 2]}


def test_expira_pasado_el_ttl():
    cache = TTLCache(ttl=0.05)
    cache.set("sync", "viejo")
    time.sleep(0.08)
    assert cache.get("sync") is None


def test_invalidar_borra_la_entrada():
    cache = TTLCache(ttl=60)
    cache.set("sync", 1)
    cache.invalidar("sync")
    assert cache.get("sync") is None


def test_invalidar_todo():
    cache = TTLCache(ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.invalidar()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_no_cachea_none():
    """Limitación conocida: un valor `None` se confunde con 'no está en caché'
    (por eso `get_or_set` no guarda resultados `None`)."""
    cache = TTLCache(ttl=60)
    cache.set("x", None)
    assert cache.get("x") is None


def test_get_or_set_usa_el_valor_cacheado():
    cache = TTLCache(ttl=60)
    cache.set("k", 1)
    assert cache.get_or_set("k", lambda: 2) == 1


def test_get_or_set_calcula_una_sola_vez_con_varios_hilos():
    """Evita el thundering herd: 5 peticiones con la caché vacía no deben
    disparar 5 consultas de 160 ms a la vez."""
    import threading

    cache = TTLCache(ttl=60)
    llamadas = []
    resultados = []

    def calcular():
        llamadas.append(1)
        time.sleep(0.1)
        return {"x": 1}

    def pedir():
        resultados.append(cache.get_or_set("k", calcular))

    hilos = [threading.Thread(target=pedir) for _ in range(5)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(llamadas) == 1
    assert resultados == [{"x": 1}] * 5


def test_debe_invalidar_prefetch():
    assert debe_invalidar_prefetch("POST", "/api/clientes", 201)
    assert debe_invalidar_prefetch("DELETE", "/api/cotizaciones/5", 200)
    assert not debe_invalidar_prefetch("GET", "/api/clientes", 200)
    assert not debe_invalidar_prefetch("POST", "/api/reportes", 200)
    assert not debe_invalidar_prefetch("POST", "/api/clientes", 500)
