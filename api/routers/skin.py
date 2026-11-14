"""api/routers/skin.py — Selector de skin/apariencia."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import sys, os
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


SKINS = [
    {"id": "default", "nombre": "Clasico", "descripcion": "Diseno original sin barra inferior"},
    {"id": "ingram", "nombre": "Moderno", "descripcion": "Bottom nav + banner con URL clickeable"},
]


@router.get("/api/skin")
def get_skin(current_user: dict = Depends(get_current_user)):
    """Devuelve el skin activo y la lista de skins disponibles."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT Valor FROM HUB_Config WHERE Clave = 'active_skin'")
    row = cur.fetchone()
    cur.close()
    conn.close()
    activo = row["Valor"] if row and row.get("Valor") else "default"
    return {"activo": activo, "skins": SKINS}


@router.put("/api/skin")
def set_skin(body: dict, current_user: dict = Depends(get_current_user)):
    """Cambia el skin activo (solo admin)."""
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden cambiar el skin.")

    skin_id = body.get("skin", "")
    if skin_id not in [s["id"] for s in SKINS]:
        raise HTTPException(status_code=400, detail="Skin no valido.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "MERGE HUB_Config AS target USING (SELECT %s AS Clave) AS source ON target.Clave = source.Clave "
        "WHEN MATCHED THEN UPDATE SET Valor = %s, Actualizado = GETDATE() "
        "WHEN NOT MATCHED THEN INSERT (Clave, Valor, Actualizado) VALUES (%s, %s, GETDATE());",
        ("active_skin", skin_id, "active_skin", skin_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "skin": skin_id}