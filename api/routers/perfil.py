"""api/routers/perfil.py — Perfil del usuario (self-service)."""
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional
import sys, os, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

def get_connection():
    from api import main as _m
    return _m.get_connection()

def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)

def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


class PerfilUpdateRequest(BaseModel):
    nombre: str = ""
    email: str = ""
    password_actual: str = ""
    password_nueva: str = ""


@router.get("/api/perfil")
def get_perfil(current_user: dict = Depends(get_current_user)):
    """Datos del perfil del usuario actual."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Id, Nombre, Email, Foto, Puesto, Nickname, AccesoInventario, AccesoNominas, "
        "AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoUsuarios, "
        "AccesoReportes, AccesoRegistroReportes, AccesoIA, AccesoValesOxxoGas, "
        "AccesoRegistroKilometros, AccesoAutomoviles FROM HUB_Users WHERE Id = %s",
        (current_user["id"],),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    permisos = {
        "inventario": bool(row.get("AccesoInventario")),
        "nominas": bool(row.get("AccesoNominas")),
        "cotizaciones": bool(row.get("AccesoCotizaciones")),
        "proveedores": bool(row.get("AccesoProveedores")),
        "oc": bool(row.get("AccesoOC")),
        "calculo": bool(row.get("AccesoCalculo")),
        "usuarios": bool(row.get("AccesoUsuarios")),
        "reportes": bool(row.get("AccesoReportes")),
        "registro_reportes": bool(row.get("AccesoRegistroReportes")),
        "ia": bool(row.get("AccesoIA")),
        "vales_oxxogas": bool(row.get("AccesoValesOxxoGas")),
        "kilometros": bool(row.get("AccesoRegistroKilometros")),
        "automoviles": bool(row.get("AccesoAutomoviles")),
    }

    return {
        "id": row["Id"],
        "nombre": row.get("Nombre", ""),
        "email": row.get("Email", ""),
        "foto": row.get("Foto", "") or "",
        "puesto": row.get("Puesto", "") or "",
        "nickname": row.get("Nickname", "") or "",
        "permisos": permisos,
    }


@router.put("/api/perfil")
def update_perfil(body: PerfilUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Actualiza nombre y email del usuario (no permisos)."""
    if not body.nombre.strip() or not body.email.strip():
        raise HTTPException(status_code=400, detail="Nombre y email son obligatorios.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE HUB_Users SET Nombre = %s, Email = %s WHERE Id = %s",
        (body.nombre.strip(), body.email.strip().lower(), current_user["id"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "nombre": body.nombre.strip(), "email": body.email.strip().lower()}


@router.put("/api/perfil/password")
def update_password(body: PerfilUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Cambia la contraseña del usuario."""
    if not body.password_actual or not body.password_nueva:
        raise HTTPException(status_code=400, detail="Contraseña actual y nueva son obligatorias.")
    if len(body.password_nueva) < 6:
        raise HTTPException(status_code=400, detail="La contraseña nueva debe tener al menos 6 caracteres.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT Password FROM HUB_Users WHERE Id = %s", (current_user["id"],))
    row = cur.fetchone()
    if not row or row[0] != body.password_actual:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta.")

    cur.execute("UPDATE HUB_Users SET Password = %s WHERE Id = %s", (body.password_nueva, current_user["id"]))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@router.put("/api/perfil/foto")
async def update_foto(foto: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Actualiza la foto de perfil del usuario."""
    try:
        contents = await foto.read()
        # Convertir a base64 data URI
        mime = foto.content_type or "image/jpeg"
        b64 = base64.b64encode(contents).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE HUB_Users SET Foto = %s WHERE Id = %s", (data_uri, current_user["id"]))
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "foto": data_uri}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir foto: {str(e)}")