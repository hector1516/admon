"""api/routers/legends.py — endpoints de legends (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from api import legends_core as _legends_core
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

_THUMBS_LEN: dict = {}

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



def _avatares_miniatura(*a, **kw):
    from api import main as _m
    return getattr(_m, "_avatares_miniatura")(*a, **kw)

@router.get("/api/legends/overview")
async def legends_overview(current_user: dict = Depends(get_current_user)):
    """Todo lo que pinta la pantalla de Legends en una sola llamada.

    Contrato compartido con Field (`legends_core.overview`): usuario, ranking,
    semana, temporada, ganador anterior, logros, historial y guía de puntos.
    Los avatares se piden recortados a 128 px: el base64 crudo pesa 150-310 KB
    por usuario y antes hacía que el ranking tardara segundos.
    """
    conn = get_connection()
    try:
        with conn.cursor(as_dict=True) as cur:
            data = _legends_core.overview(cur, current_user["id"])
            ids = [data["usuario"]["id_usuario"]] + [r["id_usuario"] for r in data["ranking"]]
            if data.get("ganador_semana"):
                ids.append(data["ganador_semana"]["id_usuario"])
            ids = sorted({int(i) for i in ids if i})
            urls = {}
            if ids:
                marcas = ",".join(str(i) for i in ids)
                cur.execute(
                    f"SELECT IdUsuario, LEN(AvatarBase64) AS AvatarLen, AvatarUrl "
                    f"FROM HUB_UserAvatars WHERE IdUsuario IN ({marcas})"
                )
                for r in cur.fetchall():
                    _THUMBS_LEN[int(r["IdUsuario"])] = int(r["AvatarLen"] or 0)
                    urls[int(r["IdUsuario"])] = r.get("AvatarUrl")

        thumbs = _avatares_miniatura(conn, ids) if ids else {}

        def _avatar(uid):
            return thumbs.get(int(uid)) or urls.get(int(uid))

        data["usuario"]["avatar"] = _avatar(data["usuario"]["id_usuario"])
        for r in data["ranking"]:
            r["avatar"] = _avatar(r["id_usuario"])
        if data.get("ganador_semana"):
            data["ganador_semana"]["avatar"] = _avatar(data["ganador_semana"]["id_usuario"])
        return data
    finally:
        conn.close()


@router.get("/api/legends/score")
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


@router.get("/api/legends/score-log")
async def legends_score_log(current_user: dict = Depends(get_current_user)):
    """Bitácora semanal de puntos del usuario actual.
    Muestra cada evento que sumó o restó puntos esta semana.
    La semana cambia el domingo 00:00; los puntos se reconstruyen desde
    HUB_ScoreLog, no se resetean a mano."""
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
            "cron_info": "La semana cierra el domingo 00:00 (hora México). El ganador se publica a las 03:00. Los puntos se reconstruyen cada 5 minutos; la temporada y los logros no se resetean.",
        }
    finally:
        conn.close()


@router.get("/api/legends/ranking")
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


@router.get("/api/legends/winners")
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


@router.get("/api/legends/avatar")
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


@router.get("/api/legends/weekly-winner")
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


# Removed: /award and /cron/weekly-calculate endpoints
# Write operations are centralized in WorkersAdmon.
# Admon only reads from the DB via the read-only endpoints below.


@router.get("/api/legends/celebrations")
async def legends_celebrations(current_user: dict = Depends(get_current_user)):
    """Cumpleaños y aniversarios del mes actual, combinados."""
    import datetime as _dt
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from tz_mx import now_mx
    mes_actual = now_mx().month

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


@router.get("/api/legends/metrics/config")
async def legends_metrics_config():
    """Catálogo de puntos, niveles, logros y guía (para la UI)."""
    return {
        "nombre_puntos": "ECCSA Points",
        "metricas": _legends_core.METRICAS,
        "niveles": {n["nombre"]: n["min"] for n in _legends_core.NIVELES},
        "iconos": {n["nombre"]: n["icono"] for n in _legends_core.NIVELES},
        "guia": _legends_core.guia(),
        "logros": _legends_core.LOGROS,
        "temporada": {
            k: v for k, v in _legends_core.temporada_actual().items()
            if k not in ("inicio_dt", "fin_dt_exclusivo")
        },
    }


# Removed: /cron/weekly-calculate endpoint
# Weekly calculation is handled by WorkersAdmon's cron_legends.py.
# Admon only reads from the DB.


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


