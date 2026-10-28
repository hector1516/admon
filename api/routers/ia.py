"""api/routers/ia.py — endpoints de ia (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tz_mx import now_mx

class IaConversacionCreate(BaseModel):
    titulo: str = "Nueva conversacion"


class IaMensajeCreate(BaseModel):
    contenido: str

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

@router.get("/api/ia/conversaciones")
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


@router.post("/api/ia/conversaciones")
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
        return {"Id": id_conv, "Titulo": body.titulo, "FechaCreacion": now_mx().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/ia/conversaciones/{id_conversacion}/mensajes")
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


@router.post("/api/ia/conversaciones/{id_conversacion}/mensajes")
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


@router.delete("/api/ia/conversaciones/{id_conversacion}")
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
        raise RuntimeError("No se pudo obtener el secreto de passkeys (BD no disponible y sin env JWT_SECRET)")
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


