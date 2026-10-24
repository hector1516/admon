"""api/routers/passkeys.py — endpoints de passkeys (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from api import legends_core as _legends_core
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

import time as _passkey_time
from urllib.parse import urlparse as _urlparse

import jwt as _pyjwt
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


RP_ID = "ecc-sa.com.mx"
RP_NAME = "ECCSA"
CHALLENGE_TTL = 5 * 60

_PASSKEY_SECRET_CACHE: Dict[str, str] = {}

class PasskeyRegisterOptionsReq(BaseModel):
    label: str = ""
class PasskeyRegisterVerifyReq(BaseModel):
    credential: dict
    state: str
    label: str = ""
class PasskeyLoginOptionsReq(BaseModel):
    rp: str = RP_ID  # el frontend siempre manda ecc-sa.com.mx (único rp válido aquí)
class PasskeyLoginVerifyReq(BaseModel):
    credential: dict
    state: str

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


def _passkey_secret() -> str:
    """Secreto para los JWT stateless de los challenges.
    Orden: env JWT_SECRET > HUB_Config 'admon_passkey_secret' (se genera y
    persiste la primera vez) > fallback temporal (solo si la BD no responde)."""
    if _PASSKEY_SECRET_CACHE.get("secret"):
        return _PASSKEY_SECRET_CACHE["secret"]
    env = os.getenv("JWT_SECRET") or os.getenv("PASSKEY_JWT_SECRET")
    if env:
        _PASSKEY_SECRET_CACHE["secret"] = env
        return env
    secret = None
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Valor FROM HUB_Config WHERE Clave = 'admon_passkey_secret'")
        row = cursor.fetchone()
        secret = (row.get("Valor") or "").strip() if row else ""
        if not secret:
            secret = _passkey_b64.urlsafe_b64encode(os.urandom(48)).decode("ascii").rstrip("=")
            cursor.execute(
                "UPDATE HUB_Config SET Valor = %s, Actualizado = GETDATE() WHERE Clave = 'admon_passkey_secret'",
                (secret,),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO HUB_Config (Clave, Valor) VALUES (%s, %s)",
                    ("admon_passkey_secret", secret),
                )
        conn.close()
    except Exception:
        secret = "admon-passkey-boot-secret"  # inestable: solo si la BD falla
    _PASSKEY_SECRET_CACHE["secret"] = secret
    return secret


def _is_allowed_origin(origin: str) -> bool:
    """Allowlist: https://ecc-sa.com.mx o cualquier subdominio (*.ecc-sa.com.mx),
    más localhost para desarrollo."""
    if not origin:
        return False
    p = _urlparse(origin)
    if p.hostname in ("localhost", "127.0.0.1"):
        return True
    if p.scheme != "https":
        return False
    host = p.hostname or ""
    return host == "ecc-sa.com.mx" or host.endswith(".ecc-sa.com.mx")


def _origin_for_request(request: Request) -> str:
    """Origin real de la petición, validado contra la allowlist."""
    origin = request.headers.get("origin", "") if request else ""
    if not _is_allowed_origin(origin):
        raise HTTPException(status_code=400, detail="Origin no permitido")
    return origin


def _b64url_encode(raw: bytes) -> str:
    return _passkey_b64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _issue_challenge(purpose: str):
    """Challenge aleatorio envuelto en JWT stateless (seguro entre reinicios)."""
    raw = os.urandom(32)
    now = int(_passkey_time.time())
    token = _pyjwt.encode(
        {"purpose": purpose, "ch": _b64url_encode(raw), "iat": now, "exp": now + CHALLENGE_TTL},
        _passkey_secret(),
        algorithm="HS256",
    )
    return token, raw


def _read_challenge(state: str, purpose: str) -> bytes:
    try:
        data = _pyjwt.decode(state, _passkey_secret(), algorithms=["HS256"])
    except _pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Desafío expirado, intenta de nuevo")
    except _pyjwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Desafío inválido")
    if data.get("purpose") != purpose or not data.get("ch"):
        raise HTTPException(status_code=400, detail="Desafío inválido")
    return base64url_to_bytes(data["ch"])


def _login_row_by_id(user_id: int):
    """Fila completa (misma forma que api_login) para armar la respuesta de sesión."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT Id, Nombre, Email, Password, Activo, AccesoInventario, AccesoNominas, "
        "AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, "
        "AccesoUsuarios, AccesoReportes, AccesoRegistroReportes, AccesoIA, Nickname, "
        "AccesoValesOxxoGas, AccesoRegistroKilometros "
        "FROM HUB_Users WHERE Id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


