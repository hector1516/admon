"""El middleware de uso no debe bloquear el event loop (Fase B) — Admon.

`_log_usage` abre conexión y hace INSERT: si se llama directo desde `dispatch`
(async), bloquea el servidor entero mientras dura. Con 1 vCPU eso se ve como
"todas las peticiones van lentas a la vez".
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from usage_tracker import UsageTrackingMiddleware  # noqa: E402


class FakeURL:
    path = "/api/reportes"


class FakeRequest:
    url = FakeURL()
    method = "GET"
    headers = {}


class FakeResponse:
    status_code = 200


async def call_next(_request):
    return FakeResponse()


def test_dispatch_no_bloquea_el_event_loop():
    middleware = UsageTrackingMiddleware(app=None)
    registros = []

    def log_lento(*args):
        time.sleep(0.20)  # simula la ida y vuelta a la BD
        registros.append(args)

    middleware._log_usage = log_lento

    async def correr_dos():
        inicio = time.monotonic()
        await asyncio.gather(
            middleware.dispatch(FakeRequest(), call_next),
            middleware.dispatch(FakeRequest(), call_next),
        )
        return time.monotonic() - inicio

    transcurrido = asyncio.run(correr_dos())

    assert len(registros) == 2
    # Si bloqueara el loop serían ~0.40 s (uno tras otro); en paralelo ~0.20 s.
    assert transcurrido < 0.35, f"el dispatch bloqueó el event loop: {transcurrido:.2f}s"
