"""api/routers/audit.py — Bitácora de actividad (audit trail)."""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

router = APIRouter()

def get_connection():
    from api import main as _m
    return _m.get_connection()

from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)

def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


class AuditLogRequest(BaseModel):
    app: str = "ADM"
    modulo: str = ""
    tipo_accion: str = "click"  # click, navigate, insert, update, delete, error, login, logout, view
    accion: str
    detalle: Optional[str] = None
    datos: Optional[Dict[str, Any]] = None
    duracion_ms: Optional[int] = None


@router.post("/api/audit/log")
def log_action(body: AuditLogRequest, current_user: dict = Depends(get_current_user)):
    """Registra una acción del usuario en la bitácora."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO HUB_ActivityLog (FechaHora, Usuario, Modulo, Accion, App, UsuarioId, "
            "TipoAccion, Detalle, Datos, Dispositivo, IpAddress, DuracionMs) "
            "VALUES (GETDATE(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (current_user.get("email", ""), body.modulo[:10], body.accion[:500], body.app[:10],
             current_user.get("id"), body.tipo_accion[:20], (body.detalle or "")[:500],
             json.dumps(body.datos) if body.datos else None, "", "", body.duracion_ms),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


@router.get("/api/audit/log")
def get_audit_log(
    usuario: Optional[str] = None,
    modulo: Optional[str] = None,
    tipo: Optional[str] = None,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Consulta la bitácora (solo admin)."""
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    conditions = ["1=1"]
    params = []
    if usuario:
        conditions.append("Usuario LIKE %s")
        params.append(f"%{usuario}%")
    if modulo:
        conditions.append("Modulo = %s")
        params.append(modulo)
    if tipo:
        conditions.append("TipoAccion = %s")
        params.append(tipo)
    if desde:
        conditions.append("FechaHora >= %s")
        params.append(desde)
    if hasta:
        conditions.append("FechaHora <= %s")
        params.append(hasta)
    where = " AND ".join(conditions)
    cur.execute(
        f"SELECT TOP ({limit}) Id, FechaHora, Usuario, Modulo, Accion, App, TipoAccion, "
        f"Detalle, Datos, DuracionMs FROM HUB_ActivityLog WHERE {where} ORDER BY FechaHora DESC",
        tuple(params),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r["Id"],
            "fecha": r["FechaHora"].strftime("%Y-%m-%d %H:%M:%S") if r.get("FechaHora") else "",
            "usuario": r["Usuario"],
            "modulo": r["Modulo"],
            "accion": r["Accion"],
            "app": r["App"],
            "tipo": r["TipoAccion"],
            "detalle": r["Detalle"],
            "datos": r["Datos"],
            "duracion_ms": r["DuracionMs"],
        }
        for r in rows
    ]


@router.delete("/api/audit/log/clean")
def clean_audit_log(dias: int = 30, current_user: dict = Depends(get_current_user)):
    """Limpia registros antiguos (solo admin)."""
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM HUB_ActivityLog WHERE FechaHora < DATEADD(day, -%s, GETDATE())", (dias,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "deleted": deleted}