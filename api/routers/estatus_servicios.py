"""api/routers/estatus_servicios.py — Módulo "Estatus de Servicios"."""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List
import sys, os, json, time, urllib.request, urllib.error, socket, ssl
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tz_mx import now_mx

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


def _filas(sql, params=()):
    from api import main as _m
    return _m._filas(sql, params)

def _una(sql, params=()):
    from api import main as _m
    return _m._una(sql, params)

def _ejecuta(sql, params=()):
    from api import main as _m
    return _m._ejecuta(sql, params)


# --- Verificadores ---

def _check_http(url: str, timeout: int = 10) -> dict:
    """Verifica un endpoint HTTP. Devuelve estatus y tiempo de respuesta."""
    inicio = time.time()
    try:
        req = urllib.request.Request(url, method="GET")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            ms = int((time.time() - inicio) * 1000)
            if resp.status == 200:
                return {"estatus": "verde", "detalle": f"OK ({resp.status})", "ms": ms}
            elif resp.status < 400:
                return {"estatus": "amarillo", "detalle": f"HTTP {resp.status}", "ms": ms}
            else:
                return {"estatus": "rojo", "detalle": f"HTTP {resp.status}", "ms": ms}
    except urllib.error.HTTPError as e:
        ms = int((time.time() - inicio) * 1000)
        if e.code < 500:
            return {"estatus": "amarillo", "detalle": f"HTTP {e.code}", "ms": ms}
        return {"estatus": "rojo", "detalle": f"HTTP {e.code}", "ms": ms}
    except Exception as e:
        ms = int((time.time() - inicio) * 1000)
        return {"estatus": "rojo", "detalle": str(e)[:200], "ms": ms}


def _check_tcp(host: str, port: int, timeout: int = 10) -> dict:
    """Verifica conexión TCP a un host:puerto."""
    inicio = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        ms = int((time.time() - inicio) * 1000)
        return {"estatus": "verde", "detalle": f"TCP OK ({host}:{port})", "ms": ms}
    except Exception as e:
        ms = int((time.time() - inicio) * 1000)
        return {"estatus": "rojo", "detalle": str(e)[:200], "ms": ms}


