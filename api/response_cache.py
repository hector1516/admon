"""Caché de respuestas GET en memoria.

Por qué existe: el servidor de SQL vive con muy poca RAM (buffer pool de 2 MB),
así que cada consulta lee del disco y recompila el plan. Navegar entre páginas
repite las mismas consultas; cachear la respuesta HTTP unos segundos las quita
de encima a la BD.

Qué cachea: solo `GET /api/*` que responda 200 y sea JSON.
- La clave incluye el token: dos usuarios nunca comparten una respuesta.
- Cualquier POST/PUT/PATCH/DELETE tira TODA la caché (simple y seguro).
- TTL corto y tope de memoria con LRU: si se llena, bota lo más viejo.
"""
import hashlib
import threading
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

TTL_SEGUNDOS = 30.0
MAX_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 1500

# Endpoints que no vale la pena cachear (baratos o de salud).
SIN_CACHE = {
    "/api/health", "/health", "/healthz",
    "/api/shell/state",
}

ESCRITURAS = ("POST", "PUT", "PATCH", "DELETE")


class ResponseCache:
    def __init__(self, ttl=TTL_SEGUNDOS, max_bytes=MAX_BYTES, max_items=MAX_ITEMS):
        self._ttl = ttl
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._datos = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, clave):
        with self._lock:
            item = self._datos.get(clave)
            if item is None:
                return None
            expira, cuerpo, tipo, headers = item
            if time.time() > expira:
                del self._datos[clave]
                self._bytes -= len(cuerpo)
                return None
            self._datos.move_to_end(clave)
            return cuerpo, tipo, headers

    def set(self, clave, cuerpo, tipo, headers=None):
        if len(cuerpo) > self._max_bytes:
            return
        with self._lock:
            viejo = self._datos.pop(clave, None)
            if viejo:
                self._bytes -= len(viejo[1])
            self._datos[clave] = (time.time() + self._ttl, cuerpo, tipo, headers or {})
            self._bytes += len(cuerpo)
            while self._datos and (
                self._bytes > self._max_bytes or len(self._datos) > self._max_items
            ):
                _, (_, cuerpo_viejo, _, _) = self._datos.popitem(last=False)
                self._bytes -= len(cuerpo_viejo)

    def clear(self):
        with self._lock:
            self._datos.clear()
            self._bytes = 0

    def stats(self):
        with self._lock:
            return {"items": len(self._datos), "bytes": self._bytes}


def _clave_usuario(request):
    auth = request.headers.get("authorization", "")
    if not auth:
        return "anon"
    return hashlib.sha256(auth.encode("utf-8")).hexdigest()[:16]


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cache=None):
        super().__init__(app)
        self.cache = cache or ResponseCache()

    async def dispatch(self, request, call_next):
        # Una escritura invalida todo: es barato y no deja datos viejos.
        if request.method in ESCRITURAS:
            self.cache.clear()
            return await call_next(request)

        ruta = request.url.path
        if request.method != "GET" or not ruta.startswith("/api/") or ruta in SIN_CACHE:
            return await call_next(request)

        clave = (ruta, request.url.query, _clave_usuario(request))
        golpe = self.cache.get(clave)
        if golpe is not None:
            cuerpo, tipo, headers = golpe
            return Response(content=cuerpo, media_type=tipo, headers=headers)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        tipo = response.headers.get("content-type", "")
        if "application/json" not in tipo:
            return response

        trozos = []
        async for trozo in response.body_iterator:
            trozos.append(trozo)
        cuerpo = b"".join(trozos)
        tipo_limpio = tipo.split(";")[0]
        headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }
        self.cache.set(clave, cuerpo, tipo_limpio, headers)

        return Response(content=cuerpo, media_type=tipo_limpio, headers=headers)
