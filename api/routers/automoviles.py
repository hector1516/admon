"""api/routers/automoviles.py — gestión de automóviles y asignación a usuarios."""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from typing import Optional
from api.routers.passkeys import _require_cotiz

router = APIRouter()


def get_connection():
    from api import main as _m
    return _m.get_connection()


@router.get("/api/automoviles")
async def automoviles_list(current_user: dict = Depends(_require_cotiz)):
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT a.Id, a.MarcaModelo, a.Placas, a.PolizaSeguro,
                   a.IdUsuarioAsignado, a.UltimoServicioKms,
                   u.Nombre AS UsuarioAsignado, u.Email AS EmailAsignado
            FROM HUB_Automoviles a
            LEFT JOIN HUB_Users u ON u.Id = a.IdUsuarioAsignado
            ORDER BY a.Id ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r["Id"],
                "marca_modelo": r["MarcaModelo"] or "",
                "placas": r["Placas"] or "",
                "poliza_seguro": r["PolizaSeguro"] or "",
                "id_usuario_asignado": r["IdUsuarioAsignado"],
                "usuario_asignado": r["UsuarioAsignado"] or "",
                "email_asignado": r["EmailAsignado"] or "",
                "ultimo_servicio_kms": r["UltimoServicioKms"] or 0,
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/automoviles/usuarios")
async def automoviles_usuarios(current_user: dict = Depends(_require_cotiz)):
    """Lista de usuarios activos para asignación."""
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id, Nombre, Email FROM HUB_Users WHERE Activo = 1 ORDER BY Nombre ASC")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r["Id"], "nombre": r["Nombre"] or "", "email": r["Email"] or ""} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/api/automoviles")
async def automoviles_create(
    marca_modelo: str = Query(...),
    placas: str = Query(...),
    poliza_seguro: Optional[str] = Query(None),
    ultimo_servicio_kms: int = Query(0),
    current_user: dict = Depends(_require_cotiz),
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO HUB_Automoviles (MarcaModelo, Placas, PolizaSeguro, UltimoServicioKms) VALUES (%s, %s, %s, %s)",
            (marca_modelo, placas, poliza_seguro, ultimo_servicio_kms),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil agregado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/automoviles/{auto_id}")
async def automoviles_update(
    auto_id: int,
    marca_modelo: Optional[str] = Query(None),
    placas: Optional[str] = Query(None),
    poliza_seguro: Optional[str] = Query(None),
    ultimo_servicio_kms: Optional[int] = Query(None),
    current_user: dict = Depends(_require_cotiz),
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sets = []
        params = []
        if marca_modelo is not None:
            sets.append("MarcaModelo = %s")
            params.append(marca_modelo)
        if placas is not None:
            sets.append("Placas = %s")
            params.append(placas)
        if poliza_seguro is not None:
            sets.append("PolizaSeguro = %s")
            params.append(poliza_seguro)
        if ultimo_servicio_kms is not None:
            sets.append("UltimoServicioKms = %s")
            params.append(ultimo_servicio_kms)
        if not sets:
            conn.close()
            return {"ok": True, "message": "Sin cambios"}
        params.append(auto_id)
        cursor.execute("UPDATE HUB_Automoviles SET " + ", ".join(sets) + " WHERE Id = %s", tuple(params))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil actualizado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/automoviles/{auto_id}/asignar/{user_id}")
async def automoviles_asignar(
    auto_id: int,
    user_id: int,
    current_user: dict = Depends(_require_cotiz),
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Desasignar cualquier auto previo del usuario
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = NULL WHERE IdUsuarioAsignado = %s", (user_id,))
        # Asignar el nuevo
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = %s WHERE Id = %s", (user_id, auto_id))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil asignado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/automoviles/{auto_id}/desasignar")
async def automoviles_desasignar(
    auto_id: int,
    current_user: dict = Depends(_require_cotiz),
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = NULL WHERE Id = %s", (auto_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil desasignado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")