"""api/routers/pantalla.py — endpoints de pantalla/portada (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from api import notas_pantalla as _pantalla
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List

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

import json as _json
import urllib.request as _urlreq
import urllib.error as _urlerr

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

def _serializable(fila):
    """pymssql → JSON: datetime a ISO y las claves en snake_case (Id → id)."""
    if fila is None:
        return None
    out = {}
    for k, v in fila.items():
        v = v.isoformat() if hasattr(v, "isoformat") else v
        out[k.lower()] = v
    return out

@router.get("/api/pantalla/estado")
async def pantalla_estado(current_user: dict = Depends(get_current_user)):
    """Estado del kiosco: si la TV está conectada, qué pantallas hay y qué
    commanders le mandaron por última vez (con su confirmación)."""
    return _panel_estado()


class PanelComandoRequest(BaseModel):
    accion: str
    pantalla: str = ""


@router.post("/api/pantalla/comando")
async def pantalla_comando(body: PanelComandoRequest, current_user: dict = Depends(get_current_user)):
    """Control remoto del kiosco: ver una pantalla, avanzar, pausar o seguir.

    La TV consulta cada 3 s: el cambio se ve en pantalla en ~3 s, no al
    instante. Por eso la UI muestra "enviado" y luego el "confirmado".
    """
    accion = (body.accion or "").strip().lower()
    if accion not in ("ver", "avanzar", "pausa", "seguir"):
        raise HTTPException(status_code=400, detail="Acción inválida: ver, avanzar, pausa o seguir.")
    if accion == "ver" and not (body.pantalla or "").strip():
        raise HTTPException(status_code=400, detail="Indica qué pantalla quieres ver.")
    return _panel_comando(accion, (body.pantalla or "").strip() or None)


class ImagenPantallaRequest(BaseModel):
    contenido_base64: str
    content_type: str = "image/jpeg"
    titulo: str = ""


@router.get("/api/pantalla/portada")
def pantalla_portada_actual(current_user: dict = Depends(get_current_user)):
    """La portada que está en pantalla ahora (metadatos + base64 para
    previsualizarla) más el historial para poder volver a una anterior."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, Titulo, ContentType, Ancho, Alto, FechaSubida
            FROM HUB_PantallaImagenes
            WHERE Clave = %s AND Activo = 1 ORDER BY Id DESC
        """, (_pantalla.CLAVE_PORTADA,))
        activa = cursor.fetchone()
        if activa:
            cursor.execute("SELECT Archivo FROM HUB_PantallaImagenes WHERE Id = %s", (activa["Id"],))
            b = cursor.fetchone()["Archivo"]
            activa["base64"] = base64.b64encode(bytes(b)).decode("ascii") if b else None
    finally:
        conn.close()
    historial = _pantalla.listar_imagenes_pantalla(get_connection)
    return {
        "activa": _serializable(activa),
        "historial": [_serializable(h) for h in historial],
    }


@router.post("/api/pantalla/portada")
async def pantalla_subir_portada(body: ImagenPantallaRequest,
                                 current_user: dict = Depends(get_current_user)):
    """Sube la imagen de portada. No va por HTTP al kiosco: se guarda en
    HUB_PantallaImagenes y la TV la toma en su próxima vuelta."""
    try:
        contenido = base64.b64decode(body.contenido_base64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen (base64 inválido).")
    r = _pantalla.guardar_imagen_pantalla(
        get_connection, contenido, body.content_type,
        titulo=body.titulo, id_usuario=int(current_user["id"]),
    )
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo guardar la imagen.")
    r["mensaje"] = "Subida. La TV la toma en su próxima vuelta."
    return r


@router.post("/api/pantalla/portada/{id_imagen:int}/restaurar")
async def pantalla_restaurar_portada(id_imagen: int, current_user: dict = Depends(get_current_user)):
    """Vuelve a poner en pantalla una portada anterior sin resubirla."""
    r = _pantalla.restaurar_imagen_pantalla(get_connection, id_imagen)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo restaurar.")
    return r


@router.delete("/api/pantalla/portada/{id_imagen:int}")
async def pantalla_borrar_portada(id_imagen: int, current_user: dict = Depends(get_current_user)):
    """Borra una portada del historial (la que está en pantalla no se puede)."""
    r = _pantalla.borrar_imagen_pantalla(get_connection, id_imagen)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo borrar.")
    return r
