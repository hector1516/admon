"""api/routers/automoviles.py — gestión de automóviles y asignación a usuarios."""
from fastapi import APIRouter, HTTPException, Depends, Request, Query, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import os, shutil
from api.routers.clientes import _require_cotiz

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


@router.get("/api/automoviles")
async def automoviles_list(current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT a.Id, a.MarcaModelo, a.Placas, a.PolizaSeguro,
                   a.IdUsuarioAsignado, a.UltimoServicioKms,
                   u.Nombre AS UsuarioAsignado, u.Email AS EmailAsignado,
                   i.NombreArchivo AS ImagenArchivo,
                   i.CreatedAt AS ImagenFecha
            FROM HUB_Automoviles a
            LEFT JOIN HUB_Users u ON u.Id = a.IdUsuarioAsignado
            LEFT JOIN HUB_AutomovilImagen i ON i.IdAutomovil = a.Id
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
                "imagen": ("/autos/" + r["ImagenArchivo"] + "?v=" + str(int(r["ImagenFecha"].timestamp()))) if r.get("ImagenArchivo") and r.get("ImagenFecha") else (("/autos/" + r["ImagenArchivo"]) if r.get("ImagenArchivo") else None),
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/automoviles/usuarios")
async def automoviles_usuarios(current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
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
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
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
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
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
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = NULL WHERE IdUsuarioAsignado = %s", (user_id,))
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = %s WHERE Id = %s", (user_id, auto_id))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil asignado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/automoviles/{auto_id}/desasignar")
async def automoviles_desasignar(
    auto_id: int,
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE HUB_Automoviles SET IdUsuarioAsignado = NULL WHERE Id = %s", (auto_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Automóvil desasignado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("/api/automoviles/{auto_id}/imagen")
async def automoviles_subir_imagen(
    auto_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id, MarcaModelo FROM HUB_Automoviles WHERE Id = %s", (auto_id,))
        auto = cursor.fetchone()
        if not auto:
            conn.close()
            raise HTTPException(status_code=404, detail="Automovil no encontrado")

        ext = os.path.splitext(file.filename or "img.png")[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        filename = f"auto_{auto_id}{ext}"
        dest_dir = os.path.join("public", "autos")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)

        # Eliminar imagen anterior si existe
        cursor.execute("SELECT NombreArchivo FROM HUB_AutomovilImagen WHERE IdAutomovil = %s", (auto_id,))
        old = cursor.fetchone()
        if old and old.get("NombreArchivo"):
            old_path = os.path.join(dest_dir, old["NombreArchivo"])
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass
            cursor.execute("DELETE FROM HUB_AutomovilImagen WHERE IdAutomovil = %s", (auto_id,))

        # Guardar nuevo archivo
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Convertir a PNG con fondo transparente si no es PNG
        if ext != ".png":
            from PIL import Image
            img = Image.open(dest_path).convert("RGBA")
            pixels = img.load()
            w, h = img.size
            for x in range(w):
                for y in range(h):
                    r, g, b, a = pixels[x, y]
                    if r > 225 and g > 225 and b > 225:
                        pixels[x, y] = (r, g, b, 0)
            png_name = f"auto_{auto_id}.png"
            png_path = os.path.join(dest_dir, png_name)
            img.save(png_path, "PNG")
            os.remove(dest_path)
            filename = png_name

        # Registrar en BD
        cursor.execute("INSERT INTO HUB_AutomovilImagen (IdAutomovil, NombreArchivo) VALUES (%s, %s)", (auto_id, filename))
        conn.commit()
        conn.close()

        return {"ok": True, "imagen": f"/autos/{filename}", "message": "Imagen subida correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/api/automoviles/{auto_id}/imagen")
async def automoviles_eliminar_imagen(
    auto_id: int,
    current_user: dict = Depends(get_current_user),
):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT NombreArchivo FROM HUB_AutomovilImagen WHERE IdAutomovil = %s", (auto_id,))
        row = cursor.fetchone()
        if row and row.get("NombreArchivo"):
            path = os.path.join("public", "autos", row["NombreArchivo"])
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        cursor.execute("DELETE FROM HUB_AutomovilImagen WHERE IdAutomovil = %s", (auto_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Imagen eliminada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
