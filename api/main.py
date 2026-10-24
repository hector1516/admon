from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse, Response
from api.pdf_cotizacion import build_cotizacion_pdf
from api.pdf_reporte import build_service_report_pdf
from api.pdf_remision import build_remision_pdf
from api.lugar import lugar_de
from api import sat_helper
from api import usuarios_foto as _foto_usuario
from api import ficha_nfc as _ficha_nfc
from api import legends_core as _legends_core
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
import pymssql
import os
import io
import json
import base64
from functools import lru_cache
from datetime import datetime
from typing import Optional, List, Dict, Any

app = FastAPI(title="HUB Admon API", version="1.0.0")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

# IP LOCAL del servidor SQL: la misma que usan Field y workersadmon. Antes el
# default era la IP de la VPN (172.26.117.220) y, como el contenedor se clonaba
# con 'docker inspect', esa IP se venía arrastrando. La variable de entorno gana
# siempre; este default solo aplica si faltara.
DB_SERVER = os.getenv("HUB_DB_SERVER", "10.188.141.15")
DB_USER = os.getenv("HUB_DB_USER", "sa")
DB_PASSWORD = os.getenv("HUB_DB_PASSWORD", "eyccazo")
DB_DATABASE = os.getenv("HUB_DB_DATABASE", "ECCSA_Admon")


def get_connection():
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE, autocommit=True)
    return conn


# --- Helper Functions (usados por IA Tools) ---

def execute_readonly_sql(sql_query: str):
    """Ejecuta SELECT de solo lectura y retorna lista de dicts."""
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return [{"Error": str(e)}]


def send_email_with_multiple_pdfs(to_email: str, subject: str, body: str, attachments: list, sender_name: str = "ECCSA", sender_email: str = "sistemas@ecc-sa.com.mx"):
    """Envía email con múltiples adjuntos PDF. Retorna (success, error_msg)."""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.application import MIMEApplication
        from email.mime.text import MIMEText

        smtp_host = os.getenv("HUB_SMTP_SERVER", "smtp.office365.com")
        smtp_port = int(os.getenv("HUB_SMTP_PORT", "587"))
        smtp_user = os.getenv("HUB_SMTP_USER", "sistemas@ecc-sa.com.mx")
        smtp_pass = os.getenv("HUB_SMTP_PASSWORD", "eyccazo")

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{smtp_user}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        for pdf_bytes, filename in attachments:
            att = MIMEApplication(pdf_bytes, _subtype="pdf")
            att.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(att)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return True, None
    except Exception as e:
        return False, str(e)


# --- Models ---

class UserLogin(BaseModel):
    email: str = Field(..., description="Usuario con dominio @ecc-ssa.com.mx o @ecc-sa.com.mx")
    password: str = Field(..., description="Contraseña de usuario")


class Token(BaseModel):
    access_token: str
    token_type: str


class UserInfo(BaseModel):
    id: int
    nombre: str
    email: str
    acceso_inventario: bool = False
    acceso_nominas: bool = False
    acceso_cotizaciones: bool = False
    acceso_proveedores: bool = False
    acceso_oc: bool = False
    acceso_calculo: bool = False
    acceso_usuarios: bool = False
    acceso_reportes: bool = False
    acceso_registro_reportes: bool = False
    acceso_ia: bool = False
    acceso_vales_oxxogas: bool = False
    nickname: str = ""
    mac_telefono: str = ""
    # Puesto y si tiene foto (para la lista/avatares). El NSS NO va aquí:
    # es dato personal y solo se entrega en la ficha del usuario.
    puesto: str = ""
    tiene_foto: bool = False
    # Enlace publico de la tarjeta NFC (app colaboradores.ecc-sa.com.mx). Es el
    # mismo token que esa app calcula: ver api/ficha_nfc.py para el contrato de
    # la derivacion, que esta escrita en los dos repos.
    ficha_url: str = ""


# --- Auth Dependency ---

def _user_from_token(token: str):
    """Valida el token simple (email|timestamp) contra HUB_Users. Retorna dict o None."""
    try:
        parts = (token or "").split("|")
        if len(parts) < 2:
            return None
        email = parts[0]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Email, AccesoInventario, AccesoNominas, AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, AccesoUsuarios, AccesoReportes, AccesoRegistroReportes, AccesoIA, Nickname, AccesoValesOxxoGas, AccesoRegistroKilometros FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s", (email.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "nombre": row[1],
                "email": row[2],
                # Nickname de Legends: lo usa el Login para sugerir el nombre de la passkey
                "nickname": (row[14] or "").strip() if len(row) > 14 and row[14] else "",
                "acceso_inventario": row[3] == 1,
                "acceso_nominas": row[4] == 1,
                "acceso_cotizaciones": row[5] == 1,
                "acceso_proveedores": row[6] == 1,
                "acceso_oc": row[7] == 1,
                "acceso_calculo": row[8] == 1,
                "acceso_usuarios": row[10] == 1,
                "acceso_reportes": row[11] == 1,
                "acceso_registro_reportes": row[12] == 1,
                "acceso_ia": row[13] == 1,
                "acceso_vales_oxxogas": row[15] == 1 if len(row) > 15 else False,
                # Módulo Kilómetros (consumo semanal + captura). row[16] = AccesoRegistroKilometros
                "acceso_registro_kilometros": row[16] == 1 if len(row) > 16 else False,
            }
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")


def get_current_user(token: str = Depends(oauth2_scheme)):
    user = _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _user_from_header_or_query(request: Request):
    """Auth para descargas/iframes: Bearer en header o ?token= en query (como Field)."""
    auth_h = request.headers.get("Authorization", "")
    token = auth_h[7:] if auth_h.startswith("Bearer ") else request.query_params.get("token", "")
    user = _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


# --- Root / health (sin auth, para Docker HEALTHCHECK y pruebas) ---
# Si existe el frontend compilado (dist/), "/" sirve la SPA; la info JSON
# de la API se mueve a "/api". Sin dist/, "/" sigue devolviendo JSON.

# --- Routers por dominio (Fase 1 del refactor) ---
from api.routers import core as core_router
app.include_router(core_router.router)
from api.routers import users as users_router
app.include_router(users_router.router)
from api.routers import clientes as clientes_router
app.include_router(clientes_router.router)
from api.routers import cotizaciones as cotizaciones_router
app.include_router(cotizaciones_router.router)
from api.routers import notas as notas_router
app.include_router(notas_router.router)
from api.routers import ia as ia_router
app.include_router(ia_router.router)
from api.routers import legends as legends_router
app.include_router(legends_router.router)
from api.routers import kilometros as kilometros_router
app.include_router(kilometros_router.router)
from api.routers import kilometros as kilometros_router
app.include_router(kilometros_router.router)
from api.routers import tickets as tickets_router
app.include_router(tickets_router.router)
from api.routers import legends as legends_router
app.include_router(legends_router.router)
from api.routers import passkeys as passkeys_router
app.include_router(passkeys_router.router)
from api.routers import ia as ia_router
app.include_router(ia_router.router)
from api.routers import reportes as reportes_router
app.include_router(reportes_router.router)
from api.routers import pantalla as pantalla_router
app.include_router(pantalla_router.router)
from api.routers import dashboard as dashboard_router
app.include_router(dashboard_router.router)
from api.routers import pdf as pdf_router
app.include_router(pdf_router.router)
from api.routers import asistencia as asistencia_router
app.include_router(asistencia_router.router)
from api.routers.pdf import ReporteCreate, ReporteUpdate, ReporteFotosSave, ReporteTecnicosSave, ReporteSignatureSave
# Re-exportar modelos que quedaron en el router pero se usan en main.py
from api.routers.clientes import SyncPushRequest


