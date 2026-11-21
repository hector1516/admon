"""Caché TTL mínima en memoria (Fase B, B2).

Para respuestas caras y compartidas que toleran desfase, como el prefetch
offline (`/api/sync/pull`). No es para datos que el usuario está mirando: eso se
lee fresco.
"""
import threading
import time

ESCRITURAS = ("POST", "PUT", "PATCH", "DELETE")
PREFIJOS_QUE_INVALIDAN = ("/api/clientes", "/api/cotizaciones")


def debe_invalidar_prefetch(method, path, status_code):
    """¿Esta petición pudo cambiar lo que devuelve /api/sync/pull?"""
    return (
        status_code < 400
        and method in ESCRITURAS
        and path.startswith(PREFIJOS_QUE_INVALIDAN)
    )


class TTLCache:
    def __init__(self, ttl=30):
        self._ttl = ttl
        self._datos = {}
        self._lock = threading.Lock()
        self._locks_por_clave = {}

    def _lock_de(self, clave):
        with self._lock:
            lock = self._locks_por_clave.get(clave)
            if lock is None:
                lock = threading.Lock()
                self._locks_por_clave[clave] = lock
            return lock

    def get(self, clave):
        with self._lock:
            entrada = self._datos.get(clave)
            if entrada is None:
                return None
            valor, expira = entrada
            if time.time() > expira:
                del self._datos[clave]
                return None
            return valor

    def set(self, clave, valor):
        with self._lock:
            self._datos[clave] = (valor, time.time() + self._ttl)

    def get_or_set(self, clave, calcular):
        """Devuelve el valor cacheado o lo calcula. Con varios hilos, solo uno
        calcula (single-flight): evita que 5 peticiones disparen la consulta
        cara a la vez."""
        valor = self.get(clave)
        if valor is not None:
            return valor
        with self._lock_de(clave):
            valor = self.get(clave)  # otro hilo pudo llenarla mientras esperaba
            if valor is not None:
                return valor
            valor = calcular()
            if valor is not None:
                self.set(clave, valor)
            return valor

    def invalidar(self, clave=None):
        with self._lock:
            if clave is None:
                self._datos.clear()
            else:
                self._datos.pop(clave, None)
