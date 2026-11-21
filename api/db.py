"""Conexión a SQL Server (ECCSA_Admon) con pool.

Fase B (B1): antes se abría una conexión TDS nueva por petición. Medido: la
consulta tarda ~1 ms en caliente, pero el endpoint tardaba 40-270 ms porque el
login TDS (prelogin, auth, env change) se pagaba entero en cada request.

Admon usa `autocommit=True` (igual que antes); el pool reutiliza conexiones
ociosas y valida con `SELECT 1` solo cuando llevan rato sin usarse.
"""
import os
import queue
import threading
import time

import pymssql

_MAX_IDLE = 8          # conexiones ociosas que se guardan
_MAX_AGE = 600         # reciclar conexiones de más de 10 minutos
_VALIDATE_AFTER = 30   # validar solo si estuvo ociosa más de 30 s


def db_config():
    """Configuración de la BD. Falla al arrancar si falta la contraseña."""
    cfg = {
        "server": os.getenv("HUB_DB_SERVER", "10.188.141.15"),
        "user": os.getenv("HUB_DB_USER", "sa"),
        "password": os.getenv("HUB_DB_PASSWORD", ""),
        "database": os.getenv("HUB_DB_DATABASE", "ECCSA_Admon"),
    }
    if not cfg["password"]:
        raise RuntimeError("HUB_DB_PASSWORD no definida — no se puede conectar a la BD")
    return cfg


def _safe_close(raw):
    try:
        raw.close()
    except Exception:
        pass


def _validate_select_one(raw):
    cur = raw.cursor()
    try:
        cur.execute("SELECT 1")
        cur.fetchone()
        return True
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _default_reset(raw):
    """Limpia el estado antes de devolver la conexión al pool."""
    raw.rollback()


def _ping(raw):
    """Admon conecta con autocommit=True: `rollback()` es un no-op y NO detecta
    una conexión muerta. Un `SELECT 1` sí (cuesta ~0.3 ms)."""
    cur = raw.cursor()
    try:
        cur.execute("SELECT 1")
        cur.fetchone()
    finally:
        try:
            cur.close()
        except Exception:
            pass


class PooledConnection:
    """Envoltura de una conexión pymssql que vuelve al pool en vez de cerrarse.

    Hace de proxy de `cursor`, `commit`, `rollback` y de cualquier otro atributo
    (`__getattr__`), para que el código existente —`conn.cursor(...)`,
    `conn.commit()`, `conn.close()`— siga funcionando sin cambios.
    """

    def __init__(self, pool, raw, born):
        self._pool = pool
        self._raw = raw
        self._born = born
        self._closed = False
        self._broken = False

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._pool.release(self._raw, self._born, healthy=not self._broken)

    def __del__(self):
        # La mayoría de los endpoints hacen `conn = get_connection()` y NUNCA
        # llaman close(): sin esto la conexión se destruye al recolectarse y el
        # pool queda vacío.
        try:
            if not object.__getattribute__(self, "_closed"):
                self.close()
        except Exception:
            pass

    def mark_broken(self):
        self._broken = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                self._raw.rollback()
            except Exception:
                self._broken = True
        self.close()
        return False

    def __getattr__(self, name):
        # `object.__getattribute__` evita recursión: `self._raw` no pasa por
        # `__getattr__` porque ya existe en el objeto.
        return getattr(object.__getattribute__(self, "_raw"), name)


class ConnectionPool:
    """Pool LIFO acotado. Cada hilo toma su propia conexión; el pool solo
    guarda las ociosas."""

    def __init__(self, factory, max_idle=_MAX_IDLE, max_age=_MAX_AGE,
                 validate=None, validate_after=_VALIDATE_AFTER, reset=None):
        self._factory = factory
        self._idle = queue.LifoQueue()
        self._max_idle = max_idle
        self._max_age = max_age
        self._validate = validate
        self._validate_after = validate_after
        self._reset = reset or _default_reset
        self._lock = threading.Lock()

    def acquire(self):
        while True:
            try:
                raw, born, last_used = self._idle.get_nowait()
            except queue.Empty:
                return self._open()

            if self._max_age and (time.time() - born) > self._max_age:
                _safe_close(raw)
                continue

            if (self._validate is not None
                    and self._validate_after is not None
                    and (time.time() - last_used) > self._validate_after):
                try:
                    if not self._validate(raw):
                        _safe_close(raw)
                        continue
                except Exception:
                    _safe_close(raw)
                    continue

            return PooledConnection(self, raw, born)

    def _open(self):
        last_err = None
        for intento in range(3):
            try:
                return PooledConnection(self, self._factory(), time.time())
            except Exception as e:
                last_err = e
                if intento < 2:
                    time.sleep(2 * (intento + 1))
        raise last_err

    def release(self, raw, born, healthy=True):
        if not healthy:
            _safe_close(raw)
            return

        try:
            # En Admon `_reset` es `_ping` (autocommit=True: rollback() es
            # no-op y no detecta una conexión muerta).
            self._reset(raw)
        except Exception:
            _safe_close(raw)
            return

        with self._lock:
            if self._idle.qsize() >= self._max_idle:
                _safe_close(raw)
                return
            try:
                self._idle.put_nowait((raw, born, time.time()))
            except Exception:
                _safe_close(raw)

    def stats(self):
        return {"idle": self._idle.qsize(), "max_idle": self._max_idle}


def _connect():
    cfg = db_config()
    return pymssql.connect(
        server=cfg["server"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        autocommit=True,
        login_timeout=15,
        timeout=30,
    )


_pool = ConnectionPool(_connect, validate=_validate_select_one, reset=_ping)


def get_connection():
    """Conexión del pool. Misma interfaz que antes (cursor/commit/close)."""
    return _pool.acquire()


def pool_stats():
    return _pool.stats()
