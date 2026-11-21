"""api/routers/vales_salud.py - Salud del flujo de vales OxxoGas (admin).

Expone un resumen para diagnosticar rapido por que un vale no se genero:
  - Heartbeat del vales_worker (edad en segundos)
  - Vales APROBADO atascados (> 15 min)
  - Ultimos vales generados / fallidos
  - Saldo Go Vale y fecha de ultimo sync
"""
import os
import time
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


def _require_admin(user):
    if not (user.get("acceso_usuarios") or user.get("AccesoAdminVales") or user.get("acceso_vales_oxxogas")):
        raise HTTPException(status_code=403, detail="Sin permiso")


@router.get("/api/vales/health")
def vales_health(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        # Heartbeat (archivo lo escribe el worker; puede no existir en el host de Admon)
        heartbeat_edad = None
        hb_path = os.getenv("VALES_HEARTBEAT_PATH", "/data/vales_worker_heartbeat")
        try:
            with open(hb_path, "r") as f:
                ts = float((f.read() or "0").strip())
            if ts > 0:
                heartbeat_edad = int(time.time() - ts)
        except Exception:
            heartbeat_edad = None

        # Vales atascados: APROBADO > 15 min
        cur.execute("""
            SELECT Id, IdSolicitante, FechaAprobado,
                   DATEDIFF(MINUTE, FechaAprobado, GETDATE()) AS Minutos
            FROM HUB_SolicitudVales
            WHERE Estatus = 'APROBADO' AND FechaAprobado IS NOT NULL
              AND DATEDIFF(MINUTE, FechaAprobado, GETDATE()) >= 15
            ORDER BY FechaAprobado ASC
        """)
        atascados = cur.fetchall()

        # Ultimos generados
        cur.execute("""
            SELECT TOP 10 Id, IdSolicitante, IdValeGoVale, FechaAprobado, Descripcion
            FROM HUB_SolicitudVales
            WHERE Estatus IN ('GENERADO','CERRADO') AND IdValeGoVale IS NOT NULL
            ORDER BY FechaAprobado DESC
        """)
        ultimos = cur.fetchall()

        # Conteo por estatus
        cur.execute("SELECT Estatus, COUNT(*) AS c FROM HUB_SolicitudVales GROUP BY Estatus")
        conteo = {r["Estatus"]: r["c"] for r in cur.fetchall()}

        # Saldo Go Vale
        cur.execute("SELECT Clave, Valor FROM HUB_Config WHERE Clave IN ('govale_saldo','govale_saldo_fecha','govale_last_sync')")
        cfg = {r["Clave"]: r["Valor"] for r in cur.fetchall()}

        return {
            "worker_heartbeat_seg": heartbeat_edad,
            "worker_ok": (heartbeat_edad is not None and heartbeat_edad < 600),
            "vales_atascados": atascados,
            "vales_atascados_count": len(atascados),
            "ultimos_generados": ultimos,
            "conteo_por_estatus": conteo,
            "govale_saldo": cfg.get("govale_saldo"),
            "govale_saldo_fecha": cfg.get("govale_saldo_fecha"),
            "govale_last_sync": cfg.get("govale_last_sync"),
        }
    finally:
        cur.close()
        conn.close()