# --- Modelos ---

class PasskeyRegisterOptionsReq(BaseModel):
    label: str = ""


class PasskeyRegisterVerifyReq(BaseModel):
    credential: dict
    state: str
    label: str = ""


class PasskeyLoginOptionsReq(BaseModel):
    rp: str = RP_ID  # el frontend siempre manda ecc-sa.com.mx (único rp válido aquí)


class PasskeyLoginVerifyReq(BaseModel):
    credential: dict
    state: str




@router.post("/api/passkeys/login/options")
async def passkey_login_options(body: PasskeyLoginOptionsReq = None):
    """Opciones de login discoverable (sin correo) para el rp raíz."""
    try:
        state, challenge = _issue_challenge("wk_login")
        options = generate_authentication_options(rp_id=RP_ID, challenge=challenge)
        return {"options": options_to_json(options), "state": state, "rp": RP_ID}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Passkey error: {str(e)}")


@router.post("/api/passkeys/login/verify")
async def passkey_login_verify(body: PasskeyLoginVerifyReq, request: Request = None):
    """Valida el assertion y devuelve la sesión igual que /api/auth/login."""
    challenge = _read_challenge(body.state, "wk_login")
    origin = _origin_for_request(request)
    cred_id = body.credential.get("id", "")
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute("SELECT * FROM HUB_Passkeys WHERE CredentialId = %s", (cred_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Passkey no reconocida en este equipo")
    # Passkeys legacy (field./hub.) no se pueden usar desde admon: el navegador
    # exige que el rpId coincida con el dominio actual.
    cred_rp = (row.get("RpId") or RP_ID).strip() or RP_ID
    if cred_rp != RP_ID:
        raise HTTPException(
            status_code=401,
            detail="Tu passkey es de otra app (Field/HUB). Crea una aquí con ＋ Agregar este equipo.",
        )
    # El userHandle debe corresponder al dueño de la credencial
    try:
        raw_handle = body.credential.get("response", {}).get("userHandle")
        handle_uid = int(base64url_to_bytes(raw_handle).decode("utf-8")) if raw_handle else row["IdUsuario"]
    except Exception:
        handle_uid = row["IdUsuario"]
    if handle_uid != row["IdUsuario"]:
        raise HTTPException(status_code=401, detail="Passkey no válida para este usuario")
    try:
        v = verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=origin,
            credential_public_key=_passkey_b64.urlsafe_b64decode(row["PublicKey"] + "=="),
            credential_current_sign_count=row["SignCount"],
            require_user_verification=False,
        )
    except Exception as e:
        print(f"[passkey] login FAIL cred={cred_id[:12]}: {e}", flush=True)
        raise HTTPException(status_code=401, detail="No se pudo verificar la passkey")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE HUB_Passkeys SET SignCount = %s, UltimoUso = GETDATE() WHERE Id = %s",
            (v.new_sign_count, row["Id"]),
        )
        conn.close()
    except Exception:
        pass  # el sign count es anti-replay best effort; no bloquea el login
    user_row = _login_row_by_id(row["IdUsuario"])
    if not user_row or not user_row[4]:
        raise HTTPException(status_code=401, detail="Usuario no válido o inactivo")
    print(f"[passkey] login OK uid={user_row[0]}", flush=True)
    return _build_login_response(user_row[2], user_row)