def _check_statuspage(url: str) -> list:
    """Verifica un Statuspage (GoDaddy, Cloudflare). Devuelve lista de componentes."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        componentes = []
        for comp in data.get("components", []):
            status = comp.get("status", "unknown")
            if status == "operational":
                estatus = "verde"
            elif status in ("degraded_performance", "partial_outage"):
                estatus = "amarillo"
            elif status in ("major_outage", "under_maintenance"):
                estatus = "rojo"
            else:
                estatus = "gris"
            componentes.append({
                "nombre": comp.get("name", ""),
                "estatus": estatus,
                "detalle": status,
            })
        # Overall status
        overall = data.get("status", {}).get("indicator", "none")
        if overall == "none":
            global_estatus = "verde"
        elif overall in ("minor", "major"):
            global_estatus = "amarillo"
        elif overall == "critical":
            global_estatus = "rojo"
        else:
            global_estatus = "gris"
        return global_estatus, componentes
    except Exception as e:
        return "rojo", [{"nombre": "Error", "estatus": "rojo", "detalle": str(e)[:200]}]


def _check_microsoft365_rss() -> tuple:
    """Verifica Microsoft 365 via RSS feed de status.office.com."""
    try:
        url = "https://status.office.com/feed"
        req = urllib.request.Request(url, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Parse RSS items
        import re
        items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)
        if not items:
            # Try Atom format
            items = re.findall(r"<entry>(.*?)</entry>", content, re.DOTALL)

        # Determine overall status from items
        # If there are recent incidents, status is degraded
        estatus = "verde"
        detalle = "Todos los servicios operativos"
        incidencias = []

        for item in items[:10]:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", item, re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""
            # Clean CDATA
            title = title.replace("<![CDATA[", "").replace("]]>", "").strip()

            desc_match = re.search(r"<description[^>]*>(.*?)</description>", item, re.DOTALL)
            desc = desc_match.group(1).strip() if desc_match else ""
            desc = desc.replace("<![CDATA[", "").replace("]]>", "").strip()

            if title:
                # Check if it's an active incident (not resolved)
                if "resolved" not in title.lower() and "resolved" not in desc.lower():
                    estatus = "amarillo"
                    incidencias.append(title)

        if incidencias:
            detalle = f"{len(incidencias)} incidencia(s) activa(s): {incidencias[0][:100]}"
        else:
            detalle = "Todos los servicios operativos"

        return estatus, detalle
    except Exception as e:
        return "rojo", f"Error al consultar RSS: {str(e)[:200]}"


def _verificar_servicio(servicio: dict) -> dict:
    """Verifica un servicio según su tipo y URL."""
    url = servicio.get("UrlCheck", "")
    nombre = servicio.get("Nombre", "")
    categoria = servicio.get("Categoria", "")

    if categoria == "microsoft":
        estatus, detalle = _check_microsoft365_rss()
        return {"estatus": estatus, "detalle": detalle, "ms": 0}
    elif categoria in ("godaddy", "cloudflare"):
        estatus, componentes = _check_statuspage(url)
        # Build detail from components
        problemas = [c for c in componentes if c["estatus"] != "verde"]
        if problemas:
            detalle = ", ".join(f"{c['nombre']}: {c['detalle']}" for c in problemas[:3])
        else:
            detalle = "Todos los componentes operativos"
        return {"estatus": estatus, "detalle": detalle, "ms": 0}
    elif url.startswith("tcp://"):
        # TCP check
        parts = url.replace("tcp://", "").split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 80
        return _check_tcp(host, port)
    elif url.startswith("http"):
        return _check_http(url)
    else:
        return {"estatus": "gris", "detalle": "Sin método de verificación", "ms": 0}


def _guardar_check(servicio_id: int, resultado: dict):
    """Guarda el resultado del check en historial y actualiza el servicio."""
    conn = get_connection()
    cur = conn.cursor()
    ahora = now_mx()
    estatus = resultado["estatus"]
    detalle = resultado["detalle"]
    ms = resultado.get("ms", 0)

    # Insertar en historial
    cur.execute(
        "INSERT INTO HUB_EstatusHistorial (IdServicio, Estatus, Detalle, TiempoRespuestaMs, FechaCheck) "
        "VALUES (%s, %s, %s, %s, %s)",
        (servicio_id, estatus, detalle[:500], ms, ahora),
    )

    # Obtener estatus anterior
    cur.execute("SELECT UltimoEstatus FROM HUB_EstatusServicios WHERE Id = %s", (servicio_id,))
    row = cur.fetchone()
    estatus_anterior = row[0] if row else None

    # Actualizar servicio
    cur.execute(
        "UPDATE HUB_EstatusServicios SET UltimoCheck = %s, UltimoEstatus = %s, "
        "UltimoDetalle = %s, TiempoRespuestaMs = %s, Actualizado = %s WHERE Id = %s",
        (ahora, estatus, detalle[:500], ms, ahora, servicio_id),
    )

    # Detectar cambio de estatus → crear incidencia
    if estatus_anterior and estatus_anterior != estatus:
        if estatus in ("amarillo", "rojo") and estatus_anterior == "verde":
            # Nueva incidencia
            cur.execute(
                "INSERT INTO HUB_EstatusIncidencias (IdServicio, Titulo, Descripcion, Estatus, FechaInicio, Fuente) "
                "VALUES (%s, %s, %s, 'activa', %s, 'api')",
                (servicio_id, f"Cambio a {estatus}", detalle[:500], ahora),
            )
        elif estatus == "verde" and estatus_anterior in ("amarillo", "rojo"):
            # Resolver incidencias activas
            cur.execute(
                "UPDATE HUB_EstatusIncidencias SET Estatus = 'resuelta', FechaResolucion = %s "
                "WHERE IdServicio = %s AND Estatus = 'activa'",
                (ahora, servicio_id),
            )

    conn.commit()
    cur.close()
    conn.close()


def _verificar_todos():
    """Verifica todos los servicios activos."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT * FROM HUB_EstatusServicios WHERE Activo = 1")
    servicios = cur.fetchall()
    cur.close()
    conn.close()

    for svc in servicios:
        resultado = _verificar_servicio(svc)
        _guardar_check(svc["Id"], resultado)