# --- Auth Endpoints ---

@app.post("/api/token")
async def login(user: UserLogin):
    """Login with email and password, returns JWT token"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Validate email domain
        valid_domains = ["@ecc-ssa.com.mx", "@ecc-sa.com.mx"]
        valid = any(user.email.endswith(d) for d in valid_domains)
        if not valid:
            raise HTTPException(status_code=400, detail="Email domain not authorized")
        
        cursor.execute("SELECT Id, Nombre, Email, Password, Activo FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s", (user.email.strip().lower(),))
        row = cursor.fetchone()
        conn.close()

        if row and row[4] and row[3] == user.password:  # Password plano + Activo, igual que el HUB
            # Create JWT token (email|issued_at)
            import time
            timestamp = int(time.time())
            token = f"{user.email}|{timestamp}"
            return {"access_token": token, "token_type": "bearer"}
        
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")


# --- Auth endpoint compatible con el frontend Svelte (POST /api/auth/login) ---
# Contrato que espera src/lib/stores/auth.ts: { token, user, expiresAt }

class LoginRequest(BaseModel):
    email: str
    password: str


def _build_login_response(email: str, row) -> dict:
    import time
    timestamp = int(time.time())
    token = f"{email}|{timestamp}"
    expires_at = (timestamp + 7 * 24 * 3600) * 1000  # 7 días en ms
    # row: Id, Nombre, Email, Password, Activo, AccesoInventario, AccesoNominas,
    #      AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo,
    #      AccesoTelegram, AccesoUsuarios, AccesoReportes, AccesoRegistroReportes,
    #      AccesoIA, Nickname, AccesoValesOxxoGas, AccesoRegistroKilometros
    b = lambda i: (row[i] == 1) if len(row) > i and row[i] is not None else False
    user = {
        "id": row[0], "nombre": row[1], "email": row[2],
        "acceso_inventario": b(5), "acceso_nominas": b(6),
        "acceso_cotizaciones": b(7), "acceso_proveedores": b(8),
        "acceso_oc": b(9), "acceso_calculo": b(10),
        # b(11) = AccesoTelegram: se lee en el SELECT pero ya NO se expone
        # (módulo Telegram eliminado de admon); acceso_usuarios sigue en b(12).
        "acceso_usuarios": b(12),
        "acceso_reportes": b(13), "acceso_registro_reportes": b(14),
        "acceso_ia": b(15),
        "acceso_vales_oxxogas": b(17),
        # Módulo Kilómetros (consumo semanal + captura)
        "acceso_registro_kilometros": b(18),
        # Para la pantalla de sugerencia de passkey (label = nickname si existe)
        "nickname": (row[16] or "").strip() if len(row) > 16 and row[16] else "",
    }
    return {"token": token, "user": user, "expiresAt": expires_at}


@app.post("/api/auth/login")
async def api_login(body: LoginRequest):
    """Login que usa el frontend Svelte. Valida dominio y password de HUB_Users."""
    try:
        valid_domains = ["@ecc-ssa.com.mx", "@ecc-sa.com.mx"]
        if not any(body.email.endswith(d) for d in valid_domains):
            raise HTTPException(status_code=400, detail="Email domain not authorized")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Email, Password, Activo, AccesoInventario, AccesoNominas, AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, AccesoUsuarios, AccesoReportes, AccesoRegistroReportes, AccesoIA, Nickname, AccesoValesOxxoGas, AccesoRegistroKilometros FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s", (body.email.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        if row and row[4] and row[3] == body.password:
            return _build_login_response(body.email, row)
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")


# --- Cambio de contraseña (igual que Field: actual + nueva) ---

class ChangePasswordRequest(BaseModel):
    actual: str
    nueva: str


@app.post("/api/auth/change-password")
async def api_change_password(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    """Cambia el Password en HUB_Users tras verificar el actual. Mínimo 6 caracteres."""
    try:
        if not body.actual or not body.nueva:
            raise HTTPException(status_code=400, detail="Completa los tres campos.")
        if len(body.nueva) < 6:
            raise HTTPException(status_code=400, detail="La nueva contraseña debe tener mínimo 6 caracteres.")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Password, Activo FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s",
            (current_user["email"].strip().lower(),),
        )
        row = cursor.fetchone()
        if not row or not row[1]:
            conn.close()
            raise HTTPException(status_code=401, detail="Sesión no válida.")
        if row[0] != body.actual:
            conn.close()
            raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
        cursor.execute(
            "UPDATE HUB_Users SET Password = %s WHERE LTRIM(RTRIM(Email)) = %s",
            (body.nueva, current_user["email"].strip().lower()),
        )
        conn.close()
        return {"ok": True, "message": "Contraseña actualizada."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Info del dispositivo (IP vista por el servidor) ---

@app.get("/api/dispositivo/ip")
async def api_device_ip(request: Request, current_user: dict = Depends(get_current_user)):
    try:
        ip = request.client.host if request.client else "?"
    except Exception:
        ip = "?"
    return {"ip": ip}


# --- Push: enviar aviso (solo AccesoUsuarios; usa HUB_PushSubscriptions + VAPID) ---

class PushSendRequest(BaseModel):
    title: str
    body: str
    all: bool = True
    user_ids: List[int] = []


@app.post("/api/push/send")
async def api_push_send(body: PushSendRequest, current_user: dict = Depends(get_current_user)):
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="No access")
    if not body.title.strip() or not body.body.strip():
        raise HTTPException(status_code=400, detail="Escribe título y mensaje.")
    try:
        import json
        from pywebpush import webpush, WebPushException
    except ImportError:
        raise HTTPException(status_code=500, detail="pywebpush no instalado en el servidor.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # VAPID
        cursor.execute("SELECT VapidPublicKey, VapidPrivateKey FROM HUB_PushConfig WHERE Id = 1")
        vk = cursor.fetchone()
        if not vk or not vk[0] or not vk[1]:
            conn.close()
            raise HTTPException(status_code=500, detail="VAPID no configurado.")
        pub_key = vk[0].strip()
        priv_key = _normalizar_vapid_privada(vk[1])
        # Destinatarios
        if body.all:
            cursor.execute("SELECT Email FROM HUB_Users WHERE Activo = 1")
            emails = [r[0] for r in cursor.fetchall()]
        else:
            if not body.user_ids:
                conn.close()
                raise HTTPException(status_code=400, detail="Selecciona al menos un usuario o marca Todos.")
            ids = [int(i) for i in body.user_ids]
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(f"SELECT Email FROM HUB_Users WHERE Id IN ({placeholders})", tuple(ids))
            emails = [r[0] for r in cursor.fetchall()]
        if not emails:
            conn.close()
            return {"sent": 0}
        eph = ",".join(["%s"] * len(emails))
        # HUB_PushSuscripciones, NO HUB_PushSubscriptions: la vieja no tiene
        # columna App (por eso el aviso de una app caería dentro del service
        # worker de otra) y además está vacía, porque a ella solo escribe
        # `mcp_server` y el navegador de Admon se suscribe en la nueva. Con la
        # vieja, este botón decía "0 usuario(s)" siempre.
        cursor.execute(
            f"SELECT Endpoint, P256dhKey, AuthKey FROM HUB_PushSuscripciones "
            f"WHERE App = 'admon' AND Activo = 1 AND IdUsuario IN "
            f"(SELECT Id FROM HUB_Users WHERE LTRIM(RTRIM(Email)) IN ({eph}))",
            tuple(emails),
        )
        subs = cursor.fetchall()
        payload = json.dumps({"title": body.title.strip(), "body": body.body.strip()})
        sent = 0
        for endpoint, p256dh, auth_key in subs:
            try:
                webpush(
                    subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth_key}},
                    data=payload,
                    vapid_private_key=priv_key,
                    vapid_claims={"sub": "mailto:robot@ecc-sa.com.mx"},
                )
                sent += 1
            except WebPushException as e:
                if e.response is not None and e.response.status_code in (410, 404):
                    try:
                        cursor.execute("DELETE FROM HUB_PushSuscripciones WHERE Endpoint = %s", (endpoint,))
                        conn.commit()
                    except Exception:
                        pass
            except Exception:
                pass
        conn.close()
        return {"sent": sent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ─── Push: suscripción de la PWA ─────────────────────────────────────────────
# Estos cuatro endpoints son el otro lado de `notif_dispatch.py` (WorkersAdmon),
# que es quien ENVÍA los avisos. Aquí solo se guarda de qué dispositivo se trata.
#
# POR QUÉ LA TABLA ES `HUB_PushSuscripciones` Y NO `HUB_PushSubscriptions`
# --------------------------------------------------------------------------
# La vieja no tiene columna de app. Una suscripción creada desde
# admon.ecc-sa.com.mx quedaría indistinguible de una creada desde
# field.ecc-sa.com.mx, para el mismo usuario: al mandar un aviso, la librería
# elegiría todas sus suscripciones y el aviso de kilómetros de Field aparecería
# dentro de Admon. Notificaciones cruzadas entre apps, que es justo lo que hace
# que la gente desactive los permisos. La nueva (migración 0056) sí lleva `App`.
#
# La vieja se sigue usando en /api/push/send y no se toca.

APP_PUSH = "admon"


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: dict = {}
    plataforma: str = ""


def _vapid_publica():
    """La clave PÚBLICA de VAPID, que el navegador necesita para suscribirse.

    Solo se entrega la pública (es pública por definición: va dentro del bundle
    de la app de cualquiera). La privada nunca sale del servidor.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT VapidPublicKey FROM HUB_PushConfig WHERE Id = 1")
        row = cursor.fetchone()
        return (row[0] or "").strip() if row and row[0] else ""
    finally:
        conn.close()


