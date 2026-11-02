"""usage_tracker.py — Middleware de tracking de uso para Admon y Field.

Registra cada petición API en HUB_ApiUsage para estadísticas de uso.
Se instala como middleware en FastAPI.

Uso en main.py:
    from api.usage_tracker import UsageTrackingMiddleware
    app.add_middleware(UsageTrackingMiddleware, app_name="admon")
"""

import time
import logging
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


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, app_name: str = "admon"):
        super().__init__(app)
        self.app_name = app_name

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
                # We don't verify here - just extract the sub/username
                # The actual verification happens in the endpoint
                payload = jwt.decode(token, options={"verify_signature": False})
                usuario = payload.get("sub") or payload.get("username") or payload.get("nombre")
        except Exception:
            pass

        # Log to DB (fire and forget, don't block response)
        try:
            self._log_usage(path, request.method, usuario, duration_ms, response.status_code)
        except Exception as e:
            logger.debug(f"Usage tracking error: {e}")

        return response

    def _log_usage(self, path, method, usuario, duration_ms, status_code):
        """Inserta un registro en HUB_ApiUsage."""
        try:
            from api import main as _m
            conn = _m.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO HUB_ApiUsage (App, Endpoint, Metodo, Usuario, Fecha, DuracionMs, StatusCode) "
                "VALUES (%s, %s, %s, %s, GETDATE(), %s, %s)",
                (self.app_name, path[:200], method, usuario, duration_ms, status_code),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"DB log error: {e}")