from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse, Response
from api.pdf_cotizacion import build_cotizacion_pdf
from api.pdf_reporte import build_service_report_pdf
from api.pdf_remision import build_remision_pdf
from api.lugar import lugar_de
from api import sat_helper
from api import usuarios_foto as _foto_usuario
from api import ficha_nfc as _ficha_nfc
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

@app.get("/api")
async def api_info():
    return {"message": "HUB Admon API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


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


@app.get("/api/users/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserInfo(**current_user)


@app.get("/api/users", response_model=List[UserInfo])
async def get_users(current_user: dict = Depends(get_current_user)):
    """Get all users - admin only"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Email, AccesoInventario, AccesoNominas, AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, AccesoUsuarios, ISNULL(Puesto, '') FROM HUB_Users")
        rows = cursor.fetchall()
        # MAC del celular por usuario (para el badge 📡 de la lista);
        # solo activas: es lo que el escáner mide para entradas/salidas.
        cursor.execute("""
            SELECT IdUsuario, MACAddress FROM HUB_NetworkDevices
            WHERE Activo = 1 AND Tipo = 'CELULAR' AND IdUsuario IS NOT NULL
        """)
        macs = {r[0]: (r[1] or "").strip() for r in cursor.fetchall()}
        # Un solo SELECT para saber quiénes tienen foto (no se traen binarios).
        con_foto = set(_foto_usuario.listar_fotos(get_connection))
        conn.close()
        result = []
        for row in rows:
            result.append(UserInfo(
                id=row[0], nombre=row[1], email=row[2],
                acceso_inventario=row[3] == 1,
                acceso_nominas=row[4] == 1,
                acceso_cotizaciones=row[5] == 1,
                acceso_proveedores=row[6] == 1,
                acceso_oc=row[7] == 1,
                acceso_calculo=row[8] == 1,
                acceso_usuarios=row[10] == 1,
                mac_telefono=macs.get(row[0], ""),
                puesto=row[11] or "",
                tiene_foto=row[0] in con_foto,
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/usuarios")
async def api_list_usuarios(current_user: dict = Depends(get_current_user)):
    """Catálogo ligero {Id, Nombre, Activo} de HUB_Users para los selects de
    técnicos en el detalle/edición de reportes (la página pide /api/usuarios;
    antes no existía y el select quedaba siempre vacío). Mismo permiso que
    los reportes. El prefetch offline también lo cachea."""
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Activo FROM HUB_Users ORDER BY Nombre")
        rows = cursor.fetchall()
        conn.close()
        # Activo como entero 1/0: el frontend filtra con `Activo === 1`
        return [{"Id": r[0], "Nombre": r[1], "Activo": 1 if r[2] else 0} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Detalle / edición de usuario (espejo del Administrador de Usuarios del HUB) ---

# Columnas de HUB_Users administrables (mismo orden que get_all_hub_users del HUB)
def _config_ficha(connect_fn):
    """(secreto, base_url) de las fichas NFC. Lee HUB_Config una vez.

    Se lee aquí y no por usuario: son dos valores constantes para toda la
    pantalla, y meterlos en el SELECT de cada usuario sería una ida a la BD por
    persona. Si falta el secreto se devuelve ("", "") y el frontend simply no
    muestra el enlace, en vez de romper la lista.
    """
    try:
        conn = connect_fn()
        cur = conn.cursor()
        cur.execute(
            "SELECT Clave, Valor FROM HUB_Config "
            "WHERE Clave IN ('colab_ficha_secreto', 'colab_ficha_base_url')"
        )
        valores = {k: (v or "").strip() for k, v in cur.fetchall()}
        conn.close()
        return (valores.get("colab_ficha_secreto", ""),
                valores.get("colab_ficha_base_url", "")
                or _ficha_nfc.BASE_POR_DEFECTO)
    except Exception as e:
        print(f"[ficha_nfc] no se pudo leer la config: {e}")
        return "", _ficha_nfc.BASE_POR_DEFECTO


_USER_COLS = (
    "Id, Email, Nombre, Password, Activo, FechaIngreso, CurpRfc, "
    "AccesoCotizaciones, AccesoVM, AccesoConfiguracion, AccesoUsuarios, AccesoReportes, "
    "AccesoRegistroReportes, AccesoCotizacionesReportes, AccesoClientes, AccesoRegistroKilometros, "
    "AccesoAutomoviles, AccesoVacaciones, AccesoConfigurarCorreo, AccesoConfigAI, "
    "Notificaciones, AccesoMisVacaciones, AccesoHorasExtras, AccesoMisHorasExtras, AccesoOxxoGas, "
    "AccesoValesOxxoGas, AccesoRegistroTicketOxxoGas, AccesoEdicionBD, AccesoNominas, AccesoInventario, "
    "AccesoCalculo, AccesoProveedores, AccesoOC, AccesoAppConfig, AccesoSolicitarVales, "
    "AccesoAdminVales, AccesoConfigOxxogas, AccesoDeteccionRed, AccesoPdfConfig, "
    "NSS, Puesto"
)
# Orden propio (cada columna UNA vez): _user_row_to_dict usa índices fijos
# id=0, email=1, nombre=2, password=3, activo=4, fecha_ingreso=5, curp_rfc=6,
# accesos desde 7 en el orden de `keys`, y al final nss=39 y puesto=40.


def _require_admin(current_user: dict):
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="No access")


def _user_row_to_dict(row) -> dict:
    d = {
        "id": row[0], "email": row[1], "nombre": row[2], "password": row[3],
        "activo": bool(row[4]),
        "fecha_ingreso": str(row[5])[:10] if row[5] else None,
        "curp_rfc": row[6] or "",
    }
    keys = [
        "AccesoCotizaciones", "AccesoVM", "AccesoConfiguracion", "AccesoUsuarios", "AccesoReportes",
        "AccesoRegistroReportes", "AccesoCotizacionesReportes", "AccesoClientes", "AccesoRegistroKilometros",
        "AccesoAutomoviles", "AccesoVacaciones", "AccesoConfigurarCorreo", "AccesoConfigAI",
        "Notificaciones", "AccesoMisVacaciones", "AccesoHorasExtras", "AccesoMisHorasExtras", "AccesoOxxoGas",
        "AccesoValesOxxoGas", "AccesoRegistroTicketOxxoGas", "AccesoEdicionBD", "AccesoNominas", "AccesoInventario",
        "AccesoCalculo", "AccesoProveedores", "AccesoOC", "AccesoAppConfig",
        "AccesoSolicitarVales", "AccesoAdminVales", "AccesoConfigOxxogas", "AccesoDeteccionRed", "AccesoPdfConfig",
    ]
    for i, k in enumerate(keys):
        v = row[7 + i]
        d[k] = (v == 1) if v is not None else False
    # NSS y Puesto van al FINAL de _USER_COLS para no mover los índices de los
    # accesos (migración 0045). Se normalizan a texto para que el front no
    # tenga que distinguir '' de None.
    d["nss"] = str(row[7 + len(keys)] or "").strip()
    d["puesto"] = str(row[8 + len(keys)] or "").strip()
    return d


@app.get("/api/users/{user_id:int}")
async def get_user_detail(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {_USER_COLS} FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return _user_row_to_dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/users/{user_id:int}/ficha")
async def get_user_ficha(user_id: int, current_user: dict = Depends(get_current_user)):
    """Enlace publico de la tarjeta NFC de un usuario, para copiarlo.

    Se devuelve aqui y no se mete en `/api/users` porque la lista es de todos los
    usuarios y el enlace solo hace falta en el detalle, que es donde se esta
    grabando la tarjeta. Asi tampoco viaja en cada listado.
    """
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        secreto, base = _config_ficha(get_connection)
        return {
            "id": row[0],
            "slug": _ficha_nfc.slug_de(row[1], row[0], secreto),
            "url": _ficha_nfc.url_de(row[1], row[0], secreto, base),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class UserUpdateRequest(BaseModel):
    nombre: str = ""
    email: str = ""
    password: str = ""
    activo: bool = True
    fecha_ingreso: Optional[str] = None
    curp_rfc: str = ""
    nss: str = ""
    puesto: str = ""
    accesos: Dict[str, bool] = {}


@app.put("/api/users/{user_id:int}")
async def update_user_detail(user_id: int, body: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if not body.nombre.strip() or not body.email.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Nombre, correo y contraseña son obligatorios.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sets = ["Nombre = %s", "Email = %s", "Password = %s", "Activo = %s", "FechaIngreso = %s", "CurpRfc = %s",
                "NSS = %s", "Puesto = %s"]
        vals: list = [
            body.nombre.strip(), body.email.strip().lower(), body.password,
            1 if body.activo else 0,
            body.fecha_ingreso or None,
            (body.curp_rfc or "").strip() or None,
            _clean_nss(body.nss),
            (body.puesto or "").strip()[:120] or None,
        ]
        allowed = [
            "AccesoCotizaciones", "AccesoVM", "AccesoConfiguracion", "AccesoUsuarios", "AccesoReportes",
            "AccesoRegistroReportes", "AccesoCotizacionesReportes", "AccesoClientes", "AccesoRegistroKilometros",
            "AccesoAutomoviles", "AccesoVacaciones", "AccesoConfigurarCorreo", "AccesoConfigAI",
            "Notificaciones", "AccesoMisVacaciones", "AccesoHorasExtras", "AccesoMisHorasExtras", "AccesoOxxoGas",
            "AccesoValesOxxoGas", "AccesoRegistroTicketOxxoGas", "AccesoEdicionBD", "AccesoNominas", "AccesoInventario",
            "AccesoCalculo", "AccesoProveedores", "AccesoOC", "AccesoAppConfig",
            "AccesoSolicitarVales", "AccesoAdminVales", "AccesoConfigOxxogas", "AccesoDeteccionRed", "AccesoPdfConfig",
        ]
        for k in allowed:
            sets.append(f"{k} = %s")
            vals.append(1 if body.accesos.get(k, False) else 0)
        vals.append(int(user_id))
        cursor.execute(f"UPDATE HUB_Users SET {', '.join(sets)} WHERE Id = %s", tuple(vals))
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/users/{user_id:int}")
async def delete_user_detail(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Email, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if (row[0] or "").strip().lower() == (current_user.get("email") or "").strip().lower():
            conn.close()
            raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta.")
        try:
            cursor.execute("DELETE FROM HUB_Users WHERE Id = %s", (int(user_id),))
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=400, detail=f"No se pudo eliminar (referencias en otros módulos): {str(e)[:150]}")
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Teléfono / MAC del usuario (relación con HUB_NetworkDevices) ---
# La tabla HUB_NetworkDevices es la que usa el escáner de red (módulo Detección
# de Red 📡) para medir ENTRADAS y SALIDAS de la oficina: si la MAC del celular
# aparece en la red, el usuario está aquí. Aquí solo se gestiona la fila
# vinculada al usuario (IdUsuario); nunca se borra (HUB_NetworkPresence y
# HUB_NetworkState tienen FK hacia ella) — al quitar la MAC se desvincula y se
# marca Activo = 0, así el historial de eventos queda intacto.

def _normalizar_mac(valor) -> Optional[str]:
    """'aa-bb-cc-dd-ee-ff' / 'aabbccddeeff' / 'aabb.ccdd.eeff' → 'AA:BB:CC:DD:EE:FF'.

    Devuelve None si no son 12 dígitos hexadecimales (formato que espera
    HUB_NetworkDevices.MACAddress, varchar(17)).
    """
    s = (valor or "").strip().upper().replace(":", "").replace("-", "").replace(".", "")
    if len(s) != 12 or any(c not in "0123456789ABCDEF" for c in s):
        return None
    return ":".join(s[i:i + 2] for i in range(0, 12, 2))


def _telefono_del_usuario(user_id: int, conn=None) -> dict:
    """Lee el celular vinculado al usuario + su presencia en la red.

    Devuelve siempre la misma forma aunque no haya MAC: la página la usa tanto
    para pintar el formulario como para mostrar 'AQUI/FUERA' y el último
    evento de entrada/salida.
    """
    propia = conn is None
    if propia:
        conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, MACAddress, NombreDispositivo, Activo, FechaRegistro
            FROM HUB_NetworkDevices
            WHERE IdUsuario = %s AND Tipo = 'CELULAR'
            ORDER BY Activo DESC, FechaRegistro DESC, Id DESC
        """, (int(user_id),))
        devs = cursor.fetchall()
        dev = next((d for d in devs if d["Activo"]), (devs[0] if devs else None))
        out = {
            "id_dispositivo": int(dev["Id"]) if dev else None,
            "mac": (dev["MACAddress"] or "").strip() if dev else "",
            "nombre_dispositivo": (dev["NombreDispositivo"] or "").strip() if dev else "",
            "activo": bool(dev["Activo"]) if dev else False,
            "estado": None,
            "ultima_vez_en_red": None,
            "ultimo_evento": None,
        }
        if not dev:
            return out
        # Estado en vivo del escáner (AQUI = detectado en la última red)
        cursor.execute("""
            SELECT Estado, UltimaVezEnRed FROM HUB_NetworkState
            WHERE IdDispositivo = %s
        """, (int(dev["Id"]),))
        st = cursor.fetchone()
        if st:
            out["estado"] = st["Estado"]
            out["ultima_vez_en_red"] = st["UltimaVezEnRed"].isoformat() if st["UltimaVezEnRed"] else None
        # Último evento de presencia (ENTRADA / SALIDA)
        cursor.execute("""
            SELECT TOP 1 TipoEvento, FechaHora FROM HUB_NetworkPresence
            WHERE IdDispositivo = %s ORDER BY Id DESC
        """, (int(dev["Id"]),))
        ev = cursor.fetchone()
        if ev:
            out["ultimo_evento"] = {
                "tipo": ev["TipoEvento"],
                "fecha": ev["FechaHora"].isoformat() if ev["FechaHora"] else None,
            }
        return out
    finally:
        if propia:
            conn.close()


class TelefonoMacRequest(BaseModel):
    mac: str = ""
    nombre_dispositivo: str = ""


@app.get("/api/users/{user_id:int}/telefono")
async def get_user_telefono(user_id: int, current_user: dict = Depends(get_current_user)):
    """MAC del celular vinculado + estado de presencia (¿está en la oficina?)."""
    _require_admin(current_user)
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT Id FROM HUB_Users WHERE Id = %s", (int(user_id),))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            return _telefono_del_usuario(user_id, conn)
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/users/{user_id:int}/telefono")
async def set_user_telefono(user_id: int, body: TelefonoMacRequest,
                            current_user: dict = Depends(get_current_user)):
    """Vincula (o desvincula) la MAC del celular al usuario.

    Upsert sobre HUB_NetworkDevices:
      · MAC vacía        → desvincula el celular del usuario (Activo = 0,
                           IdUsuario = NULL); NO se borra la fila porque
                           HUB_NetworkPresence/HUB_NetworkState dependen de ella.
      · MAC ya en uso    → si es de OTRO usuario activo, 400 (evita que dos
                           personas midan la misma MAC).
      · MAC existente    → se reutiliza la fila (realectiva si estaba apagada).
      · MAC nueva        → si el usuario tenía otra fila CELULAR se le cambia
                           la MAC; si no, se inserta una fila nueva.
    """
    _require_admin(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        nombre = (body.nombre_dispositivo or "").strip()
        mac = (body.mac or "").strip()

        # 1) MAC vacía → desvincular sin borrar historial
        if not mac:
            cursor.execute("""
                UPDATE HUB_NetworkDevices SET Activo = 0, IdUsuario = NULL
                WHERE IdUsuario = %s AND Tipo = 'CELULAR'
            """, (int(user_id),))
            conn.commit()
            return {"ok": True, **_telefono_del_usuario(user_id, conn)}

        # 2) validar formato
        normalizada = _normalizar_mac(mac)
        if not normalizada:
            raise HTTPException(status_code=400, detail="MAC inválida: usa 12 dígitos hex (ej. EE:E2:FD:A3:43:EC).")

        # 3) ¿ya la usa OTRO usuario activo?
        cursor.execute("""
            SELECT TOP 1 d.Id, d.IdUsuario, u.Nombre
            FROM HUB_NetworkDevices d
            LEFT JOIN HUB_Users u ON u.Id = d.IdUsuario
            WHERE LTRIM(RTRIM(d.MACAddress)) = %s AND d.Activo = 1
              AND d.IdUsuario IS NOT NULL AND d.IdUsuario <> %s
        """, (normalizada, int(user_id)))
        otra = cursor.fetchone()
        if otra:
            raise HTTPException(
                status_code=400,
                detail=f"Esa MAC ya está registrada a {(otra['Nombre'] or '').strip() or 'otro usuario'}. "
                       f"Quítala primero desde su ficha de usuario.",
            )

        # 4) upsert: reactivar fila con esa MAC / cambiar la MAC del usuario / insertar
        cursor.execute("""
            SELECT Id FROM HUB_NetworkDevices
            WHERE LTRIM(RTRIM(MACAddress)) = %s
            ORDER BY Activo DESC, Id DESC
        """, (normalizada,))
        existente = cursor.fetchone()
        if existente:
            sets, vals = ["MACAddress = %s", "IdUsuario = %s", "Activo = 1"], [normalizada, int(user_id)]
        else:
            cursor.execute("""
                SELECT TOP 1 Id FROM HUB_NetworkDevices
                WHERE IdUsuario = %s AND Tipo = 'CELULAR'
                ORDER BY Activo DESC, Id DESC
            """, (int(user_id),))
            previo = cursor.fetchone()
            if previo:
                sets, vals = ["MACAddress = %s", "Activo = 1"], [normalizada]
                existente = previo
            else:
                sets, vals = ["MACAddress = %s", "IdUsuario = %s", "Activo = 1", "FechaRegistro = GETDATE()"],                              [normalizada, int(user_id)]
        if nombre:
            sets.append("NombreDispositivo = %s")
            vals.append(nombre[:100])
        if existente:
            cursor.execute(f"UPDATE HUB_NetworkDevices SET {', '.join(sets)} WHERE Id = %s",
                           tuple(vals + [int(existente["Id"])]))
        else:
            cursor.execute(f"""
                INSERT INTO HUB_NetworkDevices (MACAddress, NombreDispositivo, IdUsuario, Tipo, Activo)
                VALUES (%s, %s, %s, 'CELULAR', 1)
            """, (normalizada, nombre[:100] or None, int(user_id)))
        conn.commit()
        return {"ok": True, **_telefono_del_usuario(user_id, conn)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


# --- NSS / Puesto / Foto del usuario ---------------------------------------
# NSS y Puesto son columnas de HUB_Users (migración 0045) y se editan junto con
# el resto de la ficha. La foto va en HUB_UsuariosFotos (tabla aparte, para no
# engordar HUB_Users) con su propio par de endpoints: subir y borrar.

def _clean_nss(valor) -> Optional[str]:
    """NSS: solo dígitos. El capture también pone guiones ('123-45-6789') y a
    veces 11 dígitos; se deja como 11 dígitos, sin guiones ni espacios, que es
    como lo usa el imss. Vacío = NULL (no se capturó)."""
    d = "".join(c for c in str(valor or "") if c.isdigit())
    if not d:
        return None
    return d[:20]


class FotoUsuarioRequest(BaseModel):
    contenido_base64: str
    content_type: str = "image/jpeg"


@app.get("/api/users/{user_id:int}/foto")
async def get_user_foto(user_id: int, current_user: dict = Depends(get_current_user)):
    """Foto del usuario en binario. Devuelve 404 si no tiene foto, para que el
    front pueda pintar un avatar con iniciales sin descargar nada."""
    _require_admin(current_user)
    foto = _foto_usuario.leer_foto_usuario(get_connection, user_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Este usuario no tiene foto.")
    return Response(content=foto["bytes"], media_type=foto["content_type"])


@app.put("/api/users/{user_id:int}/foto")
async def set_user_foto(user_id: int, body: FotoUsuarioRequest,
                        current_user: dict = Depends(get_current_user)):
    """Sube o reemplaza la foto del usuario. Llega en base64 (mismo camino que
    la imagen de portada de la TV), no multipart, para no sumar dependencias."""
    _require_admin(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT Id FROM HUB_Users WHERE Id = %s", (int(user_id),))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    finally:
        conn.close()
    try:
        contenido = base64.b64decode(body.contenido_base64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen (base64 inválido).")
    r = _foto_usuario.guardar_foto_usuario(
        get_connection, int(user_id), contenido, body.content_type,
        actualizado_por=int(current_user.get("id") or 0) or None)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo guardar la foto.")
    return r


@app.delete("/api/users/{user_id:int}/foto")
async def delete_user_foto(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    r = _foto_usuario.borrar_foto_usuario(get_connection, int(user_id))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo borrar la foto.")
    return r


# --- Asistencia del día -----------------------------------------------------
# Quién entró y quién salió HOY. Es la misma información que muestra la pantalla
# "🕘 Asistencia de hoy" del kiosco Dashboard (app en :8101), pero leída por
# Admon DIRECTAMENTE de la base: el kiosco va por un snapshot en disco que otro
# worker refresca cada 2 min, y acá se calcula al momento, sin depender de que
# ese proceso esté arriba.
#
# La fuente es `HUB_NetworkPresence`, que escribe el `network_scanner_worker`
# del contenedor `workersadmon` cuando ve aparecer o desaparecer una MAC conocida
# en la red. OJO: hay otras dos tablas de asistencia y NINGUNA sirve para esto
# hoy — `ControlAsistencia` (la del checador viejo) tiene su último registro de
# enero de 2023 y está abandonada, y `HUB_AsistenciaDiaria` sólo se calculó a
# mano una vez (2026-09-11) y trae casi todo en NULL.
#
# Por persona se toma la PRIMERA entrada del día y la ÚLTIMA salida: un celular
# que entra y sale seis veces no debe verse como seis llegadas distintas. Quien
# sigue dentro (su último evento es ENTRADA) va con `en_sitio`, para no pintar
# una salida que todavía no pasa.
AJUSTE_ENTRADA_MIN = 4  # ver el docstring de asistencia_hoy() en dashboard/api/datos.py

# Minutos que puede pasar el ESCÁNER sin registrar un ciclo antes de que la
# pantalla deje de dar por buenos los datos. Corre cada minuto, así que 10 min
# ya no es "un ratito": es que nadie está escaneando. Sin este aviso, un
# escáner caído deja la pantalla lanzando "9 en sitio" con datos de hace horas:
# la última cosa que se sabe de cada quien es que entró, y su salida nunca
# llegó a escribirse.
#
# OJO: se mide contra los CICLOS del escáner y NO contra los movimientos de
# gente. Los movimientos son por evento: si nadie entra ni sale en media hora no
# pasa nada y no hay ni un solo registro nuevo. Medir eso (que fue como se hizo
# primero) daba falsos positivos a media mañana, con el escáner funcionando
# perfecto. Lo que dice si el escáner vive es su último ciclo.
VENTANA_SIN_ESCANER_MIN = 10

# Marcha simultánea: cuántas personas tienen que registrar el mismo tipo de
# evento (entradas o salidas) dentro del MISMO minuto para que el dato se tome
# por escrito. Tres personas no entran ni salen de la oficina en el mismo
# segundo, así que ese patrón es del proceso, no de la gente: pasa cuando el
# escáner (o el worker que lee los ciclos) se reinicia y escribe de golpe el
# estado que tenía guardado, o cuando la red de la oficina se cae un momento y
# todos los equipos "desaparecen" juntos. Sin esta guarda, ese reinicio deja
# toda la pantalla en verde aunque la oficina esté vacía.
MARCHA_SIMULTANEA_MIN = 3


def _latido_scan(conn):
    """(ciclo, minutos) del último escáner, o (None, None) si nunca ha corrido.

    `ciclo` es la fecha del último ciclo y `minutos` su antigüedad. La
    antigüedad la calcula el SERVIDOR SQL con DATEDIFF, no Python: el reloj del
    contenedor y el del servidor SQL no están sincronizados (difieren horas) y
    restarlos en Python daba diferencias de miles de minutos.

    El escáner puede escribir en el camino NUEVO (`HUB_NetworkScanRuns`, un
    renglón por ciclo con la lista completa de MACs) o en el VIEJO
    (`HUB_NetworkScanResults`, un renglón por MAC y ciclo). Se mira EL MÁS
    RECIENTE de las dos, no la primera que tenga filas.

    OJO con esto, que ya costó un falso positivo real: si el escáner está
    escribiendo en la tabla vieja, la nueva se queda congelada con miles de
    filas viejas. Devolviendo la nueva "porque tiene datos", la pantalla
    anunciaba "el escáner no corre desde hace 16 h" mientras el escáner escribía
    hace 1 minuto. Con el MAX de las dos, el latido refleja lo que de verdad
    pasa.
    """
    consulta = ("SELECT MAX({col}) AS ciclo, "
                "DATEDIFF(MINUTE, MAX({col}), GETDATE()) AS minutos FROM dbo.{tab}")
    cur = conn.cursor(as_dict=True)
    mejor_ciclo, mejor_minutos = None, None
    for tab, col in (("HUB_NetworkScanRuns", "FechaScan"),
                     ("HUB_NetworkScanResults", "FechaScan")):
        try:
            cur.execute(consulta.format(tab=tab, col=col))
        except Exception:
            continue  # la tabla no existe en esta base: se prueba la otra
        fila = cur.fetchone()
        if not fila or not fila.get("ciclo"):
            continue
        if mejor_ciclo is None or fila["ciclo"] > mejor_ciclo:
            mejor_ciclo = fila["ciclo"]
            mejor_minutos = int(fila["minutos"] or 0)
    cur.close()
    return mejor_ciclo, mejor_minutos


@app.get("/api/asistencia")
async def get_asistencia(current_user: dict = Depends(get_current_user)):
    """Asistencia de hoy: quién llegó, quién sigue aquí y quién ya se fue.

    Devuelve {personas: [...], total, dentro, salieron, actualizado}. Cada
    persona trae los horarios como texto "YYYY-MM-DD HH:MM" (el formato que ya
    usa el kiosco, para que el front los formatee igual con hhmm()).

    `tiene_foto` viene aparte (no el binario): el front pide la foto sólo de
    quienes la tienen, por /api/users/{id}/foto, como en la lista de usuarios.
    """
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="No access")
    # UNA sola conexión para todo el endpoint. Antes cada bloque abría la suya
    # (la principal, la de fotos, la de frescura y la de la marcha): cuatro
    # conexiones al SQL Server en una sola llamada, que en la oficina se
    #-notaban como lentitud. Con una conexión el endpoint no depende de
    # cuántos clientes estén pegados a la pantalla al mismo tiempo.
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        # Un solo SELECT. `en_sitio` se resuelve con OUTER APPLY (el último evento
        # de hoy de cada quien) en vez del bucle de una consulta por persona que
        # usa el kiosco: mismo resultado, una sola ida a la base.
        # EV_FECHA: el instante del ESCANEO que prueba el evento, con respaldo
        # en la hora de proceso para los registros anteriores a esa columna.
        #
        # OJO, esto no es cosmético. El scanner guarda DOS fechas y su propio
        # docstring dice que la asistencia debe usar `FechaDeteccion` (la otra es
        # "cuándo lo procesó el worker"). Cuando el worker se quedó atascado 6 h
        # y drenó de golpe 1 195 escaneos pendientes, las dos columnas se
        # separaron y el listado mostraba la hora del drenaje: Rosa llegaba
        # 09:22 cuando llegó 08:35, y el ajuste de minutos se aplicaba sobre el
        # número equivocado. Con FechaDeteccion el ajuste cae sobre la real.
        EV = "COALESCE(p.FechaDeteccion, p.FechaHora)"
        EV2 = "COALESCE(p2.FechaDeteccion, p2.FechaHora)"

        cursor.execute(f"""
            SELECT
                d.IdUsuario AS id_usuario,
                ISNULL(u.Nombre, '(sin usuario)') AS nombre,
                -- Primera ENTRADA del día YA AJUSTADA, con tope al inicio del día
                -- para que a las 00:02 no salga "23:58 de ayer".
                CASE WHEN MIN(CASE WHEN p.TipoEvento = 'ENTRADA' THEN {EV} END)
                         IS NULL THEN NULL
                     ELSE CASE WHEN DATEADD(MINUTE, -%d, MIN(CASE WHEN p.TipoEvento = 'ENTRADA' THEN {EV} END))
                                    < CAST(CAST(GETDATE() AS date) AS datetime)
                               THEN CAST(CAST(GETDATE() AS date) AS datetime)
                               ELSE DATEADD(MINUTE, -%d, MIN(CASE WHEN p.TipoEvento = 'ENTRADA' THEN {EV} END))
                          END
                END AS entrada,
                MIN(CASE WHEN p.TipoEvento = 'ENTRADA' THEN {EV} END) AS entrada_cruda,
                MAX(CASE WHEN p.TipoEvento = 'ENTRADA' THEN {EV} END) AS ultima_entrada,
                MAX(CASE WHEN p.TipoEvento = 'SALIDA'  THEN {EV} END) AS salida,
                COUNT(*) AS eventos,
                CASE WHEN ult.ultimo_tipo = 'ENTRADA' THEN 1 ELSE 0 END AS en_sitio
            FROM HUB_NetworkPresence p
            JOIN HUB_NetworkDevices d ON d.Id = p.IdDispositivo
            LEFT JOIN HUB_Users u ON u.Id = d.IdUsuario
            OUTER APPLY (
                SELECT TOP 1 p2.TipoEvento AS ultimo_tipo
                FROM HUB_NetworkPresence p2
                JOIN HUB_NetworkDevices d2 ON d2.Id = p2.IdDispositivo
                WHERE d2.IdUsuario = d.IdUsuario
                  AND {EV2} >= CAST(CAST(GETDATE() AS date) AS datetime)
                ORDER BY p2.Id DESC
            ) ult
            WHERE {EV} >= CAST(CAST(GETDATE() AS date) AS datetime)
              AND {EV} < DATEADD(day, 1, CAST(CAST(GETDATE() AS date) AS datetime))
              AND d.IdUsuario IS NOT NULL
            GROUP BY d.IdUsuario, u.Nombre, ult.ultimo_tipo
            ORDER BY entrada
        """, (AJUSTE_ENTRADA_MIN, AJUSTE_ENTRADA_MIN))
        filas = cursor.fetchall()

        # Un SELECT aparte para saber quiénes tienen foto (no se traen binarios).
        # Es la misma lista que devuelve usuarios_foto.listar_fotos(), pero por
        # la misma conexión: ese helper abre (y cierra) la suya.
        cursor_foto = conn.cursor()
        cursor_foto.execute("SELECT IdUsuario FROM HUB_UsuariosFotos")
        con_foto = {int(r[0]) for r in cursor_foto.fetchall()}

        def _txt(fecha):
            return fecha.strftime("%Y-%m-%d %H:%M") if fecha else ""

        personas = []
        for f in filas:
            entrada_cruda = f.get("entrada_cruda")
            ultima_entrada = f.get("ultima_entrada")
            ultima_salida = f.get("salida")
            # OJO: las comparaciones van ANTES de convertir a texto. Al revés
            # revienta con "'>' not supported between datetime and str".
            en_sitio = bool(f.get("en_sitio"))

            # Si sigue dentro, la hora de SALIDA es la de una visita anterior y no la
            # de hoy: mostrarla junto a "en la oficina" se contradice ("se fue 17:36"
            # y está aquí a las 18:10, porque salió y volvió). Se vacía y, si entró
            # otra vez, se anota el reingreso.
            reingreso = ""
            if en_sitio:
                if ultima_entrada and ultima_salida and ultima_entrada > entrada_cruda:
                    reingreso = _txt(ultima_entrada)
                salida_txt = ""
            else:
                salida_txt = _txt(ultima_salida)

            # Caso límite: si al restar los 4 minutos la entrada queda DESPUÉS de la
            # salida se vería "llegó 08:05 / se fue 08:02", que es imposible y hace
            # dudar de toda la pantalla. Se queda la hora cruda (sin ajustar).
            entrada_mostrar = f.get("entrada")
            if not en_sitio and ultima_salida and entrada_mostrar and entrada_mostrar > ultima_salida:
                entrada_mostrar = entrada_cruda

            personas.append({
                "id_usuario": int(f["id_usuario"]),
                "nombre": f.get("nombre") or "(sin usuario)",
                "entrada": _txt(entrada_mostrar),
                "salida": salida_txt,
                "reingreso": reingreso,
                "eventos": int(f.get("eventos") or 0),
                "en_sitio": en_sitio,
                "tiene_foto": int(f["id_usuario"]) in con_foto,
            })

        dentro = sum(1 for p in personas if p["en_sitio"])

        # ── Qué tan frescos son los datos ─────────────────────────────────────
        # `en_sitio` se decide con el último evento de cada quien, así que sólo
        # es confiable si el escáner sigue escaneando: si se cayó, el "último
        # evento" de todos es viejo y la pantalla estaría afirmando que siguen
        # ahí con información de hace horas.
        #
        # OJO con qué se mide: el escáner escribe UN CICLO cada minuto, pero los
        # movimientos sólo existen cuando alguien entra o sale. Por eso el
        # estado se decide con el ciclo (el latido del escáner) y el último
        # movimiento se devuelve sólo como dato.
        ciclo_scan, minutos_scan = _latido_scan(conn)

        cursor2 = conn.cursor(as_dict=True)
        cursor2.execute("""
            SELECT GETDATE() AS ahora,
                   MAX(FechaHora) AS ultimo,
                   DATEDIFF(MINUTE, MAX(FechaHora), GETDATE()) AS minutos,
                   CASE WHEN MAX(FechaHora) > GETDATE() THEN 1 ELSE 0 END AS hay_futuro
            FROM HUB_NetworkPresence
            WHERE FechaHora >= CAST(CAST(GETDATE() AS date) AS datetime)
        """)
        fila = cursor2.fetchone() or {}
        ahora_servidor = fila.get("ahora") or datetime.now()
        ultimo_evento = fila.get("ultimo")
        minutos_movimiento = int(fila.get("minutos") or 0)
        hay_futuro = bool(fila.get("hay_futuro"))
        cursor2.close()

        if minutos_scan is None:
            # No hay ni un ciclo registrado: el escáner no está corriendo (o
            # nunca corrió). No se puede afirmar quién está aquí.
            estado = "congelado"
        elif minutos_scan < 0 or hay_futuro:
            # El escáner (o algún movimiento) trae fecha que todavía no llega:
            # los relojes no coinciden. Tampoco se puede afirmar nada.
            estado = "futuro"
        elif minutos_scan > VENTANA_SIN_ESCANER_MIN:
            estado = "congelado"
        elif ultimo_evento is None:
            # El escáner vive y hoy nadie ha entrado ni salido todavía.
            estado = "sin_datos"
        else:
            estado = "ok"

        # ¿El evento más reciente fue una marcha simultánea? Si sí, el estado de
        # "en sitio" que se acaba de calcular viene de esa marcha y no de la
        # realidad de la oficina (ver MARCHA_SIMULTANEA_MIN). Se marca y la vista
        # deja de pintar el estado, igual que con los datos congelados.
        marcha = None
        if estado == "ok":
            cursor3 = conn.cursor(as_dict=True)
            cursor3.execute("""
                SELECT MIN(p.FechaHora) AS desde, MAX(p.FechaHora) AS hasta,
                       p.TipoEvento, COUNT(DISTINCT d.IdUsuario) AS personas
                FROM HUB_NetworkPresence p
                JOIN HUB_NetworkDevices d ON d.Id = p.IdDispositivo
                WHERE p.FechaHora >= DATEADD(minute, -%d, GETDATE())
                GROUP BY p.TipoEvento,
                         DATEPART(hour, p.FechaHora), DATEPART(minute, p.FechaHora)
                HAVING COUNT(DISTINCT d.IdUsuario) >= %d
                ORDER BY MAX(p.FechaHora) DESC
            """, (VENTANA_SIN_ESCANER_MIN, MARCHA_SIMULTANEA_MIN))
            fila = cursor3.fetchone()
            cursor3.close()
            if fila:
                estado = "inestable"
                marcha = {
                    "tipo": fila["TipoEvento"],
                    "personas": int(fila["personas"]),
                    "desde": fila["desde"].strftime("%H:%M:%S") if fila["desde"] else "",
                    "hasta": fila["hasta"].strftime("%H:%M:%S") if fila["hasta"] else "",
                }

        return {
            "personas": personas,
            "total": len(personas),
            "dentro": dentro,
            "salieron": len(personas) - dentro,
            # Hora del servidor SQL, no la del contenedor (van horas de
            # diferencia y en pantalla se leía "Actualizado 15:12" a las 09:12
            # de la mañana).
            "actualizado": ahora_servidor.strftime("%Y-%m-%d %H:%M:%S"),
            # Latido del escáner: lo que dice si los datos son frescos.
            "ciclo_scan": ciclo_scan.strftime("%Y-%m-%d %H:%M:%S") if ciclo_scan else "",
            "minutos_sin_scan": minutos_scan,
            # Último movimiento de gente: informative, NO decide si se confía.
            "ultimo_evento": ultimo_evento.strftime("%Y-%m-%d %H:%M") if ultimo_evento else "",
            "minutos_sin_movimiento": minutos_movimiento,
            "estado": estado,
            "marcha": marcha,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        # La conexión se cierra aquí, ya con el último SELECT hecho: todas las
        # consultas de arriba (personas, fotos, frescura y marcha) salen de ella.
        if conn is not None:
            conn.close()


# --- Inventory endpoints ---

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


@app.get("/api/cotizaciones/resumen")
def cotizaciones_resumen(pagina: int = 1, porPagina: int = TOP_COTIZACIONES,
                         q: str = "", current_user: dict = Depends(get_current_user)):
    """Listado de cotizaciones de materiales para la pantalla principal.

    Es `def` y no `async def` a propósito: FastAPI corre los `def` en su
    threadpool, así que aunque una consulta se ponga lenta ya no bloquea el
    event loop de uvicorn. Antes sí lo bloqueaba, y con el loop ocupado el
    ping a /api/health del front tardaba 12 s y la app entera se anunciaba
    "Sin conexión" con datos viejos.
    """
    _require_cotiz(current_user)
    conn = None
    try:
        conn = get_connection()
        salida, total = _listar_cotizaciones(
            conn, top=max(1, min(int(porPagina or TOP_COTIZACIONES), 500)),
            pagina=pagina, q=q)
        conn.close()
        conn = None
        return {
            "cotizaciones": salida,
            "total": total,
            "pagina": max(1, int(pagina)),
            "por_pagina": max(1, min(int(porPagina or TOP_COTIZACIONES), 500)),
        }
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/cotizaciones/{folio:int}")
async def cotizacion_header(folio: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT IM.Folio, IM.IdCliente, IM.Contacto, IM.Fecha, IM.Descripcion, IM.Nota, "
            "IM.Autor, IM.Color, C.Cliente AS ClienteNombre "
            "FROM IndiceMateriales IM LEFT JOIN clientes C ON IM.IdCliente = C.IdCliente "
            "WHERE IM.Folio = %s", (int(folio),))
        r = cursor.fetchone()
        conn.close()
        if not r:
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        return {
            "folio": r[0], "folio_fmt": _fmt_folio(r[0]),
            "id_cliente": r[1] or "", "contacto": r[2] or "", "fecha": _fstr(r[3]),
            "descripcion": r[4] or "", "nota": r[5] or "", "autor": r[6] or "",
            "color": int(r[7] or 0), "cliente_nombre": r[8] or "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/cotizaciones")
async def cotizacion_create(body: CotizacionCreate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    idc = (body.id_cliente or "").strip().upper()
    if not idc or not (body.contacto or "").strip() or not (body.descripcion or "").strip():
        raise HTTPException(status_code=400, detail="Cliente, contacto y descripción son obligatorios.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Cliente FROM clientes WHERE IdCliente = %s", (idc,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"El ID de cliente {idc} no existe.")
        folio = _db_create_quotation(cursor, idc, body.contacto, body.descripcion, current_user.get("nombre") or current_user.get("email"))
        conn.commit()
        conn.close()
        # Legends: +2 por cotización creada (idempotente por folio)
        try:
            legends_registrar_metrica(current_user["id"], "cotizacion_creada", referencia_id=int(folio))
        except Exception:
            pass
        return {"folio": folio, "folio_fmt": _fmt_folio(folio)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/cotizaciones/{folio:int}")
async def cotizacion_update(folio: int, body: CotizacionUpdate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    idc = (body.id_cliente or "").strip().upper()
    if not idc or not (body.contacto or "").strip() or not (body.descripcion or "").strip():
        raise HTTPException(status_code=400, detail="Cliente, contacto y descripción son obligatorios.")
    if int(body.color) not in (0, 1, 2):
        raise HTTPException(status_code=400, detail="Estatus inválido.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT IdCliente, Contacto, Descripcion, Color FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
        cur_row = cursor.fetchone()
        if not cur_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        cur_color = int(cur_row[3] or 0)
        if cur_color in (1, 2):
            # Bloqueada: solo se permite transición de estatus, no editar datos
            if ((cur_row[0] or "") != idc or (cur_row[1] or "") != body.contacto.strip()
                    or (cur_row[2] or "") != body.descripcion.strip()):
                conn.close()
                raise HTTPException(status_code=400, detail="Cotización bloqueada (lista para facturar/facturada).")
        cursor.execute(
            "UPDATE IndiceMateriales SET IdCliente = %s, Contacto = %s, Descripcion = %s, Color = %s WHERE Folio = %s",
            (idc, body.contacto.strip(), body.descripcion.strip(), int(body.color), int(folio)),
        )
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/cotizaciones/{folio:int}/nota")
async def cotizacion_nota(folio: int, body: CotizacionNota, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE IndiceMateriales SET Nota = %s WHERE Folio = %s", ((body.nota or "").strip(), int(folio)))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/cotizaciones/{folio:int}")
async def cotizacion_delete(folio: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        color = _db_get_color(cursor, folio)
        if color is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        if color in (1, 2):
            conn.close()
            raise HTTPException(status_code=400, detail="Cotización bloqueada (lista para facturar/facturada).")
        cursor.execute("DELETE FROM Partidas WHERE Folio = %s", (int(folio),))
        # Limpieza del snapshot SAT (tabla nueva sidecar, no existe antes de 0037)
        try:
            cursor.execute("DELETE FROM HUB_PartidasSat WHERE Folio = %s", (int(folio),))
        except Exception:
            pass
        cursor.execute("DELETE FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/cotizaciones/{folio:int}/clonar")
async def cotizacion_clonar(folio: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        nuevo = _db_clone_quotation(cursor, folio, current_user.get("nombre") or current_user.get("email"))
        conn.commit()
        conn.close()
        return {"folio": nuevo, "folio_fmt": _fmt_folio(nuevo)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ----- PDF y envío por correo (como el HUB) -----

def _cotizacion_pdf_bytes(folio: int) -> tuple:
    """Arma header + partidas y genera el PDF. Retorna (filename, bytes)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT IM.Folio, IM.IdCliente, IM.Contacto, IM.Fecha, IM.Descripcion, IM.Nota, "
        "IM.Autor, IM.Color, C.Cliente AS ClienteNombre, C.CondicionesPagoDias "
        "FROM IndiceMateriales IM LEFT JOIN clientes C ON IM.IdCliente = C.IdCliente "
        "WHERE IM.Folio = %s", (int(folio),))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    autor = r[6] or ""
    telefono = "8183589075"
    try:
        cursor.execute("SELECT TOP 1 Telefono FROM MAC WHERE Nombre = %s ORDER BY Telefono DESC", (autor,))
        trow = cursor.fetchone()
        if trow and trow[0]:
            telefono = str(trow[0]).strip()
    except Exception:
        pass
    header = {
        "folio": r[0], "id_cliente": r[1] or "", "contacto": r[2] or "",
        "fecha": r[3], "descripcion": r[4] or "", "nota": r[5] or "",
        "autor": autor, "color": int(r[7] or 0), "cliente_nombre": r[8] or "",
        "condiciones_pago": r[9] or 30, "telefono": telefono,
    }
    cursor.execute(
        "SELECT P.Partida, P.Cantidad, P.Descripcion, P.PrecioCompraUnitario, P.Factor, "
        "P.Proveedor, P.TiempoEntregaDias, P.Dolar, P.Flete, "
        "S.ClaveProdServ, S.ClaveUnidad, S.Fuente, P.ArticuloGenerico "
        "FROM Partidas P "
        "LEFT JOIN HUB_PartidasSat S ON S.Folio = P.Folio AND S.Partida = P.Partida "
        "WHERE P.Folio = %s ORDER BY P.Partida ASC", (int(folio),))
    parts = [_partida_row_to_dict(int(folio), row) for row in cursor.fetchall()]
    conn.close()
    if not parts:
        raise HTTPException(status_code=400, detail="La cotización no tiene partidas.")
    return f"Cotizacion_{_fmt_folio(folio)}.pdf", build_cotizacion_pdf(header, parts)


@app.get("/api/cotizaciones/{folio:int}/pdf")
async def cotizacion_pdf(folio: int, request: Request):
    _user = _user_from_header_or_query(request)
    _require_cotiz(_user)
    try:
        filename, pdf_bytes = _cotizacion_pdf_bytes(folio)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


class CotizacionEnviar(BaseModel):
    to_email: str = ""
    subject: str = ""
    body: str = ""


def _smtp_send_with_pdf(to_email: str, subject: str, body: str, pdf_bytes: bytes,
                        pdf_filename: str, sender_email: str, cc_email=None):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT TOP 1 SmtpServer, Port, Username, Password, UseSSL, UseTLS, RequireAuth "
                   "FROM HUB_EmailConfig ORDER BY Id ASC")
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise Exception("Sin configuración SMTP (HUB_EmailConfig).")
    server_name, port, username, password = row[0].strip(), int(row[1]), row[2].strip(), row[3].strip()
    use_ssl, use_tls, require_auth = bool(row[4]), bool(row[5]), bool(row[6])
    msg = MIMEMultipart()
    msg["From"] = f"{sender_email}"
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc_email:
        msg["Cc"] = cc_email
    msg.attach(MIMEText(body or "", "plain", "utf-8"))
    part = MIMEApplication(pdf_bytes, _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(part)
    recipients = [to_email] + ([cc_email] if cc_email else [])
    if use_ssl:
        server = smtplib.SMTP_SSL(server_name, port, timeout=20)
    else:
        server = smtplib.SMTP(server_name, port, timeout=20)
        if use_tls:
            server.starttls()
    if require_auth:
        server.login(username, password)
    server.sendmail(username, recipients, msg.as_string())
    server.quit()


@app.post("/api/cotizaciones/{folio:int}/enviar")
async def cotizacion_enviar(folio: int, body: CotizacionEnviar, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    to_email = (body.to_email or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="Correo destinatario inválido.")
    try:
        filename, pdf_bytes = _cotizacion_pdf_bytes(folio)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    try:
        _smtp_send_with_pdf(to_email, (body.subject or "").strip() or f"Envío cotización {_fmt_folio(folio)}",
                            body.body or "", pdf_bytes, filename,
                            current_user.get("email"), cc_email=current_user.get("email"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo enviar: {str(e)[:200]}")
    # Legends: +6 por envío real de cotización (idempotente: 1× por folio)
    try:
        legends_registrar_metrica(current_user["id"], "cotizacion_enviada", referencia_id=int(folio))
    except Exception:
        pass
    return {"ok": True}


# ----- Partidas -----

@app.get("/api/cotizaciones/{folio:int}/partidas")
async def cotizacion_partidas(folio: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT P.Partida, P.Cantidad, P.Descripcion, P.PrecioCompraUnitario, P.Factor, "
            "P.Proveedor, P.TiempoEntregaDias, P.Dolar, P.Flete, "
            "S.ClaveProdServ, S.ClaveUnidad, S.Fuente, P.ArticuloGenerico "
            "FROM Partidas P "
            "LEFT JOIN HUB_PartidasSat S ON S.Folio = P.Folio AND S.Partida = P.Partida "
            "WHERE P.Folio = %s ORDER BY P.Partida ASC", (int(folio),))
        rows = cursor.fetchall()
        conn.close()
        return [_partida_row_to_dict(int(folio), r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/cotizaciones/{folio:int}/partidas")
async def cotizacion_partida_add(folio: int, body: PartidaCreate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    _validate_partida_input(body.cantidad, body.descripcion)
    # Códigos SAT capturados por el usuario: validar ANTES de escribir
    if body.sat_prod_serv and body.sat_prod_serv.strip():
        err = sat_helper.validar_codigos(body.sat_prod_serv, body.sat_unidad)
        if err:
            raise HTTPException(status_code=400, detail=err)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        color = _db_get_color(cursor, folio)
        if color is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        if color in (1, 2):
            conn.close()
            raise HTTPException(status_code=400, detail="Cotización bloqueada.")
        num = _db_add_partida(cursor, folio, body.cantidad, body.descripcion, body.precio_compra,
                              body.factor, body.proveedor, body.tiempo_entrega, body.dolar, body.flete,
                              body.articulo_generico)
        # Hook SAT auto-alimentado (sidecar → índice → reglas → 1 llamada IA en miss)
        try:
            sat = sat_helper.guardar_partida_sat(
                cursor, folio, num, body.descripcion, body.sat_prod_serv, body.sat_unidad)
        except ValueError as e:
            conn.close()
            raise HTTPException(status_code=400, detail=str(e))
        conn.commit()
        conn.close()
        return {"ok": True, "partida": num, "sat": sat}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/cotizaciones/{folio:int}/partidas/{partida:int}")
async def cotizacion_partida_update(folio: int, partida: int, body: PartidaUpdate, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    _validate_partida_input(body.cantidad, body.descripcion)
    # Códigos SAT capturados por el usuario: validar ANTES de escribir
    if body.sat_prod_serv and body.sat_prod_serv.strip():
        err = sat_helper.validar_codigos(body.sat_prod_serv, body.sat_unidad)
        if err:
            raise HTTPException(status_code=400, detail=err)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        color = _db_get_color(cursor, folio)
        if color is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        if color in (1, 2):
            conn.close()
            raise HTTPException(status_code=400, detail="Cotización bloqueada.")
        cursor.execute(
            "UPDATE Partidas SET Cantidad = %s, Descripcion = %s, PrecioCompraUnitario = %s, "
            "Factor = %s, Proveedor = %s, TiempoEntregaDias = %s, Dolar = %s, Flete = %s, "
            "ArticuloGenerico = %s "
            "WHERE Folio = %s AND Partida = %s",
            (int(body.cantidad), body.descripcion.strip(), float(body.precio_compra), float(body.factor),
             (body.proveedor or "").strip(), int(body.tiempo_entrega or 0), float(body.dolar or 0.0),
             float(body.flete or 0.0), _clean_articulo(body.articulo_generico), int(folio), int(partida)),
        )
        # Hook SAT: si cambió la descripción se re-resuelve; si el usuario
        # envía códigos explícitos estos ganan (fuente MANUAL)
        try:
            sat = sat_helper.guardar_partida_sat(
                cursor, folio, partida, body.descripcion, body.sat_prod_serv, body.sat_unidad)
        except ValueError as e:
            conn.close()
            raise HTTPException(status_code=400, detail=str(e))
        conn.commit()
        conn.close()
        return {"ok": True, "sat": sat}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/cotizaciones/{folio:int}/partidas/{partida:int}")
async def cotizacion_partida_delete(folio: int, partida: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        color = _db_get_color(cursor, folio)
        if color is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        if color in (1, 2):
            conn.close()
            raise HTTPException(status_code=400, detail="Cotización bloqueada.")
        cursor.execute("DELETE FROM Partidas WHERE Folio = %s AND Partida = %s", (int(folio), int(partida)))
        # Borrar también el snapshot SAT de esa partida
        try:
            cursor.execute("DELETE FROM HUB_PartidasSat WHERE Folio = %s AND Partida = %s",
                           (int(folio), int(partida)))
        except Exception:
            pass
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ----- SAT: sugerencia para el formulario (botón 🤖) -----

class SatSugerir(BaseModel):
    descripcion: str = ""


@app.post("/api/sat/sugerir")
async def sat_sugerir(body: SatSugerir, current_user: dict = Depends(get_current_user)):
    """Resuelve códigos SAT para mostrarlos en el formulario SIN guardar la
    partida: índice → reglas keywords → 1 llamada a Gemini. Solo hace upsert
    del índice (HUB_SatArticulos), no toca la partida ni las tablas existentes."""
    _require_cotiz(current_user)
    desc = (body.descripcion or "").strip()
    if not desc:
        raise HTTPException(status_code=400, detail="La descripción es obligatoria.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sugerencia = sat_helper.sugerir_para_ui(cursor, desc)
        conn.commit()
        conn.close()
        return {"sugerencia": sugerencia}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ----- Remisiones (desde cotizaciones de materiales) -----
# Port del módulo del HUB (migración 0030): creación inmutable con folio
# RM-CM#####-NN, asignación de usuario para firma en Field y PDF.
# Los códigos SAT del PDF se resuelven con un JOIN a HUB_PartidasSat
# (FolioCotizacion + Partida) — NO se altera la tabla RemisionPartidas.

class RemisionCreate(BaseModel):
    partidas: List[Dict[str, Any]] = []  # [{partida, cantidad, descripcion}]


class RemisionAsignar(BaseModel):
    id_usuario: Optional[int] = None


@app.get("/api/remisiones/usuarios")
async def remision_usuarios(current_user: dict = Depends(get_current_user)):
    """Usuarios activos para asignar la firma de la remisión en Field."""
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Id, Nombre, Email FROM HUB_Users WHERE Activo = 1 ORDER BY Nombre")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "nombre": r[1] or "", "email": r[2] or ""} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/cotizaciones/{folio:int}/remisiones")
async def remisiones_list(folio: int, current_user: dict = Depends(get_current_user)):
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT R.IdRemision, R.FolioRemision, R.FechaCreacion, R.CreadoPor, "
            "R.IdUsuarioAsignado, U.Nombre, R.FirmaConformidad, R.FechaFirma "
            "FROM IndiceRemisiones R "
            "LEFT JOIN HUB_Users U ON U.Id = R.IdUsuarioAsignado "
            "WHERE R.FolioCotizacion = %s ORDER BY R.IdRemision DESC", (int(folio),))
        rows = cursor.fetchall()
        conn.close()
        out = []
        for r in rows:
            fecha = r[2]
            out.append({
                "id": int(r[0]), "folio": r[1] or "",
                "fecha": fecha.strftime("%d/%m/%Y %H:%M") if hasattr(fecha, "strftime") else str(fecha or ""),
                "creado_por": r[3] or "",
                "id_asignado": int(r[4]) if r[4] is not None else None,
                "asignado_nombre": r[5] or "",
                "firmada": bool(r[6]),
                "fecha_firma": (r[7].strftime("%d/%m/%Y %H:%M")
                                if hasattr(r[7], "strftime") else str(r[7] or "")),
            })
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/cotizaciones/{folio:int}/remisiones")
async def remision_create(folio: int, body: RemisionCreate, current_user: dict = Depends(get_current_user)):
    """Crea una remisión inmutable desde la CM. Copia cantidad/descripción de
    las partidas elegidas (SIN precios); los códigos SAT se resuelven al
    generar el PDF vía HUB_PartidasSat."""
    _require_cotiz(current_user)
    seleccionadas = [p for p in (body.partidas or [])
                     if int(p.get("cantidad") or 0) >= 1 and str(p.get("descripcion") or "").strip()]
    if not seleccionadas:
        raise HTTPException(status_code=400, detail="La remisión necesita al menos una partida.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        color = _db_get_color(cursor, folio)
        if color is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        if color in (1, 2):
            conn.close()
            raise HTTPException(status_code=400, detail="Cotización bloqueada.")
        # Encabezado snapshot (mismo patrón que el HUB)
        cursor.execute(
            "SELECT IdCliente, Contacto, Descripcion, Autor FROM IndiceMateriales WHERE Folio = %s",
            (int(folio),))
        cm = cursor.fetchone()
        if not cm:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        # Folio contiguo RM-CM#####-NN por cotización (contador = total existente + 1)
        cursor.execute(
            "SELECT ISNULL(COUNT(*), 0) FROM IndiceRemisiones WHERE FolioCotizacion = %s",
            (int(folio),))
        n = int(cursor.fetchone()[0]) + 1
        folio_rm = f"RM-CM{int(folio):05d}-{n:02d}"
        creador = current_user.get("nombre") or current_user.get("email") or ""
        cursor.execute(
            "INSERT INTO IndiceRemisiones "
            "(FolioRemision, FolioCotizacion, IdCliente, Contacto, Descripcion, Autor, CreadoPor) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (folio_rm, int(folio), (cm[0] or "").strip(), cm[1] or "", cm[2] or "",
             cm[3] or "", creador))
        cursor.execute("SELECT @@IDENTITY")
        idr = cursor.fetchone()[0]
        if not idr:
            conn.close()
            raise HTTPException(status_code=500, detail="No se obtuvo el id de la remisión.")
        idr = int(idr)
        for p in seleccionadas:
            cursor.execute(
                "INSERT INTO RemisionPartidas (IdRemision, Partida, Cantidad, Descripcion) "
                "VALUES (%s, %s, %s, %s)",
                (idr, int(p.get("partida") or 0), int(p.get("cantidad") or 1),
                 str(p.get("descripcion") or "").strip()))
        conn.commit()
        conn.close()
        return {"ok": True, "id": idr, "folio": folio_rm}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/remisiones/{id_remision:int}")
async def remision_delete(id_remision: int, current_user: dict = Depends(get_current_user)):
    """Borra la remisión (índice + partidas por cascade). No se puede editar."""
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT FolioRemision FROM IndiceRemisiones WHERE IdRemision = %s",
                       (int(id_remision),))
        r = cursor.fetchone()
        if not r:
            conn.close()
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        # RemisionPartidas tiene FK ON DELETE CASCADE (migración 0030)
        cursor.execute("DELETE FROM IndiceRemisiones WHERE IdRemision = %s", (int(id_remision),))
        conn.commit()
        conn.close()
        return {"ok": True, "folio": r[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/remisiones/{id_remision:int}/asignar")
async def remision_asignar(id_remision: int, body: RemisionAsignar,
                           current_user: dict = Depends(get_current_user)):
    """Asigna (o con id_usuario null desasigna) un usuario para firmar en Field."""
    _require_cotiz(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT IdRemision FROM IndiceRemisiones WHERE IdRemision = %s",
                       (int(id_remision),))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        if body.id_usuario is not None:
            cursor.execute("SELECT Id FROM HUB_Users WHERE Id = %s AND Activo = 1",
                           (int(body.id_usuario),))
            if not cursor.fetchone():
                conn.close()
                raise HTTPException(status_code=400, detail="Usuario no válido o inactivo.")
        cursor.execute("UPDATE IndiceRemisiones SET IdUsuarioAsignado = %s WHERE IdRemision = %s",
                       (int(body.id_usuario) if body.id_usuario is not None else None,
                        int(id_remision)))
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/remisiones/{id_remision:int}/pdf")
async def remision_pdf(id_remision: int, request: Request):
    """PDF de la remisión (auth por header o query ?s=TOKEN para abrir en pestaña)."""
    _user = _user_from_header_or_query(request)
    _require_cotiz(_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT R.IdRemision, R.FolioRemision, R.FolioCotizacion, R.IdCliente, "
            "R.Contacto, R.Descripcion, R.Autor, R.CreadoPor, R.FechaCreacion, "
            "R.FirmaConformidad, R.FechaFirma, "
            "C.Cliente AS ClienteNombre, U.Nombre AS AsignadoNombre, "
            "(SELECT TOP 1 Telefono FROM MAC WHERE Nombre = R.Autor ORDER BY Telefono DESC) AS Telefono "
            "FROM IndiceRemisiones R "
            "LEFT JOIN clientes C ON C.IdCliente = R.IdCliente "
            "LEFT JOIN HUB_Users U ON U.Id = R.IdUsuarioAsignado "
            "WHERE R.IdRemision = %s", (int(id_remision),))
        r = cursor.fetchone()
        if not r:
            conn.close()
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        details = {
            "IdRemision": r[0], "FolioRemision": r[1], "FolioCotizacion": r[2],
            "IdCliente": r[3], "Contacto": r[4], "Descripcion": r[5], "Autor": r[6],
            "CreadoPor": r[7], "FechaCreacion": r[8], "FirmaConformidad": r[9],
            "FechaFirma": r[10], "ClienteNombre": r[11],
            "UsuarioAsignadoNombre": r[12], "Telefono": r[13] or "",
        }
        # Partidas + códigos SAT resueltos por coordenada (FolioCM + Partida)
        # contra el sidecar HUB_PartidasSat — sin tocar RemisionPartidas.
        cursor.execute(
            "SELECT RP.Partida, RP.Cantidad, RP.Descripcion, "
            "S.ClaveProdServ, S.ClaveUnidad "
            "FROM RemisionPartidas RP "
            "LEFT JOIN HUB_PartidasSat S ON S.Folio = %s AND S.Partida = RP.Partida "
            "WHERE RP.IdRemision = %s ORDER BY RP.Partida ASC",
            (int(r[2]), int(id_remision)))
        items = [{"Partida": ir[0], "Cantidad": ir[1], "Descripcion": ir[2],
                  "sat_prod_serv": ir[3] or "", "sat_unidad": ir[4] or ""}
                 for ir in cursor.fetchall()]
        conn.close()
        if not items:
            raise HTTPException(status_code=400, detail="La remisión no tiene partidas.")
        pdf_bytes = build_remision_pdf(details, items)
        fname = f"{details['FolioRemision']}.pdf"
        return Response(content=pdf_bytes, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{fname}"'})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ----- Clientes -----

@app.get("/api/clientes")
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


@app.post("/api/clientes")
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


@app.put("/api/clientes/{id_cliente}")
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


@app.delete("/api/clientes/{id_cliente}")
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


@app.get("/api/clientes/{id_cliente}/nombre")
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


@app.put("/api/clientes/{id_cliente}/contactos")
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


@app.delete("/api/clientes/{id_cliente}/contactos")
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


@app.get("/api/clientes/{id_cliente}/contactos")
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


@app.get("/api/clientes/{id_cliente}/contactos/detalle")
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


@app.get("/api/dashboard/kpis")
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

@app.post("/api/pdf/generate")
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


@app.get("/api/reportes")
async def api_list_reportes(tecnico: str = "", eliminados: bool = False, current_user: dict = Depends(get_current_user)):
    """Lista reportes (top 500). Filtra por técnico si se pasa. eliminados=true muestra papelera."""
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        where_eliminado = "AND Eliminado = 1" if eliminados else "AND (Eliminado = 0 OR Eliminado IS NULL)"
        
        if tecnico:
            cursor.execute(f"""
                SELECT IdReporte, Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                       DescripcionServicio, Estatus, Notas, MaquinaLinea, FechaHoraInicio, FechaHoraFin,
                       TiempoTraslado, TiempoComida, FirmaConformidad, Cotizacion, Eliminado, FechaEliminado
                FROM ReportesServicio
                WHERE (Tecnico = %s
                   OR IdReporte IN (SELECT IdReporte FROM ReportesServicioTecnicos
                                    INNER JOIN HUB_Users u ON u.Id = ReportesServicioTecnicos.IdUsuario
                                    WHERE u.Nombre = %s))
                   {where_eliminado}
                ORDER BY Fecha DESC, IdReporte DESC
            """, (tecnico.strip(), tecnico.strip()))
        else:
            cursor.execute(f"""
                SELECT TOP 500 IdReporte, Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                       DescripcionServicio, Estatus, Notas, MaquinaLinea, FechaHoraInicio, FechaHoraFin,
                       TiempoTraslado, TiempoComida, FirmaConformidad, Cotizacion, Eliminado, FechaEliminado
                FROM ReportesServicio
                WHERE 1=1 {where_eliminado}
                ORDER BY Fecha DESC, IdReporte DESC
            """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip([c[0] for c in cursor.description], r)) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/reportes/excel")
async def api_reportes_excel(ids: str, current_user: dict = Depends(get_current_user)):
    """Genera el formato de Excel (hoja "Calculo") con UN reporte por fila.

    Formato: "formatos excel/Formato Cotizaciones.xlsx" (en el contenedor se
    copia como "formatos_excel/FormatoCotizaciones.xlsx"). La fila 2 son los
    encabezados (Part/Cant/Desc…) y los datos arrancan en la fila 3:
      A = consecutivo de partidas (1, 2, 3…)
      B = total de horas del reporte: (Fin − Inicio) + TiempoTraslado
      C = "Folio · Descripción del servicio"
    Reglas: todos los reportes deben ser del MISMO cliente, Firmados y sin
    papelera. `ids` viene como IdReporte separados por coma.
    """
    _require_reporte(current_user)
    # Imports locales: openpyxl solo se carga al pedir el Excel (no al arrancar).
    import io
    import re
    import unicodedata
    from copy import copy as _copy
    from pathlib import Path

    import openpyxl

    # --- Parseo y límites de ids -------------------------------------------
    try:
        lista_ids = sorted({int(x) for x in str(ids).split(",") if str(x).strip()})
    except ValueError:
        raise HTTPException(status_code=400, detail="ids inválidos: usa IdReporte separados por coma.")
    if not lista_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos un reporte.")
    if len(lista_ids) > 500:
        raise HTTPException(status_code=400, detail="Máximo 500 reportes por descarga.")

    # --- Carga de los reportes pedidos --------------------------------------
    try:
        conn = get_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["%s"] * len(lista_ids))
        cursor.execute(f"""
            SELECT IdReporte, Folio, Cliente, DescripcionServicio, Fecha,
                   FechaHoraInicio, FechaHoraFin, TiempoTraslado, Estatus, Eliminado
            FROM ReportesServicio
            WHERE IdReporte IN ({placeholders})
        """, tuple(lista_ids))  # tuple: pymssql 2.2.11 (producción) rechaza list
        rows = [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
        conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

    por_id = {r["IdReporte"]: r for r in rows}
    faltantes = [str(i) for i in lista_ids if i not in por_id]
    if faltantes:
        raise HTTPException(status_code=404, detail=f"Reportes no encontrados: {', '.join(faltantes)}")

    # --- Validaciones del negocio ------------------------------------------
    no_firmados = sorted(
        r["Folio"] for r in rows
        if r.get("Estatus") != "Firmado" or r.get("Eliminado") not in (0, False, None)
    )
    if no_firmados:
        raise HTTPException(status_code=400,
                            detail=f"Solo reportes FIRMADOS y fuera de la papelera: {', '.join(no_firmados)}")
    clientes = {(r.get("Cliente") or "").strip() for r in rows}
    if len(clientes) > 1:
        raise HTTPException(status_code=400,
                            detail="Todos los reportes deben ser del mismo cliente. Hay: "
                                   + ", ".join(sorted(clientes)))
    sin_horas = sorted(r["Folio"] for r in rows if not r.get("FechaHoraInicio") or not r.get("FechaHoraFin"))
    if sin_horas:
        raise HTTPException(status_code=400,
                            detail=f"Faltan horas (inicio/fin) en: {', '.join(sin_horas)}")

    # Orden determinista por fecha y folio, para que el consecutivo de la
    # columna A salga corrido siempre igual.
    reportes = sorted(rows, key=lambda r: (str(r.get("Fecha") or ""), str(r.get("Folio") or "")))

    def _horas(r):
        """(Fin − Inicio) + Traslado, en horas decimales con 2 cifras."""
        h = (r["FechaHoraFin"] - r["FechaHoraInicio"]).total_seconds() / 3600.0
        h += float(r.get("TiempoTraslado") or 0)
        return round(h, 2)

    # --- Template: en el repo en "formatos excel/", en el contenedor en
    #     "formatos_excel/" (lo copia el Dockerfile sin espacios en la ruta).
    base = Path(__file__).resolve().parent.parent
    candidatos = [
        base / "formatos_excel" / "FormatoCotizaciones.xlsx",
        base / "formatos excel" / "Formato Cotizaciones.xlsx",
    ]
    template = next((p for p in candidatos if p.exists()), None)
    if not template:
        raise HTTPException(status_code=500, detail="No se encontró el template del formato de Excel.")

    wb = openpyxl.load_workbook(template)
    ws = wb["Calculo"]

    # Estilo de la fila 3 del template (fila de ejemplo) para replicarlo en
    # cada fila nueva: si no, las filas escritas saldrían sin formato.
    estilos = {c: _copy(ws[f"{c}3"]._style) for c in ("A", "B", "C", "G", "I", "J", "K")}
    estilos["J6"] = _copy(ws["J6"]._style)  # estilo de la fila de totales
    estilos["K6"] = _copy(ws["K6"]._style)

    # Los 0 de ejemplo del costo (P.Com.Uni, Factor) van en blanco: el usuario
    # los captura a mano después y las fórmulas de precio dan 0 solas.
    for col in ("E", "F", "H"):
        ws[f"{col}3"] = None

    # Totales: el template trae =SUM(J3:J3) en la fila 6. Si los totales NO
    # caen ahí (distinto número de reportes), se limpia ANTES de escribir los
    # datos para no dejar SUM viejos… y sin borrar después las fórmulas que
    # el propio loop deja en J6/K6 cuando la fila 6 resulta ser un dato (n ≥ 4).
    ultima = 2 + len(reportes)
    fila_tot = ultima + 1
    if fila_tot != 6:
        ws["J6"] = None
        ws["K6"] = None

    for idx, r in enumerate(reportes, start=1):
        fila = 2 + idx  # los datos empiezan en la 3 (la 2 son los encabezados)
        desc = (r.get("DescripcionServicio") or "").strip()
        ws[f"A{fila}"] = idx
        ws[f"B{fila}"] = _horas(r)
        ws[f"C{fila}"] = f"{r['Folio']} · {desc}" if desc else str(r["Folio"])
        # Fórmulas de precio del formato, replicadas hacia abajo como si se
        # arrastrara la fila 3: quedan en 0 hasta que capturen costo/precio.
        ws[f"G{fila}"] = f"=F{fila}*B{fila}"
        ws[f"I{fila}"] = f"=F{fila}*(1+H{fila})"
        ws[f"J{fila}"] = f"=I{fila}*B{fila}"
        ws[f"K{fila}"] = f"=J{fila}-G{fila}"
        for col in ("A", "B", "C", "G", "I", "J", "K"):
            ws[f"{col}{fila}"]._style = estilos[col]

    # Fila de totales contra el rango real de datos (fila justa debajo).
    ws[f"J{fila_tot}"] = f"=SUM(J3:J{ultima})"
    ws[f"K{fila_tot}"] = f"=SUM(K3:K{ultima})"
    ws[f"J{fila_tot}"]._style = estilos["J6"]
    ws[f"K{fila_tot}"]._style = estilos["K6"]

    # --- Nombre genérico del archivo: Reportes_<Cliente>_AAAA-MM-DD.xlsx ----
    cliente = next(iter(clientes)) or "Cliente"
    nombre_cliente = unicodedata.normalize("NFKD", cliente).encode("ascii", "ignore").decode()
    nombre_cliente = re.sub(r"[^\w\s-]", "", nombre_cliente).strip().replace(" ", "_")[:40] or "Cliente"
    nombre = f"Reportes_{nombre_cliente}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@app.get("/api/reportes/{id_reporte}")
async def api_get_reporte(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT IdReporte, Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                   DescripcionServicio, Estatus, Notas, MaquinaLinea, FechaHoraInicio, FechaHoraFin,
                   TiempoTraslado, TiempoComida, FirmaConformidad, Cotizacion
            FROM ReportesServicio
            WHERE IdReporte = %s
        """, (int(id_reporte),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        return dict(zip([c[0] for c in cursor.description], row))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# El formulario de reportes captura FECHA (input date) y HORA (input time) por
# separado. FechaHoraInicio/Fin son DATETIME: guardar solo la hora ("09:25")
# hace que SQL Server le ponga 1900-01-01 (los reportes que salieron con fecha
# 1900). Aquí se combinan con la fecha del reporte.
def _fecha_hora(fecha, hora):
    if not hora:
        return None
    h = str(hora).strip()
    # <input type="datetime-local"> manda "YYYY-MM-DDTHH:MM": ya trae la fecha,
    # solo se cambia la 'T' por espacio (SQL Server lo prefiere así).
    if "T" in h:
        return h.replace("T", " ")
    if not fecha:
        return h
    partes = h.split(":")
    es_solo_hora = len(partes) in (2, 3) and all(p.isdigit() for p in partes)
    return f"{str(fecha).strip()} {h}" if es_solo_hora else h


@app.post("/api/reportes")
async def api_create_reporte(body: ReporteCreate, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ISNULL(MAX(IdReporte), 0) + 1 FROM ReportesServicio")
        row = cursor.fetchone()
        next_id = int(row[0]) if row else 1
        folio = f"RS-{str(next_id).zfill(5)}"

        fecha_str = str(body.fecha)
        cursor.execute("""
            INSERT INTO ReportesServicio (
                Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                DescripcionServicio, Estatus, Notas, MaquinaLinea,
                FechaHoraInicio, FechaHoraFin, TiempoTraslado, TiempoComida
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Borrador', %s, %s, %s, %s, %s, %s)
        """, (
            folio,
            body.cliente.strip(),
            body.contacto.strip() if body.contacto else None,
            body.correo_contacto.strip() if body.correo_contacto else None,
            fecha_str,
            body.tecnico.strip(),
            body.descripcion.strip() if body.descripcion else None,
            body.notas.strip() if body.notas else None,
            body.maquina_linea.strip() if body.maquina_linea else None,
            _fecha_hora(fecha_str, body.fecha_inicio),
            _fecha_hora(fecha_str, body.fecha_fin),
            float(body.tiempo_traslado or 0.0),
            1 if body.tiempo_comida else 0,
        ))
        conn.commit()
        cursor.execute("SELECT SCOPE_IDENTITY()")
        row = cursor.fetchone()
        id_reporte = int(row[0]) if row and row[0] else None

        # Tecnicos adicionales
        if id_reporte and body.tecnicos_adicionales:
            for t in body.tecnicos_adicionales:
                cursor.execute("SELECT Id FROM HUB_Users WHERE Nombre = %s", (t.strip(),))
                ur = cursor.fetchone()
                if ur:
                    cursor.execute("INSERT INTO ReportesServicioTecnicos (IdReporte, IdUsuario) VALUES (%s, %s)", (id_reporte, ur[0]))
            conn.commit()

        conn.close()
        # Legends: +3 por registro de reporte (idempotente por id)
        if id_reporte:
            try:
                legends_registrar_metrica(current_user["id"], "reporte_creado", referencia_id=int(id_reporte))
            except Exception:
                pass
        return {"ok": True, "folio": folio, "id_reporte": id_reporte}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.put("/api/reportes/{id_reporte}")
async def api_update_reporte(id_reporte: int, body: ReporteUpdate, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Build dynamic update
        fields = []
        vals = []
        # La fecha y la hora vienen SEPARADAS (input date + input time).
        # FechaHoraInicio/Fin son DATETIME: guardar solo la hora ("09:25") hacía
        # que SQL Server le pusiera 1900-01-01. Se combinan con la fecha del
        # reporte (la del body, o la que ya está en la BD si no viene).
        fecha_reporte = str(body.fecha).strip() if body.fecha else None
        if not fecha_reporte and (body.fecha_inicio or body.fecha_fin):
            cursor.execute("SELECT Fecha FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
            fr = cursor.fetchone()
            fecha_reporte = fr[0] if fr else None
        if body.cliente:
            fields.append("Cliente = %s"); vals.append(body.cliente.strip())
        if body.contacto is not None:
            fields.append("Contacto = %s"); vals.append(body.contacto.strip() if body.contacto else None)
        if body.correo_contacto is not None:
            fields.append("CorreoContacto = %s"); vals.append(body.correo_contacto.strip() if body.correo_contacto else None)
        if body.fecha:
            fields.append("Fecha = %s"); vals.append(str(body.fecha))
        if body.tecnico:
            fields.append("Tecnico = %s"); vals.append(body.tecnico.strip())
        if body.descripcion is not None:
            fields.append("DescripcionServicio = %s"); vals.append(body.descripcion.strip() if body.descripcion else None)
        if body.estatus:
            fields.append("Estatus = %s"); vals.append(body.estatus.strip())
        if body.notas is not None:
            fields.append("Notas = %s"); vals.append(body.notas.strip() if body.notas else None)
        if body.maquina_linea is not None:
            fields.append("MaquinaLinea = %s"); vals.append(body.maquina_linea.strip() if body.maquina_linea else None)
        if body.fecha_inicio:
            fields.append("FechaHoraInicio = %s"); vals.append(_fecha_hora(fecha_reporte, body.fecha_inicio))
        if body.fecha_fin:
            fields.append("FechaHoraFin = %s"); vals.append(_fecha_hora(fecha_reporte, body.fecha_fin))
        if body.tiempo_traslado is not None:
            fields.append("TiempoTraslado = %s"); vals.append(float(body.tiempo_traslado or 0.0))
        if body.tiempo_comida is not None:
            fields.append("TiempoComida = %s"); vals.append(1 if body.tiempo_comida else 0)

        if fields:
            vals.append(int(id_reporte))
            cursor.execute(f"UPDATE ReportesServicio SET {', '.join(fields)} WHERE IdReporte = %s", tuple(vals))

        # Tecnicos adicionales (replace)
        if body.tecnicos_adicionales is not None:
            cursor.execute("DELETE FROM ReportesServicioTecnicos WHERE IdReporte = %s", (int(id_reporte),))
            for t in body.tecnicos_adicionales:
                cursor.execute("SELECT Id FROM HUB_Users WHERE Nombre = %s", (t.strip(),))
                ur = cursor.fetchone()
                if ur:
                    cursor.execute("INSERT INTO ReportesServicioTecnicos (IdReporte, IdUsuario) VALUES (%s, %s)", (id_reporte, ur[0]))

        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/reportes/{id_reporte}")
async def api_delete_reporte(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Soft delete: marcar como eliminado en lugar de borrar
        cursor.execute("SELECT Folio FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        row = cursor.fetchone()
        folio = row[0] if row else str(id_reporte)
        cursor.execute("UPDATE ReportesServicio SET Eliminado = 1, FechaEliminado = GETDATE() WHERE IdReporte = %s", (int(id_reporte),))
        conn.commit()
        conn.close()
        return {"ok": True, "folio": folio, "message": "Movido a papelera"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/reportes/{id_reporte}/restaurar")
async def api_restaurar_reporte(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ReportesServicio SET Eliminado = 0, FechaEliminado = NULL WHERE IdReporte = %s", (int(id_reporte),))
        conn.commit()
        cursor.execute("SELECT Folio FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        row = cursor.fetchone()
        conn.close()
        return {"ok": True, "folio": row[0] if row else "", "message": "Restaurado desde papelera"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/reportes/{id_reporte}/purge")
async def api_purge_reporte(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Folio FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        row = cursor.fetchone()
        folio = row[0] if row else str(id_reporte)
        cursor.execute("DELETE FROM ReportesServicioFotos WHERE IdReporte = %s", (int(id_reporte),))
        cursor.execute("DELETE FROM ReportesServicioTecnicos WHERE IdReporte = %s", (int(id_reporte),))
        cursor.execute("DELETE FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        conn.commit()
        conn.close()
        return {"ok": True, "folio": folio, "message": "Eliminado permanentemente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/reportes/{id_reporte}/fotos")
async def api_get_fotos(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT IdFoto, FotoComprimida, Orden FROM ReportesServicioFotos WHERE IdReporte = %s ORDER BY Orden", (int(id_reporte),))
        rows = cursor.fetchall()
        conn.close()
        # La BD guarda JPEG crudos (varbinary, igual que HUB/Field); el frontend
        # espera base64 ( <img src="data:image/jpeg;base64,{base64}"> ).
        # Compat doble: si la fila ya es texto base64 ASCII, se devuelve tal cual.
        result = []
        for r in rows:
            foto = r[1]
            if isinstance(foto, (bytes, bytearray)):
                if foto[:2] in (b"\xff\xd8", b"\x89P") or len(foto) > 4096:
                    foto = base64.b64encode(bytes(foto)).decode("ascii")
                else:
                    foto = bytes(foto).decode("ascii", errors="replace")
            result.append({"id": r[0], "base64": foto, "orden": r[2]})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/reportes/{id_reporte}/fotos")
async def api_save_fotos(id_reporte: int, body: ReporteFotosSave, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ReportesServicioFotos WHERE IdReporte = %s", (int(id_reporte),))
        # FotoComprimida es varbinary con JPEG crudos (convención HUB/Field);
        # hay que decodificar el base64 del frontend a bytes, si no SQL Server
        # rechaza el nvarchar con error 257.
        fotos_bytes = []
        for i, b64 in enumerate(body.fotos):
            try:
                fotos_bytes.append(base64.b64decode(b64.split(",")[-1]))
            except Exception:
                conn.close()
                raise HTTPException(status_code=400, detail=f"Foto {i + 1}: base64 inválido.")
        for i, foto_bytes in enumerate(fotos_bytes):
            cursor.execute("INSERT INTO ReportesServicioFotos (IdReporte, FotoComprimida, Orden) VALUES (%s, %s, %s)", (int(id_reporte), foto_bytes, i))
        conn.commit()
        conn.close()
        # Legends: +2 por evidencia fotográfica, 1× por reporte aunque se
        # vuelvan a guardar las fotos (el endpoint reemplaza el set completo)
        if body.fotos:
            try:
                legends_registrar_metrica(current_user["id"], "reporte_fotos", referencia_id=int(id_reporte))
            except Exception:
                pass
        return {"ok": True, "guardadas": len(body.fotos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/reportes/{id_reporte}/fotos/{id_foto}")
async def api_delete_foto(id_reporte: int, id_foto: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ReportesServicioFotos WHERE IdFoto = %s AND IdReporte = %s", (int(id_foto), int(id_reporte)))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/reportes/{id_reporte}/tecnicos")
async def api_get_tecnicos(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.Nombre FROM ReportesServicioTecnicos t
            INNER JOIN HUB_Users u ON u.Id = t.IdUsuario
            WHERE t.IdReporte = %s
        """, (int(id_reporte),))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/reportes/{id_reporte}/tecnicos")
async def api_save_tecnicos(id_reporte: int, body: ReporteTecnicosSave, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ReportesServicioTecnicos WHERE IdReporte = %s", (int(id_reporte),))
        for t in body.tecnicos:
            cursor.execute("SELECT Id FROM HUB_Users WHERE Nombre = %s", (t.strip(),))
            ur = cursor.fetchone()
            if ur:
                cursor.execute("INSERT INTO ReportesServicioTecnicos (IdReporte, IdUsuario) VALUES (%s, %s)", (int(id_reporte), ur[0]))
        conn.commit()
        conn.close()
        return {"ok": True, "guardados": len(body.tecnicos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/reportes/{id_reporte}/firma")
async def api_save_firma(id_reporte: int, body: ReporteSignatureSave, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ReportesServicio SET FirmaConformidad = %s, Estatus = 'Firmado' WHERE IdReporte = %s", (body.signature_base64, int(id_reporte)))
        conn.commit()
        cursor.execute("SELECT Folio FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        row = cursor.fetchone()
        conn.close()
        # Legends: mismos puntos que Field al firmar (+10 al firmante y
        # horas de servicio a los participantes; idempotente por ReferenciaId)
        try:
            legends_registrar_metrica(current_user["id"], "reporte_firmado", referencia_id=int(id_reporte))
        except Exception:
            pass
        try:
            legends_registrar_puntos_servicio(int(id_reporte))
        except Exception:
            pass
        return {"ok": True, "folio": row[0] if row else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/reportes/{id_reporte}/pdf")
async def api_reporte_pdf(id_reporte: int, request: Request, current_user: dict = Depends(_user_from_header_or_query)):
    """Genera PDF del reporte de servicio IDÉNTICO al HUB (pdf_generator.generate_service_report_pdf)."""
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Reporte completo
        cursor.execute("""
            SELECT IdReporte, Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                   DescripcionServicio, Estatus, Notas, MaquinaLinea, FechaHoraInicio, FechaHoraFin,
                   TiempoTraslado, TiempoComida, FirmaConformidad, Cotizacion
            FROM ReportesServicio WHERE IdReporte = %s
        """, (int(id_reporte),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        # Técnicos adicionales
        cursor.execute("""
            SELECT u.Nombre FROM ReportesServicioTecnicos t
            INNER JOIN HUB_Users u ON u.Id = t.IdUsuario
            WHERE t.IdReporte = %s
        """, (int(id_reporte),))
        tecnicos_rows = cursor.fetchall()
        tecnicos_adicionales = [r[0] for r in tecnicos_rows if r[0] != row[6]]  # excluir técnico principal

        # Fotos
        cursor.execute("SELECT IdFoto, FotoComprimida, Orden FROM ReportesServicioFotos WHERE IdReporte = %s ORDER BY Orden", (int(id_reporte),))
        fotos_rows = cursor.fetchall()
        fotos = [{"FotoComprimida": r[1], "Orden": r[2]} for r in fotos_rows]

        # Nombre del cliente (razón social)
        cursor.execute("SELECT Cliente FROM clientes WHERE IdCliente = %s", (row[2],))
        cliente_row = cursor.fetchone()
        cliente_nombre = cliente_row[0] if cliente_row else None

        conn.close()

        # Build report dict compatible with HUB pdf_generator
        report = {
            "IdReporte": row[0],
            "Folio": row[1],
            "Cliente": row[2],
            "Contacto": row[3],
            "CorreoContacto": row[4],
            "Fecha": row[5],
            "Tecnico": row[6],
            "DescripcionServicio": row[7],
            "Estatus": row[8],
            "Notas": row[9],
            "MaquinaLinea": row[10],
            "FechaHoraInicio": row[11],
            "FechaHoraFin": row[12],
            "TiempoTraslado": row[13],
            "TiempoComida": row[14],
            "FirmaConformidad": row[15],
            "Cotizacion": row[16],
        }

        pdf_bytes = build_service_report_pdf(report, tecnicos_adicionales=tecnicos_adicionales, fotos=fotos, cliente_nombre=cliente_nombre)
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{row[1]}.pdf"'})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {str(e)}")


@app.get("/api/reportes/{id_reporte}/enviar")
async def api_reporte_enviar(id_reporte: int, email: str, current_user: dict = Depends(get_current_user)):
    """Envía PDF del reporte por email (adjunto) — usa el mismo PDF IDÉNTICO al HUB."""
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT IdReporte, Folio, Cliente, Contacto, CorreoContacto, Fecha, Tecnico,
                   DescripcionServicio, Estatus, Notas, MaquinaLinea, FechaHoraInicio, FechaHoraFin,
                   TiempoTraslado, TiempoComida, FirmaConformidad, Cotizacion
            FROM ReportesServicio WHERE IdReporte = %s
        """, (int(id_reporte),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Reporte no encontrado")

        cursor.execute("""
            SELECT u.Nombre FROM ReportesServicioTecnicos t
            INNER JOIN HUB_Users u ON u.Id = t.IdUsuario
            WHERE t.IdReporte = %s
        """, (int(id_reporte),))
        tecnicos_rows = cursor.fetchall()
        tecnicos_adicionales = [r[0] for r in tecnicos_rows if r[0] != row[6]]

        cursor.execute("SELECT IdFoto, FotoComprimida, Orden FROM ReportesServicioFotos WHERE IdReporte = %s ORDER BY Orden", (int(id_reporte),))
        fotos_rows = cursor.fetchall()
        fotos = [{"FotoComprimida": r[1], "Orden": r[2]} for r in fotos_rows]

        cursor.execute("SELECT Cliente FROM clientes WHERE IdCliente = %s", (row[2],))
        cliente_row = cursor.fetchone()
        cliente_nombre = cliente_row[0] if cliente_row else None

        conn.close()

        report = {
            "IdReporte": row[0],
            "Folio": row[1],
            "Cliente": row[2],
            "Contacto": row[3],
            "CorreoContacto": row[4],
            "Fecha": row[5],
            "Tecnico": row[6],
            "DescripcionServicio": row[7],
            "Estatus": row[8],
            "Notas": row[9],
            "MaquinaLinea": row[10],
            "FechaHoraInicio": row[11],
            "FechaHoraFin": row[12],
            "TiempoTraslado": row[13],
            "TiempoComida": row[14],
            "FirmaConformidad": row[15],
            "Cotizacion": row[16],
        }

        pdf_bytes = build_service_report_pdf(report, tecnicos_adicionales=tecnicos_adicionales, fotos=fotos, cliente_nombre=cliente_nombre)

        # Send email
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.application import MIMEApplication
        from email.mime.text import MIMEText

        smtp_host = os.getenv("HUB_SMTP_SERVER", "smtp.office365.com")
        smtp_port = int(os.getenv("HUB_SMTP_PORT", "587"))
        smtp_user = os.getenv("HUB_SMTP_USER", "sistemas@ecc-sa.com.mx")
        smtp_pass = os.getenv("HUB_SMTP_PASSWORD", "eyccazo")

        msg = MIMEMultipart()
        msg["Subject"] = f"Reporte de Servicio {row[1]} - {row[2]}"
        msg["From"] = smtp_user
        msg["To"] = email
        msg.attach(MIMEText(f"Adjunto reporte de servicio {row[1]} para el cliente {row[2]}.", "plain"))
        att = MIMEApplication(pdf_bytes, _subtype="pdf")
        att.add_header("Content-Disposition", "attachment", filename=f"{row[1]}.pdf")
        msg.attach(att)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return {"ok": True, "message": f"Enviado a {email}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enviando email: {str(e)}")


# ===== ECCSA IA CHAT (AccesoIA) =====

class IaConversacionCreate(BaseModel):
    titulo: str = "Nueva conversación"


class IaMensajeCreate(BaseModel):
    contenido: str


def _require_ia(current_user: dict):
    """En el HUB, Jarvis está disponible para todos los usuarios logueados sin permiso especial."""
    pass  # No restriction


def _cleanup_fifo_conversaciones(cursor, user_id: int):
    """FIFO cleanup: mantiene solo las últimas 10 conversaciones por usuario (igual que HUB)."""
    cursor.execute("""
        DELETE FROM HUB_JarvisMensajes 
        WHERE IdConversacion IN (
            SELECT Id FROM HUB_JarvisConversaciones 
            WHERE IdUsuario = %s 
            ORDER BY FechaCreacion DESC
            OFFSET 10 ROWS
        )
    """, (user_id,))
    cursor.execute("""
        DELETE FROM HUB_JarvisConversaciones 
        WHERE Id IN (
            SELECT Id FROM HUB_JarvisConversaciones 
            WHERE IdUsuario = %s 
            ORDER BY FechaCreacion DESC
            OFFSET 10 ROWS
        )
    """, (user_id,))


@app.get("/api/ia/conversaciones")
async def ia_list_conversaciones(current_user: dict = Depends(get_current_user)):
    _require_ia(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # FIFO cleanup: max 10 conversations per user
        _cleanup_fifo_conversaciones(cursor, current_user["id"])
        # Listar del usuario
        cursor.execute("""
            SELECT Id, Titulo, FechaCreacion
            FROM HUB_JarvisConversaciones
            WHERE IdUsuario = %s
            ORDER BY FechaCreacion DESC
        """, (current_user["id"],))
        rows = cursor.fetchall()
        conn.close()
        return [{"Id": r[0], "Titulo": r[1], "FechaCreacion": r[2]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/ia/conversaciones")
async def ia_create_conversacion(body: IaConversacionCreate, current_user: dict = Depends(get_current_user)):
    _require_ia(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO HUB_JarvisConversaciones (IdUsuario, Titulo)
            VALUES (%s, %s);
            SELECT SCOPE_IDENTITY();
        """, (current_user["id"], body.titulo[:200]))
        row = cursor.fetchone()
        id_conv = int(row[0]) if row else None
        conn.commit()
        conn.close()
        return {"Id": id_conv, "Titulo": body.titulo, "FechaCreacion": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/ia/conversaciones/{id_conversacion}/mensajes")
async def ia_get_mensajes(id_conversacion: int, current_user: dict = Depends(get_current_user)):
    _require_ia(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Verificar propiedad
        cursor.execute("SELECT Id FROM HUB_JarvisConversaciones WHERE Id = %s AND IdUsuario = %s", (id_conversacion, current_user["id"]))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        # Obtener mensajes
        cursor.execute("""
            SELECT Id, [Role], Contenido, FechaRegistro
            FROM HUB_JarvisMensajes
            WHERE IdConversacion = %s
            ORDER BY FechaRegistro ASC, Id ASC
        """, (id_conversacion,))
        rows = cursor.fetchall()
        conn.close()
        return [{"Id": r[0], "Role": r[1], "Contenido": r[2], "FechaRegistro": r[3]} for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/ia/conversaciones/{id_conversacion}/mensajes")
async def ia_send_mensaje(id_conversacion: int, body: IaMensajeCreate, current_user: dict = Depends(get_current_user)):
    """
    CLON EXACTO del HUB views/edwin_jarvis.py process_jarvis_query
    3 Tools: execute_query, send_quote_pdf, send_service_reports
    System instruction con schema completo + admin/non-admin filtering
    """
    _require_ia(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Verificar propiedad
        cursor.execute("SELECT Id FROM HUB_JarvisConversaciones WHERE Id = %s AND IdUsuario = %s", (id_conversacion, current_user["id"]))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # 1. Guardar mensaje del usuario
        cursor.execute("""
            INSERT INTO HUB_JarvisMensajes (IdConversacion, [Role], Contenido)
            VALUES (%s, 'user', %s)
        """, (id_conversacion, body.contenido))
        conn.commit()

        # 2. Obtener config IA (api_key + model)
        # OJO: la columna se llama `Model` (no `Modelo`) en HUB_AiConfig.
        cursor.execute("SELECT ApiKey, Model FROM HUB_AiConfig WHERE Id = 1")
        ai_cfg_row = cursor.fetchone()
        if not ai_cfg_row or not ai_cfg_row[0]:
            # Guardar mensaje de error
            cursor.execute("INSERT INTO HUB_JarvisMensajes (IdConversacion, [Role], Contenido) VALUES (%s, 'model', %s)",
                          (id_conversacion, "❌ No hay una clave de API (API Key) configurada para Google Gemini. Por favor configúrala en el HUB en 'Configuración IA'."))
            conn.commit()
            conn.close()
            return await ia_get_mensajes(id_conversacion, current_user)

        api_key, model_name = ai_cfg_row[0], ai_cfg_row[1] or 'gemini-3.5-flash-lite'

        # 3. Obtener historial para contexto (últimos 8 turnos = 16 mensajes)
        cursor.execute("""
            SELECT [Role], Contenido FROM HUB_JarvisMensajes 
            WHERE IdConversacion = %s 
            ORDER BY FechaRegistro DESC
        """, (id_conversacion,))
        historial_rows = cursor.fetchall()
        historial = []
        for r in reversed(historial_rows[-16:]):
            role = r[0] if r[0] in ('user', 'model') else 'user'
            historial.append({"role": role, "parts": [r[1]]})

        # 4. Obtener info usuario para system_instruction
        cursor.execute("SELECT Nombre, Email, Id FROM HUB_Users WHERE Id = %s", (current_user["id"],))
        user_row = cursor.fetchone()
        user_name = user_row[0] if user_row else "Colaborador"
        user_email = user_row[1] if user_row else ""
        user_id = user_row[2] if user_row else current_user["id"]
        is_admin = current_user.get("acceso_usuarios", False)

        # 5. Definir Tools (igual que HUB)
        def execute_query(sql_query: str) -> str:
            """Ejecuta una consulta SQL SELECT de solo lectura en la base de datos de ECCSA."""
            # Admin filter injection block for non-admin users
            if not is_admin:
                sql_upper = sql_query.upper()
                if "FROM HUB_USER" in sql_upper or "FROM HUB_VACACIONES" in sql_upper or "FROM HUB_HORASEXTRAS" in sql_upper or "FROM HUB_REGISTROREPORTES" in sql_upper or "FROM HUB_REPORTES" in sql_upper:
                    if f"IDUSUARIO = {user_id}" not in sql_upper and f"ID = {user_id}" not in sql_upper and f"USUARIO = {user_id}" not in sql_upper:
                        if " WHERE " in sql_upper:
                            sql_query += f" AND IdUsuario = {user_id}"
                        else:
                            if "HUB_HORASEXTRASREGISTROS" in sql_upper:
                                sql_query += f" WHERE IdUsuario = {user_id}"
                            elif "HUB_VACACIONESREGISTROS" in sql_upper:
                                sql_query += f" WHERE IdUsuario = {user_id}"
                            elif "HUB_USERS" in sql_upper:
                                sql_query += f" WHERE Id = {user_id}"
            res = execute_readonly_sql(sql_query)
            try:
                import json
                return json.dumps(res, default=str, ensure_ascii=False)
            except:
                return str(res)

        def send_quote_pdf(folio: str, recipient_email: str = None) -> str:
            """Genera el PDF de la cotización indicada y la envía por correo electrónico."""
            target_email = (recipient_email or user_email).strip()
            try:
                q_rows = execute_readonly_sql(f"SELECT * FROM IndiceMateriales WHERE Folio = '{folio.strip()}'")
                if not q_rows or "Error" in q_rows[0] or len(q_rows) == 0:
                    return f"No se encontró ninguna cotización con folio {folio} en la base de datos."
                pdf_bytes = build_cotizacion_pdf(q_rows[0], q_rows[1:]) if len(q_rows) > 1 else build_cotizacion_pdf(q_rows[0], [])
                if not pdf_bytes:
                    return f"Error al generar el archivo PDF para la cotización {folio}."
                
                import random
                butler_quotes = [
                    "Es un honor servirle. He preparado y despachado el documento solicitado con la mayor diligencia.",
                    "Como siempre, me he tomado la libertad de gestionar el envío de este documento para facilitar sus labores.",
                    "Hecho. He enviado la cotización adjunta. Avíseme si requiere que prepare alguna bebida o asista en otra labor.",
                    "El archivo ha sido enviado. Quedo a su entera disposición para cualquier requerimiento adicional, señor.",
                    "Confirmado. El reporte digital ha sido enviado al buzón indicado de forma inmediata."
                ]
                quote = random.choice(butler_quotes)
                
                from api.main import send_email_with_multiple_pdfs
                success, msg_err = send_email_with_multiple_pdfs(
                    to_email=target_email,
                    subject=f"ECCSA IA: Cotización de Materiales {folio}",
                    body=f"Hola,\n\n{quote}\n\nAquí tienes el PDF de la cotización {folio} que solicitaste.\n\nSaludos,\nECCSA IA",
                    attachments=[(pdf_bytes, f"Cotizacion_{folio}.pdf")] if pdf_bytes else [],
                    sender_name="ECCSA IA",
                    sender_email="robot@ecc-sa.com.mx"
                )
                if success:
                    return f"La cotización {folio} ha sido generada en PDF y enviada a {target_email} exitosamente."
                else:
                    return f"Error SMTP al enviar el correo: {msg_err}"
            except Exception as ex:
                return f"Error al procesar la cotización: {str(ex)}"

        def send_service_reports(folios: list, recipient_email: str = None) -> str:
            """Genera los PDFs de los folios de reporte indicados y los envía consolidados al correo."""
            target_email = (recipient_email or user_email).strip()
            try:
                attachments = []
                for f in folios:
                    f_clean = f.strip()
                    rep_rows = execute_readonly_sql(f"SELECT * FROM HUB_RegistroReportes WHERE Folio = '{f_clean}'")
                    if not rep_rows or "Error" in rep_rows[0]:
                        continue
                    pdf_bytes = build_service_report_pdf(rep_rows[0], [], [], None)
                    if pdf_bytes:
                        attachments.append((pdf_bytes, f"Reporte_Servicio_{f_clean}.pdf"))
                
                if not attachments:
                    return "No se pudieron generar los PDFs de los folios provistos."
                
                import random
                butler_quotes = [
                    "Cumpliendo con su solicitud, he recopilado y enviado los reportes de servicio técnico pertinentes.",
                    "Los reportes de campo solicitados ya han sido despachados a su correo. Espero sean de utilidad.",
                    "Operación completada. Adjunto el historial de servicios técnicos solicitados.",
                    "He enviado la correspondencia electrónica con los adjuntos correspondientes. Quedo atento a nuevas instrucciones."
                ]
                quote = random.choice(butler_quotes)
                
                from api.main import send_email_with_multiple_pdfs
                success, msg_err = send_email_with_multiple_pdfs(
                    to_email=target_email,
                    subject=f"ECCSA IA: Reportes de Servicio Técnico",
                    body=f"Hola,\n\n{quote}\n\nAdjunto a este correo encontrarás los reportes de servicio que solicitaste:\n{', '.join(folios)}\n\nSaludos,\nECCSA IA",
                    attachments=attachments,
                    sender_name="ECCSA IA",
                    sender_email="robot@ecc-sa.com.mx"
                )
                if success:
                    return f"Se han enviado los reportes ({', '.join(folios)}) en PDF a {target_email} exitosamente."
                else:
                    return f"Error SMTP al enviar los reportes por correo: {msg_err}"
            except Exception as ex:
                return f"Error al procesar reportes: {str(ex)}"

        tools_dict = {
            "execute_query": execute_query,
            "send_quote_pdf": send_quote_pdf,
            "send_service_reports": send_service_reports
        }

        # 6. System instruction CLON EXACTO del HUB
        system_instruction = f"""Eres ECCSA IA, el asistente de inteligencia artificial personalizado de ECCSA Automation.
Te estás comunicando con el usuario {user_name} cuyo correo electrónico es {user_email} (su IdUsuario es {user_id}).
Debes dirigirte a él o ella por su nombre de pila ({user_name}) y hablar de forma extremadamente formal, servicial y profesional.

Tienes acceso directo de consulta a la base de datos de ECCSA mediante la herramienta `execute_query`.
ESTRUCTURA DE NUESTRAS TABLAS EN SQL SERVER:
1. `HUB_Users` (Id, Email, Nombre, Activo, FechaIngreso)
2. `IndiceMateriales` (Folio, IdCliente, Contacto, Fecha, Descripcion, Autor, Color) -- Contiene el encabezado de las cotizaciones de materiales.
3. `Partidas` (Folio, Partida, Cantidad, Descripcion, PrecioCompraUnitario, Factor, Proveedor, TiempoEntregaDias, Dolar, Flete) -- Contiene las partidas/artículos de las cotizaciones de materiales.
4. `HUB_RegistroReportes` (IdReporte, Folio, Cliente, Contacto, CorreoContacto, FechaHoraInicio, FechaHoraFin, TiempoTraslado, TiempoComida, Tecnico, DescripcionServicio, Notas, Estatus)
5. `HUB_HorasExtrasRegistros` (Id, IdUsuario, Fecha, HoraEntrada, HoraSalida, HorasComida, HorasTraslado, HorasExtrasCalculadas, Descripcion, Cliente, Estatus)
6. `HUB_VacacionesRegistros` (Id, IdUsuario, Fecha, Tipo, Comentarios)
7. `clientes` (IdCliente, Cliente, Contacto, Telefono, Email) -- Catálogo de clientes de la empresa.
8. `vw_ResumenCotizaciones` (Folio, IdCliente, Cliente, Contacto, Fecha, DescripcionGeneral, Autor, Estatus, SumaPartidas, FleteCotizacion, Subtotal, IVA, TotalFinal) -- Vista útil para consultar resúmenes de cotizaciones.

REGLAS DE SEGURIDAD:
- Solo ejecuta consultas SQL SELECT de lectura. Tienes prohibido alterar nada en la base de datos.
- Si el usuario NO es Administrador (Administrador es cuando is_admin={is_admin} es True, actualmente is_admin={is_admin}), solo puedes mostrarle información perteneciente a su propio IdUsuario ({user_id}) de las tablas de horas extras, vacaciones, reportes de servicio, etc. Para esto, siempre inyecta la condición `IdUsuario = {user_id}` en tus consultas SQL.
- Tienes prohibido inventar o consultar datos de nómina u horas de otros usuarios si el usuario no es administrador.

HABILIDADES DE ENVÍO DE DOCUMENTOS:
- Si el usuario te pide que le envíes una cotización, llama a la herramienta `send_quote_pdf` pasándole el folio. Puede enviar a otro correo o usuario si te lo especifica en el argumento `recipient_email`.
- Si te pide que le envíes reportes de servicio por correo, llama a la herramienta `send_service_reports` pasándole la lista de folios. Puede enviar a otro correo o usuario si te lo especifica en el argumento `recipient_email`.

CONTESTAR PREGUNTAS GENERALES:
- Puedes contestar libremente sobre cualquier otro tema (SAT, cotizaciones, explicaciones técnicas, cálculos matemáticos, redacción de correos profesionales, etc.) usando tu propio conocimiento general. Si te preguntan por códigos del SAT para partidas de cotización, haz una consulta a las partidas de la cotización pedida, analiza los productos, sugiere las claves del SAT más convenientes y explica el porqué.

Sé claro, directo, estructurado y presenta los datos de forma elegante en tablas Markdown cuando corresponda.
"""

        # 7. Llamar a Gemini con function calling
        import google.generativeai as genai
        import google.ai.generativelanguage as glm
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            tools=[execute_query, send_quote_pdf, send_service_reports]
        )
        
        chat = model.start_chat(history=historial[:-1] if len(historial) > 1 else [])
        response = chat.send_message(body.contenido)

        # 8. Handle Function Calling loop (max 8 loops como HUB)
        loop_count = 0
        while response.candidates and response.candidates[0].content.parts and loop_count < 8:
            has_fcall = False
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    has_fcall = True
                    name_tool = part.function_call.name
                    args = dict(part.function_call.args)
                    
                    if name_tool in tools_dict:
                        tool_func = tools_dict[name_tool]
                        func_result = tool_func(**args)
                        
                        response = chat.send_message(
                            glm.Content(
                                parts=[
                                    glm.Part(
                                        function_response=glm.FunctionResponse(
                                            name=name_tool,
                                            response={'result': func_result}
                                        )
                                    )
                                ]
                            )
                        )
                        break
            
            if not has_fcall:
                break
            loop_count += 1
        
        # 9. Obtener respuesta final
        try:
            respuesta = response.text.strip()
        except Exception:
            texts = [p.text for p in response.candidates[0].content.parts if p.text]
            respuesta = "".join(texts).strip() if texts else "🤖 *ECCSA IA*: Disculpe la molestia, señor. He procesado la consulta en nuestra base de datos, pero la respuesta no contiene texto legible."

        # 10. Guardar respuesta del model
        cursor.execute("""
            INSERT INTO HUB_JarvisMensajes (IdConversacion, [Role], Contenido)
            VALUES (%s, 'model', %s)
        """, (id_conversacion, respuesta))

        # 11. Auto-título si es primera conversación (título = primeras 50 chars del primer mensaje)
        cursor.execute("SELECT Titulo FROM HUB_JarvisConversaciones WHERE Id = %s", (id_conversacion,))
        titulo_row = cursor.fetchone()
        titulo_actual = titulo_row[0] if titulo_row else "Nueva conversación"
        nuevo_titulo = titulo_actual
        if titulo_actual == "Nueva conversación":
            corto = body.contenido[:50].strip()
            if len(body.contenido) > 50:
                corto += "..."
            nuevo_titulo = corto
            cursor.execute("UPDATE HUB_JarvisConversaciones SET Titulo = %s WHERE Id = %s", (nuevo_titulo, id_conversacion))

        conn.commit()

        # 12. Devolver mensajes actualizados
        cursor.execute("""
            SELECT Id, [Role], Contenido, FechaRegistro
            FROM HUB_JarvisMensajes
            WHERE IdConversacion = %s
            ORDER BY FechaRegistro ASC, Id ASC
        """, (id_conversacion,))
        rows = cursor.fetchall()
        conn.close()

        mensajes = [{"Id": r[0], "Role": r[1], "Contenido": r[2], "FechaRegistro": r[3]} for r in rows]
        return {"mensajes": mensajes, "titulo": nuevo_titulo}
        
    except HTTPException:
        raise
    except Exception as e:
        # En caso de error, guardar mensaje de error
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO HUB_JarvisMensajes (IdConversacion, [Role], Contenido) VALUES (%s, 'model', %s)",
                          (id_conversacion, f"🤖 *ECCSA IA*: Disculpe, he experimentado un percance técnico al procesar su solicitud. Detalle del error: {str(e)}"))
            conn.commit()
            conn.close()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/ia/conversaciones/{id_conversacion}")
async def ia_delete_conversacion(id_conversacion: int, current_user: dict = Depends(get_current_user)):
    _require_ia(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM HUB_JarvisConversaciones WHERE Id = %s AND IdUsuario = %s", (id_conversacion, current_user["id"]))
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        conn.commit()
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Passkeys (WebAuthn) — port desde Field -----------------------------------
# Autenticación con huella / Face ID usando la tabla compartida HUB_Passkeys.
# IMPORTANTE: desde este subdominio (admon.ecc-sa.com.mx) el navegador SOLO
# permite passkeys con rpId = ecc-sa.com.mx (el rp raíz). Las passkeys legacy
# (rpId field./hub.ecc-sa.com.mx) NO se pueden usar aquí: el navegador rechaza
# cualquier rpId que no sea sufijo del dominio actual (SecurityError). Por eso
# el registro SIEMPRE usa el rp nuevo y el login también.
import base64 as _passkey_b64
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

RP_ID = "ecc-sa.com.mx"  # rp raíz: funciona en cualquier subdominio (hub, field, admon)
RP_NAME = "ECCSA"
CHALLENGE_TTL = 5 * 60  # desafíos de 5 minutos

_PASSKEY_SECRET_CACHE: Dict[str, str] = {}


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


@app.post("/api/passkeys/login/options")
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


@app.post("/api/passkeys/login/verify")
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


@app.post("/api/passkeys/register/options")
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


@app.post("/api/passkeys/register/verify")
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


@app.get("/api/passkeys/mine")
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


@app.delete("/api/passkeys/{pid}")
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
# El cron semanal (ganador + reset domingo 3 AM) y el audit cada 5 min los
# ejecuta el contenedor `workersadmon` (programas legends_cron y legends_audit;
# migración del 2026-09-26 — antes eran programs del supervisord de Field) sobre
# la misma BD; aquí solo exponemos los endpoints de lectura, /award y el cálculo
# manual. Ojo: `legends_audit` debe tener UNA sola instancia en todo el entorno
# (si se duplica, duplica HUB_ScoreLog).
# Diferencias con Field: auth = get_current_user (token simple email|ts),
# push adaptado al esquema de Admon (HUB_PushSubscriptions.UserEmail +
# VAPID en HUB_PushConfig), y conexiones siempre cerradas.

LEGENDS_METRICAS = {
    "reporte_firmado":  10,
    "kilometro":         5,
    "ticket_oxxogas":    3,
    "vale_generado":    -2,
    "comida_reporte":   -1,
    "firma_remota":      8,
    "servicio":          0,  # Calculado dinámicamente por legends_registrar_puntos_servicio
    "racha_dia":         3,
    # ── Métricas propias de Admon (oficina) ──
    "cotizacion_enviada":  6,   # Envío real por correo (1× por folio)
    "cliente_alta":        4,   # Alta de cliente nuevo
    "reporte_creado":      3,   # Registro de reporte de servicio
    "reporte_fotos":       2,   # Evidencia fotográfica (1× por reporte)
    "cotizacion_creada":   2,   # Cotización creada desde cero
}

LEGENDS_NIVELES = [
    ("Diamante", 3500),
    ("Oro",      1500),
    ("Plata",     500),
    ("Bronce",      0),
]

LEGENDS_ICONO = {
    "Diamante": "💎",
    "Oro":      "🥇",
    "Plata":    "🥈",
    "Bronce":   "🥉",
}

# Descripciones legibles de las métricas (para /score-log)
LEGENDS_METRICA_DESC = {
    "reporte_firmado":  ("Reporte firmado", "✍️", 10),
    "kilometro":        ("Kilómetros registrados", "⛽", 5),
    "ticket_oxxogas":   ("Ticket OxxoGas", "🎫", 3),
    "vale_generado":    ("Vale generado", "💰", -2),
    "comida_reporte":   ("Hora de comida en reporte", "🍽️", -1),
    "firma_remota":     ("Firma remota de reporte", "📱", 8),
    "servicio":         ("Servicio registrado", "🔧", 0),
    "racha_dia":        ("Racha diaria activa", "🔥", 3),
    "cotizacion_enviada": ("Cotización enviada", "📤", 6),
    "cliente_alta":     ("Cliente nuevo registrado", "📇", 4),
    "reporte_creado":   ("Reporte de servicio registrado", "🗂️", 3),
    "reporte_fotos":    ("Fotos de evidencia subidas", "📸", 2),
    "cotizacion_creada": ("Cotización creada", "🧾", 2),
}


def legends_calcular_nivel(puntos: int) -> str:
    """Nivel gamificado según puntuación total acumulada."""
    for nombre, min_pts in LEGENDS_NIVELES:
        if puntos >= min_pts:
            return nombre
    return "Bronce"


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


def legends_registrar_metrica(id_usuario: int, metrica: str, referencia_id: int = None, puntos_override: int = None):
    """Registra una métrica y actualiza la puntuación del usuario.
    Solo otorga puntos si el usuario tiene passkey (nickname).
    Detecta cambios de nivel y ranking para notificar. Port exacto de
    Field `_registrar_metrica` (idempotencia por ReferenciaId incluida)."""
    if metrica not in LEGENDS_METRICAS and puntos_override is None:
        return
    puntos = puntos_override if puntos_override is not None else LEGENDS_METRICAS[metrica]

    # Idempotencia: métricas con ReferenciaId = entidad única no deben repetirse.
    # 'kilometro' excluido: su ReferenciaId es el vehículo, no el registro de km.
    _idempotent = {
        "reporte_firmado", "ticket_oxxogas", "vale_generado",
        "comida_reporte", "servicio", "firma_remota",
        # Admon: reenviar cotización, reintentar insert o volver a guardar
        # las fotos del MISMO reporte no debe volver a sumar.
        "cotizacion_enviada", "cotizacion_creada", "reporte_creado", "reporte_fotos",
    }
    if metrica in _idempotent and referencia_id is not None:
        conn0 = get_connection()
        try:
            with conn0.cursor() as cur0:
                cur0.execute(
                    "SELECT 1 AS existe FROM HUB_ScoreLog WHERE IdUsuario=%s AND Metrica=%s AND ReferenciaId=%s",
                    (id_usuario, metrica, referencia_id),
                )
                if cur0.fetchone():
                    return
        finally:
            conn0.close()

    old_level = None
    old_pos = None
    new_level = None
    nueva_semanal = 0

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

            # Capturar estado ANTES del update
            cur.execute("SELECT PuntuacionSemanal, PuntuacionTotal, Nivel FROM HUB_UserScores WHERE IdUsuario = %s", (id_usuario,))
            row = cur.fetchone()
            old_level = row["Nivel"] if row else "Bronce"
            old_weekly = row["PuntuacionSemanal"] if row else 0
            old_total = row["PuntuacionTotal"] if row else 0

            # Posición anterior
            cur.execute("""
                SELECT COUNT(*) AS total FROM HUB_UserScores s
                JOIN HUB_Users u ON s.IdUsuario = u.Id
                WHERE u.Activo = 1 AND s.PuntuacionSemanal > %s
            """, (old_weekly,))
            old_pos = (cur.fetchone()["total"] + 1) if row else 999

            # Insertar log (re-chequeo dentro de la misma conexión por si hubo carrera)
            if metrica in _idempotent and referencia_id is not None:
                cur.execute(
                    "SELECT 1 AS existe FROM HUB_ScoreLog WHERE IdUsuario=%s AND Metrica=%s AND ReferenciaId=%s",
                    (id_usuario, metrica, referencia_id),
                )
                if cur.fetchone():
                    return
            cur.execute(
                "INSERT INTO HUB_ScoreLog (IdUsuario, Metrica, Puntos, ReferenciaId) VALUES (%s, %s, %s, %s)",
                (id_usuario, metrica, puntos, referencia_id)
            )

            # Actualizar score
            if row:
                nueva_semanal = old_weekly + puntos
                nueva_total = old_total + puntos
                new_level = legends_calcular_nivel(nueva_total)
                cur.execute(
                    "UPDATE HUB_UserScores SET PuntuacionSemanal = %s, PuntuacionTotal = %s, Nivel = %s, UltimoActivo = GETDATE(), FechaCalculo = GETDATE() WHERE IdUsuario = %s",
                    (nueva_semanal, nueva_total, new_level, id_usuario)
                )
            else:
                nueva_semanal = max(puntos, 0)
                nueva_total = max(puntos, 0)
                new_level = legends_calcular_nivel(nueva_total)
                cur.execute(
                    "INSERT INTO HUB_UserScores (IdUsuario, PuntuacionSemanal, PuntuacionTotal, Nivel, UltimoActivo) VALUES (%s, %s, %s, %s, GETDATE())",
                    (id_usuario, nueva_semanal, nueva_total, new_level)
                )

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
                    SELECT IdReporte, Tecnico, FechaHoraInicio, FechaHoraFin,
                           TiempoTraslado, TiempoComida, Estatus
                    FROM ReportesServicio WHERE IdReporte = %s
                """, (id_reporte,))
                reporte = cur.fetchone()
                if not reporte or reporte['Estatus'] != 'Firmado':
                    return 0
                if not reporte['FechaHoraInicio'] or not reporte['FechaHoraFin']:
                    return 0

                # Otorgar +10 por reporte_firmado si no existe en ScoreLog
                cur.execute("SELECT 1 AS existe FROM HUB_ScoreLog WHERE ReferenciaId = %s AND Metrica = 'reporte_firmado'", (id_reporte,))
                if not cur.fetchone():
                    # Buscar IdUsuario del técnico principal
                    cur.execute("SELECT Id FROM HUB_Users WHERE Nombre = %s AND Activo = 1", (reporte['Tecnico'],))
                    u = cur.fetchone()
                    if u:
                        legends_registrar_metrica(u['Id'], 'reporte_firmado', referencia_id=id_reporte)

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

@app.get("/api/legends/score")
async def legends_score(current_user: dict = Depends(get_current_user)):
    """Puntuación del usuario actual (semanal + total + nivel + racha)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id FROM HUB_UserAvatars WHERE IdUsuario = %s", (current_user["id"],))
        tiene_avatar = bool(cursor.fetchone())
        # Nickname vive en HUB_Users (migración 0034); la passkey solo da elegibilidad
        cursor.execute("SELECT TOP 1 Nickname FROM HUB_Users WHERE Id = %s", (current_user["id"],))
        u_row = cursor.fetchone()
        nickname = (u_row.get("Nickname") or None) if u_row else None
        cursor.execute("SELECT TOP 1 1 AS existe FROM HUB_Passkeys WHERE IdUsuario = %s", (current_user["id"],))
        tiene_passkey = bool(cursor.fetchone())
        cursor.execute("SELECT * FROM HUB_UserScores WHERE IdUsuario = %s", (current_user["id"],))
        row = cursor.fetchone()
        if not row:
            return {
                "puntuacion_semanal": 0, "puntuacion_total": 0,
                "racha_dias": 0, "nivel": "Bronce",
                "icono_nivel": "🥉", "ultimo_activo": None, "tiene_avatar": tiene_avatar,
                "nickname": nickname, "tiene_passkey": tiene_passkey,
            }
        return {
            "puntuacion_semanal": row["PuntuacionSemanal"],
            "puntuacion_total": row["PuntuacionTotal"],
            "racha_dias": row["RachaDias"],
            "nivel": row["Nivel"],
            "icono_nivel": LEGENDS_ICONO.get(row["Nivel"], "🥉"),
            "ultimo_activo": row["UltimoActivo"].isoformat() if row["UltimoActivo"] else None,
            "tiene_avatar": tiene_avatar,
            "nickname": nickname,
            "tiene_passkey": tiene_passkey,
        }
    finally:
        conn.close()


@app.get("/api/legends/score-log")
async def legends_score_log(current_user: dict = Depends(get_current_user)):
    """Bitácora semanal de puntos del usuario actual.
    Muestra cada evento que sumó o restó puntos esta semana.
    Se resetea cada domingo 3 AM igual que los puntos."""
    import datetime as _dt
    # Domingo 00:00 en HORA MÉXICO. El contenedor corre en UTC y con
    # date.today() la semana empezaba el sábado 18:00 hora México, dejando la
    # bitácora y la puntuación semanal vacías (mismo fix que legends_time.py en
    # Field/WorkersAdmon).
    import pytz as _pytz
    _ahora_mx = _dt.datetime.now(_pytz.timezone("America/Mexico_City"))
    sunday = (_ahora_mx - _dt.timedelta(days=(_ahora_mx.weekday() + 1) % 7)).date()

    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, Metrica, Puntos, ReferenciaId, FechaRegistro
            FROM HUB_ScoreLog
            WHERE IdUsuario = %s AND FechaRegistro >= %s
              AND Metrica != 'sync_completado'
            ORDER BY FechaRegistro DESC
        """, (current_user["id"], sunday))
        logs = cursor.fetchall()

        # Enriquecer con descripciones legibles
        result = []
        for log in logs:
            metrica = log["Metrica"]
            desc, icono, _pts_base = LEGENDS_METRICA_DESC.get(metrica, (metrica, "📌", 0))
            result.append({
                "id": log["Id"],
                "metrica": metrica,
                "descripcion": desc,
                "icono": icono,
                "puntos": log["Puntos"],
                "fecha": log["FechaRegistro"].isoformat() if log["FechaRegistro"] else None,
                "referencia_id": log["ReferenciaId"],
            })

        # Total de la semana (excluye métricas retiradas)
        cursor.execute("""
            SELECT ISNULL(SUM(Puntos), 0) AS total
            FROM HUB_ScoreLog
            WHERE IdUsuario = %s AND FechaRegistro >= %s
              AND Metrica != 'sync_completado'
        """, (current_user["id"], sunday))
        total_semana = cursor.fetchone()["total"]

        return {
            "semana_inicio": sunday.isoformat(),
            "total_semana": total_semana,
            "eventos": result,
            "cron_info": "Los puntos se sincronizan en tiempo real. El ranking se calcula cada domingo a las 3:00 AM y los puntos se resetean.",
        }
    finally:
        conn.close()


@app.get("/api/legends/ranking")
def legends_ranking(current_user: dict = Depends(get_current_user)):
    """Ranking semanal de todos los usuarios activos con passkey."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT u.Id AS IdUsuario, u.Nombre,
                   ISNULL(s.PuntuacionSemanal, 0) AS PuntuacionSemanal,
                   ISNULL(s.PuntuacionTotal, 0) AS PuntuacionTotal,
                   ISNULL(s.Nivel, 'Bronce') AS Nivel,
                   ISNULL(s.RachaDias, 0) AS RachaDias,
                   LEN(a.AvatarBase64) AS AvatarLen, a.AvatarUrl,
                   u.Nickname AS Nickname
            FROM HUB_Users u
            INNER JOIN HUB_Passkeys p ON u.Id = p.IdUsuario
            LEFT JOIN HUB_UserScores s ON u.Id = s.IdUsuario
            LEFT JOIN HUB_UserAvatars a ON u.Id = a.IdUsuario
            WHERE u.Activo = 1
            GROUP BY u.Id, u.Nombre, s.PuntuacionSemanal, s.PuntuacionTotal,
                     s.Nivel, s.RachaDias, LEN(a.AvatarBase64), a.AvatarUrl, u.Nickname
            ORDER BY ISNULL(s.PuntuacionSemanal, 0) DESC
        """)
        rows = cursor.fetchall()

        # Los avatares NO se traen en la consulta: solo su longitud. El base64
        # crudo pesa 150-310 KB por usuario (2.5 MB en total) y además estaba en
        # el GROUP BY, que es agrupar por una columna LOB — el mismo error que
        # hacía tardar 26 s al listado de cotizaciones. Se piden solo los que
        # no estén ya en caché, ya recortados a 128 px.
        for r in rows:
            _THUMBS_LEN[int(r["IdUsuario"])] = int(r["AvatarLen"] or 0)
        thumbs = _avatares_miniatura(conn, [int(r["IdUsuario"]) for r in rows])

        ranking = []
        for i, r in enumerate(rows):
            ranking.append({
                "posicion": i + 1,
                "id_usuario": r["IdUsuario"],
                "nombre": r.get("Nickname") or r["Nombre"],
                "puntuacion_semanal": r["PuntuacionSemanal"],
                "puntuacion_total": r["PuntuacionTotal"],
                "nivel": r["Nivel"],
                "icono_nivel": LEGENDS_ICONO.get(r["Nivel"], "🥉"),
                "racha_dias": r["RachaDias"],
                "avatar": thumbs.get(int(r["IdUsuario"])) or r.get("AvatarUrl"),
                "es_yo": r["IdUsuario"] == current_user["id"],
            })
        return {"ranking": ranking}
    finally:
        conn.close()


@app.get("/api/legends/winners")
async def legends_winners(current_user: dict = Depends(get_current_user)):
    """Historial de ganadores semanales (últimas 12 semanas)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT TOP 12 w.PuntuacionSemana, w.FechaInicio, w.FechaFin,
                   w.FechaCalculo, u.Nombre, u.Nickname
            FROM HUB_WeeklyWinners w
            JOIN HUB_Users u ON w.IdUsuario = u.Id
            ORDER BY w.FechaInicio DESC
        """)
        rows = cursor.fetchall()
        winners = []
        for r in rows:
            winners.append({
                "nombre": r.get("Nickname") or r["Nombre"],
                "puntuacion": r["PuntuacionSemana"],
                "fecha_inicio": r["FechaInicio"].isoformat() if r["FechaInicio"] else None,
                "fecha_fin": r["FechaFin"].isoformat() if r["FechaFin"] else None,
            })
        return {"winners": winners}
    finally:
        conn.close()


@app.get("/api/legends/avatar")
async def legends_avatar(current_user: dict = Depends(get_current_user)):
    """Avatar IA del usuario actual."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT * FROM HUB_UserAvatars WHERE IdUsuario = %s", (current_user["id"],))
        row = cursor.fetchone()
        if not row:
            return {"generado": False}
        return {
            "generado": True,
            "avatar": row["AvatarBase64"] or row.get("AvatarUrl"),
            "nickname": row.get("Nickname"),
            "prompt": row["PromptUsado"],
            "fecha": row["FechaGenerado"].isoformat() if row["FechaGenerado"] else None,
        }
    finally:
        conn.close()


@app.get("/api/legends/weekly-winner")
async def legends_weekly_winner(current_user: dict = Depends(get_current_user)):
    """Ganador de la semana más reciente."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT TOP 1 w.*, u.Nombre, u.Nickname
            FROM HUB_WeeklyWinners w
            JOIN HUB_Users u ON w.IdUsuario = u.Id
            ORDER BY w.FechaInicio DESC
        """)
        row = cursor.fetchone()
        if not row:
            return {"hay_ganador": False}
        return {
            "hay_ganador": True,
            "nombre": row.get("Nickname") or row["Nombre"],
            "puntuacion": row["PuntuacionSemana"],
            "fecha_inicio": row["FechaInicio"].isoformat() if row["FechaInicio"] else None,
            "fecha_fin": row["FechaFin"].isoformat() if row["FechaFin"] else None,
        }
    finally:
        conn.close()


@app.post("/api/legends/award")
async def legends_award(payload: dict, current_user: dict = Depends(get_current_user)):
    """Registra una métrica para el usuario autenticado."""
    metrica = payload.get("metrica", "")
    referencia_id = payload.get("referencia_id")
    if metrica not in LEGENDS_METRICAS:
        return {"error": f"Metrica '{metrica}' no reconocida. Disponibles: {list(LEGENDS_METRICAS.keys())}"}
    legends_registrar_metrica(current_user["id"], metrica, referencia_id)
    return {"ok": True, "metrica": metrica, "puntos": LEGENDS_METRICAS[metrica]}


@app.get("/api/legends/celebrations")
async def legends_celebrations(current_user: dict = Depends(get_current_user)):
    """Cumpleaños y aniversarios del mes actual, combinados."""
    import datetime as _dt
    mes_actual = _dt.datetime.now().month

    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT u.Nombre,
                CASE
                    WHEN u.FechaNacimiento IS NOT NULL THEN DAY(u.FechaNacimiento)
                    WHEN u.CurpRfc IS NOT NULL AND LEN(u.CurpRfc) >= 10 THEN
                        CAST(SUBSTRING(u.CurpRfc, 9, 2) AS INT)
                    ELSE NULL
                END AS dia,
                CASE
                    WHEN u.FechaNacimiento IS NOT NULL THEN MONTH(u.FechaNacimiento)
                    WHEN u.CurpRfc IS NOT NULL AND LEN(u.CurpRfc) >= 10 THEN
                        CAST(SUBSTRING(u.CurpRfc, 7, 2) AS INT)
                    ELSE NULL
                END AS mes,
                CASE
                    WHEN u.FechaNacimiento IS NOT NULL THEN
                        YEAR(GETDATE()) - YEAR(u.FechaNacimiento)
                    WHEN u.CurpRfc IS NOT NULL AND LEN(u.CurpRfc) >= 10 THEN
                        CASE
                            WHEN CAST(SUBSTRING(u.CurpRfc, 5, 2) AS INT) > 30
                                THEN YEAR(GETDATE()) - (1900 + CAST(SUBSTRING(u.CurpRfc, 5, 2) AS INT))
                            ELSE YEAR(GETDATE()) - (2000 + CAST(SUBSTRING(u.CurpRfc, 5, 2) AS INT))
                        END
                    ELSE NULL
                END AS edad
            FROM HUB_Users u
            WHERE u.Activo = 1
                AND (
                    (u.FechaNacimiento IS NOT NULL AND MONTH(u.FechaNacimiento) = %s)
                    OR (u.CurpRfc IS NOT NULL AND LEN(u.CurpRfc) >= 10
                        AND CAST(SUBSTRING(u.CurpRfc, 7, 2) AS INT) = %s)
                )
            ORDER BY dia
        """, (mes_actual, mes_actual))
        cumpleanos = cursor.fetchall()

        cursor.execute("""
            SELECT u.Nombre,
                DAY(u.FechaIngreso) AS dia,
                MONTH(u.FechaIngreso) AS mes,
                YEAR(GETDATE()) - YEAR(u.FechaIngreso) AS anos
            FROM HUB_Users u
            WHERE u.Activo = 1
                AND u.FechaIngreso IS NOT NULL
                AND MONTH(u.FechaIngreso) = %s
            ORDER BY dia
        """, (mes_actual,))
        aniversarios = cursor.fetchall()
    finally:
        conn.close()

    month_names = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    return {
        "mes": month_names.get(mes_actual, ""),
        "cumpleanos": cumpleanos,
        "aniversarios": aniversarios,
    }


@app.get("/api/legends/metrics/config")
async def legends_metrics_config():
    """Configuración actual de métricas y puntos (pública dentro de la API)."""
    return {
        "nombre_puntos": "ECCSA Points",
        "metricas": LEGENDS_METRICAS,
        "niveles": {n: p for n, p in LEGENDS_NIVELES},
        "iconos": LEGENDS_ICONO,
    }


@app.post("/api/legends/cron/weekly-calculate")
async def legends_weekly_calculate():
    """Calcula ganador de la semana anterior, guarda historial, resetea puntos semanales.
    En producción lo ejecuta el worker legends_cron de Field (domingo 3 AM);
    este endpoint permite el cálculo manual. Idempotente por FechaInicio/FechaFin."""
    import pytz
    from datetime import datetime, timedelta

    mexico_tz = pytz.timezone("America/Mexico_City")
    ahora = datetime.now(mexico_tz)
    fin = ahora - timedelta(days=(ahora.weekday() + 1) % 7)
    inicio = fin - timedelta(days=7)

    print(f"[LEGENDS CRON] Calculando ganador: {inicio.date()} al {fin.date()}", flush=True)

    conn = get_connection()
    try:
        with conn.cursor(as_dict=True) as cur:
            # Usuario con más puntos semanales
            cur.execute("""
                SELECT TOP 1 IdUsuario, PuntuacionSemanal
                FROM HUB_UserScores
                WHERE PuntuacionSemanal > 0
                ORDER BY PuntuacionSemanal DESC
            """)
            winner = cur.fetchone()

            if not winner:
                print("[LEGENDS CRON] Sin actividad en la semana.", flush=True)
                return {"ok": False, "detail": "Sin actividad"}

            # Verificar si ya existe registro (idempotencia)
            cur.execute(
                "SELECT Id FROM HUB_WeeklyWinners WHERE FechaInicio = %s AND FechaFin = %s",
                (inicio.date(), fin.date())
            )
            if cur.fetchone():
                print("[LEGENDS CRON] Ya existe ganador para esta semana.", flush=True)
                return {"ok": False, "detail": "Ya calculado"}

            # Guardar ganador
            cur.execute(
                "INSERT INTO HUB_WeeklyWinners (IdUsuario, PuntuacionSemana, FechaInicio, FechaFin) VALUES (%s, %s, %s, %s)",
                (winner["IdUsuario"], winner["PuntuacionSemanal"], inicio.date(), fin.date())
            )

            # Resetear puntos semanales de TODOS
            cur.execute("UPDATE HUB_UserScores SET PuntuacionSemanal = 0")
            conn.commit()

            cur.execute("SELECT Nombre FROM HUB_Users WHERE Id = %s", (winner["IdUsuario"],))
            u = cur.fetchone()
            nombre = u["Nombre"] if u else "Desconocido"
            print(f"[LEGENDS CRON] Ganador: {nombre} con {winner['PuntuacionSemanal']} ECCSA Points", flush=True)

        # Notificar a todos (fuera del cursor; best-effort)
        legends_notify_weekly_winner(winner["IdUsuario"], winner["PuntuacionSemanal"])

        return {
            "ok": True,
            "ganador": nombre,
            "puntos": winner["PuntuacionSemanal"],
            "semana": f"{inicio.date()} al {fin.date()}",
        }
    finally:
        conn.close()


# ============================================================================
# --- Tickets de OxxoGas (solo lectura) --------------------------------------
# Muestra los tickets físicos capturados en Field/HUB (tabla HUB_OxxoGasTickets)
# con su factura CFDI enlazada (HUB_OxxoGasVales) y la estación capturada.
# Identificador principal: FolioTicket (folio del ticket impreso).
# Orden: por FechaRegistro descendente (el más reciente arriba).
# Sin factura o sin estación → null; el frontend muestra "Pendiente".
# ============================================================================

def _require_vales_oxxogas(current_user: dict):
    """Gate del módulo: mismo permiso que 'Vales OxxoGas' en el HUB."""
    if not current_user.get("acceso_vales_oxxogas"):
        raise HTTPException(status_code=403, detail="No access")


@app.get("/api/tickets-oxxogas")
def tickets_oxxogas_list(current_user: dict = Depends(get_current_user)):
    """Índice de tickets de OxxoGas con la relación factura ↔ vale.

    POR QUÉ YA NO SE USA EL `OUTER APPLY` CON `LIKE`:
    el folio del ticket vive dentro del CFDI (`NoIdentificacion`), así que hace
    falta un `LIKE '%folio%'` sobre `XmlContent`. Con 22 tickets y 255 vales de
    ~6 KB de XML, eso son 36 MB de texto escaneados en cada petición: la consulta
    tardaba 8 s de CPU y desde la API se iba a más de 20 s (timeout). Y como el
    endpoint era `async def` con pymssql síncrono, esas 8 s detenían el event
    loop y la app se anunciaba "Sin conexión".

    Ahora los vales se leen UNA vez (0.5 s) y la coincidencia del folio dentro
    del XML se hace en Python (0.08 s): 0.84 s en total, con los mismos 22
    tickets emparejados a su factura. Sin índices nuevos y sin tocar la base.

    La igualdad `XmlFolio = FolioTicket` se conserva como Atajo: es la vía
    rápida cuando el CFDI sí trae el folio parseado (hoy no matchea ninguno, pero
    si la tabla se puebla así ya no se recorre el XML). Cuando varios vales
    contienen el folio, gana el más reciente, igual que el `ORDER BY Fecha DESC`
    del `TOP 1` original.
    """
    _require_vales_oxxogas(current_user)
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(as_dict=True)
        # Cliente y proyecto/servicio pueden venir del TICKET o, si el ticket no
        # los trae (el formulario de Field ya no los captura), del VALE enlazado
        # por IdSolicitudVale. Se usa COALESCE y el clientes único (alias) para
        # no multiplicar filas con los IdCliente duplicados.
        cursor.execute(f"""
            SELECT TOP 300
                T.Id, T.FolioTicket, T.FechaRegistro, T.Estacion,
                COALESCE(NULLIF(LTRIM(RTRIM(T.Descripcion)), ''), S.Descripcion) AS Descripcion,
                CASE WHEN T.ImagenTicket IS NOT NULL THEN 1 ELSE 0 END AS TieneFoto,
                COALESCE(C.Cliente, SC.Cliente) AS Cliente,
                A.MarcaModelo, A.Placas, U.Nombre AS Capturo,
                S.FechaSolicitud AS ValeSolicitud, S.Id AS ValeId
            FROM HUB_OxxoGasTickets T
            LEFT JOIN {_CLIENTES_UNICOS} C ON C.IdCliente = T.IdCliente
            LEFT JOIN HUB_Automoviles A ON A.Id = T.IdVehiculo
            LEFT JOIN HUB_Users U ON U.Id = T.IdUsuario
            LEFT JOIN HUB_SolicitudVales S
                   ON S.Id = T.IdSolicitudVale
                  AND S.IdSolicitante = T.IdUsuario
            LEFT JOIN {_CLIENTES_UNICOS} SC ON SC.IdCliente = S.IdCliente
            ORDER BY T.FechaRegistro DESC
        """)
        tickets = cursor.fetchall()

        # Los vales se leen del más reciente al más viejo: el primero que
        # contiene el folio es el que se queda, como el TOP 1 por Fecha.
        cursor.execute(
            "SELECT XmlFolio, Fecha, Monto, XmlLitros, XmlConcepto, XmlContent "
            "FROM HUB_OxxoGasVales ORDER BY Fecha DESC"
        )
        vales = cursor.fetchall()
        conn.close()
        conn = None

        # Atajo por folio exacto, sin recorrer el XML.
        por_folio = {}
        for v in vales:
            xv = str(v["XmlFolio"] or "").strip()
            if xv and xv not in por_folio:
                por_folio[xv] = v

        resultado = []
        for t in tickets:
            folio = (t["FolioTicket"] or "").strip()
            v = por_folio.get(folio) if folio else None
            if v is None and folio:
                for cand in vales:
                    if folio in str(cand["XmlContent"] or ""):
                        v = cand
                        break
            estacion = (t["Estacion"] or "").strip()
            resultado.append({
                "id": t["Id"],
                "folio": folio,
                "fecha": t["FechaRegistro"].isoformat() if t["FechaRegistro"] else None,
                # Fecha en que se SOLICITÓ el vale asociado al ticket. Es la
                # fecha que interesa al usuario: el vale se pide antes de
                # cargar y el ticket se captura después (a veces días después —
                # p.ej. el #60: vale del 29/09, ticket del 06/10), así que
                # FechaRegistro no representa cuándo se surtió el combustible.
                # El JOIN exige que el solicitante sea el mismo usuario que
                # capturó el ticket; si no, queda null y el front usa `fecha`.
                "fecha_vale": t["ValeSolicitud"].isoformat() if t["ValeSolicitud"] else None,
                "estacion": estacion or None,          # null → front muestra "Pendiente"
                "descripcion": t["Descripcion"] or "",
                "tiene_foto": bool(t["TieneFoto"]),
                "cliente": t["Cliente"],
                "vale": f"VL-{int(t['ValeId']):05d}" if t.get("ValeId") else None,
                "marca_modelo": t["MarcaModelo"],
                "placas": t["Placas"],
                "capturo": t["Capturo"],
                "factura": (v["XmlFolio"] or None) if v else None,   # null → "Pendiente"
                "monto": float(v["Monto"]) if v and v["Monto"] is not None else None,
                "litros": float(v["XmlLitros"]) if v and v["XmlLitros"] is not None else None,
                "concepto": v["XmlConcepto"] if v else None,
            })
        return resultado
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# Face Value típico de un vale Go Vale de gasolina (monto fijo). Solo se usa para
# el estimado de "vales restantes" = saldo // MONTO_POR_VALE; el saldo real es el
# de la tarjeta. Si Go Vale cambia el monto, se ajusta aquí (y el front lo toma
# del campo `monto_por_vale` del endpoint, no lo tiene cableado).
MONTO_POR_VALE = 500.0


@app.get("/api/tickets-oxxogas/saldo")
def tickets_oxxogas_saldo(current_user: dict = Depends(get_current_user)):
    """Saldo de la cuenta Go Vale (HUB_Config 'govale_saldo'/'govale_saldo_fecha').

    El valor lo actualiza el worker del HUB (cron_sync_govale_vouchers.py) cada
    ~5 min con login en govale-digital.oxxogas.com; aquí solo se lee para
    mostrarlo en la tarjeta del módulo (mismo estilo/umbral $2,000 que el HUB).
    Se registra ANTES de la ruta con {ticket_id:int} para que el orden de rutas
    de FastAPI resuelva 'saldo' como literal.

    `vales_restantes` es un aproximado: divide el saldo entre el monto típico de
    un vale (MONTO_POR_VALE). Go Vale emite vales de monto fijo (500 por
    omisión), así que el estimado sirve para planear recargas, no para
    contabilidad exacta. Va en el API (no en el front) para que el cálculo
    quede en un solo lugar si más adelante el monto deja de ser fijo."""
    _require_vales_oxxogas(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(
            "SELECT Clave, Valor FROM HUB_Config "
            "WHERE Clave IN ('govale_saldo', 'govale_saldo_fecha')"
        )
        cfg = {r["Clave"]: r["Valor"] for r in cursor.fetchall()}
        saldo_raw = (cfg.get("govale_saldo") or "").strip()
        try:
            saldo = float(saldo_raw)
        except (TypeError, ValueError):
            saldo = None
        vales = (saldo // MONTO_POR_VALE) if saldo is not None else None
        return {
            "saldo": saldo,
            "fecha": (cfg.get("govale_saldo_fecha") or "").strip() or None,
            "umbral": 2000.0,
            "monto_por_vale": MONTO_POR_VALE,
            # null si no hay saldo conocido; 0 si el saldo ya no alcanza para uno.
            "vales_restantes": int(vales) if vales is not None else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.get("/api/tickets-oxxogas/{ticket_id:int}/imagen")
async def tickets_oxxogas_imagen(ticket_id: int, w: int = 0,
                                 current_user: dict = Depends(_user_from_header_or_query)):
    """JPEG del ticket. Acepta ?token= en query para poder usarse en <img>
    (auth vía _user_from_header_or_query, igual que los PDFs). w>0 = thumbnail.
    Algunos tickets sincronizados desde Field traen 15 bytes de basura antes del
    JPEG (bug de data-URL en field/api sync) → se recorta desde el SOI (FF D8 FF)."""
    _require_vales_oxxogas(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ImagenTicket FROM HUB_OxxoGasTickets WHERE Id = %s", (int(ticket_id),))
        row = cursor.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="El ticket no tiene imagen")
        data = bytes(row[0])
        idx = data.find(b"\xff\xd8\xff")
        if idx < 0:
            raise HTTPException(status_code=415, detail="Imagen inválida")
        if idx > 0:
            data = data[idx:]
        if w and w > 0:
            try:
                import io as _io
                from PIL import Image
                img = Image.open(_io.BytesIO(data))
                img.thumbnail((int(w), int(w)))
                buf = _io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
                data = buf.getvalue()
            except Exception:
                pass  # si falla el resize servimos el original
        return Response(
            content=data, media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    finally:
        conn.close()



# ═══════════════════════════════════════════════════════════════════════════
# Módulo Kilómetros — consumo semanal de la flota + captura de odómetro
# ═══════════════════════════════════════════════════════════════════════════
# Tabla de datos: HUB_RegistroKilometros (Id, IdAutomovil, Kilometros,
# FechaHora, IdUsuario) — la misma que escribe el HUB, así que lo capturado en
# cualquiera de las dos apps se ve en las otras. Reglas heredadas del HUB:
#   · 1 registro por automóvil por día (dedup por CAST(FechaHora AS DATE))
#   · el odómetro no puede bajar del último valor registrado
# Los "vales" se cuentan con HUB_OxxoGasTickets (tickets de gasolina capturados
# en Field: traen IdVehiculo SIEMPRE, a diferencia de HUB_OxxoGasVales que llega
# de GoVale sin IdVehiculo y no se puede atribuir a un automóvil).
MONTO_VALE = 500.0  # monto fijo de cada vale (mismo criterio que el HUB)


def _require_registro_kilometros(current_user: dict):
    """Gate del módulo: permiso 'Registro Kilómetros' (AccesoRegistroKilometros)."""
    if not current_user.get("acceso_registro_kilometros"):
        raise HTTPException(status_code=403, detail="No access")


def _ahora_mexico():
    """Fecha/hora de México. Sin horario de verano desde 2022, así que UTC-6 fijo."""
    from datetime import timedelta
    return datetime.utcnow() - timedelta(hours=6)


def _rango_semana(anio=None, semana=None):
    """(inicio, fin_exclusivo) de una semana ISO: lunes 00:00 -> lunes 00:00.

    Sin argumentos devuelve la semana en curso. Los límites se calculan en hora
    de México para que coincidan con los registros que captura el HUB.
    """
    from datetime import date, timedelta
    hoy = _ahora_mexico().date()
    try:
        if anio and semana:
            lunes = date.fromisocalendar(int(anio), int(semana), 1)
        else:
            lunes = hoy - timedelta(days=hoy.weekday())
    except (ValueError, TypeError):
        lunes = hoy - timedelta(days=hoy.weekday())
    return (
        datetime(lunes.year, lunes.month, lunes.day),
        datetime(lunes.year, lunes.month, lunes.day) + timedelta(days=7),
        lunes,
    )


class KilometroRegistroReq(BaseModel):
    id_automovil: int
    kilometros: int
    fecha_hora: str = ""  # ISO; vacío = ahora (hora de México)


@app.get("/api/kilometros/vehiculos")
async def kilometros_vehiculos(current_user: dict = Depends(get_current_user)):
    """Flota completa con el último odómetro leído, para el selector de captura."""
    _require_registro_kilometros(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT a.Id, a.MarcaModelo, a.Placas, a.PolizaSeguro, a.UltimoServicioKms,
                   u.Nombre AS Conductor,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                           WHERE k.IdAutomovil = a.Id ORDER BY k.FechaHora DESC, k.Id DESC), 0)
                       AS KilometrosActuales,
                   (SELECT MAX(k.FechaHora) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS UltimaLectura,
                   (SELECT COUNT(*) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS TotalRegistros
            FROM HUB_Automoviles a
            LEFT JOIN HUB_Users u ON a.IdUsuarioAsignado = u.Id
            ORDER BY a.MarcaModelo ASC
        """)
        out = []
        for r in cursor.fetchall():
            km_act = int(r["KilometrosActuales"] or 0)
            ult_serv = r["UltimoServicioKms"]
            desde = (km_act - int(ult_serv)) if ult_serv is not None else None
            out.append({
                "id": r["Id"],
                "marca_modelo": r["MarcaModelo"],
                "placas": r["Placas"],
                "poliza": r["PolizaSeguro"] or "",
                "conductor": r["Conductor"] or "",
                "km_actuales": km_act,
                "ultima_lectura": r["UltimaLectura"].isoformat() if r["UltimaLectura"] else None,
                "total_registros": int(r["TotalRegistros"] or 0),
                "kms_desde_servicio": desde,
                # Mismo umbral que el HUB (views/administrador_usuarios / get_automoviles)
                "requiere_servicio": bool(desde is not None and desde >= 9500),
            })
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.get("/api/kilometros/consumo")
async def kilometros_consumo(anio: str = "", semana: str = "",
                             current_user: dict = Depends(get_current_user)):
    """Consumo de la flota por vehículo.

    Consumo semanal = ÚLTIMO registro de la semana actual − ÚLTIMO registro de la
    semana anterior (esa lectura es el odómetro base). Es la forma que funciona
    aunque el vehículo lea el odómetro una sola vez por semana; si solo hay
    lecturas dentro de la misma semana no habría diferencia posible.

    También se devuelven las ventanas de la semana anterior y de hace dos
    semanas, para que la UI pueda comparar (variación) sin otra consulta.
    Los vales se cuentan con HUB_OxxoGasTickets (traen IdVehiculo siempre) y
    todos valen $500 (MONTO_VALE, mismo criterio que el HUB).

    anio/semana se reciben como texto: si no son numéricos se cae a la semana en
    curso en vez de responder 422."""
    _require_registro_kilometros(current_user)
    try:
        anio_i, semana_i = int(anio or 0), int(semana or 0)
    except (TypeError, ValueError):
        anio_i, semana_i = 0, 0
    ini, fin, lunes = _rango_semana(anio_i or None, semana_i or None)

    from datetime import timedelta
    ini_1, fin_1 = ini - timedelta(days=7), fin - timedelta(days=7)   # semana pasada
    ini_2, fin_2 = ini - timedelta(days=14), fin - timedelta(days=14)  # hace dos semanas

    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT a.Id, a.MarcaModelo, a.Placas, u.Nombre AS Conductor,
                   (SELECT COUNT(*) FROM HUB_RegistroKilometros k
                     WHERE k.IdAutomovil = a.Id AND k.FechaHora >= %(ini)s AND k.FechaHora < %(fin)s)
                       AS Registros,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                            WHERE k.IdAutomovil = a.Id AND k.FechaHora >= %(ini)s AND k.FechaHora < %(fin)s
                            ORDER BY k.FechaHora DESC, k.Id DESC), 0) AS UltimoKm,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                            WHERE k.IdAutomovil = a.Id AND k.FechaHora >= %(ini_1)s AND k.FechaHora < %(fin_1)s
                            ORDER BY k.FechaHora DESC, k.Id DESC), 0) AS UltimoKmP1,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                            WHERE k.IdAutomovil = a.Id AND k.FechaHora >= %(ini_2)s AND k.FechaHora < %(fin_2)s
                            ORDER BY k.FechaHora DESC, k.Id DESC), 0) AS UltimoKmP2,
                   (SELECT COUNT(*) FROM HUB_OxxoGasTickets t
                     WHERE t.IdVehiculo = a.Id AND t.FechaRegistro >= %(ini)s AND t.FechaRegistro < %(fin)s)
                       AS Vales,
                   (SELECT COUNT(*) FROM HUB_OxxoGasTickets t
                     WHERE t.IdVehiculo = a.Id AND t.FechaRegistro >= %(ini_1)s AND t.FechaRegistro < %(fin_1)s)
                       AS ValesP1,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                            WHERE k.IdAutomovil = a.Id ORDER BY k.FechaHora DESC, k.Id DESC), 0) AS KmActuales,
                   (SELECT MAX(k.FechaHora) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS UltimaLectura,
                   (SELECT COUNT(*) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS TotalRegistros,
                   a.UltimoServicioKms
            FROM HUB_Automoviles a
            LEFT JOIN HUB_Users u ON a.IdUsuarioAsignado = u.Id
        """, {"ini": ini, "fin": fin, "ini_1": ini_1, "fin_1": fin_1,
              "ini_2": ini_2, "fin_2": fin_2})
        filas = cursor.fetchall()

        vehiculos = []
        for r in filas:
            reg = int(r["Registros"] or 0)
            ult = int(r["UltimoKm"] or 0)
            ult_p1 = int(r["UltimoKmP1"] or 0)
            ult_p2 = int(r["UltimoKmP2"] or 0)
            vales = int(r["Vales"] or 0)
            vales_p1 = int(r["ValesP1"] or 0)
            km_act = int(r["KmActuales"] or 0)
            ult_serv = r["UltimoServicioKms"]
            desde = (km_act - int(ult_serv)) if ult_serv is not None else None
            # Consumo = lectura de esta semana - lectura de la semana pasada.
            # Si falta cualquiera de las dos no hay comparación posible (0 + flag).
            consumo = (ult - ult_p1) if (reg > 0 and ult_p1 > 0) else 0
            consumo_p1 = (ult_p1 - ult_p2) if (ult_p1 > 0 and ult_p2 > 0) else 0
            vehiculos.append({
                "id": r["Id"],
                "marca_modelo": r["MarcaModelo"],
                "placas": r["Placas"],
                "conductor": r["Conductor"] or "",
                "registros": reg,
                # Flag para la UI: se puede calcular el consumo de la semana.
                "comparable": bool(reg > 0 and ult_p1 > 0),
                "ultimo_km": ult if reg > 0 else None,
                "ultimo_km_pasada": ult_p1 or None,
                "consumo_km": max(consumo, 0),
                "consumo_ant": max(consumo_p1, 0),
                "vales": vales,
                "vales_ant": vales_p1,
                "monto_vales": round(vales * MONTO_VALE, 2),
                "km_actuales": km_act,
                "ultima_lectura": r["UltimaLectura"].isoformat() if r["UltimaLectura"] else None,
                "total_registros": int(r["TotalRegistros"] or 0),
                "tiene_registros": int(r["TotalRegistros"] or 0) > 0,
                "kms_desde_servicio": desde,
                "requiere_servicio": bool(desde is not None and desde >= 9500),
            })
        # Con datos primero; dentro, mayor consumo.
        vehiculos.sort(key=lambda v: (not v["tiene_registros"], -v["consumo_km"], v["marca_modelo"] or ""))

        iso = lunes.isocalendar()
        domingo = fin - timedelta(days=1)
        return {
            "semana": {
                "anio": iso[0], "num": iso[1],
                "inicio": ini.isoformat(), "fin": fin.isoformat(),
                "etiqueta": f"{lunes.strftime('%d/%m/%Y')} - {domingo.strftime('%d/%m/%Y')}",
            },
            "monto_vale": MONTO_VALE,
            "resumen": {
                "vehiculos": sum(1 for v in vehiculos if v["tiene_registros"]),
                "vehiculos_total": len(vehiculos),
                "con_lectura": sum(1 for v in vehiculos if v["registros"] > 0),
                "consumo_km": sum(v["consumo_km"] for v in vehiculos),
                "consumo_ant": sum(v["consumo_ant"] for v in vehiculos),
                "vales": sum(v["vales"] for v in vehiculos),
                "monto_vales": round(sum(v["vales"] for v in vehiculos) * MONTO_VALE, 2),
                "requieren_servicio": sum(1 for v in vehiculos if v["requiere_servicio"]),
            },
            "vehiculos": vehiculos,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.get("/api/kilometros/vehiculo/{id_automovil:int}")
async def kilometros_vehiculo(id_automovil: int, n: int = 30,
                              current_user: dict = Depends(get_current_user)):
    """Detalle de un vehículo: sus lecturas de odómetro y sus tickets de(vales)."""
    _require_registro_kilometros(current_user)
    try:
        n = max(1, min(int(n or 30), 200))
    except (TypeError, ValueError):
        n = 30
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT a.Id, a.MarcaModelo, a.Placas, a.PolizaSeguro, a.UltimoServicioKms,
                   u.Nombre AS Conductor,
                   ISNULL((SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k
                           WHERE k.IdAutomovil = a.Id ORDER BY k.FechaHora DESC, k.Id DESC), 0)
                       AS KilometrosActuales,
                   (SELECT MAX(k.FechaHora) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS UltimaLectura,
                   (SELECT COUNT(*) FROM HUB_RegistroKilometros k
                    WHERE k.IdAutomovil = a.Id) AS TotalRegistros
            FROM HUB_Automoviles a
            LEFT JOIN HUB_Users u ON a.IdUsuarioAsignado = u.Id
            WHERE a.Id = %s
        """, (int(id_automovil),))
        auto = cursor.fetchone()
        if not auto:
            raise HTTPException(status_code=404, detail="El automóvil no existe.")

        cursor.execute("""
            SELECT TOP (%(n)s) k.Id, k.Kilometros, k.FechaHora, u.Nombre AS Usuario
            FROM HUB_RegistroKilometros k
            LEFT JOIN HUB_Users u ON u.Id = k.IdUsuario
            WHERE k.IdAutomovil = %(id)s
            ORDER BY k.FechaHora DESC, k.Id DESC
        """, {"n": n, "id": int(id_automovil)})
        lecturas = [{
            "id": r["Id"],
            "kilometros": r["Kilometros"],
            "fecha_hora": r["FechaHora"].isoformat() if r["FechaHora"] else None,
            "usuario": r["Usuario"] or "",
        } for r in cursor.fetchall()]

        cursor.execute("""
            SELECT TOP (%(n)s) t.Id, t.FolioTicket, t.FechaRegistro, t.Estacion, t.Descripcion,
                   t.IdCliente, c.Cliente
            FROM HUB_OxxoGasTickets t
            LEFT JOIN clientes c ON c.IdCliente = t.IdCliente
            WHERE t.IdVehiculo = %(id)s
            ORDER BY t.FechaRegistro DESC, t.Id DESC
        """, {"n": n, "id": int(id_automovil)})
        tickets = [{
            "id": r["Id"],
            "folio": (r["FolioTicket"] or "").strip() or None,
            "fecha": r["FechaRegistro"].isoformat() if r["FechaRegistro"] else None,
            "estacion": (r["Estacion"] or "").strip() or None,
            "descripcion": r["Descripcion"] or "",
            "cliente": r["Cliente"] or r["IdCliente"] or "",
        } for r in cursor.fetchall()]

        km_act = int(auto["KilometrosActuales"] or 0)
        ult_serv = auto["UltimoServicioKms"]
        desde = (km_act - int(ult_serv)) if ult_serv is not None else None
        return {
            "vehiculo": {
                "id": auto["Id"],
                "marca_modelo": auto["MarcaModelo"],
                "placas": auto["Placas"],
                "poliza": auto["PolizaSeguro"] or "",
                "conductor": auto["Conductor"] or "",
                "km_actuales": km_act,
                "ultima_lectura": auto["UltimaLectura"].isoformat() if auto["UltimaLectura"] else None,
                "total_registros": int(auto["TotalRegistros"] or 0),
                "total_tickets": len(tickets),
                "kms_desde_servicio": desde,
                "requiere_servicio": bool(desde is not None and desde >= 9500),
            },
            "lecturas": lecturas,
            "tickets": tickets,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.get("/api/kilometros/recientes")
async def kilometros_recientes(n: int = 15, current_user: dict = Depends(get_current_user)):
    """Últimas capturas de odómetro (de Field o del HUB: es la misma tabla)."""
    _require_registro_kilometros(current_user)
    try:
        n = max(1, min(int(n or 15), 100))
    except (TypeError, ValueError):
        n = 15
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT TOP (%(n)s) k.Id, k.IdAutomovil, k.Kilometros, k.FechaHora, k.IdUsuario,
                   a.MarcaModelo, a.Placas, u.Nombre AS Usuario
            FROM HUB_RegistroKilometros k
            JOIN HUB_Automoviles a ON a.Id = k.IdAutomovil
            LEFT JOIN HUB_Users u ON u.Id = k.IdUsuario
            ORDER BY k.FechaHora DESC, k.Id DESC
        """, {"n": n})
        return [{
            "id": r["Id"],
            "id_automovil": r["IdAutomovil"],
            "kilometros": r["Kilometros"],
            "fecha_hora": r["FechaHora"].isoformat() if r["FechaHora"] else None,
            "marca_modelo": r["MarcaModelo"],
            "placas": r["Placas"],
            "usuario": r["Usuario"] or "",
        } for r in cursor.fetchall()]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.post("/api/kilometros/registro")
async def kilometros_registro(body: KilometroRegistroReq,
                              current_user: dict = Depends(get_current_user)):
    """Captura de odómetro. Mismas reglas que el HUB (views/kilometros.py):
    un registro por automóvil por día y el odómetro nunca puede bajar."""
    _require_registro_kilometros(current_user)
    id_auto = int(body.id_automovil)
    km = int(body.kilometros)
    if km < 0:
        raise HTTPException(status_code=400, detail="Los kilómetros no pueden ser negativos.")
    if not body.fecha_hora:
        fecha = _ahora_mexico()
    else:
        from datetime import timezone as _tz, timedelta as _td
        try:
            fecha = datetime.fromisoformat(str(body.fecha_hora).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha/hora inválida. Formato: YYYY-MM-DDTHH:MM")
        if fecha.tzinfo is not None:
            # Cliente que envía con offset (p. ej. "...Z" = UTC): convertir a
            # hora de México (UTC−6). Antes se hacía .replace(tzinfo=None),
            # que guardaba la hora UTC cruda y dejaba el registro 6 h adelantado.
            fecha = fecha.astimezone(_tz(_td(hours=-6))).replace(tzinfo=None)
        # Si viene sin offset (formato normal de la UI) ya ES hora de México:
        # la UI la genera con Intl en America/Mexico_City, se guarda tal cual.
    # El día del registro se calcula en hora de México (no con la fecha del
    # servidor, que corre en UTC): un registro de "hoy" hecho a las 23:30 en CDMX
    # no debe contar como registro de mañana.
    from datetime import timedelta
    hoy_local = _ahora_mexico().date()
    # Rechazar fechas futuras: un cliente con reloj mal (o en UTC) mandaría
    # "ahora" adelantado, el registro se guardaría mal Y bloquearía el registro
    # real del día por la regla de 1 por día. Tolerancia de 10 min.
    if fecha > _ahora_mexico() + timedelta(minutes=10):
        raise HTTPException(
            status_code=400,
            detail="La fecha y hora del registro no puede ser futura.")

    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id, MarcaModelo, Placas FROM HUB_Automoviles WHERE Id = %s", (id_auto,))
        auto = cursor.fetchone()
        if not auto:
            raise HTTPException(status_code=404, detail="El automóvil no existe.")

        cursor.execute(
            "SELECT TOP 1 k.Kilometros FROM HUB_RegistroKilometros k "
            "WHERE k.IdAutomovil = %s ORDER BY k.FechaHora DESC, k.Id DESC", (id_auto,))
        row = cursor.fetchone()
        km_previo = int(row["Kilometros"]) if row and row["Kilometros"] is not None else None
        if km_previo is not None and km < km_previo:
            raise HTTPException(
                status_code=400,
                detail=(f"Los kilómetros reportados ({km:,}) no pueden ser menores al "
                        f"último registro ({km_previo:,} km)."))

        # 1 registro por auto por día (misma regla del HUB: cualquier app que
        # capture, el duplicado se detecta aquí).
        cursor.execute(
            "SELECT COUNT(*) AS n FROM HUB_RegistroKilometros "
            "WHERE IdAutomovil = %s AND CAST(FechaHora AS DATE) = %s",
            (id_auto, hoy_local))
        if int(cursor.fetchone()["n"] or 0) > 0:
            raise HTTPException(
                status_code=409,
                detail=("Este automóvil ya tiene un registro de kilometraje de hoy. "
                        "Solo se permite un registro por día."))

        cursor.execute(
            "INSERT INTO HUB_RegistroKilometros (IdAutomovil, Kilometros, FechaHora, IdUsuario) "
            "VALUES (%s, %s, %s, %s)",
            (id_auto, km, fecha, int(current_user["id"])))
        conn.commit()
        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        nuevo = cursor.fetchone()["id"]
        return {
            "ok": True, "id": int(nuevo) if nuevo is not None else None,
            "id_automovil": id_auto, "kilometros": km,
            "fecha_hora": fecha.isoformat(),
            "vehiculo": f"{auto['MarcaModelo']} ({auto['Placas']})",
            "km_previo": km_previo,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


# --- Notas del equipo (módulo Notas de Admon → pantalla 📌 del Dashboard) ---
# Tabla HUB_DashboardNotas: la MISMA que lee el kiosco de la TV
# (dashboard.ecc-sa.com.mx:8101, api/datos.py → notas()). El kiosco es solo
# lectura; el CRUD vive acá. Por eso las notas que se capturan en Admon
# aparecen solas en la pantalla de la oficina.
#   Color  = acento en la nota (hex #RRGGBB; el kiosco usa #F59E0B si viene vacío)
#   Fija   = las fijas salen primero en el kiosco
#   Autor  = nombre del usuario al momento de crearla (varchar, no FK)
# Sin permiso propio: todos los logueados ven y editan el tablero.

COLOR_NOTA_DEFECTO = "#F59E0B"


class NotaCrear(BaseModel):
    titulo: str
    contenido: str
    color: str = COLOR_NOTA_DEFECTO
    fija: bool = False


class NotaActualizar(BaseModel):
    titulo: str
    contenido: str
    color: str = COLOR_NOTA_DEFECTO
    fija: bool = False


def _color_nota(valor) -> str:
    """Solo #RRGGBB o #RGB; cualquier otra cosa cae al ámbar del kiosco."""
    s = str(valor or "").strip()
    if s.startswith("#"):
        hexa = s[1:]
        if all(c in "0123456789abcdefABCDEF" for c in hexa) and len(hexa) in (3, 6):
            return s
    return COLOR_NOTA_DEFECTO


def _nota_desde_row(r: dict) -> dict:
    """Normaliza una fila de HUB_DashboardNotas al JSON que consume el front."""
    return {
        "id": int(r["Id"]),
        "titulo": r["Titulo"],
        "contenido": r["Contenido"] or "",
        "color": r["Color"] or COLOR_NOTA_DEFECTO,
        "autor": r["Autor"] or "—",
        "fija": bool(r["Fija"]),
        "fecha_creacion": r["FechaCreacion"].isoformat() if r["FechaCreacion"] else None,
        "fecha_modificado": r["FechaModificado"].isoformat() if r["FechaModificado"] else None,
    }


@app.get("/api/notas")
async def notas_listar(current_user: dict = Depends(get_current_user)):
    """Notas del tablero, en el mismo orden que las ve el kiosco (fijas primero)."""
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas
            ORDER BY ISNULL(Fija, 0) DESC,
                     ISNULL(FechaModificado, FechaCreacion) DESC,
                     Id DESC
        """)
        return [_nota_desde_row(r) for r in cursor.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.post("/api/notas")
async def notas_crear(body: NotaCrear, current_user: dict = Depends(get_current_user)):
    """Crea una nota; el autor es el usuario logueado."""
    titulo = (body.titulo or "").strip()
    contenido = (body.contenido or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío.")
    if not contenido:
        raise HTTPException(status_code=400, detail="El contenido no puede estar vacío.")
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            INSERT INTO HUB_DashboardNotas
                (Titulo, Contenido, Color, Autor, Fija, FechaCreacion, FechaModificado)
            VALUES (%s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (titulo[:200], contenido, _color_nota(body.color),
              str(current_user.get("nombre") or "")[:100], 1 if body.fija else 0))
        conn.commit()
        cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        nuevo_id = int(cursor.fetchone()["id"])
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas WHERE Id = %s
        """, (nuevo_id,))
        return _nota_desde_row(cursor.fetchone())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.put("/api/notas/{id_nota:int}")
async def notas_editar(id_nota: int, body: NotaActualizar,
                       current_user: dict = Depends(get_current_user)):
    """Edita la nota; actualiza FechaModificado (sube en el orden del kiosco)."""
    titulo = (body.titulo or "").strip()
    contenido = (body.contenido or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío.")
    if not contenido:
        raise HTTPException(status_code=400, detail="El contenido no puede estar vacío.")
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id FROM HUB_DashboardNotas WHERE Id = %s", (id_nota,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La nota no existe.")
        cursor.execute("""
            UPDATE HUB_DashboardNotas
            SET Titulo = %s, Contenido = %s, Color = %s, Fija = %s,
                FechaModificado = GETDATE()
            WHERE Id = %s
        """, (titulo[:200], contenido, _color_nota(body.color),
              1 if body.fija else 0, id_nota))
        conn.commit()
        cursor.execute("""
            SELECT Id, Titulo, Contenido, Color, Autor, Fija,
                   FechaCreacion, FechaModificado
            FROM HUB_DashboardNotas WHERE Id = %s
        """, (id_nota,))
        return _nota_desde_row(cursor.fetchone())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@app.delete("/api/notas/{id_nota:int}")
async def notas_borrar(id_nota: int, current_user: dict = Depends(get_current_user)):
    """Borra una nota (desaparece de la pantalla del kiosco)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM HUB_DashboardNotas WHERE Id = %s", (id_nota,))
        if cursor.rowcount == 0:
            conn.commit()
            raise HTTPException(status_code=404, detail="La nota no existe.")
        conn.commit()
        return {"ok": True, "id": id_nota}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()

# --- Pestaña "Pantalla de la TV" (módulo Notas del Dashboard) ---
# Imagen de portada + control remoto del kiosco. La lógica de la imagen vive
# en api/notas_pantalla.py (tabla HUB_PantallaImagenes) y el control remoto
# habla con el panel del snapshotter: GET /api/panel/estado sin token,
# POST /api/panel/comando CON token (HUB_PANEL_TOKEN).
# Sin permiso propio, igual que Notas: para todos los logueados.
import json as _json
import urllib.request as _urlreq
import urllib.error as _urlerr
from api import notas_pantalla as _pantalla


def _serializable(fila):
    """pymssql → JSON: datetime a ISO y las claves en snake_case (Id → id)."""
    if fila is None:
        return None
    out = {}
    for k, v in fila.items():
        v = v.isoformat() if hasattr(v, "isoformat") else v
        out[k.lower()] = v
    return out


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


@app.get("/api/pantalla/estado")
async def pantalla_estado(current_user: dict = Depends(get_current_user)):
    """Estado del kiosco: si la TV está conectada, qué pantallas hay y qué
    commanders le mandaron por última vez (con su confirmación)."""
    return _panel_estado()


class PanelComandoRequest(BaseModel):
    accion: str
    pantalla: str = ""


@app.post("/api/pantalla/comando")
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


@app.get("/api/pantalla/portada")
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


@app.post("/api/pantalla/portada")
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


@app.post("/api/pantalla/portada/{id_imagen:int}/restaurar")
async def pantalla_restaurar_portada(id_imagen: int, current_user: dict = Depends(get_current_user)):
    """Vuelve a poner en pantalla una portada anterior sin resubirla."""
    r = _pantalla.restaurar_imagen_pantalla(get_connection, id_imagen)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo restaurar.")
    return r


@app.delete("/api/pantalla/portada/{id_imagen:int}")
async def pantalla_borrar_portada(id_imagen: int, current_user: dict = Depends(get_current_user)):
    """Borra una portada del historial (la que está en pantalla no se puede)."""
    r = _pantalla.borrar_imagen_pantalla(get_connection, id_imagen)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo borrar.")
    return r


# --- Servir frontend compilado (dist/) si existe; si no, la API sigue sola ---
# El build de Vite genera dist/ y Docker lo copia a la imagen. Este bloque
# (definido AL FINAL para no tapar las rutas de la API) sirve:
#   "/"            -> index.html de la SPA (o JSON si no hay dist/)
#   "/assets/..."  -> archivos estáticos del build
#   "/admon_logo.png", favicon, etc. -> archivos de dist/
#   "/login", "/dashboard", ... -> index.html (client-side routing)
try:
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    _dist = Path(__file__).resolve().parent.parent / "dist"
    _has_spa = _dist.is_dir() and (_dist / "index.html").exists()
    if _has_spa and (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # Rutas de la SPA que devuelven index.html. Se compara el PRIMER segmento, así
    # que "usuarios" también cubre /usuarios/{id} y "admin" también /admin/usuarios.
    _SPA_ROUTES = {"login", "dashboard", "cotizaciones", "cotizaciones_materiales", "usuarios", "admin", "config", "clientes", "registro_reportes", "registro_reportes/", "ia", "legends", "tickets_oxxogas", "kilometros", "notas", "panel", "pantalla_tv"}
    # Shell y PWA nunca se cachean (el bundle js/css usa hashes y sí se cachea)
    _NO_STORE = {"Cache-Control": "no-store, must-revalidate"}
    _NO_STORE_FILES = {"index.html", "sw.js", "manifest.webmanifest"}

    def _spa_file(name: str):
        resp = FileResponse(str(_dist / name))
        resp.headers.update(_NO_STORE)
        return resp

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
except Exception:
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)