# --- Endpoints ---

@router.get("/api/estatus-servicios")
def listar_servicios(usuario=Depends(get_current_user)):
    """Lista todos los servicios con su estatus actual."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Id, Nombre, Tipo, Categoria, Icono, Activo, UltimoCheck, "
        "UltimoEstatus, UltimoDetalle, TiempoRespuestaMs, Orden, UrlStatus "
        "FROM HUB_EstatusServicios WHERE Activo = 1 ORDER BY Orden, Nombre"
    )
    servicios = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": s["Id"],
            "nombre": s["Nombre"],
            "tipo": s["Tipo"],
            "categoria": s["Categoria"],
            "icono": s["Icono"],
            "activo": bool(s["Activo"]),
            "ultimo_check": s["UltimoCheck"].strftime("%Y-%m-%d %H:%M") if s.get("UltimoCheck") else None,
            "estatus": s["UltimoEstatus"] or "gris",
            "detalle": s["UltimoDetalle"],
            "tiempo_respuesta_ms": s["TiempoRespuestaMs"],
            "url_status": s["UrlStatus"],
        }
        for s in servicios
    ]


@router.get("/api/estatus-servicios/resumen")
def resumen(usuario=Depends(get_current_user)):
    """Resumen global de estatus."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT UltimoEstatus, COUNT(*) AS Total FROM HUB_EstatusServicios "
        "WHERE Activo = 1 GROUP BY UltimoEstatus"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    conteo = {"verde": 0, "amarillo": 0, "rojo": 0, "gris": 0}
    for r in rows:
        est = r["UltimoEstatus"] or "gris"
        conteo[est] = r["Total"]

    if conteo["rojo"] > 0:
        global_est = "rojo"
    elif conteo["amarillo"] > 0:
        global_est = "amarillo"
    elif conteo["gris"] > 0:
        global_est = "gris"
    else:
        global_est = "verde"

    return {
        "global": global_est,
        "total": sum(conteo.values()),
        "verdes": conteo["verde"],
        "amarillos": conteo["amarillo"],
        "rojos": conteo["rojo"],
        "grises": conteo["gris"],
    }