def _detectar_plataforma(user_agent: str) -> str:
    """'iOS' | 'Android' | 'Escritorio'. Solo informativo: el panel dice
    '3 iPhone, 1 PC' en vez de un número pelado."""
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "iOS"
    # iPadOS 13+ se reporta como Macintosh, pero tiene puntos táctiles; aquí solo
    # llega el User-Agent, así que se resuelve por la palabra "Macintosh".
    if "macintosh" in ua:
        return "iOS"
    if "android" in ua:
        return "Android"
    return "Escritorio"


@app.get("/api/push/vapid-public-key")
async def api_push_vapid(current_user: dict = Depends(get_current_user)):
    """La clave pública de VAPID. El cliente la pide antes de suscribirse."""
    publica = _vapid_publica()
    if not publica:
        raise HTTPException(status_code=500, detail="VAPID no configurado.")
    return {"publicKey": publica}


@app.post("/api/push/subscribe")
async def api_push_subscribe(request: Request, body: PushSubscribeRequest,
                             current_user: dict = Depends(get_current_user)):
    """
    Registra (o re-registra) la suscripción de ESTE dispositivo.

    Es un UPSERT por endpoint. La re-registración es lo que hace `revincular()`
    en el cliente: la suscripción pertenece al service worker y sobrevive al
    cierre de sesión, así que si el usuario entra con otra cuenta en el mismo
    teléfono el endpoint seguiría apuntando al usuario anterior.

    SQL Server 2014 no tiene ON CONFLICT: se hace UPDATE y, si no tocó filas,
    INSERT. Un MERGE haría lo mismo en una sentencia, pero con triggers es
    notoriously difícil de depurar.
    """
    endpoint = (body.endpoint or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="Suscripción vacía")
    if len(endpoint) > 2000:
        raise HTTPException(status_code=400, detail="Suscripción demasiado larga")
    p256dh = str((body.keys or {}).get("p256dh") or "").strip()[:500]
    auth = str((body.keys or {}).get("auth") or "").strip()[:500]
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Suscripción incompleta")

    plataforma = (body.plataforma or "").strip()[:20] or _detectar_plataforma(
        request.headers.get("User-Agent", ""))

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE HUB_PushSuscripciones "
            "SET IdUsuario = %s, P256dhKey = %s, AuthKey = %s, Plataforma = %s, Activo = 1, "
            "    UltimoUso = GETDATE() "
            "WHERE Endpoint = %s",
            (current_user["id"], p256dh, auth, plataforma, endpoint),
        )
        if cursor.rowcount == 0:
            try:
                cursor.execute(
                    "INSERT INTO HUB_PushSuscripciones "
                    "(App, IdUsuario, Endpoint, P256dhKey, AuthKey, Plataforma, Creado, Activo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, GETDATE(), 1)",
                    (APP_PUSH, current_user["id"], endpoint, p256dh, auth, plataforma),
                )
            except Exception:
                # Carrera entre dos POST del mismo dispositivo: si otra petición
                # ganó, el UPDATE de arriba ya lo dejó bien. No es un error para
                # el usuario.
                cursor.execute(
                    "UPDATE HUB_PushSuscripciones SET IdUsuario = %s, Activo = 1 "
                    "WHERE Endpoint = %s",
                    (current_user["id"], endpoint),
                )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "plataforma": plataforma}


@app.post("/api/push/unsubscribe")
async def api_push_unsubscribe(body: PushSubscribeRequest,
                               current_user: dict = Depends(get_current_user)):
    """Da de baja SOLO este dispositivo. Las filas se marcan Activo=0 en vez de
    borrarse: si el usuario vuelve a entrar, la fila sigue ahí y reactivarla es
    un UPDATE en vez de un INSERT."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE HUB_PushSuscripciones SET Activo = 0 "
            "WHERE Endpoint = %s AND IdUsuario = %s",
            ((body.endpoint or "").strip(), current_user["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/push/suscripciones")
async def api_push_suscripciones(current_user: dict = Depends(get_current_user)):
    """Dispositivos de ESTE usuario, para poder decir 'este teléfono sí, esa
    laptop no'."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Id, Plataforma, Creado, UltimoUso FROM HUB_PushSuscripciones "
            "WHERE IdUsuario = %s AND App = %s AND Activo = 1 ORDER BY Creado DESC",
            (current_user["id"], APP_PUSH),
        )
        filas = cursor.fetchall()
        return {"suscripciones": [
            {"id": f[0], "plataforma": f[1] or "?", "creado": str(f[2]),
             "ultimoUso": str(f[3]) if f[3] else None}
            for f in filas]}
    finally:
        conn.close()