@router.post("/api/passkeys/register/options")
async def passkey_register_options(
    body: PasskeyRegisterOptionsReq = None,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Options de registro (requiere sesión). Siempre en el rp raíz."""
    origin = _origin_for_request(request)
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        "SELECT CredentialId FROM HUB_Passkeys WHERE IdUsuario = %s",
        (current_user["id"],),
    )
    existing = [dict(r) for r in cursor.fetchall()]
    conn.close()
    exclude = []
    for c in existing:
        try:
            exclude.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["CredentialId"])))
        except Exception:
            continue
    state, challenge = _issue_challenge("wk_reg")
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(current_user["id"]).encode("utf-8"),
        user_name=current_user["email"],
        user_display_name=current_user["nombre"],
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude or None,
    )
    return {"options": options_to_json(options), "state": state}


@router.post("/api/passkeys/register/verify")
async def passkey_register_verify(
    body: PasskeyRegisterVerifyReq,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Valida el attestation y guarda la passkey en HUB_Passkeys."""
    challenge = _read_challenge(body.state, "wk_reg")
    origin = _origin_for_request(request)
    try:
        v = verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=origin,
        )
    except Exception as e:
        print(f"[passkey] register FAIL uid={current_user['id']}: {e}", flush=True)
        raise HTTPException(status_code=400, detail="No se pudo registrar la passkey")
    cred_id = _b64url_encode(v.credential_id)
    pubkey = _b64url_encode(v.credential_public_key)
    transports = ",".join(body.credential.get("transports", []) or [])
    label = (body.label or "Mi equipo")[:100]
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id FROM HUB_Passkeys WHERE CredentialId = %s", (cred_id,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Esta passkey ya está registrada")
        cursor.execute(
            "INSERT INTO HUB_Passkeys (IdUsuario, CredentialId, PublicKey, SignCount, Transports, Etiqueta, RpId) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (current_user["id"], cred_id, pubkey, v.sign_count, transports, label, RP_ID),
        )
        # Nickname de Legends: inicializar SOLO si está vacío (no sobrescribir)
        cursor.execute("SELECT Nickname FROM HUB_Users WHERE Id = %s", (current_user["id"],))
        u = cursor.fetchone()
        nick = (u.get("Nickname") or "").strip() if u else ""
        if not nick:
            cursor.execute("UPDATE HUB_Users SET Nickname = %s WHERE Id = %s", (label, current_user["id"]))
        conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar la passkey: {str(e)}")
    print(f"[passkey] register OK uid={current_user['id']} label={label}", flush=True)
    return {"ok": True}


@router.get("/api/passkeys/mine")
async def passkey_mine(current_user: dict = Depends(get_current_user)):
    """Passkeys del usuario con badge nueva/legacy para la UI."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        "SELECT Id, Etiqueta, FechaCreacion, UltimoUso, RpId FROM HUB_Passkeys "
        "WHERE IdUsuario = %s ORDER BY FechaCreacion DESC",
        (current_user["id"],),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        for k in ("FechaCreacion", "UltimoUso"):
            if r.get(k) is not None:
                r[k] = str(r[k])
        rp = (r.get("RpId") or "").strip()
        r["EsNueva"] = rp == RP_ID
    return {"passkeys": rows}


@router.delete("/api/passkeys/{pid}")
async def passkey_delete(pid: int, current_user: dict = Depends(get_current_user)):
    """Elimina una passkey propia."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM HUB_Passkeys WHERE Id = %s AND IdUsuario = %s", (pid, current_user["id"]))
    deleted = cursor.rowcount
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Passkey no encontrada")
    return {"ok": True}


# --- ECCSA Legends — port desde Field (api/routers/legends.py) ----------------
# Sistema gamificado de puntos/ranking sobre las MISMAS tablas compartidas:
#   HUB_UserScores (semanal+total+nivel+racha), HUB_ScoreLog (bitácora),
#   HUB_UserAvatars, HUB_WeeklyWinners, HUB_Users.Nickname + HUB_Passkeys.
# El cron semanal (ganador del domingo 03:00, sin reset) y el audit cada 5 min los
# ejecuta el contenedor `workersadmon` (programas legends_cron y legends_audit;
# migración del 2026-09-26 — antes eran programs del supervisord de Field) sobre
# la misma BD; aquí solo exponemos los endpoints de lectura, /award y el cálculo
# manual. Ojo: `legends_audit` debe tener UNA sola instancia en todo el entorno
# (si se duplica, duplica HUB_ScoreLog).
# Diferencias con Field: auth = get_current_user (token simple email|ts),
# push adaptado al esquema de Admon (HUB_PushSubscriptions.UserEmail +
# VAPID en HUB_PushConfig), y conexiones siempre cerradas.

