"""api/routers/pdf.py — generación de PDFs (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
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

@router.post("/api/pdf/generate")
async def generate_pdf(current_user: dict = Depends(get_current_user)):
    """Generate PDF for cotización or reporte"""
    if not current_user["acceso_cotizaciones"]:
        raise HTTPException(status_code=403, detail="No access")
    try:
        # This would integrate with the pdf_generator module
        # For now, return a placeholder
        return {"message": "PDF generation endpoint - integrate pdf_generator module"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ===== REPORTES DE SERVICIO (AccesoRegistroReportes / AccesoReportes) =====

class ReporteCreate(BaseModel):
    cliente: str
    contacto: str = ""
    correo_contacto: str = ""
    fecha: str  # YYYY-MM-DD
    tecnico: str
    descripcion: str = ""
    notas: str = ""
    fecha_inicio: str  # HH:MM
    fecha_fin: str  # HH:MM
    tiempo_traslado: float = 0.0
    tiempo_comida: int = 0
    maquina_linea: str = ""
    tecnicos_adicionales: List[str] = []


class ReporteUpdate(BaseModel):
    cliente: str = ""
    contacto: str = ""
    correo_contacto: str = ""
    fecha: str = ""
    tecnico: str = ""
    descripcion: str = ""
    estatus: str = ""
    notas: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""
    tiempo_traslado: float = 0.0
    tiempo_comida: int = 0
    maquina_linea: str = ""
    tecnicos_adicionales: List[str] = []


class ReporteFotosSave(BaseModel):
    fotos: List[str]  # base64 strings


class ReporteTecnicosSave(BaseModel):
    tecnicos: List[str]


class ReporteSignatureSave(BaseModel):
    signature_base64: str


def _require_reporte(current_user: dict):
    if not (current_user.get("acceso_registro_reportes") or current_user.get("acceso_reportes")):
        raise HTTPException(status_code=403, detail="Requiere permiso de Reportes de Servicio")


def _folio_from_id(cur, next_id: int) -> str:
    return f"RS-{str(next_id).zfill(5)}"