@app.post("/api/push/prueba")
async def api_push_prueba(current_user: dict = Depends(get_current_user)):
    """
    Manda un push de prueba a los dispositivos de QUIEN LO PIDIÓ.

    A propósito NO es un broadcast: el botón "🧪 Enviar prueba" de Config.svelte
    tiene que probar el teléfono de quien lo apretó, no avisar a todo el mundo de
    que alguien está probando. Por eso va por IdUsuario y no por un flag de "todos".

    Se manda con la misma ruta de envío que usa el worker (`eccsa_db` del
    WorkersAdmon no está en este contenedor), replicando su formato de payload:
    `badge_count` en vez de `badge` porque en iOS `badge` es un NÚMERO y en
    Android la URL de una imagen, y lo traduce el service worker.
    """
    try:
        import json
        from pywebpush import webpush, WebPushException
    except ImportError:
        raise HTTPException(status_code=500, detail="pywebpush no instalado en el servidor.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT VapidPrivateKey FROM HUB_PushConfig WHERE Id = 1")
        fila = cursor.fetchone()
        priv_key = (fila[0] or "").strip() if fila and fila[0] else ""
        if not priv_key:
            raise HTTPException(status_code=500, detail="VAPID no configurado.")
        # La privada tiene que estar en base64url de los 32 bytes CRUDOS. Si
        # alguien la dejó en PEM o DER, pywebpush falla siempre y el mensaje no
        # dice por qué (le pasó a Mailbox).
        priv_key = _normalizar_vapid_privada(priv_key)

        cursor.execute(
            "SELECT Endpoint, P256dhKey, AuthKey FROM HUB_PushSuscripciones "
            "WHERE IdUsuario = %s AND App = %s AND Activo = 1",
            (current_user["id"], APP_PUSH))
        subs = cursor.fetchall()
    finally:
        conn.close()

    if not subs:
        return {"sent": 0, "detail": "No hay ningún dispositivo suscrito en este equipo."}

    payload = json.dumps({
        "title": "🔔 Admon · aviso de prueba",
        "body": "Si lees esto, las notificaciones de Admon funcionan en este equipo.",
        "url": "/config",
        "tag": "admon-prueba",
        "badge_count": 1,
    })
    enviados, fallidos = 0, 0
    for endpoint, p256dh, auth_key in subs:
        try:
            webpush(
                subscription_info={"endpoint": endpoint,
                                   "keys": {"p256dh": p256dh, "auth": auth_key}},
                data=payload,
                vapid_private_key=priv_key,
                vapid_claims={"sub": "mailto:robot@ecc-sa.com.mx"},
            )
            enviados += 1
        except WebPushException as e:
            # 404/410 = la suscripción murió (se desinstaló la PWA). Se borra,
            # igual que hace el worker, para no reintentar contra la nada.
            if e.response is not None and e.response.status_code in (410, 404):
                conn = get_connection()
                try:
                    c2 = conn.cursor()
                    c2.execute("DELETE FROM HUB_PushSuscripciones WHERE Endpoint = %s",
                               (endpoint,))
                    conn.commit()
                finally:
                    conn.close()
            fallidos += 1
        except Exception:
            fallidos += 1

    return {"sent": enviados, "failed": fallidos,
            "detail": f"{enviados} enviado(s), {fallidos} sin éxito."}


def _normalizar_vapid_privada(priv: str) -> str:
    """Deja la clave privada en el formato que `pywebpush` sí entiende.

    Quiere base64url de los 32 bytes CRUDOS. Si quedó una PEM o un DER en
    base64, el envío falla SIEMPRE y el error que sale no dice nada útil: parece
    que el push no llegó a ningún dispositivo.
    """
    import base64
    original = (priv or "").strip()
    if not original:
        return original

    def _b64d(texto):
        pad = "=" * ((4 - len(texto) % 4) % 4)
        return base64.urlsafe_b64decode((texto + pad).replace("-", "+").replace("_", "/"))

    try:
        if len(_b64d(original)) == 32:
            return original
    except Exception:
        pass
    try:
        from cryptography.hazmat.primitives import serialization
        if "BEGIN" in original:
            clave = serialization.load_pem_private_key(original.encode(), password=None)
        else:
            clave = serialization.load_der_private_key(_b64d(original), password=None)
        crudo = clave.private_numbers().private_value.to_bytes(32, "big")
        return base64.urlsafe_b64encode(crudo).rstrip(b"=").decode()
    except Exception:
        return original

# --- User Endpoints ---

@app.get("/api/shell/state")
async def shell_state(request: Request, current_user: dict = Depends(get_current_user)):
    """Estado del banner común (ECCSA-Shell · docs/CONTRATO.md).
    El cliente combina esto con su store de sync (pendientes/sincronizando);
    aquí va lo que solo el servidor sabe: app, versiones, usuario y lugar.

    Admon autentica con `Authorization: Bearer`, igual que Field, así que el
    componente del shell necesita que la app le pase su propio `fetcher`."""
    import json
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _lee(nombre):
        try:
            with open(os.path.join(raiz, nombre), encoding="utf-8") as fh:
                return fh.read().strip() or "?"
        except OSError:
            return "?"

    # app.version = package.json (fuente única; el shell la estampa en shell.js)
    try:
        with open(os.path.join(raiz, "package.json"), encoding="utf-8") as fh:
            app_version = json.load(fh).get("version", "?")
    except (OSError, ValueError):
        app_version = "?"

    # lugar.py: X-Forwarded-For (primera entrada) → X-Real-IP → socket.
    modo, ip = lugar_de(request.headers,
                        request.client.host if request.client else "")
    return {
        "app": {"id": "admon", "nombre": "Admon", "version": app_version},
        "shell": {"version": _lee("ECCSA_SHELL_VERSION")},
        "user": {"nombre": current_user.get("nombre"),
                 "email": current_user.get("email"),
                 "rol": "admin" if current_user.get("acceso_usuarios") else "usuario"},
        "sync": {"estado": "idle", "pendientes": 0, "ultimo": None},
        "lugar": {"modo": modo, "ip": ip},
    }


