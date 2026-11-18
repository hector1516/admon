"""api/routers/mi_asistencia.py - Modulo Mi Asistencia (self-service)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time, timedelta
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tz_mx import now_mx

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


class MarcarReq(BaseModel):
    tipo: str  # 'Entrada' o 'Salida'
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    precision: Optional[int] = None
    verificacion_facial: bool = False
    id_foto_verificacion: Optional[int] = None
    passkey_credential_id: Optional[str] = None
    dispositivo: Optional[str] = None

class GenerarReporteReq(BaseModel):
    periodo_inicio: str  # YYYY-MM-DD
    periodo_fin: str     # YYYY-MM-DD
    notas: Optional[str] = None


@router.post("/api/mi-asistencia/marcar")
def marcar_asistencia(req: MarcarReq, current_user: dict = Depends(get_current_user)):
    """Marca entrada o salida del empleado (self-service)."""
    if req.tipo not in ('Entrada', 'Salida'):
        raise HTTPException(status_code=400, detail="Tipo debe ser 'Entrada' o 'Salida'")
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    ahora = now_mx()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO HUB_AsistenciaMarcado
            (IdUsuario, Fecha, Tipo, Hora, Latitud, Longitud, Precision,
             VerificacionFacial, IdFotoVerificacion, PasskeyCredentialId,
             Dispositivo, FechaRegistro, Estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, ahora.date(), req.tipo, ahora.time(),
              req.latitud, req.longitud, req.precision,
              1 if req.verificacion_facial else 0, req.id_foto_verificacion,
              req.passkey_credential_id, req.dispositivo, ahora, 'Valido'))
        conn.commit()
        return {"ok": True, "tipo": req.tipo, "fecha": str(ahora.date()),
                "hora": str(ahora.time()), "mensaje": f"{req.tipo} registrada correctamente"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/mi-asistencia/historial")
def historial_asistencia(dias: int = 30, current_user: dict = Depends(get_current_user)):
    """Historial de marcados del empleado."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("""
            SELECT Id, Fecha, Tipo, Hora, Latitud, Longitud, Precision,
                   VerificacionFacial, Dispositivo, Estado, FechaRegistro
            FROM HUB_AsistenciaMarcado
            WHERE IdUsuario = %s
              AND Fecha >= DATEADD(day, -%s, GETDATE())
            ORDER BY Fecha DESC, Hora DESC
        """, (user_id, dias))
        rows = cur.fetchall()
        return {"registros": rows, "total": len(rows)}
    finally:
        cur.close()
        conn.close()


@router.get("/api/mi-asistencia/horas-extras")
def horas_extras_pendientes(current_user: dict = Depends(get_current_user)):
    """Horas extras acumuladas (pendientes de reporte) del empleado."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("""
            SELECT Id, Fecha, HoraEntrada, HoraSalida, HorasComida, HorasTraslado,
                   HorasExtrasCalculadas, Descripcion, Cliente, Calificacion, Estatus
            FROM HUB_HorasExtrasRegistros
            WHERE IdUsuario = %s AND Estatus = 'Pendiente'
            ORDER BY Fecha ASC
        """, (user_id,))
        rows = cur.fetchall()
        total_horas = sum(float(r.get('HorasExtrasCalculadas') or 0) for r in rows)
        return {"registros": rows, "total_horas": round(total_horas, 2), "total_registros": len(rows)}
    finally:
        cur.close()
        conn.close()


@router.get("/api/mi-asistencia/horas-extras/calculo")
def calculo_horas_extras(current_user: dict = Depends(get_current_user)):
    """Calculo informativo de horas extras segun LFT vigente."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        # Sueldo semanal del usuario
        cur.execute("SELECT Sueldo FROM HUB_Nomina WHERE IdUsuario = %s", (user_id,))
        row = cur.fetchone()
        sueldo_semana = float(row['Sueldo']) if row and row.get('Sueldo') else 0.0

        # Config LFT vigente
        cur.execute("SELECT * FROM HUB_AsistenciaConfigLFT WHERE Activo = 1 ORDER BY Anio DESC")
        cfg = cur.fetchone()
        if not cfg:
            cfg = {}
        dias_trabajo = int(cfg.get('DiasTrabajoSemana', 6))
        horas_jornada = float(cfg.get('HorasJornada', 8.0))
        semanas_mes = float(cfg.get('SemanasPorMes', 4.33))

        # Calculos informativos
        sueldo_diario = sueldo_semana / dias_trabajo if dias_trabajo > 0 else 0
        sueldo_hora = sueldo_diario / horas_jornada if horas_jornada > 0 else 0
        sueldo_mensual = sueldo_semana * semanas_mes
        sueldo_anual = sueldo_semana * 52

        # Horas extras pendientes
        cur.execute("""
            SELECT ISNULL(SUM(HorasExtrasCalculadas), 0) as total
            FROM HUB_HorasExtrasRegistros
            WHERE IdUsuario = %s AND Estatus = 'Pendiente'
        """, (user_id,))
        total_he = float(cur.fetchone().get('total', 0))

        # Desglose: dobles (primeras 9h/semana) y triples (siguientes)
        he_dobles_max = float(cfg.get('HorasExtrasDoblesMax', 9.0))
        he_dobles = min(total_he, he_dobles_max)
        he_triples = max(0, total_he - he_dobles_max)

        # Monto estimado (informativo)
        # Dobles: tarifa * 2, Triples: tarifa * 3
        monto_dobles = he_dobles * sueldo_hora * 2
        monto_triples = he_triples * sueldo_hora * 3
        monto_total = monto_dobles + monto_triples

        return {
            "sueldo_semanal": round(sueldo_semana, 2),
            "sueldo_diario": round(sueldo_diario, 2),
            "sueldo_hora": round(sueldo_hora, 2),
            "sueldo_mensual": round(sueldo_mensual, 2),
            "sueldo_anual": round(sueldo_anual, 2),
            "horas_extras_pendientes": round(total_he, 2),
            "horas_extras_dobles": round(he_dobles, 2),
            "horas_extras_triples": round(he_triples, 2),
            "monto_estimado_dobles": round(monto_dobles, 2),
            "monto_estimado_triples": round(monto_triples, 2),
            "monto_estimado_total": round(monto_total, 2),
            "config_lft": {
                "anio": cfg.get('Anio'),
                "jornada_diurna_max": float(cfg.get('JornadaDiurnaMax', 8)),
                "jornada_nocturna_max": float(cfg.get('JornadaNocturnaMax', 7)),
                "jornada_mixta_max": float(cfg.get('JornadaMixtaMax', 7.5)),
                "horas_extras_dobles_max": float(cfg.get('HorasExtrasDoblesMax', 9)),
                "limite_he_dia": float(cfg.get('LimiteHorasExtrasDia', 3)),
                "limite_he_semana": int(cfg.get('LimiteHorasExtrasSemana', 3)),
                "prima_dominical": float(cfg.get('PrimaDominical', 0.25)),
                "dias_trabajo_semana": int(cfg.get('DiasTrabajoSemana', 6)),
                "horas_jornada": float(cfg.get('HorasJornada', 8)),
                "semanas_por_mes": float(cfg.get('SemanasPorMes', 4.33)),
                "fecha_vigencia_ley": str(cfg.get('FechaVigenciaLey', '')),
            },
            "nota": "Calculo informativo. El pago real se determina al generar el reporte y firmarlo. Conforme a LFT vigente."
        }
    finally:
        cur.close()
        conn.close()


