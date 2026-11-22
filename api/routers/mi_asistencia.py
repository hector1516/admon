"""api/routers/mi_asistencia.py - Modulo Mi Asistencia (self-service)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time, timedelta
import sys, os
import json
import base64

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
    stepup_token: str  # obligatorio (D3 B): lo emite /passkey/verify


class PasskeyOptionsReq(BaseModel):
    rp: Optional[str] = None


class PasskeyVerifyReq(BaseModel):
    state: str
    credential: dict

class GenerarReporteReq(BaseModel):
    periodo_inicio: str  # YYYY-MM-DD
    periodo_fin: str     # YYYY-MM-DD
    notas: Optional[str] = None


@router.post("/marcar")
def marcar_asistencia(req: MarcarReq, current_user: dict = Depends(get_current_user)):
    """Marca entrada o salida del empleado (self-service)."""
    if req.tipo not in ('Entrada', 'Salida'):
        raise HTTPException(status_code=400, detail="Tipo debe ser 'Entrada' o 'Salida'")
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    from api.routers import passkeys as _pk
    try:
        credencial = stepup.validar(req.stepup_token, user_id, _pk._passkey_secret())
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="La verificación con passkey expiró o no es válida. Vuelve a intentarlo.")
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
        """, (user_id, ahora.date(), req.tipo, ahora.strftime('%H:%M:%S'),
              req.latitud, req.longitud, req.precision,
              1 if req.verificacion_facial else 0, req.id_foto_verificacion, credencial,
              req.dispositivo, ahora, 'Valido'))
        conn.commit()
        return {"ok": True, "tipo": req.tipo, "fecha": str(ahora.date()),
                "hora": str(ahora.time()), "mensaje": f"{req.tipo} registrada correctamente"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/historial")
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
                   VerificacionFacial, PasskeyCredentialId, Dispositivo, Estado,
                   FechaRegistro
            FROM HUB_AsistenciaMarcado
            WHERE IdUsuario = %s
              AND Fecha >= DATEADD(day, -%s, GETDATE())
            ORDER BY Fecha DESC, Hora DESC
        """, (user_id, dias))
        rows = cur.fetchall()
        for r in rows:
            if r.get('Hora') is not None and hasattr(r['Hora'], 'strftime'):
                r['Hora'] = r['Hora'].strftime('%H:%M:%S')
            if r.get('Fecha') is not None and hasattr(r['Fecha'], 'strftime'):
                r['Fecha'] = r['Fecha'].strftime('%Y-%m-%d')
            if r.get('FechaRegistro') is not None and hasattr(r['FechaRegistro'], 'strftime'):
                r['FechaRegistro'] = r['FechaRegistro'].strftime('%Y-%m-%d %H:%M:%S')
        # Config LFT vigente: la tarjeta del ciclo calcula las horas extra con
        # estos valores, no con números escritos a mano en el frontend.
        cur.execute("""
            SELECT TOP 1 HorasJornada, LimiteHorasExtrasDia, HorasExtrasDoblesMax
            FROM HUB_AsistenciaConfigLFT
            WHERE Activo = 1
            ORDER BY Anio DESC
        """)
        cfg = cur.fetchone() or {}
        config_lft = {
            "horas_jornada": float(cfg.get("HorasJornada") or 8),
            "extras_max_dia": float(cfg.get("LimiteHorasExtrasDia") or 3),
            "extras_dobles_semana": float(cfg.get("HorasExtrasDoblesMax") or 9),
        }
        return {"registros": rows, "total": len(rows), "config_lft": config_lft}
    finally:
        cur.close()
        conn.close()


@router.get("/horas-extras")
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
        for r in rows:
            if r.get('HoraEntrada') is not None and hasattr(r['HoraEntrada'], 'strftime'):
                r['HoraEntrada'] = r['HoraEntrada'].strftime('%H:%M')
            if r.get('HoraSalida') is not None and hasattr(r['HoraSalida'], 'strftime'):
                r['HoraSalida'] = r['HoraSalida'].strftime('%H:%M')
            if r.get('Fecha') is not None and hasattr(r['Fecha'], 'strftime'):
                r['Fecha'] = r['Fecha'].strftime('%Y-%m-%d')
        total_horas = sum(float(r.get('HorasExtrasCalculadas') or 0) for r in rows)
        return {"registros": rows, "total_horas": round(total_horas, 2), "total_registros": len(rows)}
    finally:
        cur.close()
        conn.close()


@router.get("/horas-extras/calculo")
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


@router.post("/horas-extras/generar-reporte")
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


@router.get("/horas-extras/reportes")
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
        for r in rows:
            for k in ['FechaGeneracion', 'PeriodoInicio', 'PeriodoFin']:
                if r.get(k) is not None and hasattr(r[k], 'strftime'):
                    r[k] = r[k].strftime('%Y-%m-%d')
        return {"reportes": rows, "total": len(rows)}
    finally:
        cur.close()
        conn.close()


from fastapi.responses import Response
import io

@router.get("/horas-extras/reporte/{id_reporte}/pdf")
def pdf_horas_extras(id_reporte: int, current_user: dict = Depends(get_current_user)):
    """Genera PDF del reporte de horas extras."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Obtener reporte
        cur.execute("""
            SELECT r.Id, r.IdUsuario, r.Folio, r.FechaGeneracion, r.PeriodoInicio, r.PeriodoFin,
                   r.TotalHorasExtras, r.TotalMonto, r.SueldoSemana, r.Estatus, r.Notas,
                   u.Nombre
            FROM HUB_HorasExtrasReportes r
            LEFT JOIN HUB_Users u ON u.Id = r.IdUsuario
            WHERE r.Id = %s
        """, (id_reporte,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        # Obtener registros
        cur.execute("""
            SELECT Fecha, HoraEntrada, HoraSalida, HorasComida, HorasTraslado,
                   HorasExtrasCalculadas, Descripcion, Cliente, Calificacion, Nota
            FROM HUB_HorasExtrasRegistros
            WHERE IdReporte = %s
            ORDER BY Fecha ASC
        """, (id_reporte,))
        reg_rows = cur.fetchall()

        registros = []
        for r in reg_rows:
            registros.append({
                'Fecha': r[0],
                'HoraEntrada': r[1],
                'HoraSalida': r[2],
                'HorasComida': r[3],
                'HorasTraslado': r[4],
                'HorasExtrasCalculadas': r[5],
                'Descripcion': r[6],
                'Cliente': r[7],
                'Calificacion': r[8],
                'Nota': r[9],
            })

        nombre = row[11] or 'Empleado'
        total_horas = float(row[6] or 0)
        sueldo_semana = float(row[8] or 0)
        periodo_inicio = row[4]
        periodo_fin = row[5]
        notas = row[10]
        folio = row[2]

        from api.pdf_reporte import generate_horas_extras_reporte_pdf
        pdf_bytes = generate_horas_extras_reporte_pdf(
            nombre=nombre,
            registros=registros,
            total_horas=total_horas,
            sueldo_semana=sueldo_semana,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            notas=notas,
            folio=folio
        )

        if not pdf_bytes:
            raise HTTPException(status_code=500, detail="Error generando PDF")

        return Response(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{folio or "reporte_horas_extras"}.pdf"'})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {str(e)}")
    finally:
        cur.close()
        conn.close()


@router.get("/admin/reportes")
def admin_reportes_horas_extras(current_user: dict = Depends(get_current_user)):
    """Lista todos los reportes de horas extras (admin)."""
    # Check admin permission
    if not (current_user.get("acceso_usuarios") or current_user.get("acceso_reportes")):
        raise HTTPException(status_code=403, detail="Sin permiso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("""
            SELECT r.Id, r.IdUsuario, u.Nombre, r.Folio, r.FechaGeneracion,
                   r.PeriodoInicio, r.PeriodoFin, r.TotalHorasExtras, r.TotalMonto,
                   r.Estatus, r.Notas
            FROM HUB_HorasExtrasReportes r
            LEFT JOIN HUB_Users u ON u.Id = r.IdUsuario
            ORDER BY r.FechaGeneracion DESC
        """)
        rows = cur.fetchall()
        return {"reportes": rows, "total": len(rows)}
    finally:
        cur.close()
        conn.close()


@router.get("/admin/config-lft")
def admin_config_lft(current_user: dict = Depends(get_current_user)):
    """Obtiene la configuracion LFT vigente."""
    if not (current_user.get("acceso_usuarios") or current_user.get("acceso_reportes")):
        raise HTTPException(status_code=403, detail="Sin permiso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("SELECT * FROM HUB_AsistenciaConfigLFT WHERE Activo = 1 ORDER BY Anio DESC")
        rows = cur.fetchall()
        return {"configs": rows, "total": len(rows)}
    finally:
        cur.close()
        conn.close()




@router.post("/passkey/options")
def passkey_options(req: Optional[PasskeyOptionsReq] = None,
                    current_user: dict = Depends(get_current_user)):
    """Desafío para firmar con la passkey del usuario (paso previo al marcado)."""
    from api.routers import passkeys as _pk
    # Admon solo permite el RP raíz: aquí no hay RP legacy como en Field.
    state, challenge = _pk._issue_challenge("marcado")
    options = _pk.generate_authentication_options(rp_id=_pk.RP_ID, challenge=challenge)
    return {"options": _pk.options_to_json(options), "state": state, "rp": _pk.RP_ID}


@router.post("/passkey/verify")
def passkey_verify(req: PasskeyVerifyReq, request: Request,
                   current_user: dict = Depends(get_current_user)):
    """Valida la firma del autenticador y devuelve el token de paso (2 min)."""
    from api.routers import passkeys as _pk
    user_id = int(current_user.get("id") or current_user.get("Id"))
    challenge = _pk._read_challenge(req.state, "marcado")
    cred_id = req.credential.get("id", "")
    conn = get_connection()
    try:
        with conn.cursor(as_dict=True) as cur:
            cur.execute("SELECT * FROM HUB_Passkeys WHERE CredentialId = %s", (cred_id,))
            fila = cur.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Passkey no reconocida")
        if int(fila["IdUsuario"]) != user_id:
            raise HTTPException(status_code=403, detail="Esa passkey no es tuya")
        expected_origin = _pk._origin_for_request(request)
        try:
            v = _pk.verify_authentication_response(
                credential=req.credential,
                expected_challenge=challenge,
                expected_rp_id=_pk.RP_ID,
                expected_origin=expected_origin,
                credential_public_key=base64.urlsafe_b64decode(fila["PublicKey"] + "=="),
                credential_current_sign_count=fila["SignCount"],
                require_user_verification=False,
            )
        except Exception:
            raise HTTPException(status_code=401, detail="No se pudo verificar la passkey")
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE HUB_Passkeys SET SignCount = %s, UltimoUso = GETDATE() WHERE Id = %s",
                (v.new_sign_count, fila["Id"]))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "credential_id": cred_id,
            "stepup_token": stepup.emitir(user_id, cred_id, _pk._passkey_secret())}


# ─────────────────────────────────────────────────────────────────────────────
# Horarios de asistencia: catálogo con nombre («Operativo», «Administrativo») y
# asignación por usuario. Las tablas viven en la migración 0061.
# ─────────────────────────────────────────────────────────────────────────────


class HorarioDiaReq(BaseModel):
    dia: int                      # 1 = lunes … 7 = domingo
    entrada: Optional[str] = None  # 'HH:MM'
    salida: Optional[str] = None
    comida: int = 60
    descanso: bool = False


class HorarioReq(BaseModel):
    nombre: str
    dias: List[HorarioDiaReq] = []


class AsignarHorarioReq(BaseModel):
    id_horario: Optional[int] = None


def _requiere_admin(user: dict):
    if not (user.get("acceso_usuarios") or user.get("acceso_reportes")):
        raise HTTPException(status_code=403, detail="Sin permiso")


def _minutos(hhmm):
    if not hhmm:
        return None
    partes = str(hhmm).split(":")
    try:
        return int(partes[0]) * 60 + int(partes[1])
    except (ValueError, IndexError):
        return None


def _horas_semana(dias):
    """Suma de los días laborables, descontando la comida. En horas decimales."""
    total = 0
    for d in dias:
        if d.get("descanso"):
            continue
        e, s = _minutos(d.get("entrada")), _minutos(d.get("salida"))
        if e is None or s is None:
            continue
        if s < e:
            s += 1440
        total += max(0, s - e - int(d.get("comida") or 0))
    return round(total / 60, 2)


def _leer_dias(cur, id_horario):
    cur.execute(
        """
        SELECT DiaSemana, HoraEntrada, HoraSalida, ComidaMin, Descanso
        FROM HUB_AsistenciaHorarioDias
        WHERE IdHorario = %s
        ORDER BY DiaSemana
        """,
        (id_horario,),
    )
    dias = []
    for r in cur.fetchall():
        dias.append(
            {
                "dia": r["DiaSemana"],
                "entrada": r["HoraEntrada"].strftime("%H:%M") if r["HoraEntrada"] else None,
                "salida": r["HoraSalida"].strftime("%H:%M") if r["HoraSalida"] else None,
                "comida": r["ComidaMin"],
                "descanso": bool(r["Descanso"]),
            }
        )
    return dias


def _config_lft(cur):
    cur.execute(
        "SELECT TOP 1 HorasJornada, DiasTrabajoSemana, JornadaDiurnaMax "
        "FROM HUB_AsistenciaConfigLFT WHERE Activo = 1 ORDER BY Anio DESC"
    )
    cfg = cur.fetchone() or {}
    jornada = float(cfg.get("HorasJornada") or 8)
    dias = int(cfg.get("DiasTrabajoSemana") or 6)
    return {
        "horas_jornada": jornada,
        "dias_semana": dias,
        "tope_semana": round(float(cfg.get("JornadaDiurnaMax") or jornada) * dias, 2),
    }


@router.get("/admin/horarios")
def listar_horarios(current_user: dict = Depends(get_current_user)):
    """Catálogo de horarios con sus días y el total semanal."""
    _requiere_admin(current_user)
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute(
            "SELECT Id, Nombre, Activo, Notas FROM HUB_AsistenciaHorarios ORDER BY Nombre"
        )
        horarios = []
        for h in cur.fetchall():
            dias = _leer_dias(cur, h["Id"])
            horarios.append(
                {
                    "id": h["Id"],
                    "nombre": h["Nombre"],
                    "activo": bool(h["Activo"]),
                    "notas": h["Notas"],
                    "dias": dias,
                    "horas_semana": _horas_semana(dias),
                }
            )
        return {"horarios": horarios, "lft": _config_lft(cur)}
    finally:
        cur.close()
        conn.close()


def _guardar_dias(cur, id_horario, dias):
    cur.execute("DELETE FROM HUB_AsistenciaHorarioDias WHERE IdHorario = %s", (id_horario,))
    for d in dias:
        if d.dia < 1 or d.dia > 7:
            continue
        if d.descanso or not d.entrada or not d.salida:
            cur.execute(
                "INSERT INTO HUB_AsistenciaHorarioDias "
                "(IdHorario, DiaSemana, Descanso, ComidaMin) VALUES (%s, %s, 1, 0)",
                (id_horario, d.dia),
            )
        else:
            cur.execute(
                "INSERT INTO HUB_AsistenciaHorarioDias "
                "(IdHorario, DiaSemana, HoraEntrada, HoraSalida, ComidaMin, Descanso) "
                "VALUES (%s, %s, CONVERT(TIME(0), %s), CONVERT(TIME(0), %s), %s, 0)",
                (id_horario, d.dia, d.entrada, d.salida, max(0, min(240, int(d.comida or 0)))),
            )


@router.post("/admin/horarios")
def crear_horario(req: HorarioReq, current_user: dict = Depends(get_current_user)):
    """Crea un horario con nombre y sus días."""
    _requiere_admin(current_user)
    nombre = (req.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El horario necesita un nombre")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("SELECT Id FROM HUB_AsistenciaHorarios WHERE Nombre = %s", (nombre,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un horario con ese nombre")
        cur.execute(
            "INSERT INTO HUB_AsistenciaHorarios (Nombre, Activo, ActualizadoPor) "
            "OUTPUT INSERTED.Id VALUES (%s, 1, %s)",
            (nombre, current_user.get("id") or current_user.get("Id")),
        )
        id_horario = cur.fetchone()["Id"]
        _guardar_dias(cur, id_horario, req.dias)
        conn.commit()
        return {"ok": True, "id": id_horario}
    finally:
        cur.close()
        conn.close()


@router.put("/admin/horarios/{id_horario}")
def actualizar_horario(
    id_horario: int, req: HorarioReq, current_user: dict = Depends(get_current_user)
):
    """Renombra y reemplaza los días de un horario. Afecta a todos los asignados."""
    _requiere_admin(current_user)
    nombre = (req.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El horario necesita un nombre")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute("SELECT Id FROM HUB_AsistenciaHorarios WHERE Id = %s", (id_horario,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Horario no encontrado")
        cur.execute(
            "SELECT Id FROM HUB_AsistenciaHorarios WHERE Nombre = %s AND Id <> %s",
            (nombre, id_horario),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Ya existe un horario con ese nombre")
        cur.execute(
            "UPDATE HUB_AsistenciaHorarios SET Nombre = %s, Actualizado = GETDATE(), "
            "ActualizadoPor = %s WHERE Id = %s",
            (nombre, current_user.get("id") or current_user.get("Id"), id_horario),
        )
        _guardar_dias(cur, id_horario, req.dias)
        conn.commit()
        return {"ok": True}
    finally:
        cur.close()
        conn.close()


@router.delete("/admin/horarios/{id_horario}")
def borrar_horario(id_horario: int, current_user: dict = Depends(get_current_user)):
    """Borra un horario. Falla si alguien lo tiene asignado."""
    _requiere_admin(current_user)
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute(
            "SELECT COUNT(*) AS n FROM HUB_AsistenciaUsuarioHorario WHERE IdHorario = %s",
            (id_horario,),
        )
        if (cur.fetchone() or {}).get("n", 0) > 0:
            raise HTTPException(
                status_code=409,
                detail="Ese horario está asignado: quítalo de los usuarios primero",
            )
        cur.execute("DELETE FROM HUB_AsistenciaHorarios WHERE Id = %s", (id_horario,))
        conn.commit()
        return {"ok": True}
    finally:
        cur.close()
        conn.close()


@router.get("/admin/horarios/usuarios")
def usuarios_con_horario(current_user: dict = Depends(get_current_user)):
    """Usuarios activos con el horario que tengan asignado."""
    _requiere_admin(current_user)
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute(
            """
            SELECT u.Id, u.Nombre, uh.IdHorario, h.Nombre AS Horario
            FROM HUB_Users u
            LEFT JOIN HUB_AsistenciaUsuarioHorario uh ON uh.IdUsuario = u.Id
            LEFT JOIN HUB_AsistenciaHorarios h ON h.Id = uh.IdHorario
            ORDER BY u.Nombre
            """
        )
        return {"usuarios": cur.fetchall()}
    finally:
        cur.close()
        conn.close()


@router.put("/admin/horarios/usuario/{id_usuario}")
def asignar_horario(
    id_usuario: int, req: AsignarHorarioReq, current_user: dict = Depends(get_current_user)
):
    """Asigna un horario a un usuario. `id_horario` nulo lo deja sin horario."""
    _requiere_admin(current_user)
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        if req.id_horario is None:
            cur.execute(
                "DELETE FROM HUB_AsistenciaUsuarioHorario WHERE IdUsuario = %s", (id_usuario,)
            )
        else:
            cur.execute(
                "SELECT Id FROM HUB_AsistenciaHorarios WHERE Id = %s", (req.id_horario,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Horario no encontrado")
            cur.execute(
                """
                IF EXISTS (SELECT 1 FROM HUB_AsistenciaUsuarioHorario WHERE IdUsuario = %s)
                    UPDATE HUB_AsistenciaUsuarioHorario
                       SET IdHorario = %s, Actualizado = GETDATE()
                     WHERE IdUsuario = %s
                ELSE
                    INSERT INTO HUB_AsistenciaUsuarioHorario (IdUsuario, IdHorario)
                    VALUES (%s, %s)
                """,
                (id_usuario, req.id_horario, id_usuario, id_usuario, req.id_horario),
            )
        conn.commit()
        return {"ok": True}
    finally:
        cur.close()
        conn.close()


@router.get("/horario")
def mi_horario(current_user: dict = Depends(get_current_user)):
    """El horario del usuario de la sesión, día por día (para las tarjetas)."""
    user_id = current_user.get("id") or current_user.get("Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuario no identificado")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    try:
        cur.execute(
            "SELECT IdHorario FROM HUB_AsistenciaUsuarioHorario WHERE IdUsuario = %s",
            (user_id,),
        )
        fila = cur.fetchone()
        if not fila:
            return {"id_horario": None, "nombre": None, "dias": {}}
        id_horario = fila["IdHorario"]
        cur.execute("SELECT Nombre FROM HUB_AsistenciaHorarios WHERE Id = %s", (id_horario,))
        nombre = (cur.fetchone() or {}).get("Nombre")
        dias = {}
        for d in _leer_dias(cur, id_horario):
            dias[str(d["dia"])] = (
                None
                if d["descanso"]
                else {"entrada": d["entrada"], "salida": d["salida"], "comida": d["comida"]}
            )
        return {"id_horario": id_horario, "nombre": nombre, "dias": dias}
    finally:
        cur.close()
        conn.close()
