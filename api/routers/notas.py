"""api/routers/notas.py — endpoints de notas (Fase 4 del refactor)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List

COLOR_NOTA_DEFECTO = "#F59E0B"

class NotaCrear(BaseModel):
    titulo: str
    contenido: str
    color: str = COLOR_NOTA_DEFECTO
    fija: bool = False

class NotaActualizar(BaseModel):
    titulo: str
    contenido: str
    color: str = COLOR_NOTA_DEFECTO
    fija: bool = False

router = APIRouter()


def get_connection():
    from api import main as _m
    return _m.get_connection()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


def _color_nota(valor) -> str:
    """Solo #RRGGBB o #RGB; cualquier otra cosa cae al ámbar del kiosco."""
    s = str(valor or "").strip()
    if s.startswith("#"):
        hexa = s[1:]
        if all(c in "0123456789abcdefABCDEF" for c in hexa) and len(hexa) in (3, 6):
            return s
    return COLOR_NOTA_DEFECTO

def _nota_desde_row(r: dict) -> dict:
    """Normaliza una fila de HUB_DashboardNotas al JSON que consume el front."""
    return {
        "id": int(r["Id"]),
        "titulo": r["Titulo"],
        "contenido": r["Contenido"] or "",
        "color": r["Color"] or COLOR_NOTA_DEFECTO,
        "autor": r["Autor"] or "—",
        "fija": bool(r["Fija"]),
        "fecha_creacion": r["FechaCreacion"].isoformat() if r["FechaCreacion"] else None,
        "fecha_modificado": r["FechaModificado"].isoformat() if r["FechaModificado"] else None,
    }

@router.get("/api/notas")
async def notas_listar(current_user: dict = Depends(get_current_user)):
    """Notas del tablero, en el mismo orden que las ve el kiosco (fijas primero)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas
            ORDER BY ISNULL(Fija, 0) DESC,
                     ISNULL(FechaModificado, FechaCreacion) DESC,
                     Id DESC
        """)
        return [_nota_desde_row(r) for r in cursor.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@router.post("/api/notas")
async def notas_crear(body: NotaCrear, current_user: dict = Depends(get_current_user)):
    """Crea una nota; el autor es el usuario logueado."""
    titulo = (body.titulo or "").strip()
    contenido = (body.contenido or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío.")
    if not contenido:
        raise HTTPException(status_code=400, detail="El contenido no puede estar vacío.")
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            INSERT INTO HUB_DashboardNotas
                (Titulo, Contenido, Color, Autor, Fija, FechaCreacion, FechaModificado)
            VALUES (%s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (titulo[:200], contenido, _color_nota(body.color),
              str(current_user.get("nombre") or "")[:100], 1 if body.fija else 0))
        conn.commit()
        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        nuevo_id = int(cursor.fetchone()["id"])
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas WHERE Id = %s
        """, (nuevo_id,))
        return _nota_desde_row(cursor.fetchone())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@router.put("/api/notas/{id_nota:int}")
async def notas_editar(id_nota: int, body: NotaActualizar,
                       current_user: dict = Depends(get_current_user)):
    """Edita la nota; actualiza FechaModificado (sube en el orden del kiosco)."""
    titulo = (body.titulo or "").strip()
    contenido = (body.contenido or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío.")
    if not contenido:
        raise HTTPException(status_code=400, detail="El contenido no puede estar vacío.")
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id FROM HUB_DashboardNotas WHERE Id = %s", (id_nota,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La nota no existe.")
        cursor.execute("""
            UPDATE HUB_DashboardNotas
            SET Titulo = %s, Contenido = %s, Color = %s, Fija = %s,
                FechaModificado = GETDATE()
            WHERE Id = %s
        """, (titulo[:200], contenido, _color_nota(body.color),
              1 if body.fija else 0, id_nota))
        conn.commit()
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas WHERE Id = %s
        """, (id_nota,))
        return _nota_desde_row(cursor.fetchone())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@router.delete("/api/notas/{id_nota:int}")
async def notas_borrar(id_nota: int, current_user: dict = Depends(get_current_user)):
    """Borra una nota (desaparece de la pantalla del kiosco)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM HUB_DashboardNotas WHERE Id = %s", (id_nota,))
        if cursor.rowcount == 0:
            conn.commit()
            raise HTTPException(status_code=404, detail="La nota no existe.")
        conn.commit()
        return {"ok": True, "id": id_nota}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()

# --- Pestaña "Pantalla de la TV" (módulo Notas del Dashboard) ---
# Imagen de portada + control remoto del kiosco. La lógica de la imagen vive
# en api/notas_pantalla.py (tabla HUB_PantallaImagenes) y el control remoto
# habla con el panel del snapshotter: GET /api/panel/estado sin token,
# POST /api/panel/comando CON token (HUB_PANEL_TOKEN).
# Sin permiso propio, igual que Notas: para todos los logueados.
import json as _json
import urllib.request as _urlreq
import urllib.error as _urlerr
from api import notas_pantalla as _pantalla


def _serializable(fila):
    """pymssql → JSON: datetime a ISO y las claves en snake_case (Id → id)."""
    if fila is None:
        return None
    out = {}
    for k, v in fila.items():
        v = v.isoformat() if hasattr(v, "isoformat") else v
        out[k.lower()] = v
    return out


def _panel_estado() -> dict:
    """Estado del kiosco: pantallas publicadas por la TV + último comando.

    No pide token. Si el snapshotter está caído devuelve el error en vez de
    reventar la vista, que para eso está el try/except en el endpoint.
    """
    url = f"{_pantalla.PANEL_URL}/api/panel/estado"
    try:
        with _urlreq.urlopen(url, timeout=5) as r:
            return _json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"No se pudo leer el estado de la pantalla: {e}"}


def _panel_comando(accion: str, pantalla: str = None) -> dict:
    """Manda un comando al kiosco (ver | avanzar | pausa | seguir).

    Exige el token compartido: sin él el panel responde 403 a propósito
    (escribir en la TV necesita credencial). NUNCA se manda en blanco.
    """
    if not _pantalla.PANEL_TOKEN:
        return {"ok": False, "error": "Falta HUB_PANEL_TOKEN en el servidor; el control remoto queda deshabilitado."}
    cuerpo = {"accion": accion}
    if pantalla:
        cuerpo["pantalla"] = pantalla
    req = _urlreq.Request(
        f"{_pantalla.PANEL_URL}/api/panel/comando",
        data=_json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Panel-Token": _pantalla.PANEL_TOKEN},
        method="POST",
    )
    try:
        with _urlreq.urlopen(req, timeout=5) as r:
            return _json.loads(r.read().decode("utf-8"))
    except _urlerr.HTTPError as e:
        # El cuerpo trae {"ok": false, "error": "..."}: se reenvía tal cual
        # para que la UI lo muestre en vez de tragárselo.
        try:
            return _json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"El panel rechazó el comando (HTTP {e.code})."}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo hablar con la pantalla: {e}"}


