"""api/routers/core.py — endpoints de salud y metadata de la app.

Fase 1 del refactor de main.py: se extraen los endpoints más simples y
autocontenidos. El resto se moverá en fases posteriores.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api")
def api_info():
    return {"message": "HUB Admon API", "version": "1.0.0"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/health")
def api_health():
    return {"status": "ok"}