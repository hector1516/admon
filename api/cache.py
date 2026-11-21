"""Caché TTL mínima en memoria (Fase B, B2).

Para respuestas caras y compartidas que toleran desfase, como el prefetch
offline (`/api/sync/pull`). No es para datos que el usuario está mirando: eso se
lee fresco.
"""
import threading
import time


class TTLCache:
    def __init__(self, ttl=30):
        self._ttl = ttl
        self._datos = {}
        self._lock = threading.Lock()

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

    def invalidar(self, clave=None):
        with self._lock:
            if clave is None:
                self._datos.clear()
            else:
                self._datos.pop(clave, None)
