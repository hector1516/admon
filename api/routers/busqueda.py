"""api/routers/busqueda.py — Búsqueda global en módulos de Admon."""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
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


@router.get("/api/busqueda-global")
def busqueda_global(
    q: str = Query("", min_length=0, max_length=200),
    current_user: dict = Depends(get_current_user),
):
    """Búsqueda global en módulos de Admon según permisos del usuario."""
    if not q.strip():
        return {"resultados": [], "total": 0}

    patron = f"%{q.strip()}%"
    resultados = []

    conn = get_connection()
    cur = conn.cursor(as_dict=True)

    # Cotizaciones
    if current_user.get("acceso_cotizaciones"):
        try:
            cur.execute(
                "SELECT TOP 10 Folio, Cliente, Descripcion, Fecha, Estatus "
                "FROM Cotizaciones WHERE Folio LIKE %s OR Cliente LIKE %s OR Descripcion LIKE %s "
                "ORDER BY Fecha DESC",
                (patron, patron, patron),
            )
            for r in cur.fetchall():
                resultados.append({
                    "tipo": "cotizacion",
                    "titulo": f"Cotización #{r.get('Folio', '')}",
                    "descripcion": r.get("Descripcion", "") or r.get("Cliente", ""),
                    "fecha": str(r.get("Fecha", ""))[:10],
                    "url": f"/cotizaciones/{r.get('Folio', '')}",
                })
        except Exception:
            pass

    # Clientes
    if current_user.get("acceso_cotizaciones"):
        try:
            cur.execute(
                "SELECT TOP 10 IdCliente, Cliente FROM Clientes "
                "WHERE IdCliente LIKE %s OR Cliente LIKE %s",
                (patron, patron),
            )
            for r in cur.fetchall():
                resultados.append({
                    "tipo": "cliente",
                    "titulo": r.get("Cliente", "") or r.get("IdCliente", ""),
                    "descripcion": f"ID: {r.get('IdCliente', '')}",
                    "fecha": "",
                    "url": f"/clientes/{r.get('IdCliente', '')}",
                })
        except Exception:
            pass

    # Reportes
    if current_user.get("acceso_reportes"):
        try:
            cur.execute(
                "SELECT TOP 10 IdReporte, Folio, Descripcion FROM ReportesServicio "
                "WHERE Folio LIKE %s OR Descripcion LIKE %s",
                (patron, patron),
            )
            for r in cur.fetchall():
                resultados.append({
                    "tipo": "reporte",
                    "titulo": f"Reporte {r.get('Folio', '')}",
                    "descripcion": (r.get("Descripcion", "") or "")[:80],
                    "fecha": "",
                    "url": f"/reporte_detalle/{r.get('IdReporte', '')}",
                })
        except Exception:
            pass

    # Tickets OxxoGas
    if current_user.get("acceso_vales_oxxogas"):
        try:
            cur.execute(
                "SELECT TOP 10 Id, Folio, Estacion FROM HUB_OxxoGasTickets "
                "WHERE Folio LIKE %s OR Estacion LIKE %s",
                (patron, patron),
            )
            for r in cur.fetchall():
                resultados.append({
                    "tipo": "ticket",
                    "titulo": f"Ticket {r.get('Folio', '')}",
                    "descripcion": r.get("Estacion", "") or "",
                    "fecha": "",
                    "url": f"/tickets_oxxogas",
                })
        except Exception:
            pass

    # Usuarios
    if current_user.get("acceso_usuarios"):
        try:
            cur.execute(
                "SELECT TOP 10 Id, Nombre, Email FROM HUB_Users "
                "WHERE Nombre LIKE %s OR Email LIKE %s",
                (patron, patron),
            )
            for r in cur.fetchall():
                resultados.append({
                    "tipo": "usuario",
                    "titulo": r.get("Nombre", ""),
                    "descripcion": r.get("Email", ""),
                    "fecha": "",
                    "url": f"/usuarios",
                })
        except Exception:
            pass

    cur.close()
    conn.close()

    return {"resultados": resultados, "total": len(resultados)}