@router.post("/api/mi-asistencia/horas-extras/generar-reporte")
def generar_reporte_horas_extras(req: GenerarReporteReq, current_user: dict = Depends(get_current_user)):
    """Genera un reporte de horas extras (quema las horas pendientes)."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        # Obtener horas extras pendientes
        cur.execute("""
            SELECT Id, HorasExtrasCalculadas FROM HUB_HorasExtrasRegistros
            WHERE IdUsuario = %s AND Estatus = 'Pendiente'
        """, (user_id,))
        pendientes = cur.fetchall()
        if not pendientes:
            raise HTTPException(status_code=400, detail="No hay horas extras pendientes")
        total_horas = sum(float(r.get('HorasExtrasCalculadas') or 0) for r in pendientes)

        # Sueldo semanal
        cur.execute("SELECT Sueldo FROM HUB_Nomina WHERE IdUsuario = %s", (user_id,))
        row = cur.fetchone()
        sueldo_semana = float(row['Sueldo']) if row and row.get('Sueldo') else 0.0

        # Config LFT
        cur.execute("SELECT * FROM HUB_AsistenciaConfigLFT WHERE Activo = 1 ORDER BY Anio DESC")
        cfg = cur.fetchone() or {}
        dias_trabajo = int(cfg.get('DiasTrabajoSemana', 6))
        horas_jornada = float(cfg.get('HorasJornada', 8.0))
        sueldo_hora = (sueldo_semana / dias_trabajo / horas_jornada) if (dias_trabajo > 0 and horas_jornada > 0) else 0

        he_dobles_max = float(cfg.get('HorasExtrasDoblesMax', 9.0))
        he_dobles = min(total_horas, he_dobles_max)
        he_triples = max(0, total_horas - he_dobles_max)
        monto_total = (he_dobles * sueldo_hora * 2) + (he_triples * sueldo_hora * 3)

        # Generar folio
        cur.execute("SELECT ISNULL(MAX(Id), 0) + 1 FROM HUB_HorasExtrasReportes")
        next_id = cur.fetchone().get('', 0) or 1
        # Simpler: count + 1
        cur.execute("SELECT COUNT(*) as c FROM HUB_HorasExtrasReportes")
        count = cur.fetchone().get('c', 0)
        folio = "HE-%05d" % (count + 1)

        # Insertar reporte
        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO HUB_HorasExtrasReportes
            (IdUsuario, Folio, PeriodoInicio, PeriodoFin, TotalHorasExtras, TotalMonto, SueldoSemana, Estatus, Notas)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, folio, req.periodo_inicio, req.periodo_fin,
              round(total_horas, 2), round(monto_total, 2), sueldo_semana,
              'Generado', req.notas))
        conn.commit()

        # Obtener el Id del reporte recien creado
        cur.execute("SELECT MAX(Id) as id FROM HUB_HorasExtrasReportes WHERE IdUsuario = %s", (user_id,))
        reporte_id = cur.fetchone().get('id')

        # Quemar horas extras (marcar como Pagado y vincular al reporte)
        cur2.execute("""
            UPDATE HUB_HorasExtrasRegistros
            SET Estatus = 'Pagado', IdReporte = %s
            WHERE IdUsuario = %s AND Estatus = 'Pendiente'
        """, (reporte_id, user_id))
        conn.commit()

        return {
            "ok": True,
            "folio": folio,
            "reporte_id": reporte_id,
            "total_horas": round(total_horas, 2),
            "total_monto": round(monto_total, 2),
            "horas_dobles": round(he_dobles, 2),
            "horas_triples": round(he_triples, 2),
            "mensaje": "Reporte generado. Las horas extras han sido quemadas."
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/api/mi-asistencia/horas-extras/reportes")
def reportes_horas_extras(current_user: dict = Depends(get_current_user)):
    """Historial de reportes de horas extras del empleado."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("""
            SELECT Id, Folio, FechaGeneracion, PeriodoInicio, PeriodoFin,
                   TotalHorasExtras, TotalMonto, SueldoSemana, Estatus, Notas
            FROM HUB_HorasExtrasReportes
            WHERE IdUsuario = %s
            ORDER BY FechaGeneracion DESC
        """, (user_id,))
        rows = cur.fetchall()
        return {"reportes": rows, "total": len(rows)}
    finally:
        cur.close()
        conn.close()
