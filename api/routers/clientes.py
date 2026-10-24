"""api/routers/clientes.py — endpoints de clientes (Fase 2 del refactor)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ClienteCreate(BaseModel):
    id_cliente: str = ""
    nombre: str = ""
    dias_pago: int = 30

class ClienteUpdate(BaseModel):
    nombre: str = ""
    dias_pago: int = 30

def _require_cotiz(*a, **kw):
    from api import main as _m
    return _m._require_cotiz(*a, **kw)


router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


# --- Acceso lazy a helpers de api.main ---
def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)



def _require_cotiz(*a, **kw):
    from api import main as _m
    return getattr(_m, "_require_cotiz")(*a, **kw)

@router.get("/api/clientes")
async def clientes_list(current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # OJO: `_CLIENTES_UNICOS` es una tabla derivada y SQL Server exige un
        # alias (el `C`). Sin él la consulta truena con "Incorrect syntax near
        # the keyword 'ORDER'" y este endpoint devolvía 500 siempre.
        cursor.execute("SELECT IdCliente, Cliente, Dias AS CondicionesPagoDias FROM "
                       + _CLIENTES_UNICOS + " C ORDER BY IdCliente ASC")
        rows = cursor.fetchall()
        conn.close()
        return [{"id_cliente": r[0], "nombre": r[1], "dias_pago": r[2]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/api/clientes")
async def cliente_create(body: ClienteCreate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    idc = (body.id_cliente or "").strip().upper()
    if not idc or not (body.nombre or "").strip():
        raise HTTPException(status_code=400, detail="ID y razón social son obligatorios.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Cliente FROM clientes WHERE IdCliente = %s", (idc,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"El ID {idc} ya está registrado.")
        cursor.execute(
            "INSERT INTO clientes (IdCliente, Cliente, CondicionesPagoDias) VALUES (%s, %s, %s)",
            (idc, body.nombre.strip(), int(body.dias_pago or 0)),
        )
        conn.commit()
        conn.close()
        # Legends: +4 por alta de cliente nuevo (IdCliente es varchar → sin ref int)
        try:
            legends_registrar_metrica(current_user["id"], "cliente_alta")
        except Exception:
            pass
        return {"ok": True, "id_cliente": idc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/clientes/{id_cliente}")
async def cliente_update(id_cliente: str, body: ClienteUpdate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    if not (body.nombre or "").strip():
        raise HTTPException(status_code=400, detail="La razón social no puede estar vacía.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE clientes SET Cliente = %s, CondicionesPagoDias = %s WHERE IdCliente = %s",
            (body.nombre.strip(), int(body.dias_pago or 0), id_cliente.strip().upper()),
        )
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/api/clientes/{id_cliente}")
async def cliente_delete(id_cliente: str, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM clientes WHERE IdCliente = %s", (id_cliente.strip().upper(),))
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=400, detail="No se puede eliminar: tiene cotizaciones asociadas.")
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/clientes/{id_cliente}/nombre")
async def cliente_nombre(id_cliente: str, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Cliente FROM clientes WHERE IdCliente = %s", (id_cliente.strip().upper(),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Cliente no existe.")
        return {"id_cliente": id_cliente.strip().upper(), "nombre": row[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class ContactoRename(BaseModel):
    anterior: str = ""
    nuevo: str = ""


@router.put("/api/clientes/{id_cliente}/contactos")
async def cliente_contacto_rename(id_cliente: str, body: ContactoRename, current_user: dict = Depends(get_current_user)):
    """Renombra un contacto en todas las cotizaciones del cliente (los contactos
    son historial en IndiceMateriales.Contacto, no catálogo: renombrar = UPDATE)."""
    _require_cotiz(current_user)
    anterior = (body.anterior or "").strip()
    nuevo = (body.nuevo or "").strip()
    if not anterior or not nuevo:
        raise HTTPException(status_code=400, detail="Contacto anterior y nuevo son obligatorios.")
    if anterior == nuevo:
        return {"ok": True, "actualizados": 0}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE IndiceMateriales SET Contacto = %s WHERE IdCliente = %s AND Contacto = %s",
            (nuevo, id_cliente.strip().upper(), anterior),
        )
        try:
            n = cursor.rowcount
        except Exception:
            n = 0
        conn.commit()
        conn.close()
        return {"ok": True, "actualizados": int(n or 0)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class ContactoBorrar(BaseModel):
    contacto: str = ""


@router.delete("/api/clientes/{id_cliente}/contactos")
async def cliente_contacto_delete(id_cliente: str, body: ContactoBorrar, current_user: dict = Depends(get_current_user)):
    """Quita un contacto del catálogo HUB_ContactosClientes (decisión de diseño:
    SOLO catálogo — las cotizaciones NO se modifican, conservan su campo Contacto
    y por eso el contacto puede seguir apareciendo en el historial)."""
    _require_cotiz(current_user)
    contacto = (body.contacto or "").strip()
    if not contacto:
        raise HTTPException(status_code=400, detail="El contacto es obligatorio.")
    idc = id_cliente.strip().upper()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # 1) Borrar del catálogo (si la tabla no existe en esta BD → 400 claro)
        try:
            cursor.execute(
                "DELETE FROM HUB_ContactosClientes WHERE IdCliente = %s AND LTRIM(RTRIM(Contacto)) = %s",
                (idc, contacto))
            borrados = cursor.rowcount or 0
        except Exception:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="El catálogo de contactos (HUB_ContactosClientes) no existe en esta base de datos.")
        # 2) Contar cotizaciones que aún usan ese contacto (para el mensaje de la UI)
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM IndiceMateriales WHERE IdCliente = %s AND Contacto = %s",
                (idc, contacto))
            en_cotizaciones = int(cursor.fetchone()[0] or 0)
        except Exception:
            en_cotizaciones = 0
        conn.commit()
        conn.close()
        return {"ok": True, "borrados": int(borrados), "en_cotizaciones": en_cotizaciones}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/clientes/{id_cliente}/contactos")
async def cliente_contactos(id_cliente: str, current_user: dict = Depends(get_current_user)):
    """Contactos del cliente: catálogo HUB_ContactosClientes + historial de
    cotizaciones (mismo UNION que el HUB/Field; si el catálogo no existe en la
    BD, regresa solo el historial)."""
    _require_cotiz(current_user)
    idc = id_cliente.strip().upper()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        rows = _contactos_union(cursor, idc)
        conn.close()
        return [r for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


def _contactos_union(cursor, idc: str):
    """Lista de contactos (catálogo ∪ historial), tolerante a BD sin 0031."""
    try:
        cursor.execute(
            "SELECT Contacto FROM ("
            "  SELECT Contacto FROM HUB_ContactosClientes "
            "  WHERE IdCliente = %s AND Contacto IS NOT NULL AND LTRIM(RTRIM(Contacto)) <> '' "
            "  UNION "
            "  SELECT Contacto FROM IndiceMateriales "
            "  WHERE IdCliente = %s AND Contacto IS NOT NULL AND LTRIM(RTRIM(Contacto)) <> ''"
            ") x ORDER BY Contacto ASC", (idc, idc))
        return [r[0] for r in cursor.fetchall()]
    except Exception:
        cursor.execute(
            "SELECT DISTINCT Contacto FROM IndiceMateriales "
            "WHERE IdCliente = %s AND Contacto IS NOT NULL AND LTRIM(RTRIM(Contacto)) <> '' "
            "ORDER BY Contacto ASC", (idc,))
        return [r[0] for r in cursor.fetchall()]


@router.get("/api/clientes/{id_cliente}/contactos/detalle")
async def cliente_contactos_detalle(id_cliente: str, current_user: dict = Depends(get_current_user)):
    """Detalle de cada contacto con su origen: en_catálogo (borrable con el botón)
    y cuántas cotizaciones lo usan (esas NO se tocan al borrar)."""
    _require_cotiz(current_user)
    idc = id_cliente.strip().upper()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Catálogo (si la tabla no existe → conjunto vacío)
        catalogo = set()
        try:
            cursor.execute(
                "SELECT LTRIM(RTRIM(Contacto)) FROM HUB_ContactosClientes "
                "WHERE IdCliente = %s AND Contacto IS NOT NULL AND LTRIM(RTRIM(Contacto)) <> ''",
                (idc,))
            catalogo = {r[0] for r in cursor.fetchall()}
        except Exception:
            catalogo = set()
        # Historial: contacto → nº de cotizaciones
        try:
            cursor.execute(
                "SELECT LTRIM(RTRIM(Contacto)), COUNT(*) FROM IndiceMateriales "
                "WHERE IdCliente = %s AND Contacto IS NOT NULL AND LTRIM(RTRIM(Contacto)) <> '' "
                "GROUP BY LTRIM(RTRIM(Contacto))", (idc,))
            hist = {r[0]: int(r[1] or 0) for r in cursor.fetchall()}
        except Exception:
            hist = {}
        conn.close()
        nombres = sorted(set(catalogo) | set(hist), key=lambda s: s.lower())
        return [
            {
                "contacto": n,
                "en_catalogo": n in catalogo,
                "n_cotizaciones": hist.get(n, 0),
            }
            for n in nombres
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ----- Sync offline (outbox estilo Field) -----
# Entidades: cotizacion (create/update/delete/nota), partida (add/update/delete).
# Los pendientes locales usan id_local (uuid); el servidor asigna folio real y
# devuelve el mapeo para reescribir partidas del mismo lote.

class SyncItem(BaseModel):
    entity: str = ""
    action: str = ""
    id_local: str = ""
    payload: Dict[str, Any] = {}


class SyncPushRequest(BaseModel):
    items: List[SyncItem] = []


