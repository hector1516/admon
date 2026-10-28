"""api/routers/cotizaciones.py — endpoints de cotizaciones, SAT y remisiones (Fase 3)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from api.pdf_cotizacion import build_cotizacion_pdf
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from api.routers.passkeys import legends_subtotal_cotizacion, legends_registrar_metrica

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

TOP_COTIZACIONES = 100


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


class CotizacionCreate(BaseModel):
    id_cliente: str = ""
    contacto: str = ""
    descripcion: str = ""

class CotizacionEnviar(BaseModel):
    to_email: str = ""
    subject: str = ""
    body: str = ""

class CotizacionNota(BaseModel):
    nota: str = ""

class CotizacionUpdate(BaseModel):
    id_cliente: str = ""
    contacto: str = ""
    descripcion: str = ""
    color: int = 0

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

class RemisionAsignar(BaseModel):
    id_usuario: Optional[int] = None

class RemisionCreate(BaseModel):
    partidas: List[Dict[str, Any]] = []  # [{partida, cantidad, descripcion}]



def _clean_articulo(*a, **kw):
    from api import main as _m
    return getattr(_m, "_clean_articulo")(*a, **kw)


def _db_add_partida(*a, **kw):
    from api import main as _m
    return getattr(_m, "_db_add_partida")(*a, **kw)


def _db_clone_quotation(*a, **kw):
    from api import main as _m
    return getattr(_m, "_db_clone_quotation")(*a, **kw)


def _db_create_quotation(*a, **kw):
    from api import main as _m
    return getattr(_m, "_db_create_quotation")(*a, **kw)


def _db_get_color(*a, **kw):
    from api import main as _m
    return getattr(_m, "_db_get_color")(*a, **kw)


def _fmt_folio(*a, **kw):
    from api import main as _m
    return getattr(_m, "_fmt_folio")(*a, **kw)


def _fstr(*a, **kw):
    from api import main as _m
    return getattr(_m, "_fstr")(*a, **kw)


def _listar_cotizaciones(*a, **kw):
    from api import main as _m
    return getattr(_m, "_listar_cotizaciones")(*a, **kw)


def _partida_row_to_dict(*a, **kw):
    from api import main as _m
    return getattr(_m, "_partida_row_to_dict")(*a, **kw)


def _require_cotiz(*a, **kw):
    from api import main as _m
    return getattr(_m, "_require_cotiz")(*a, **kw)


def _user_from_header_or_query(*a, **kw):
    from api import main as _m
    return getattr(_m, "_user_from_header_or_query")(*a, **kw)


def _validate_partida_input(*a, **kw):
    from api import main as _m
    return getattr(_m, "_validate_partida_input")(*a, **kw)

@router.get("/api/cotizaciones/resumen")
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


@router.get("/api/cotizaciones/{folio:int}")
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


@router.post("/api/cotizaciones")
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
        # ¿Es la primera cotización de este cliente? Se consulta antes del
        # commit, con la fila recién insertada ya visible en la transacción.
        cursor.execute(
            "SELECT COUNT(*) FROM IndiceMateriales WHERE IdCliente = %s AND Folio <> %s",
            (idc, int(folio)),
        )
        primera = int((cursor.fetchone() or [1])[0] or 0) == 0
        conn.commit()
        conn.close()
        # Legends: +2 por cotización creada y +5 si es cliente nuevo.
        try:
            legends_registrar_metrica(current_user["id"], "cotizacion_creada", referencia_id=int(folio))
            if primera:
                legends_registrar_metrica(current_user["id"], "cliente_nuevo_cotizado", referencia_id=int(folio))
        except Exception:
            pass
        return {"folio": folio, "folio_fmt": _fmt_folio(folio)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/cotizaciones/{folio:int}")
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
        cursor.execute("SELECT IdCliente, Contacto, Descripcion, Color, Autor FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
        cur_row = cursor.fetchone()
        if not cur_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Cotización no encontrada")
        cur_color = int(cur_row[3] or 0)
        autor = cur_row[4] or ""
        if cur_color in (1, 2):
            # Bloqueada: solo se permite transición de estatus (amarillo->verde), no editar datos
            # Para verde (2): completamente bloqueada, no se permite ningún cambio
            if cur_color == 2:
                conn.close()
                raise HTTPException(status_code=400, detail="Cotización bloqueada (facturada). No se puede modificar.")
            # Para amarillo (1): solo se permite cambiar el color (a verde), no los datos
            nuevo_color_check = int(body.color)
            if nuevo_color_check == cur_color:
                # Mismo color: verificar que no se editaron los datos
                if ((str(cur_row[0] or "").strip().upper() != idc
                        or str(cur_row[1] or "").strip() != body.contacto.strip()
                        or str(cur_row[2] or "").strip() != body.descripcion.strip())):
                    conn.close()
                    raise HTTPException(status_code=400, detail="Cotización bloqueada (lista para facturar). Solo se puede cambiar el estatus.")
        nuevo_color = int(body.color)
        cursor.execute(
            "UPDATE IndiceMateriales SET IdCliente = %s, Contacto = %s, Descripcion = %s, Color = %s WHERE Folio = %s",
            (idc, body.contacto.strip(), body.descripcion.strip(), nuevo_color, int(folio)),
        )
        subtotal = 0.0
        if nuevo_color == 2 and cur_color != 2:
            subtotal = legends_subtotal_cotizacion(cursor, folio)
        conn.commit()
        conn.close()

        # Legends: se premia la TRANSICIÓN, no cada edición. Si se marca
        # PAGADA una cotización que ya lo estaba, no se vuelve a pagar.
        try:
            uid_autor = legends_usuario_por_nombre(autor)
            if nuevo_color >= 1 and cur_color == 0 and uid_autor:
                legends_registrar_metrica(uid_autor, "cotizacion_entregada", referencia_id=int(folio))
            if nuevo_color == 2 and cur_color != 2:
                pts = _legends_core.puntos_cotizacion_pagada(subtotal)
                if uid_autor:
                    legends_registrar_metrica(
                        uid_autor, "cotizacion_pagada",
                        referencia_id=int(folio), puntos_override=pts,
                    )
                # El que cobra también mueve dinero, pero solo si no es el
                # mismo autor (evita duplicar el premio de la venta).
                if current_user["id"] != uid_autor:
                    legends_registrar_metrica(
                        current_user["id"], "cobranza_registrada",
                        referencia_id=int(folio),
                    )
        except Exception:
            pass
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/cotizaciones/{folio:int}/nota")
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


@router.delete("/api/cotizaciones/{folio:int}")
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


@router.post("/api/cotizaciones/{folio:int}/clonar")
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


@router.get("/api/cotizaciones/{folio:int}/pdf")
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


@router.post("/api/cotizaciones/{folio:int}/enviar")
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

@router.get("/api/cotizaciones/{folio:int}/partidas")
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


@router.post("/api/cotizaciones/{folio:int}/partidas")
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
        cursor.execute("SELECT COUNT(*) FROM Partidas WHERE Folio = %s", (int(folio),))
        primera_partida = int((cursor.fetchone() or [1])[0] or 0) == 0
        autor = ""
        if primera_partida:
            cursor.execute("SELECT Autor FROM IndiceMateriales WHERE Folio = %s", (int(folio),))
            fila_autor = cursor.fetchone()
            autor = (fila_autor[0] or "") if fila_autor else ""
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
        # Legends: +2 por la primera partida (cotización completa). Se le
        # acredita al autor de la cotización, no a quien la capturó.
        if primera_partida:
            try:
                uid_autor = legends_usuario_por_nombre(autor)
                if uid_autor:
                    legends_registrar_metrica(
                        uid_autor, "cotizacion_con_partidas",
                        referencia_id=int(folio),
                    )
            except Exception:
                pass
        return {"ok": True, "partida": num, "sat": sat}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/cotizaciones/{folio:int}/partidas/{partida:int}")
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


@router.delete("/api/cotizaciones/{folio:int}/partidas/{partida:int}")
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


@router.post("/api/sat/sugerir")
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


@router.get("/api/remisiones/usuarios")
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


@router.get("/api/cotizaciones/{folio:int}/remisiones")
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


@router.post("/api/cotizaciones/{folio:int}/remisiones")
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


@router.delete("/api/remisiones/{id_remision:int}")
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


@router.put("/api/remisiones/{id_remision:int}/asignar")
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


@router.get("/api/remisiones/{id_remision:int}/pdf")
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