LEGENDS_METRICAS = dict(_legends_core.METRICAS)

LEGENDS_NIVELES = [(n["nombre"], n["min"]) for n in reversed(_legends_core.NIVELES)]

LEGENDS_ICONO = {n["nombre"]: n["icono"] for n in _legends_core.NIVELES}

# Descripciones legibles de las métricas (para /score-log)
LEGENDS_METRICA_DESC = {
    "reporte_firmado":  ("Reporte firmado", "✍️", 10),
    "kilometro":        ("Kilómetros registrados", "⛽", 4),
    "ticket_oxxogas":   ("Ticket OxxoGas", "🎫", 3),
    "vale_generado":    ("Vale generado", "💰", -1),
    "comida_reporte":   ("Hora de comida en reporte", "🍽️", -1),
    "firma_remota":     ("Firma remota de reporte", "📱", 6),
    "servicio":         ("Servicio registrado", "🔧", 0),
    "racha_dia":        ("Racha diaria activa", "🔥", 2),
    "logro":            ("Logro desbloqueado", "🏅", 0),
    "cotizacion_enviada": ("Cotización enviada", "📤", 5),
    "cliente_alta":     ("Cliente nuevo registrado", "📇", 4),
    "reporte_creado":   ("Reporte de servicio registrado", "🗂️", 3),
    "reporte_fotos":    ("Fotos de evidencia subidas", "📸", 2),
    "cotizacion_creada": ("Cotización creada", "🧾", 2),
    # Métricas económicas (2026-10-23)
    "cliente_nuevo_cotizado": ("Cliente nuevo cotizado", "🎯", 5),
    "cotizacion_con_partidas": ("Cotización con partidas", "📋", 2),
    "cotizacion_entregada": ("Cotización entregada", "🤝", 10),
    # El valor real es dinámico (+15 a +75 según subtotal); 15 es la base.
    "cotizacion_pagada": ("Cotización pagada", "💵", 15),
    "cobranza_registrada": ("Cobranza registrada", "🏦", 3),
    "reporte_mismo_dia": ("Reporte cerrado el mismo día", "📅", 3),
    "vale_con_comprobante": ("Vale con comprobante", "🧾", 2),
    "vale_sin_comprobante": ("Vale sin comprobante", "🚫", -2),
    "reporte_tardio": ("Reporte tardío", "⏰", -2),
    "retrabajo": ("Retrabajo de reporte", "🔁", -5),
}


def legends_calcular_nivel(puntos: int) -> str:
    """Nivel de temporada para esos puntos (Bronce → Leyenda)."""
    return _legends_core.nivel_de(puntos)["nombre"]


def legends_push_all(title: str, body: str):
    """Push a TODOS los suscriptores (esquema Admon: UserEmail + HUB_PushConfig).
    Best-effort: cualquier error se imprime y nunca rompe el flujo."""
    try:
        import json as _json
        from pywebpush import webpush
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VapidPrivateKey FROM HUB_PushConfig WHERE Id = 1")
            vk = cursor.fetchone()
            if not vk or not vk[0]:
                return
            priv_key = vk[0].strip()
            cursor.execute("SELECT Endpoint, P256dhKey, AuthKey FROM HUB_PushSubscriptions")
            subs = cursor.fetchall()
        finally:
            conn.close()
        if not subs:
            return
        payload = _json.dumps({"title": title, "body": body})
        for endpoint, p256dh, auth_key in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": {"p256dh": p256dh, "auth": auth_key},
                    },
                    data=payload,
                    vapid_private_key=priv_key,
                    vapid_claims={"sub": "mailto:robot@ecc-sa.com.mx"},
                )
            except Exception:
                # Suscripción vencida o error transitorio: no afecta a las demás
                pass
    except Exception as e:
        print(f"[legends push] {e}", flush=True)


