"""api/routers/dashboard.py — KPIs del dashboard (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List

router = APIRouter()

def get_connection():
    from api import main as _m
    return _m.get_connection()

def get_current_user(token: str = Depends(lambda: None)):
    from api import main as _m
    return _m.get_current_user(token)

def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)

@router.get("/api/dashboard/kpis")
async def get_dashboard_kpis(current_user: dict = Depends(get_current_user)):
    """Get KPIs filtered by user permissions"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        kpis = []
        
        # Inventory KPI
        if current_user["acceso_inventario"]:
            cursor.execute("SELECT COUNT(*) FROM HUB_Inventario WHERE Cantidad <= StockMinimo")
            row = cursor.fetchone()
            kpis.append({"modulo": "inventario", "valor": row[0] if row else 0, "etiqueta": "Items con stock bajo"})
        
        # Cotizaciones KPI (la vista trae Estatus como texto; IndiceMateriales no tiene esa columna)
        if current_user["acceso_cotizaciones"]:
            cursor.execute("SELECT COUNT(*) FROM vw_ResumenCotizaciones WHERE Estatus LIKE '%PENDIENTE%'")
            row = cursor.fetchone()
            kpis.append({"modulo": "cotizaciones", "valor": row[0] if row else 0, "etiqueta": "Cotizaciones pendientes"})
        
        # Users count
        cursor.execute("SELECT COUNT(*) FROM HUB_Users WHERE Activo = 1")
        row = cursor.fetchone()
        kpis.append({"modulo": "usuarios", "valor": row[0] if row else 0, "etiqueta": "Usuarios activos"})
        
        conn.close()
        return {"kpis": kpis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- PDF generation endpoint (placeholder) ---

