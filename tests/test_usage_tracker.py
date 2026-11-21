"""El middleware de uso no debe costar latencia en la respuesta (Fase B) — Admon.

`HUB_ApiUsage` medía 16-216 ms por INSERT (25k filas, 3 índices, 1 vCPU). Si el
INSERT se espera en `dispatch`, cada petición paga ese tiempo. Con una cola y un
escritor en segundo plano que agrupa filas, la respuesta sale sin esperar y la
BD recibe un INSERT múltiple en vez de 25.
"""
import asyncio
import os
import queue
import sys
import threading
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


def test_dispatch_no_espera_al_insert():
    middleware = UsageTrackingMiddleware(app=None)
    insertado = threading.Event()

    def insert_lento(_lote):
        time.sleep(0.25)
        insertado.set()

    middleware._insertar_lote = insert_lento

    async def correr():
        inicio = time.monotonic()
        await asyncio.gather(
            *(middleware.dispatch(FakeRequest(), call_next) for _ in range(5))
        )
        return time.monotonic() - inicio

    transcurrido = asyncio.run(correr())

    # El dispatch no espera al INSERT: 5 peticiones deben salir casi al instante.
    assert transcurrido < 0.10, f"dispatch esperó al INSERT: {transcurrido:.2f}s"
    assert insertado.wait(timeout=2), "el escritor nunca procesó el lote"


def test_agrupa_los_inserts():
    middleware = UsageTrackingMiddleware(app=None)
    lotes = []
    listo = threading.Event()

    def insertar(lote):
        lotes.append(list(lote))
        if sum(len(l) for l in lotes) >= 20:
            listo.set()

    middleware._insertar_lote = insertar

    for _ in range(20):
        middleware._encolar("/api/x", "GET", "it", 1, 200)

    assert listo.wait(timeout=3), "no se procesaron los 20 registros"
    assert sum(len(l) for l in lotes) == 20
    assert len(lotes) < 20, f"no agrupó: {len(lotes)} INSERTs para 20 filas"


def test_cola_llena_descarta_sin_romper():
    middleware = UsageTrackingMiddleware(app=None)
    middleware._cola = queue.Queue(maxsize=2)
    middleware._insertar_lote = lambda _lote: time.sleep(2)

    for _ in range(10):
        middleware._encolar("/api/x", "GET", "it", 1, 200)  # no debe lanzar


def test_una_fila_mala_no_tira_el_lote():
    """Un solo registro inválido no debe perder las otras 19 filas del lote."""
    middleware = UsageTrackingMiddleware(app=None)
    guardadas = []

    def insertar(lote):
        if any(fila[0] == "/api/malo" for fila in lote):
            raise ValueError("fila mala")
        guardadas.extend(lote)

    middleware._insertar_lote = insertar
    middleware._escribir([
        ("/api/ok1", "GET", "it", 1, 200),
        ("/api/malo", "GET", "it", 1, 200),
        ("/api/ok2", "GET", "it", 1, 200),
    ])

    assert [f[0] for f in guardadas] == ["/api/ok1", "/api/ok2"]