@router.get("/api/estatus-servicios/{servicio_id}")
def detalle_servicio(servicio_id: int, usuario=Depends(get_current_user)):
    """Detalle de un servicio con historial reciente."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Id, Nombre, Tipo, Categoria, Icono, Activo, UltimoCheck, "
        "UltimoEstatus, UltimoDetalle, TiempoRespuestaMs, Orden, UrlStatus, UrlCheck "
        "FROM HUB_EstatusServicios WHERE Id = %s", (servicio_id,)
    )
    svc = cur.fetchone()
    if not svc:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    # Historial últimas 24h
    cur.execute(
        "SELECT Estatus, Detalle, TiempoRespuestaMs, FechaCheck "
        "FROM HUB_EstatusHistorial WHERE IdServicio = %s "
        "AND FechaCheck >= DATEADD(hour, -24, GETDATE()) ORDER BY FechaCheck DESC",
        (servicio_id,),
    )
    historial = cur.fetchall()

    # Incidencias
    cur.execute(
        "SELECT Id, Titulo, Descripcion, Estatus, FechaInicio, FechaResolucion, Fuente "
        "FROM HUB_EstatusIncidencias WHERE IdServicio = %s ORDER BY FechaInicio DESC",
        (servicio_id,),
    )
    incidencias = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "id": svc["Id"],
        "nombre": svc["Nombre"],
        "tipo": svc["Tipo"],
        "categoria": svc["Categoria"],
        "icono": svc["Icono"],
        "activo": bool(svc["Activo"]),
        "ultimo_check": svc["UltimoCheck"].strftime("%Y-%m-%d %H:%M") if svc.get("UltimoCheck") else None,
        "estatus": svc["UltimoEstatus"] or "gris",
        "detalle": svc["UltimoDetalle"],
        "tiempo_respuesta_ms": svc["TiempoRespuestaMs"],
        "url_status": svc["UrlStatus"],
        "historial": [
            {
                "estatus": h["Estatus"],
                "detalle": h["Detalle"],
                "tiempo_respuesta_ms": h["TiempoRespuestaMs"],
                "fecha": h["FechaCheck"].strftime("%Y-%m-%d %H:%M") if h.get("FechaCheck") else "",
            }
            for h in historial
        ],
        "incidencias": [
            {
                "id": i["Id"],
                "titulo": i["Titulo"],
                "descripcion": i["Descripcion"],
                "estatus": i["Estatus"],
                "fecha_inicio": i["FechaInicio"].strftime("%Y-%m-%d %H:%M") if i.get("FechaInicio") else "",
                "fecha_resolucion": i["FechaResolucion"].strftime("%Y-%m-%d %H:%M") if i.get("FechaResolucion") else None,
                "fuente": i["Fuente"],
            }
            for i in incidencias
        ],
    }


@router.get("/api/estatus-servicios/{servicio_id}/historial")
def historial_servicio(servicio_id: int, horas: int = 24, usuario=Depends(get_current_user)):
    """Historial de checks de un servicio."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Estatus, Detalle, TiempoRespuestaMs, FechaCheck "
        "FROM HUB_EstatusHistorial WHERE IdServicio = %s "
        "AND FechaCheck >= DATEADD(hour, -%s, GETDATE()) ORDER BY FechaCheck ASC",
        (servicio_id, horas),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "estatus": r["Estatus"],
            "detalle": r["Detalle"],
            "tiempo_respuesta_ms": r["TiempoRespuestaMs"],
            "fecha": r["FechaCheck"].strftime("%Y-%m-%d %H:%M") if r.get("FechaCheck") else "",
        }
        for r in rows
    ]


@router.post("/api/estatus-servicios/verificar")
def verificar_todos(usuario=Depends(get_current_user)):
    """Fuerza verificación de todos los servicios."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    _verificar_todos()
    return {"ok": True, "mensaje": "Verificación completada"}


@router.post("/api/estatus-servicios/verificar/{servicio_id}")
def verificar_uno(servicio_id: int, usuario=Depends(get_current_user)):
    """Fuerza verificación de un servicio."""
    if not usuario.get("AccesoMailbox") and not usuario.get("AccesoUsuarios"):
        raise HTTPException(status_code=403, detail="Sin acceso")
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute("SELECT * FROM HUB_EstatusServicios WHERE Id = %s", (servicio_id,))
    svc = cur.fetchone()
    cur.close()
    conn.close()
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    resultado = _verificar_servicio(svc)
    _guardar_check(servicio_id, resultado)
    return {"ok": True, "estatus": resultado["estatus"], "detalle": resultado["detalle"]}


# --- API pública para otras apps y widget ---

@router.get("/api/estatus-servicios/api/v1/servicios")
def api_servicios():
    """Lista compacta de servicios (sin auth, para consumo interno)."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Id, Nombre, Tipo, Categoria, Icono, UltimoEstatus, UltimoDetalle, "
        "TiempoRespuestaMs, UltimoCheck, UrlStatus FROM HUB_EstatusServicios WHERE Activo = 1 ORDER BY Orden, Nombre"
    )
    servicios = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": s["Id"],
            "nombre": s["Nombre"],
            "tipo": s["Tipo"],
            "categoria": s["Categoria"],
            "icono": s["Icono"],
            "estatus": s["UltimoEstatus"] or "gris",
            "detalle": s["UltimoDetalle"],
            "tiempo_respuesta_ms": s["TiempoRespuestaMs"],
            "ultimo_check": s["UltimoCheck"].strftime("%Y-%m-%d %H:%M") if s.get("UltimoCheck") else None,
            "url_status": s["UrlStatus"],
        }
        for s in servicios
    ]


