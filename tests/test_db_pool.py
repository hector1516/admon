"""Tests del pool de conexiones a SQL Server (Fase B, B1) — Admon.

No tocan la BD: usan una fábrica falsa de conexiones. Lo que se prueba es la
política del pool (reutilizar, devolver, descartar rotas, tope de ociosas,
validar solo las viejas), que es justo donde un pool casero se rompe.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from db import ConnectionPool  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, *args):
        self.conn.executed.append(sql)
        return self

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.rolled_back = 0
        self.committed = 0

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


def make_pool(created, **kwargs):
    def factory():
        conn = FakeConnection()
        created.append(conn)
        return conn

    return ConnectionPool(factory, **kwargs)


def test_close_returns_connection_to_the_pool():
    """Pedir, cerrar y volver a pedir no debe abrir una conexión nueva."""
    created = []
    pool = make_pool(created)

    primera = pool.acquire()
    raw = primera._raw
    primera.close()

    segunda = pool.acquire()
    assert segunda._raw is raw
    assert len(created) == 1
    segunda.close()


def test_release_rolls_back_open_transaction():
    created = []
    pool = make_pool(created)

    conn = pool.acquire()
    raw = conn._raw
    conn.close()

    assert raw.rolled_back == 1
    assert raw.closed is False


def test_broken_connection_is_closed_and_not_reused():
    created = []
    pool = make_pool(created)

    conn = pool.acquire()
    raw = conn._raw
    conn.mark_broken()
    conn.close()

    assert raw.closed is True

    nueva = pool.acquire()
    assert nueva._raw is not raw
    assert len(created) == 2
    nueva.close()


def test_max_idle_closes_the_extra_connections():
    created = []
    pool = make_pool(created, max_idle=2)

    conexiones = [pool.acquire() for _ in range(5)]
    for conn in conexiones:
        conn.close()

    cerradas = [c for c in created if c.closed]
    assert len(cerradas) == 3


def test_double_close_is_safe():
    """Un `finally: conn.close()` después de un close explícito no debe romper."""
    created = []
    pool = make_pool(created)

    conn = pool.acquire()
    raw = conn._raw
    conn.close()
    conn.close()

    assert raw.rolled_back == 1
    assert raw.closed is False


def test_stale_connection_is_validated_before_reuse():
    created = []
    validadas = []

    def validate(raw):
        validadas.append(raw)
        return False

    pool = make_pool(created, validate=validate, validate_after=-1)

    primera = pool.acquire()
    raw_vieja = primera._raw
    primera.close()

    segunda = pool.acquire()
    assert validadas == [raw_vieja]
    assert segunda._raw is not raw_vieja
    assert len(created) == 2
    segunda.close()


def test_fresh_connection_is_not_validated():
    """Validar en cada request costaría un round-trip: solo se valida si estuvo ociosa."""
    created = []
    validadas = []

    def validate(raw):
        validadas.append(raw)
        return True

    pool = make_pool(created, validate=validate, validate_after=3600)

    primera = pool.acquire()
    primera.close()
    segunda = pool.acquire()

    assert validadas == []
    assert segunda._raw is primera._raw
    segunda.close()


def test_cursor_and_commit_are_proxied():
    created = []
    pool = make_pool(created)

    conn = pool.acquire()
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT 1")
    conn.commit()

    assert conn._raw.executed == ["SELECT 1"]
    assert conn._raw.committed == 1
    conn.close()


def test_context_manager_returns_connection():
    created = []
    pool = make_pool(created)

    with pool.acquire() as conn:
        raw = conn._raw
        conn.cursor().execute("SELECT 1")

    assert raw.closed is False
    assert raw.rolled_back == 1