def legends_notify_level_up(user_id: int, new_level: str):
    """Notifica a TODOS cuando alguien sube de nivel."""
    try:
        emoji = LEGENDS_ICONO.get(new_level, "🎯")
        legends_push_all("🎉 ¡Sube de nivel!", f"{legends_get_display_name(user_id)} alcanzó nivel {new_level} {emoji}")
    except Exception:
        pass


def legends_notify_ranking_pass(user_id: int, passed_user_id: int, new_position: int):
    """Notifica a TODOS cuando alguien pasa a otro en el ranking."""
    try:
        passer = legends_get_display_name(user_id)
        passed = legends_get_display_name(passed_user_id)
        legends_push_all(
            "🏆 ¡Movimiento en el ranking!",
            f"{passer} pasó a {passed} — ahora en posición #{new_position}",
        )
    except Exception:
        pass


def legends_notify_weekly_winner(user_id: int, points: int):
    """Notifica a TODOS cuando se elige al ganador semanal."""
    try:
        name = legends_get_display_name(user_id)
        legends_push_all("🏆 ¡Ganador de la semana!", f"{name} ganó la semana con {points} puntos")
    except Exception:
        pass


def legends_get_display_name(user_id: int) -> str:
    """Nombre para mostrar: Nickname de Legends si existe, si no Nombre."""
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute("SELECT Nombre, Nickname FROM HUB_Users WHERE Id = %s", (user_id,))
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            return "Alguien"
        nick = (row.get("Nickname") or "").strip()
        return nick or (row.get("Nombre") or "Alguien")
    except Exception:
        return "Alguien"


def legends_get_posicion(user_id: int) -> int:
    """Posición actual del usuario en el ranking semanal (1-based)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT PuntuacionSemanal FROM HUB_UserScores WHERE IdUsuario = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return 999
        weekly = row["PuntuacionSemanal"]
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM HUB_UserScores s
            JOIN HUB_Users u ON s.IdUsuario = u.Id
            WHERE u.Activo = 1 AND s.PuntuacionSemanal > %s
        """, (weekly,))
        r = cursor.fetchone()
        return (r["total"] + 1) if r else 1
    finally:
        conn.close()


def legends_usuario_pasado(user_id: int, old_pos: int) -> Optional[int]:
    """Id del usuario que se dejó de encabezar al subir en el ranking, o None."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT IdUsuario FROM (
                SELECT s.IdUsuario,
                       ROW_NUMBER() OVER (ORDER BY s.PuntuacionSemanal DESC) AS rn
                FROM HUB_UserScores s
                JOIN HUB_Users u ON s.IdUsuario = u.Id
                WHERE u.Activo = 1
            ) t
            WHERE rn = %s
        """, (old_pos,))
        row = cursor.fetchone()
        if row and row["IdUsuario"] != user_id:
            return row["IdUsuario"]
        return None
    finally:
        conn.close()


def legends_usuario_por_nombre(nombre: str) -> Optional[int]:
    """Id del usuario activo con ese nombre (mismo criterio que Field)."""
    if not nombre:
        return None
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor(as_dict=True)
            cursor.execute(
                "SELECT TOP 1 Id FROM HUB_Users "
                "WHERE LTRIM(RTRIM(Nombre)) = LTRIM(RTRIM(%s)) AND Activo = 1 "
                "ORDER BY Id",
                (nombre,),
            )
            row = cursor.fetchone()
            return int(row["Id"]) if row else None
        finally:
            conn.close()
    except Exception:
        return None


def legends_subtotal_cotizacion(cursor, folio: int) -> float:
    """Subtotal SIN IVA de una cotización: material con factor + flete."""
    cursor.execute(
        "SELECT ISNULL(SUM(ISNULL(Cantidad, 0) * ISNULL(PrecioCompraUnitario, 0) "
        "* (1 + ISNULL(Factor, 0)) + ISNULL(Flete, 0)), 0) AS total "
        "FROM Partidas WHERE Folio = %s",
        (int(folio),),
    )
    row = cursor.fetchone()
    return float(row[0] or 0) if row else 0.0


