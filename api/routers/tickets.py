"""api/routers/tickets.py — endpoints de tickets (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


def _user_from_header_or_query(request):
    from api import main as _m
    return _m._user_from_header_or_query(request)


def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


@router.get("/api/tickets-oxxogas")
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


