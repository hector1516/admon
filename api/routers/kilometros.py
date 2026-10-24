"""api/routers/kilometros.py — endpoints de kilometros (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class KilometroRegistroReq(BaseModel):
    id_automovil: int
    kilometros: int
    fecha_hora: str = ""

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

def _require_registro_kilometros(current_user: dict):
    """Gate del módulo: permiso 'Registro Kilómetros' (AccesoRegistroKilometros)."""
    if not current_user.get("acceso_registro_kilometros"):
        raise HTTPException(status_code=403, detail="No access")

@router.get("/api/kilometros/vehiculos")
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


@router.get("/api/kilometros/consumo")
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


@router.get("/api/kilometros/vehiculo/{id_automovil:int}")
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


@router.get("/api/kilometros/recientes")
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


@router.post("/api/kilometros/registro")
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


