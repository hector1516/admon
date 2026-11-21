"""usage_tracker.py — Middleware de tracking de uso para Admon y Field.

Registra cada petición API en HUB_ApiUsage para estadísticas de uso.
Se instala como middleware en FastAPI.

Uso en main.py:
    from api.usage_tracker import UsageTrackingMiddleware
    app.add_middleware(UsageTrackingMiddleware, app_name="admon")

Fase B: el INSERT medía 16-216 ms (25k filas, 3 índices, 1 vCPU). Esperarlo en
`dispatch` metía ese costo en CADA respuesta. Ahora se encola y un hilo de fondo
agrupa hasta 50 filas en un solo INSERT: la respuesta no espera y la BD recibe
~1 escritura por ráfaga en vez de una por petición. Es telemetría: si la cola se
llena, se descarta.
"""

import logging
import queue
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("usage_tracker")

# Endpoints que NO se trackean (ruido)
SKIP_PATHS = {
    "/api/shell/state",
    "/api/panel/estado",
    "/api/panel/latido",
    "/health",
    "/healthz",
    "/api/health",
}

# Endpoints que NO requieren auth (se trackean con usuario null)
AUTH_OPTIONAL = {"/api/token", "/api/shell/state"}

# Cuántas filas se juntan como máximo en un INSERT múltiple. 20: medido, 50
# filas en un solo INSERT se dispara a 130-430 ms (compila 300 parámetros);
# 20 se queda en ~50-70 ms.
MAX_LOTE = 20
# Cuántos registros se guardan como máximo si el escritor va lento.
MAX_COLA = 5000


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, app_name: str = "admon"):
        super().__init__(app)
        self.app_name = app_name
        self._cola = queue.Queue(maxsize=MAX_COLA)
        self._hilo = None
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip non-API paths and noise
        if not path.startswith("/api/") or path in SKIP_PATHS:
            return await call_next(request)

        # Skip static files
        if path.startswith("/static/") or path.startswith("/media/"):
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Extract user from JWT (best effort, no blocking)
        usuario = None
        try:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Decode without verification (just for tracking)
                import jwt
                payload = jwt.decode(token, options={"verify_signature": False})
                usuario = payload.get("sub") or payload.get("username") or payload.get("nombre")
        except Exception:
            pass

        try:
            self._encolar(path, request.method, usuario, duration_ms, response.status_code)
        except Exception as e:
            logger.debug(f"Usage tracking error: {e}")

        return response

    # --- cola + escritor en segundo plano -----------------------------------

    def _encolar(self, path, method, usuario, duration_ms, status_code):
        self._arrancar_escritor()
        try:
            self._cola.put_nowait((path, method, usuario, duration_ms, status_code))
        except queue.Full:
            # Telemetría: mejor perder una fila que bloquear una respuesta.
            pass

    def _arrancar_escritor(self):
        if self._hilo is not None:
            return
        with self._lock:
            if self._hilo is None:
                hilo = threading.Thread(
                    target=self._bucle_escritor, daemon=True, name="usage-writer"
                )
                hilo.start()
                self._hilo = hilo

    def _bucle_escritor(self):
        while True:
            lote = [self._cola.get()]
            while len(lote) < MAX_LOTE:
                try:
                    lote.append(self._cola.get_nowait())
                except queue.Empty:
                    break
            self._escribir(lote)

    def _escribir(self, lote):
        """Un registro inválido no debe tirar las otras 19 filas del lote."""
        try:
            self._insertar_lote(lote)
            return
        except Exception as e:
            logger.warning(
                "telemetria: lote de %d filas falló (%s); reintento fila por fila",
                len(lote), e,
            )
        if len(lote) == 1:
            return
        fallos_seguidos = 0
        for fila in lote:
            try:
                self._insertar_lote([fila])
                fallos_seguidos = 0
            except Exception as e:
                fallos_seguidos += 1
                logger.debug("telemetria: fila perdida (%s)", e)
                if fallos_seguidos >= 3:
                    # La BD está caída: no seguir martillando con el resto.
                    break

    def _insertar_lote(self, lote):
        from api import db as _db

        valores = ",".join(["(%s, %s, %s, %s, GETDATE(), %s, %s)"] * len(lote))
        params = []
        for path, method, usuario, duration_ms, status_code in lote:
            params.extend([
                self.app_name, path[:200], method, usuario,
                duration_ms, status_code,
            ])
        conn = _db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO HUB_ApiUsage "
                "(App, Endpoint, Metodo, Usuario, Fecha, DuracionMs, StatusCode) "
                "VALUES " + valores,
                tuple(params),
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