@router.get("/api/estatus-servicios/api/v1/servicio/{servicio_id}")
def api_servicio(servicio_id: int):
    """Estatus de un servicio individual (sin auth)."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Id, Nombre, Tipo, Categoria, Icono, UltimoEstatus, UltimoDetalle, "
        "TiempoRespuestaMs, UltimoCheck, UrlStatus FROM HUB_EstatusServicios WHERE Id = %s AND Activo = 1",
        (servicio_id,),
    )
    s = cur.fetchone()
    cur.close()
    conn.close()
    if not s:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return {
        "id": s["Id"],
        "nombre": s["Nombre"],
        "tipo": s["Tipo"],
        "categoria": s["Categoria"],
        "icono": s["Icono"],
        "estatus": s["UltimoEstatus"] or "gris",
        "detalle": s["UltimoDetalle"],
        "tiempo_respuesta_ms": s["TiempoRespuestaMs"],
        "ultimo_check": s["UltimoCheck"].strftime("%Y-%m-%d %H:%M") if s.get("UltimoCheck") else None,
        "url_status": s["UrlStatus"],
    }


@router.get("/api/estatus-servicios/api/v1/resumen")
def api_resumen():
    """Resumen global compacto (sin auth)."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT UltimoEstatus, COUNT(*) AS Total FROM HUB_EstatusServicios "
        "WHERE Activo = 1 GROUP BY UltimoEstatus"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    conteo = {"verde": 0, "amarillo": 0, "rojo": 0, "gris": 0}
    for r in rows:
        est = r["UltimoEstatus"] or "gris"
        conteo[est] = r["Total"]

    if conteo["rojo"] > 0:
        global_est = "rojo"
    elif conteo["amarillo"] > 0:
        global_est = "amarillo"
    elif conteo["gris"] > 0:
        global_est = "gris"
    else:
        global_est = "verde"

    return {
        "global": global_est,
        "total": sum(conteo.values()),
        "verdes": conteo["verde"],
        "amarillos": conteo["amarillo"],
        "rojos": conteo["rojo"],
        "grises": conteo["gris"],
        "actualizado": now_mx().strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/api/estatus-servicios/api/v1/widget")
def api_widget():
    """Payload optimizado para widget de Scriptable (iOS)."""
    conn = get_connection()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        "SELECT Nombre, Icono, UltimoEstatus FROM HUB_EstatusServicios WHERE Activo = 1 ORDER BY Orden, Nombre"
    )
    servicios = cur.fetchall()

    cur.execute(
        "SELECT UltimoEstatus, COUNT(*) AS Total FROM HUB_EstatusServicios "
        "WHERE Activo = 1 GROUP BY UltimoEstatus"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    conteo = {"verde": 0, "amarillo": 0, "rojo": 0, "gris": 0}
    for r in rows:
        est = r["UltimoEstatus"] or "gris"
        conteo[est] = r["Total"]

    if conteo["rojo"] > 0:
        global_est = "rojo"
    elif conteo["amarillo"] > 0:
        global_est = "amarillo"
    elif conteo["gris"] > 0:
        global_est = "gris"
    else:
        global_est = "verde"

    return {
        "global": global_est,
        "total": sum(conteo.values()),
        "verdes": conteo["verde"],
        "amarillos": conteo["amarillo"],
        "rojos": conteo["rojo"],
        "grises": conteo["gris"],
        "actualizado": now_mx().strftime("%Y-%m-%d %H:%M"),
        "servicios": [
            {
                "nombre": s["Nombre"],
                "estatus": s["UltimoEstatus"] or "gris",
                "icono": s["Icono"],
            }
            for s in servicios
        ],
    }