def legends_tiene_score_global(cursor, metrica: str, referencia_id: int) -> bool:
    """¿Ya existe el score para esa entidad, sin importar el usuario?

    Se usa para `reporte_fotos`: el punto es del reporte, no de quien subió la
    foto. Sin esto, Admon y Field pueden premiar el mismo reporte dos veces
    (una por el oficinista y otra por el técnico).
    """
    cursor.execute(
        "SELECT TOP 1 1 AS existe FROM HUB_ScoreLog "
        "WHERE Metrica = %s AND ReferenciaId = %s",
        (metrica, int(referencia_id)),
    )
    return cursor.fetchone() is not None


def legends_registrar_metrica(id_usuario: int, metrica: str, referencia_id: int = None, puntos_override: int = None):
    """Registra una métrica y recalcula la fila del usuario.

    Usa el motor compartido `legends_core`: los puntos se recalculan desde
    `HUB_ScoreLog` (no se suman a mano) y el nivel es el de la temporada.
    Solo otorga puntos si el usuario tiene passkey + nickname.
    """
    if metrica not in LEGENDS_METRICAS and puntos_override is None:
        return
    puntos = puntos_override if puntos_override is not None else LEGENDS_METRICAS[metrica]

    old_level = "Bronce"
    old_pos = 999
    new_level = "Bronce"

    conn = get_connection()
    try:
        with conn.cursor(as_dict=True) as cur:
            # Elegibilidad: passkey (identidad) + Nickname en HUB_Users
            cur.execute("""
                SELECT TOP 1 1 AS existe FROM HUB_Users u
                WHERE u.Id = %s
                  AND u.Nickname IS NOT NULL AND LTRIM(RTRIM(u.Nickname)) <> ''
                  AND EXISTS (SELECT 1 FROM HUB_Passkeys p WHERE p.IdUsuario = u.Id)
            """, (id_usuario,))
            if not cur.fetchone():
                return

            # Idempotencia por (usuario, métrica, referencia). Vale para todas
            # las métricas con referencia, incluida `kilometro` (que ahora usa
            # el Id del registro, no el del vehículo).
            if referencia_id is not None:
                cur.execute(
                    "SELECT TOP 1 1 AS existe FROM HUB_ScoreLog "
                    "WHERE IdUsuario=%s AND Metrica=%s AND ReferenciaId=%s",
                    (id_usuario, metrica, referencia_id),
                )
                if cur.fetchone():
                    return

            cur.execute(
                "SELECT PuntuacionSemanal, PuntuacionTotal, Nivel "
                "FROM HUB_UserScores WHERE IdUsuario = %s",
                (id_usuario,),
            )
            row = cur.fetchone()
            old_level = row["Nivel"] if row else "Bronce"
            old_pos = next(
                (u["posicion"] for u in _legends_core.ranking(cur, id_usuario)
                 if u["id_usuario"] == int(id_usuario)),
                999,
            )

            cur.execute(
                "INSERT INTO HUB_ScoreLog (IdUsuario, Metrica, Puntos, ReferenciaId) "
                "VALUES (%s, %s, %s, %s)",
                (id_usuario, metrica, puntos, referencia_id),
            )

            stats = _legends_core.stats_usuario(cur, id_usuario)
            _legends_core.guardar_scores(cur, id_usuario, stats)
            new_level = stats["nivel"]
            conn.commit()
    finally:
        conn.close()

    # Notificaciones fuera del cursor (best-effort, igual que Field)
    if puntos != 0:
        try:
            if new_level != old_level:
                legends_notify_level_up(id_usuario, new_level)
            if puntos > 0 and old_pos is not None:
                new_pos = legends_get_posicion(id_usuario)
                if new_pos < old_pos:
                    passed_id = legends_usuario_pasado(id_usuario, old_pos)
                    if passed_id:
                        legends_notify_ranking_pass(id_usuario, passed_id, new_pos)
        except Exception:
            pass