@app.get("/api/inventory/items")
def get_inventory_items(current_user: dict = Depends(get_current_user)):
    """Listado del inventario.

    La columna de llave se llama `IdInventario`, no `Id`: con `Id` la consulta
    fallaba siempre con "Invalid column name 'Id'" y este endpoint devolvía 500
    en todas partes. Son 519 ítems, así que la pantalla los pagina de 100 en 100.
    """
    if not current_user["acceso_inventario"]:
        raise HTTPException(status_code=403, detail="No access")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT IdInventario, Marca, Modelo, Descripcion, Cantidad, StockMinimo, "
            "Ubicacion, Proveedor, Precio FROM HUB_Inventario ORDER BY IdInventario"
        )
        rows = cursor.fetchall()
        conn.close()
        conn = None
        items = []
        for row in rows:
            items.append({
                "id": row[0], "marca": row[1], "modelo": row[2], "descripcion": row[3],
                "cantidad": row[4], "stock_minimo": row[5], "ubicacion": row[6],
                "proveedor": row[7], "precio": float(row[8]) if row[8] else 0.0
            })
        return items
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/inventory/items/{item_id:int}")
def get_inventory_item(item_id: int, current_user: dict = Depends(get_current_user)):
    if not current_user["acceso_inventario"]:
        raise HTTPException(status_code=403, detail="No access")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Marca, Modelo, Descripcion, Cantidad, StockMinimo, Ubicacion, Proveedor, Precio FROM HUB_Inventario WHERE IdInventario = %s", (item_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0], "marca": row[1], "modelo": row[2], "descripcion": row[3],
                "cantidad": row[4], "stock_minimo": row[5], "ubicacion": row[6],
                "proveedor": row[7], "precio": float(row[8]) if row[8] else 0.0
            }
        raise HTTPException(status_code=404, detail="Item not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# `clientes` tiene 7 `IdCliente` repetidos (ATTC, Dail, GRMA, IJDM, ISAL, LEOS,
# SSMT) y no hay ninguna columna que diga cuál es el bueno: son registros viejos
# conviviendo con los actuales (Dail es 'DAIL' y también 'Sergio Salazar'). Un
# `LEFT JOIN clientes` a secas multiplica las filas de las 57 cotizaciones de
# esos clientes: salían duplicadas en el listado y sus importes se sumaban dos
# veces. Se agrupa por IdCliente y se toma el nombre menor, que al menos es
# estable entre llamadas. Para arreglarlo de fondo hay que limpiar esas 7
# filas duplicadas de `clientes`.
_CLIENTES_UNICOS = (
    "(SELECT IdCliente, MIN(Cliente) AS Cliente, MIN(CondicionesPagoDias) AS Dias "
    "FROM clientes GROUP BY IdCliente)"
)


# ── Avatares en miniatura ─────────────────────────────────────────────────────
# El ranking de Legends traía el avatar EN BASE64 de cada usuario: son PNG de
# 578×432, entre 150 y 310 KB cada uno, así que la respuesta pesaba 2.5 MB y
# tardaba 5 s. Los avatares se muestran en 128 px, así que se recortan aquí.
# La respuesta no cambia de forma (sigue siendo data:image/png;base64), así que
# el front no se entera.
#
# El recorte se memoriza: son siempre los mismos avatares yabrirlos cuesta
# ~50 ms la primera vez y ~5 ms después.
# Caché de miniaturas: (IdUsuario, longitud del base64) → miniatura.
# La longitud sirve de huella barata para detectar un avatar nuevo sin tener que
# traer el base64 completo (que son 150-310 KB por usuario).
_THUMBS: dict = {}


@lru_cache(maxsize=256)
def _recortar_avatar(b64: str, lado: int) -> str:
    """Recorta un avatar base64 a `lado` px."""
    from PIL import Image
    crudo = base64.b64decode(b64.split(",", 1)[-1])
    img = Image.open(io.BytesIO(crudo))
    img.thumbnail((lado, lado))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _avatar_thumb(b64: Optional[str], lado: int = 128) -> Optional[str]:
    """Recorta un avatar base64. Si algo falla devuelve el original."""
    if not b64:
        return None
    try:
        return _recortar_avatar(b64, lado)
    except Exception:
        return b64


def _avatares_miniatura(conn, ids: list, lado: int = 128) -> dict:
    """Miniaturas de varios usuarios, trayendo el base64 solo de los que faltan.

    Así el listado no arrastra 2.5 MB de avatares crudos en cada petición: solo
    se descargan los que aún no están en caché.
    """
    faltan = {}
    for i in ids:
        try:
            largo = _THUMBS_LEN.get(i)
        except Exception:
            largo = None
        if largo and (i, largo) not in _THUMBS:
            faltan[i] = largo
    if faltan:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT IdUsuario, AvatarBase64 FROM HUB_UserAvatars WHERE IdUsuario IN ("
            + ",".join(str(int(i)) for i in faltan) + ")"
        )
        for r in cur.fetchall():
            b64 = r.get("AvatarBase64")
            if not b64:
                continue
            try:
                _THUMBS[(int(r["IdUsuario"]), len(b64))] = _recortar_avatar(b64, lado)
            except Exception:
                pass
    salida = {}
    for i in ids:
        largo = _THUMBS_LEN.get(i)
        salida[i] = _THUMBS.get((i, largo)) if largo else None
    return salida


# Longitud del base64 de cada avatar con avatar, para poder checar la caché sin
# traer el contenido. Se llena una vez por petición.
_THUMBS_LEN: dict = {}


# --- Cotizaciones de materiales (réplica exacta del módulo HUB) ---
# Tablas: IndiceMateriales (Folio IDENTITY, IdCliente, Contacto, Fecha,
# Descripcion, Autor, Color, Nota) + Partidas (Folio, Partida, Cantidad,
# Descripcion, PrecioCompraUnitario, Factor, Proveedor, TiempoEntregaDias,
# Dolar, Flete). Vista: vw_ResumenCotizaciones. Folio display: CM00001.
# Fórmulas HUB: venta_unit = compra*(1+factor); total_item = venta_unit*cant+flete;
# subtotal = Σ; iva = subtotal*0.16; total = subtotal+iva.
# Color: 0 = enviada, 1 = lista para facturar, 2 = facturada (1 y 2 bloquean edición).

def _require_cotiz(current_user: dict):
    if not current_user.get("acceso_cotizaciones"):
        raise HTTPException(status_code=403, detail="No access")


def _fmt_folio(folio) -> str:
    try:
        return f"CM{int(folio):05d}"
    except Exception:
        return str(folio)


def _fnum(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0


def _fstr(v) -> str:
    try:
        return str(v)[:10] if v is not None else ""
    except Exception:
        return ""


def _partida_row_to_dict(folio, row) -> dict:
    # row: Partida, Cantidad, Descripcion, PrecioCompraUnitario, Factor,
    #      Proveedor, TiempoEntregaDias, Dolar, Flete,
    #      [+ SAT opcional: ClaveProdServ, ClaveUnidad, Fuente]  (LEFT JOIN sidecar)
    #      [+ ArticuloGenerico]  (va AL FINAL para no mover los índices SAT)
    compra = _fnum(row[3])
    factor = _fnum(row[4])
    cant = int(row[1] or 0)
    flete = _fnum(row[8])
    venta_unit = compra * (1.0 + factor)
    sat_prod = row[9] if len(row) > 9 else None
    sat_uni = row[10] if len(row) > 10 else None
    sat_fuente = row[11] if len(row) > 11 else None
    articulo = row[12] if len(row) > 12 else None
    return {
        "folio": folio, "partida": row[0], "cantidad": cant,
        "descripcion": row[2] or "", "precio_compra": compra, "factor": factor,
        "proveedor": row[5] or "", "tiempo_entrega": int(row[6] or 0),
        "dolar": _fnum(row[7]), "flete": flete,
        "venta_unit": venta_unit, "total_venta": venta_unit * cant + flete,
        "sat_prod_serv": sat_prod or "", "sat_unidad": sat_uni or "",
        "sat_fuente": sat_fuente or "",
        "articulo_generico": (articulo or "").strip(),
    }


# ----- Helpers de escritura (sin commit; el llamador hace commit) -----

def _db_get_color(cur, folio) -> Optional[int]:
    cur.execute("SELECT Color FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
    r = cur.fetchone()
    return None if not r else (int(r[0]) if r[0] is not None else 0)


def _db_create_quotation(cur, id_cliente, contacto, descripcion, autor) -> int:
    cur.execute(
        "INSERT INTO IndiceMateriales (IdCliente, Contacto, Fecha, Descripcion, Autor, Color) "
        "VALUES (%s, %s, GETDATE(), %s, %s, 0)",
        (id_cliente.strip().upper(), contacto.strip(), descripcion.strip(), autor),
    )
    cur.execute("SELECT @@IDENTITY")
    r = cur.fetchone()
    if not r or not r[0]:
        raise Exception("No se obtuvo el folio generado.")
    return int(r[0])


def _db_add_partida(cur, folio, cantidad, descripcion, precio_compra, factor, proveedor, tiempo_entrega, dolar, flete, articulo_generico=None) -> int:
    cur.execute("SELECT ISNULL(MAX(Partida), 0) + 1 FROM Partidas WHERE Folio = %s", (int(folio),))
    r = cur.fetchone()
    nxt = int(r[0]) if r and r[0] else 1
    cur.execute(
        "INSERT INTO Partidas (Folio, Partida, Cantidad, Descripcion, PrecioCompraUnitario, Factor, Proveedor, TiempoEntregaDias, Dolar, Flete, ArticuloGenerico) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (int(folio), nxt, int(cantidad), descripcion.strip(), float(precio_compra), float(factor),
         (proveedor or "").strip(), int(tiempo_entrega or 0), float(dolar or 0.0), float(flete or 0.0),
         _clean_articulo(articulo_generico)),
    )
    return nxt


def _db_clone_quotation(cur, folio, autor) -> int:
    cur.execute("SELECT IdCliente, Contacto, Descripcion, Color, Nota FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
    orig = cur.fetchone()
    if not orig:
        raise Exception("Cotización original no encontrada.")
    cur.execute(
        "INSERT INTO IndiceMateriales (IdCliente, Contacto, Fecha, Descripcion, Autor, Color, Nota) "
        "VALUES (%s, %s, GETDATE(), %s, %s, %s, %s)",
        (orig[0], orig[1], orig[2], autor, orig[3], orig[4]),
    )
    cur.execute("SELECT @@IDENTITY")
    r = cur.fetchone()
    if not r or not r[0]:
        raise Exception("No se obtuvo el folio clonado.")
    nuevo = int(r[0])
    cur.execute(
        "SELECT Partida, Cantidad, Descripcion, PrecioCompraUnitario, Factor, Proveedor, TiempoEntregaDias, Dolar, Flete, ArticuloGenerico "
        "FROM Partidas WHERE Folio = %s ORDER BY Partida ASC", (int(folio),))
    for p in cur.fetchall():
        cur.execute(
            "INSERT INTO Partidas (Folio, Partida, Cantidad, Descripcion, PrecioCompraUnitario, Factor, Proveedor, TiempoEntregaDias, Dolar, Flete, ArticuloGenerico) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (nuevo, p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9]),
        )
    # Copiar el snapshot SAT de las partidas originales al folio clonado
    # (el índice HUB_SatArticulos no se duplica, solo el sidecar por partida)
    try:
        cur.execute(
            "INSERT INTO HUB_PartidasSat (Folio, Partida, ClaveNormalizada, ClaveProdServ, ClaveUnidad, Fuente) "
            "SELECT %s, Partida, ClaveNormalizada, ClaveProdServ, ClaveUnidad, Fuente "
            "FROM HUB_PartidasSat WHERE Folio = %s",
            (nuevo, int(folio)))
    except Exception as e:
        print(f"[sat] Error copiando snapshot SAT al clonar: {e}")
    return nuevo


def _validate_partida_input(cantidad, descripcion):
    if int(cantidad or 0) < 1:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0.")
    if not (descripcion or "").strip():
        raise HTTPException(status_code=400, detail="La descripción es obligatoria.")


def _clean_articulo(v) -> str:
    """Artículo genérico (p. ej. 'disyuntor'): texto libre corto y en una sola
    línea, porque se imprime dentro de la celda de descripción del PDF."""
    return " ".join(str(v or "").split())[:200]


# ----- Modelos -----

class CotizacionCreate(BaseModel):
    id_cliente: str = ""
    contacto: str = ""
    descripcion: str = ""


class CotizacionUpdate(BaseModel):
    id_cliente: str = ""
    contacto: str = ""
    descripcion: str = ""
    color: int = 0


class CotizacionNota(BaseModel):
    nota: str = ""


class PartidaCreate(BaseModel):
    cantidad: int = 1
    descripcion: str = ""
    precio_compra: float = 0.0
    factor: float = 0.25
    proveedor: str = ""
    tiempo_entrega: int = 1
    dolar: float = 0.0
    flete: float = 0.0
    # Códigos SAT CFDI 4.0 (opcionales). Si llegan vacíos el servidor los
    # resuelve solo (sidecar → índice → reglas → Gemini); si llegan con valor
    # se guardan como captura MANUAL.
    sat_prod_serv: Optional[str] = None
    sat_unidad: Optional[str] = None
    # Artículo genérico del artículo en compras (NO es el código SAT):
    # "controlador lógico", "disyuntor", "cable de comunicación". Se imprime
    # en el PDF delante del código SAT y de la unidad.
    articulo_generico: Optional[str] = None


class PartidaUpdate(PartidaCreate):
    pass


class ClienteCreate(BaseModel):
    id_cliente: str = ""
    nombre: str = ""
    dias_pago: int = 30


class ClienteUpdate(BaseModel):
    nombre: str = ""
    dias_pago: int = 30


# ----- Índice / encabezado -----

# Cuántas cotizaciones trae el listado. Ojo: este tope NO es el que arregla la
# lentitud (eso era el GROUP BY sobre una columna varchar(max), ver la nota del
# endpoint). Es un tope de tamaño de la respuesta: con 1 203 cotizaciones el
# navegador tenía que pintar más de mil tarjetas.
#
# Si se baja de ~300, ojo con el buscador de la pantalla: filtra del lado del
# cliente sobre lo que llegó, así que un tope chico esconde de la búsqueda las
# cotizaciones más viejas. Si se quiere tope chico de verdad, el buscador tiene
# que pasar al servidor (parámetro de folio/cliente/texto).
TOP_COTIZACIONES = 100

# Cuántas cotizaciones se guardan en la copia offline (`/api/sync/pull`). Son 100
# a propósito y no más: ese endpoint se dispara al iniciar sesión, y bajar 500
# arrastraba 500 filas con su columna `Descripcion` y tardaba 28 s — con eso la
# app arrancaba lentísima. Con 100 baja a ~1 s y sin conexión se sigue teniendo
# la última pantalla para trabajar.
TOTAL_COTIZACIONES_MAX = 100

# Etiquetas de estatus por el campo Color de IndiceMateriales. La vista
# `vw_ResumenCotizaciones` hacía este mismo CASE; aquí se resuelve en Python
# para no depender de ella (ver la nota de abajo).
_ESTATUS_COLOR = {0: "PENDIENTE", 1: "ENTREGADA", 2: "PAGADA"}


def _listar_cotizaciones(conn, top: int = TOP_COTIZACIONES, pagina: int = 1,
                         q: str = "") -> tuple:
    """Listado de cotizaciones de materiales (compartido por dos endpoints).

    POR QUÉ NO SE USA LA VISTA `vw_ResumenCotizaciones`:
    esa vista hace `GROUP BY I.Descripcion`, que es varchar(max), una columna
    LOB; agrupar por una LOB cuesta ~26 s en SQL Server. Los índices no lo
    arreglan y no se crea ninguno: el problema es el tipo de la columna, no la
    falta de índice. Además la vista se equivocaba en los importes: hace
    `LEFT JOIN Clientes` y `Clientes` tiene 7 `IdCliente` repetidos (ATTC,
    Dail, GRMA, IJDM, ISAL, LEOS, SSMT), así que cada partida se contaba dos
    veces y el total salía al doble. El detalle y el PDF leen `Partidas` de
    forma directa, o sea que el listado mostraba una cifra que el PDF no
    respaldaba. Aquí el agregado sale de `Partidas` solo: la misma que usan el
    detalle y el PDF.

    Aquí van dos consultas baratas —encabezado y suma de partidas de esos
    folios— combinadas en Python: ~0.3 s.

    Los importes se calculan igual que en la vista:
      SumaPartidas = SUM((PrecioCompraUnitario * (1 + Factor)) * Cantidad)
      Flete        = MAX(Flete)
      Subtotal     = SumaPartidas + Flete
      IVA          = Subtotal * 0.16
      TotalFinal   = Subtotal * 1.16
    """
    cursor = conn.cursor(as_dict=True)

    # Búsqueda del servidor. OJO: no busca en `Descripcion` a propósito, es
    # varchar(max) y un `LIKE` sobre ella obliga a leer la tabla completa: con
    # el disco de ese SQL Server en frío eso son 25 s. Se busca por folio,
    # cliente, contacto, autor y estatus, que son columnas normales.
    texto = (q or "").strip()
    condiciones, params = [], []
    if texto:
        like = "%" + texto + "%"
        if texto.isdigit():
            condiciones.append("(I.Folio = %s OR I.Folio LIKE %s)")
            params += [int(texto), texto + "%"]
        # El nombre del cliente se busca con `IdCliente IN (subconsulta)` y NO
        # con `ISNULL(C.Cliente,'') LIKE`: ese ISNULL obliga a SQL Server a
        # recorrer clientes por cada cotización y el COUNT del total se iba a
        # 25 s. Con la subconsulta el mismo filtro tarda 0.01 s.
        condiciones.append(
            "(I.IdCliente IN (SELECT IdCliente FROM clientes WHERE Cliente LIKE %s) "
            "OR I.Contacto LIKE %s OR I.Autor LIKE %s)"
        )
        params += [like, like, like]
    where = (" WHERE " + " OR ".join(condiciones)) if condiciones else ""
    paginas = max(1, int(pagina))
    top = max(1, int(top))
    inicio = (paginas - 1) * top

    # ── Dos consultas, y el orden importa ──
    # 1) Los FOLIOS de la página, sin la columna de descripción.
    #    Saltar con `OFFSET n` sobre una consulta que sí trae `Descripcion`
    #    obligaba a SQL Server a leer y descartar las n filas anteriores con su
    #    texto: la página 13 ( OFFSET 1200 ) tardó 28 s con el caché en frío.
    #    Con solo el folio el salto se resuelve por el índice y es instantáneo.
    sql_folios = ("SELECT I.Folio FROM IndiceMateriales I" + where +
                  " ORDER BY I.Folio DESC OFFSET %d ROWS FETCH NEXT %d ROWS ONLY"
                  % (inicio, top))
    cursor.execute(sql_folios, tuple(params))
    folios = [r["Folio"] for r in cursor.fetchall()]

    if texto:
        cursor.execute("SELECT COUNT(*) AS n FROM IndiceMateriales I" + where, tuple(params))
        total = int(cursor.fetchone()["n"] or 0)
    else:
        cursor.execute("SELECT COUNT(*) AS n FROM IndiceMateriales")
        total = int(cursor.fetchone()["n"] or 0)

    # 2) El detalle de esos folios: aquí sí se lee `Descripcion`, pero solo de
    #    las 100 filas que se van a mostrar.
    cabeceras = []
    if folios:
        lista = ",".join(str(int(f)) for f in folios)
        cursor.execute(
            "SELECT I.Folio, I.IdCliente, ISNULL(C.Cliente, '') AS Cliente, I.Contacto, "
            "I.Fecha, I.Descripcion, I.Autor, I.Color "
            "FROM IndiceMateriales I LEFT JOIN " + _CLIENTES_UNICOS +
            " C ON C.IdCliente = I.IdCliente WHERE I.Folio IN (" + lista + ")"
        )
        por_folio = {r["Folio"]: r for r in cursor.fetchall()}
        cabeceras = [por_folio[f] for f in folios if f in por_folio]

    # 2) Suma de partidas SOLO de las cotizaciones que se devuelven.
    #    Antes se agregaba la tabla entera (1 179 folios) y se descartaban más
    #    de mil: con `Partidas` sin índice es un GROUP BY completo, y con la
    #    base en frío llegó a tardar 20 s. Filtrar por la lista de folios deja
    #    el trabajo en unas 200 filas.
    folios = [r["Folio"] for r in cabeceras]
    agg = {}
    if folios:
        # pymssql no admite `?` ni listas expandidas: se interpolan los folios,
        # que vienen de la BD como numéricos.
        lista = ",".join(str(int(f)) for f in folios)
        cursor.execute(
            "SELECT Folio, SUM((PrecioCompraUnitario * (1.0 + Factor)) * Cantidad) AS Suma, "
            f"ISNULL(MAX(Flete), 0) AS Flete FROM Partidas "
            f"WHERE Folio IN ({lista}) GROUP BY Folio"
        )
        agg = {r["Folio"]: (r["Suma"], r["Flete"]) for r in cursor.fetchall()}

    salida = []
    for r in cabeceras:
        folio = r["Folio"]
        suma, flete = agg.get(folio, (0, 0))
        suma = float(suma or 0)
        flete = float(flete or 0)
        subtotal = suma + flete
        salida.append({
            "folio": folio, "folio_fmt": _fmt_folio(folio),
            "id_cliente": r["IdCliente"] or "", "cliente": r["Cliente"] or "",
            "contacto": r["Contacto"] or "", "fecha": _fstr(r["Fecha"]),
            "descripcion": r["Descripcion"] or "", "autor": r["Autor"] or "",
            "estatus": _ESTATUS_COLOR.get(int(r["Color"] or 0), "DESCONOCIDO"),
            "suma_partidas": _fnum(suma), "flete": _fnum(flete),
            "subtotal": _fnum(subtotal), "iva": _fnum(subtotal * 0.16),
            "total": _fnum(subtotal * 1.16),
        })
    return salida, total


@app.post("/api/sync/push")
async def sync_push(body: SyncPushRequest, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    autor = current_user.get("nombre") or current_user.get("email")
    results = []
    idmap: Dict[str, int] = {}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for it in body.items:
            r: dict = {"id_local": it.id_local, "status": "error", "message": ""}
            try:
                p = it.payload or {}

                def _folio_of(pl: dict) -> Optional[int]:
                    if pl.get("folio") is not None:
                        return int(pl["folio"])
                    lid = pl.get("id_local") or it.id_local
                    return idmap.get(lid)

                if it.entity == "cotizacion" and it.action == "create":
                    folio = _db_create_quotation(cursor, p.get("id_cliente", ""), p.get("contacto", ""),
                                                 p.get("descripcion", ""), autor)
                    idmap[it.id_local] = folio
                    r.update({"status": "ok", "folio": folio, "folio_fmt": _fmt_folio(folio)})
                elif it.entity == "cotizacion" and it.action == "update":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    cursor.execute(
                        "UPDATE IndiceMateriales SET IdCliente = %s, Contacto = %s, Descripcion = %s, Color = %s WHERE Folio = %s",
                        ((p.get("id_cliente") or "").strip().upper(), (p.get("contacto") or "").strip(),
                         (p.get("descripcion") or "").strip(), int(p.get("color", 0)), folio),
                    )
                    r.update({"status": "ok", "folio": folio})
                elif it.entity == "cotizacion" and it.action == "delete":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    cursor.execute("DELETE FROM Partidas WHERE Folio = %s", (folio,))
                    try:
                        cursor.execute("DELETE FROM HUB_PartidasSat WHERE Folio = %s", (folio,))
                    except Exception:
                        pass
                    cursor.execute("DELETE FROM IndiceMateriales WHERE Folio = %s", (folio,))
                    r.update({"status": "ok", "folio": folio})
                elif it.entity == "cotizacion" and it.action == "nota":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    cursor.execute("UPDATE IndiceMateriales SET Nota = %s WHERE Folio = %s",
                                   ((p.get("nota") or "").strip(), folio))
                    r.update({"status": "ok", "folio": folio})
                elif it.entity == "partida" and it.action == "add":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    num = _db_add_partida(cursor, folio, int(p.get("cantidad", 1)), p.get("descripcion", ""),
                                          float(p.get("precio_compra", 0.0)), float(p.get("factor", 0.0)),
                                          p.get("proveedor", ""), int(p.get("tiempo_entrega", 0) or 0),
                                          float(p.get("dolar", 0.0) or 0.0), float(p.get("flete", 0.0) or 0.0),
                                          p.get("articulo_generico"))
                    # Hook SAT igual que en el POST online (la cola trae los campos si el cliente los envió)
                    try:
                        sat_helper.guardar_partida_sat(
                            cursor, folio, num, p.get("descripcion", ""),
                            p.get("sat_prod_serv"), p.get("sat_unidad"))
                    except Exception as e:
                        print(f"[sat] sync add: {e}")
                    r.update({"status": "ok", "folio": folio, "partida": num})
                elif it.entity == "partida" and it.action == "update":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    cursor.execute(
                        "UPDATE Partidas SET Cantidad = %s, Descripcion = %s, PrecioCompraUnitario = %s, "
                        "Factor = %s, Proveedor = %s, TiempoEntregaDias = %s, Dolar = %s, Flete = %s, "
                        "ArticuloGenerico = %s "
                        "WHERE Folio = %s AND Partida = %s",
                        (int(p.get("cantidad", 1)), (p.get("descripcion") or "").strip(),
                         float(p.get("precio_compra", 0.0)), float(p.get("factor", 0.0)),
                         (p.get("proveedor") or "").strip(), int(p.get("tiempo_entrega", 0) or 0),
                         float(p.get("dolar", 0.0) or 0.0), float(p.get("flete", 0.0) or 0.0),
                         _clean_articulo(p.get("articulo_generico")),
                         folio, int(p.get("partida", 0))),
                    )
                    try:
                        sat_helper.guardar_partida_sat(
                            cursor, folio, int(p.get("partida", 0)), (p.get("descripcion") or "").strip(),
                            p.get("sat_prod_serv"), p.get("sat_unidad"))
                    except Exception as e:
                        print(f"[sat] sync update: {e}")
                    r.update({"status": "ok", "folio": folio})
                elif it.entity == "partida" and it.action == "delete":
                    folio = _folio_of(p)
                    if folio is None:
                        raise Exception("Sin folio (aún no sincronizada).")
                    cursor.execute("DELETE FROM Partidas WHERE Folio = %s AND Partida = %s",
                                   (folio, int(p.get("partida", 0))))
                    try:
                        cursor.execute("DELETE FROM HUB_PartidasSat WHERE Folio = %s AND Partida = %s",
                                       (folio, int(p.get("partida", 0))))
                    except Exception:
                        pass
                    r.update({"status": "ok", "folio": folio})
                else:
                    r["message"] = f"Entidad/acción no soportada: {it.entity}/{it.action}"
            except Exception as e:
                r["message"] = str(e)[:200]
            results.append(r)
        conn.commit()
        conn.close()
        return {"results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/sync/pull")
def sync_pull(current_user: dict = Depends(get_current_user)):
    """Descarga para la caché offline (cotizaciones + clientes).

    Este endpoint corría en el prefetch que dispara el login, y usaba la misma
    consulta lenta de 999 filas de la vista: entrar a la app congelaba el
    servidor ~26 s. Reusa el listado ya corregido y, como es `def`, no bloquea
    el event loop.
    """
    _require_cotiz(current_user)
    conn = None
    try:
        conn = get_connection()
        filas, _ = _listar_cotizaciones(conn, top=TOTAL_COTIZACIONES_MAX)
        cots = [{"folio": r["folio"], "id_cliente": r["id_cliente"], "cliente": r["cliente"],
                 "contacto": r["contacto"], "fecha": r["fecha"], "descripcion": r["descripcion"],
                 "autor": r["autor"], "estatus": r["estatus"], "suma_partidas": r["suma_partidas"],
                 "flete": r["flete"], "subtotal": r["subtotal"], "iva": r["iva"], "total": r["total"]}
                for r in filas]
        cursor = conn.cursor()
        cursor.execute("SELECT IdCliente, Cliente, CondicionesPagoDias FROM clientes ORDER BY IdCliente ASC")
        clis = [{"id_cliente": r[0], "nombre": r[1], "dias_pago": r[2]} for r in cursor.fetchall()]
        conn.close()
        conn = None
        return {"cotizaciones": cots, "clientes": clis}
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Dashboard endpoint ---

class KPIData(BaseModel):
    modulo: str
    valor: float
    etiqueta: str


@app.get("/")
async def spa_root():
    if _has_spa:
        return _spa_file("index.html")
    return {"message": "HUB Admon API", "version": "1.0.0"}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
        # 1) Archivo real de dist/ (logo, favicon, iconos, etc.)
        if _has_spa:
            candidate = (_dist / full_path)
            try:
                # Evitar path traversal fuera de dist/
                candidate.resolve().relative_to(_dist.resolve())
            except ValueError:
                raise HTTPException(status_code=404, detail="Not found")
            if full_path and candidate.is_file():
                resp = FileResponse(str(candidate))
                if candidate.name in _NO_STORE_FILES:
                    resp.headers.update(_NO_STORE)
                return resp
            # 2) Ruta de la SPA -> index.html (el router del frontend decide)
            first = full_path.split("/", 1)[0]
            if first in _SPA_ROUTES:
                return _spa_file("index.html")
        raise HTTPException(status_code=404, detail="Not found")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
