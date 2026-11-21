"""Caché TTL para el prefetch offline de Admon (Fase B, B2).

`/api/sync/pull` cuesta 43-756 ms (mediana ~160 ms) y lo pide el shell en cada
carga de página. Su carga útil es la misma para todos los usuarios con acceso y
el cliente ya tolera desfase (es un prefetch), así que se cachea unos segundos.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from cache import TTLCache  # noqa: E402


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
    """Un `None` no debe confundirse con 'no está en caché'."""
    cache = TTLCache(ttl=60)
    cache.set("x", None)
    assert cache.get("x") is None
