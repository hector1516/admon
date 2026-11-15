"""api/routers/debug.py — Sistema de debugging con códigos de error únicos."""
from fastapi import APIRouter, HTTPException, Depends
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


class DebugLogRequest(BaseModel):
    codigo: str
    app: str = "ADM"
    modulo: str = ""
    mensaje: str
    contexto: Optional[Dict[str, Any]] = None
    url: Optional[str] = None


@router.post("/api/debug/log")
def log_debug(body: DebugLogRequest, current_user: dict = Depends(get_current_user)):
    """Registra un error de debug en la bitácora."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO HUB_DebugLog (Codigo, App, Modulo, Mensaje, Contexto, Url, Usuario, Fecha) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, GETDATE())",
            (body.codigo[:30], body.app[:10], body.modulo[:10], body.mensaje[:500],
             json.dumps(body.contexto) if body.contexto else None,
             (body.url or "")[:500], current_user.get("email", "")),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


@router.get("/api/debug/log")
def get_debug_log(
    codigo: Optional[str] = None,
    app: Optional[str] = None,
    modulo: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Consulta el log de debug (solo admin)."""
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    conditions = ["1=1"]
    params = []
    if codigo:
        conditions.append("Codigo LIKE %s")
        params.append(f"%{codigo}%")
    if app:
        conditions.append("App = %s")
        params.append(app)
    if modulo:
        conditions.append("Modulo = %s")
        params.append(modulo)
    where = " AND ".join(conditions)
    cur.execute(
        f"SELECT TOP ({limit}) Id, Codigo, App, Modulo, Mensaje, Contexto, Url, Usuario, Fecha "
        f"FROM HUB_DebugLog WHERE {where} ORDER BY Fecha DESC",
        tuple(params),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r["Id"],
            "codigo": r["Codigo"],
            "app": r["App"],
            "modulo": r["Modulo"],
            "mensaje": r["Mensaje"],
            "contexto": r["Contexto"],
            "url": r["Url"],
            "usuario": r["Usuario"],
            "fecha": r["Fecha"].strftime("%Y-%m-%d %H:%M:%S") if r.get("Fecha") else "",
        }
        for r in rows
    ]