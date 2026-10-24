"""api/routers/asistencia.py — endpoint de asistencia (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List

def _latido_scan(conn):
    """Último ciclo del escáner de red y minutos desde entonces."""
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 FechaScan FROM HUB_NetworkScanRuns ORDER BY Id DESC")
        row = cur.fetchone()
        cur.close()
        if row and row.get("FechaScan"):
            ciclo = row["FechaScan"]
            minutos = int((__import__("datetime").datetime.now() - ciclo).total_seconds() / 60)
            return ciclo, minutos
    except Exception:
        pass
    return None, None


AJUSTE_ENTRADA_MIN = 4

VENTANA_SIN_ESCANER_MIN = 15

router = APIRouter()

def get_connection():
    from api import main as _m
    return _m.get_connection()

from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)

def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)

@router.get("/api/asistencia")
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

