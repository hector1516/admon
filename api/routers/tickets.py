"""api/routers/tickets.py — endpoints de tickets (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request, Query, Form, UploadFile, File
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

router = APIRouter()
_CLIENTES_UNICOS = (
    "(SELECT IdCliente, MIN(Cliente) AS Cliente, MIN(CondicionesPagoDias) AS Dias "
    "FROM clientes GROUP BY IdCliente)"
)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


from fastapi import Request

def _user_from_header_or_query(request: Request):
    from api import main as _m
    return _m._user_from_header_or_query(request)


def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


def _require_vales_oxxogas(current_user: dict):
    """Gate del módulo: mismo permiso que 'Vales OxxoGas' en el HUB."""
    if not current_user.get("acceso_vales_oxxogas"):
        raise HTTPException(status_code=403, detail="No access")

@router.get("/api/tickets-oxxogas")
def tickets_oxxogas_list(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
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
        # Total (sin paginar)
        cursor.execute("SELECT COUNT(*) AS n FROM HUB_OxxoGasTickets T")
        total = int(cursor.fetchone()["n"] or 0)

        # Página de tickets
        cursor.execute(f"""
            SELECT
                T.Id, T.FolioTicket, T.FechaRegistro, T.Estacion,
                T.IdSolicitudVale,
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
            OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """)
        tickets = cursor.fetchall()

        # Los vales se leen del más reciente al más viejo: el primero que
        # contiene el folio es el que se queda, como el TOP 1 por Fecha.
        cursor.execute(
            "SELECT XmlFolio, Fecha, Monto, XmlLitros, XmlConcepto, XmlContent, IdSolicitudVale, IdUsuario "
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

        # Índice por IdSolicitudVale para match directo (Option B)
        por_solicitud = {}
        for v in vales:
            sid = v.get("IdSolicitudVale")
            if sid is not None and sid not in por_solicitud:
                por_solicitud[sid] = v

        # Índice por usuario para matching por fecha
        vales_por_usuario = {}
        for v in vales:
            uid = v.get("IdUsuario")
            if uid not in vales_por_usuario:
                vales_por_usuario[uid] = []
            vales_por_usuario[uid].append(v)

        # Vales GENERADOS desde ayer que aún no tienen ticket capturado.
        conn2 = get_connection()
        cur2 = conn2.cursor(as_dict=True)
        cur2.execute("""
            SELECT S.Id, S.IdSolicitante, S.FechaSolicitud, S.Placa, S.Descripcion,
                   S.Cantidad, S.MontoUnit, S.IdAutomovil, S.IdCliente, S.IdValeGoVale,
                   U.Nombre AS SolicitanteNombre,
                   A.MarcaModelo, A.Placas AS AutoPlacas
            FROM HUB_SolicitudVales S
            LEFT JOIN HUB_Users U ON U.Id = S.IdSolicitante
            LEFT JOIN HUB_Automoviles A ON A.Id = S.IdAutomovil
            WHERE S.Estatus = 'GENERADO'
              AND S.IdTicketCierre IS NULL
              AND S.FechaSolicitud >= DATEADD(day, -1, CAST(GETDATE() AS DATE))
            ORDER BY S.FechaSolicitud DESC
        """)
        solicitudes_pendientes = cur2.fetchall()
        conn2.close()

        resultado = []
        for t in tickets:
            folio = (t["FolioTicket"] or "").strip()
            v = None
            # 1. Match directo por IdSolicitudVale (más preciso)
            sid = t.get("IdSolicitudVale")
            if sid is not None and sid in por_solicitud:
                v = por_solicitud[sid]
            # 2. Atajo por folio exacto
            if v is None:
                v = por_folio.get(folio) if folio else None
            # 3. Búsqueda LIKE en XML
            if v is None and folio:
                for cand in vales:
                    if folio in str(cand["XmlContent"] or ""):
                        v = cand
                        break
            # 4. Matching por usuario + fecha (±3 días) si no se encontró
            if v is None:
                uid = t.get("IdUsuario")
                fecha_ticket = t.get("FechaRegistro")
                if uid and fecha_ticket and uid in vales_por_usuario:
                    mejores = []
                    for cand in vales_por_usuario[uid]:
                        fecha_vale = cand.get("Fecha")
                        if fecha_vale:
                            delta = abs((fecha_ticket - fecha_vale).days) if hasattr(fecha_ticket, 'date') else 999
                            if delta <= 3:
                                mejores.append((delta, cand))
                    if mejores:
                        mejores.sort(key=lambda x: x[0])
                        v = mejores[0][1]
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
                "fecha_vale": (t["ValeSolicitud"].isoformat() if t["ValeSolicitud"] else (v["Fecha"].isoformat() if v and v.get("Fecha") else None)),
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
        # Agregar vales GENERADOS sin ticket como "tickets pendientes"
        for s in solicitudes_pendientes:
            resultado.append({
                "id": f"vale-{s['Id']}",
                "folio": None,
                "fecha": s["FechaSolicitud"].isoformat() if s["FechaSolicitud"] else None,
                "fecha_vale": s["FechaSolicitud"].isoformat() if s["FechaSolicitud"] else None,
                "estacion": None,
                "descripcion": s["Descripcion"] or "",
                "tiene_foto": False,
                "cliente": s["IdCliente"],
                "vale": f"VL-{int(s['Id']):05d}",
                "marca_modelo": s["MarcaModelo"],
                "placas": s["AutoPlacas"] or s["Placa"],
                "capturo": s["SolicitanteNombre"],
                "factura": None,
                "monto": float(s["MontoUnit"]) if s["MontoUnit"] is not None else None,
                "litros": None,
                "concepto": None,
                "pendiente_ticket": True,
                "id_solicitud": s["Id"],
            })
        total = len(resultado)
        return {"items": resultado, "total": total, "limit": limit, "offset": offset}
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


@router.get("/api/tickets-oxxogas/saldo")
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


@router.get("/api/tickets-oxxogas/{ticket_id:int}/imagen")
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

# ═══════════════════════════════════════════════════════════════════════════
# Captura manual de ticket OxxoGas desde Admon
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/tickets-oxxogas/vales-abiertos")
def tickets_oxxogas_vales_abiertos(
    vehiculo: int = Query(...),
    current_user: dict = Depends(get_current_user),
):
    _require_vales_oxxogas(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT S.Id, S.IdSolicitante, S.FechaSolicitud, S.Placa, S.Descripcion,
                   S.Cantidad, S.MontoUnit, S.IdAutomovil, S.IdCliente, S.IdValeGoVale,
                   U.Nombre AS SolicitanteNombre,
                   A.MarcaModelo, A.Placas AS AutoPlacas
            FROM HUB_SolicitudVales S
            LEFT JOIN HUB_Users U ON U.Id = S.IdSolicitante
            LEFT JOIN HUB_Automoviles A ON A.Id = S.IdAutomovil
            WHERE S.Estatus = 'GENERADO'
              AND S.IdTicketCierre IS NULL
              AND S.IdAutomovil = %s
            ORDER BY S.FechaSolicitud DESC
        """, (vehiculo,))
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@router.get("/api/tickets-oxxogas/estaciones")
def tickets_oxxogas_estaciones(current_user: dict = Depends(get_current_user)):
    _require_vales_oxxogas(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Estacion FROM HUB_EstacionesTickets ORDER BY Estacion")
        return [r["Estacion"] for r in cursor.fetchall()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


@router.post("/api/tickets-oxxogas/crear")
async def tickets_oxxogas_crear(
    id_vehiculo: int = Form(...),
    id_cliente: str = Form(""),
    folio_ticket: str = Form(""),
    estacion: str = Form(""),
    descripcion: str = Form(""),
    id_solicitud_vale: str = Form(""),
    foto: UploadFile = Form(None),
    current_user: dict = Depends(get_current_user),
):
    _require_vales_oxxogas(current_user)
    folio_val = (folio_ticket or "").strip()
    estacion_val = (estacion or "").strip()
    desc_val = (descripcion or "").strip()
    cliente_val = (id_cliente or "").strip() or None
    vale_val = int(id_solicitud_vale) if (id_solicitud_vale or "").strip().isdigit() else None

    if not folio_val:
        raise HTTPException(status_code=400, detail="Folio del ticket es obligatorio")
    if not estacion_val:
        raise HTTPException(status_code=400, detail="Estacion es obligatoria")
    if not foto:
        raise HTTPException(status_code=400, detail="Foto del ticket es obligatoria")

    image_bytes = await foto.read()
    image_name = foto.filename or "ticket.jpg"

    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        if vale_val:
            cursor.execute("SELECT IdCliente, Descripcion FROM HUB_SolicitudVales WHERE Id = %s", (vale_val,))
            v = cursor.fetchone()
            if v:
                if not cliente_val:
                    cliente_val = (v["IdCliente"] or "").strip() or None
                if not desc_val:
                    desc_val = (v["Descripcion"] or "").strip()

        cursor.execute("""
            INSERT INTO HUB_OxxoGasTickets
            (FolioTicket, Estacion, ImagenTicket, ImagenNombre, IdVehiculo, Descripcion,
             IdCliente, IdUsuario, FechaRegistro, IdSolicitudVale)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), %s);
            SELECT CAST(SCOPE_IDENTITY() AS INT) AS new_id;
        """, (folio_val, estacion_val, image_bytes, image_name,
              id_vehiculo, desc_val, cliente_val, current_user["id"], vale_val))
        new_id = int(cursor.fetchone()["new_id"])

        if vale_val:
            cursor.execute("UPDATE HUB_SolicitudVales SET IdTicketCierre = %s, FechaCierre = GETDATE(), Estatus = 'CERRADO' WHERE Id = %s", (new_id, vale_val))

        conn.commit()
        return {"success": True, "folio": folio_val, "id_server": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()

@router.post("/api/tickets/ai-extraer-folio")
async def ai_extraer_folio(
    foto: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _require_vales_oxxogas(current_user)
    api_key = None
    model_name = "gemini-2.0-flash"
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT ApiKey, Model FROM HUB_AIConfig WHERE Id = 1")
        row = cursor.fetchone()
        if row:
            api_key = row.get("ApiKey")
            if row.get("Model"):
                model_name = row["Model"]
    except Exception:
        pass
    finally:
        conn.close()
    if not api_key:
        raise HTTPException(status_code=400, detail="No hay clave de IA configurada")

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        image_bytes = await foto.read()
        import PIL.Image
        import io
        img = PIL.Image.open(io.BytesIO(image_bytes))

        prompt = (
            "Eres un lector de tickets de OxxoGas. "
            "Extrae el folio (numero de 10-12 digitos cerca de codigo de barras o etiqueta Folio/Ticket/Secuencia) "
            "y la estacion (texto despues de ESTACION/Estacion/EST./SUCURSAL). "
            "Responde EXACTAMENTE en este formato, sin nada mas:\n"
            "FOLIO=numero_o_vacio ESTACION=texto_o_vacio"
        )
        response = model.generate_content([prompt, img])
        text = (response.text or "").strip()
        import re
        folio_m = re.search(r"FOLIO\s*=\s*(\S+)", text, re.IGNORECASE)
        est_m = re.search(r"ESTACION\s*=\s*(.+)$", text, re.IGNORECASE)
        folio = folio_m.group(1) if folio_m else ""
        estacion = est_m.group(1).strip() if est_m else ""
        if not folio:
            num_m = re.search(r"\b(\d{10,12})\b", text)
            if num_m:
                folio = num_m.group(1)
        if folio and not re.match(r"^\d{6,15}$", folio):
            folio_num = re.search(r"\d{6,15}", folio)
            folio = folio_num.group(0) if folio_num else ""
        return {"folio": folio, "estacion": estacion}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error con IA: {str(e)}")




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
    """Fecha/hora de México. Usa tz_mx para no depender de la configuración del contenedor."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from tz_mx import now_mx
    return now_mx()


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