def legends_registrar_puntos_servicio(id_reporte: int):
    """Calcula y registra puntos por horas de servicio firmado.

    También otorga +10 por reporte_firmado si no se ha registrado antes.
    Si TiempoComida=True, aplica -1 punto de penalización.

    Fórmula:
      HorasTotales = (FechaHoraFin - FechaHoraInicio)
      HorasNetas   = HorasTotales - TiempoTraslado - (TiempoComida ? 1 : 0)
      PuntosPersona = max(floor(HorasNetas / NumIngenieros), 1)
    """
    import math
    try:
        conn = get_connection()
        try:
            with conn.cursor(as_dict=True) as cur:
                cur.execute("""
                    SELECT IdReporte, Tecnico, Fecha, FechaHoraInicio, FechaHoraFin,
                           TiempoTraslado, TiempoComida, Estatus
                    FROM ReportesServicio WHERE IdReporte = %s
                """, (id_reporte,))
                reporte = cur.fetchone()
                if not reporte or reporte['Estatus'] != 'Firmado':
                    return 0

                # Buscar IdUsuario del técnico principal (el premio es suyo,
                # no de quien capture la firma desde la oficina).
                cur.execute(
                    "SELECT TOP 1 Id FROM HUB_Users "
                    "WHERE LTRIM(RTRIM(Nombre)) = LTRIM(RTRIM(%s)) AND Activo = 1 "
                    "ORDER BY Id",
                    (reporte['Tecnico'],),
                )
                u = cur.fetchone()
                uid_tec = int(u['Id']) if u else None

                # +10 por reporte firmado, aunque falten las horas.
                if uid_tec:
                    legends_registrar_metrica(uid_tec, 'reporte_firmado', referencia_id=id_reporte)

                # Calidad del cierre: mismo día (+3) o tardío (−2).
                fin = reporte.get('FechaHoraFin')
                fecha = reporte.get('Fecha')
                if uid_tec and fin and fecha:
                    fecha_dia = fecha.date() if hasattr(fecha, 'date') else fecha
                    fin_dia = fin.date() if hasattr(fin, 'date') else fin
                    if fin_dia == fecha_dia:
                        legends_registrar_metrica(uid_tec, 'reporte_mismo_dia', referencia_id=id_reporte)
                    inicio_dia = datetime.combine(fecha_dia, datetime.min.time())
                    if (fin - inicio_dia).total_seconds() > 48 * 3600:
                        legends_registrar_metrica(uid_tec, 'reporte_tardio', referencia_id=id_reporte)

                if not reporte['FechaHoraInicio'] or not reporte['FechaHoraFin']:
                    return 0

                horas_totales = (reporte['FechaHoraFin'] - reporte['FechaHoraInicio']).total_seconds() / 3600.0
                if horas_totales <= 0:
                    return 0

                traslado = float(reporte['TiempoTraslado'] or 0)
                comida = 1.0 if reporte['TiempoComida'] else 0.0
                horas_netas = horas_totales - traslado - comida
                if horas_netas <= 0:
                    return 0

                # Participantes (técnico principal + adicionales)
                cur.execute("""
                    SELECT u.Nombre FROM ReportesServicioTecnicos t
                    JOIN HUB_Users u ON t.IdUsuario = u.Id WHERE t.IdReporte = %s
                """, (id_reporte,))
                adicionales = [r['Nombre'] for r in cur.fetchall()]
                participantes = [reporte['Tecnico']] + adicionales
                num = len(participantes)
                pts = max(math.floor(horas_netas / num), 1)

                count = 0
                for nombre in participantes:
                    cur.execute("SELECT Id FROM HUB_Users WHERE Nombre = %s AND Activo = 1", (nombre,))
                    u = cur.fetchone()
                    if not u:
                        continue
                    legends_registrar_metrica(u['Id'], 'servicio', referencia_id=id_reporte, puntos_override=pts)
                    # Penalización por comida: -1 punto
                    if reporte['TiempoComida']:
                        legends_registrar_metrica(u['Id'], 'comida_reporte', referencia_id=id_reporte, puntos_override=-1)
                    count += 1

                conn.commit()
                print(f"[legends] Reporte {id_reporte}: {pts} pts x {count} ingenieros ({horas_netas:.1f}h netas)", flush=True)
                return pts * count
        finally:
            conn.close()
    except Exception as e:
        print(f"legends_registrar_puntos_servicio error: {e}", flush=True)
        return 0


# --- Legends endpoints ---

