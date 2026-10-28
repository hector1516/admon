"""api/routers/reportes.py — endpoints de reportes (Fase 4)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from api.pdf_reporte import build_service_report_pdf
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

router = APIRouter()
from api.routers.pdf import ReporteCreate, ReporteUpdate, ReporteFotosSave, ReporteTecnicosSave, ReporteSignatureSave
from api.routers.ia import IaConversacionCreate, IaMensajeCreate
from api.routers.passkeys import legends_registrar_metrica

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


def _require_reporte(current_user: dict):
    if not (current_user.get("acceso_registro_reportes") or current_user.get("acceso_reportes")):
        raise HTTPException(status_code=403, detail="Requiere permiso de Reportes de Servicio")

@router.get("/api/reportes")
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


@router.get("/api/reportes/excel")
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
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from tz_mx import now_mx
    nombre = f"Reportes_{nombre_cliente}_{now_mx().strftime('%Y-%m-%d')}.xlsx"

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/api/reportes/{id_reporte}")
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


@router.post("/api/reportes")
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


@router.put("/api/reportes/{id_reporte}")
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


@router.delete("/api/reportes/{id_reporte}")
async def api_delete_reporte(id_reporte: int, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Soft delete: marcar como eliminado en lugar de borrar
        cursor.execute(
            "SELECT Folio, Tecnico, Estatus, FirmaConformidad "
            "FROM ReportesServicio WHERE IdReporte = %s",
            (int(id_reporte),),
        )
        row = cursor.fetchone()
        folio = row[0] if row else str(id_reporte)
        tecnico = row[1] if row else ""
        era_firmado = bool(row and (row[2] == "Firmado" or row[3]))
        cursor.execute("UPDATE ReportesServicio SET Eliminado = 1, FechaEliminado = GETDATE() WHERE IdReporte = %s", (int(id_reporte),))
        conn.commit()
        conn.close()
        # Legends: -5 si se elimina un reporte ya firmado (retrabajo). Borrar
        # un borrador no castiga; restaurarlo tampoco devuelve los puntos.
        if era_firmado:
            try:
                uid = legends_usuario_por_nombre(tecnico)
                if uid:
                    legends_registrar_metrica(uid, "retrabajo", referencia_id=int(id_reporte))
            except Exception:
                pass
        return {"ok": True, "folio": folio, "message": "Movido a papelera"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/api/reportes/{id_reporte}/restaurar")
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


@router.delete("/api/reportes/{id_reporte}/purge")
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


@router.get("/api/reportes/{id_reporte}/fotos")
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


@router.post("/api/reportes/{id_reporte}/fotos")
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
        cursor.execute("SELECT Tecnico FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        fila_tec = cursor.fetchone()
        tecnico = (fila_tec[0] or "") if fila_tec else ""
        ya_puntuado = legends_tiene_score_global(cursor, "reporte_fotos", int(id_reporte))
        conn.commit()
        conn.close()
        # Legends: +2 por evidencia fotográfica, 1× por reporte aunque se
        # vuelvan a guardar las fotos. El punto es del TÉCNICO del reporte,
        # no de quien sube la foto desde la oficina.
        if body.fotos and not ya_puntuado:
            try:
                uid = legends_usuario_por_nombre(tecnico)
                if uid:
                    legends_registrar_metrica(uid, "reporte_fotos", referencia_id=int(id_reporte))
            except Exception:
                pass
        return {"ok": True, "guardadas": len(body.fotos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/api/reportes/{id_reporte}/fotos/{id_foto}")
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


@router.get("/api/reportes/{id_reporte}/tecnicos")
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


@router.post("/api/reportes/{id_reporte}/tecnicos")
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


@router.post("/api/reportes/{id_reporte}/firma")
async def api_save_firma(id_reporte: int, body: ReporteSignatureSave, current_user: dict = Depends(get_current_user)):
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE ReportesServicio SET FirmaConformidad = %s, Estatus = 'Firmado' WHERE IdReporte = %s", (body.signature_base64, int(id_reporte)))
        conn.commit()
        cursor.execute("SELECT Folio, Tecnico FROM ReportesServicio WHERE IdReporte = %s", (int(id_reporte),))
        row = cursor.fetchone()
        conn.close()
        # Legends: +10 al TÉCNICO del reporte (no a quien captura la firma
        # desde la oficina) + horas de servicio a los participantes.
        try:
            uid_tec = legends_usuario_por_nombre(row[1] if row else "")
            if uid_tec:
                legends_registrar_metrica(uid_tec, "reporte_firmado", referencia_id=int(id_reporte))
        except Exception:
            pass
        try:
            legends_registrar_puntos_servicio(int(id_reporte))
        except Exception:
            pass
        return {"ok": True, "folio": row[0] if row else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/reportes/{id_reporte}/pdf")
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


@router.get("/api/reportes/{id_reporte}/enviar")
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
        smtp_pass = os.getenv("HUB_SMTP_PASSWORD", "")
        if not smtp_pass:
            raise RuntimeError("HUB_SMTP_PASSWORD no definida — no se puede enviar correo")

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


