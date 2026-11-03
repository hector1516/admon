"""PDF de cotizacion de materiales — diseño original HUB.

Colores originales, layout original, un solo QR en la zona de totales.
"""

import datetime
import hashlib
import hmac
import io
import os

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from api.numbers_helper import numero_a_letras


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 6.5)
        self.setFillColor(colors.HexColor("#475569"))
        address_text = "Fray Luis de Leon 1713, Jardin Español, Monterrey, Nuevo Leon, Cp. 64820 | www.ecc-sa.com.mx"
        self.drawString(30, 12, address_text)
        page_text = f"Pagina {self._pageNumber} de {page_count}"
        self.drawRightString(582, 12, page_text)
        self.restoreState()


def _logo_flowables():
    for cand in ("/eccsa_logo.png", "eccsa_logo.png"):
        try:
            if not os.path.exists(cand):
                continue
            with open(cand, "rb") as f:
                raw = f.read()
            try:
                from PIL import Image as PILImage
                im = PILImage.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((300, 300))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=50)
                buf.seek(0)
                data = buf
            except Exception:
                data = io.BytesIO(raw)
            return [RLImage(data, width=175, height=52), Spacer(1, 4)]
        except Exception:
            continue
    return []


_QR_SECRET = os.getenv("COTIZACION_QR_SECRET", "eccsa-qr-verify-2026")


def generar_token_qr(folio: int) -> str:
    msg = str(folio).encode("utf-8")
    sig = hmac.new(_QR_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:8]
    return f"{folio}-{sig}"


def verificar_token_qr(token: str) -> int | None:
    try:
        folio_str, sig = token.rsplit("-", 1)
        folio = int(folio_str)
        expected = hmac.new(_QR_SECRET.encode("utf-8"), str(folio).encode("utf-8"), hashlib.sha256).hexdigest()[:8]
        if hmac.compare_digest(sig, expected):
            return folio
    except (ValueError, Exception):
        pass
    return None


def _generar_qr_image(folio: int) -> io.BytesIO | None:
    try:
        token = generar_token_qr(folio)
        url = f"https://admon.ecc-sa.com.mx/cotizacion/{token}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#000000", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception:
        return None


def build_cotizacion_pdf(header: dict, partidas: list) -> bytes:
    if not header:
        header = {}
    if not partidas:
        partidas = []
    valid_parts = []
    for item in partidas:
        if not isinstance(item, dict):
            continue
        try:
            cant = float(item.get("cantidad") or 0)
            precio = float(item.get("precio_compra") or 0)
            if cant <= 0 or precio < 0:
                continue
            valid_parts.append(item)
        except (ValueError, TypeError):
            continue
    partidas = valid_parts
    if not partidas:
        raise ValueError("La cotizacion no tiene partidas validas.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=15,
        rightMargin=15,
        topMargin=15,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle("Norm", fontName="Helvetica", fontSize=8.5, leading=10, textColor=colors.black)
    style_bold = ParagraphStyle("Bld", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.black)
    style_meta_label = ParagraphStyle("MLbl", fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=2, textColor=colors.black)
    style_meta_value = ParagraphStyle("MVal", fontName="Helvetica", fontSize=9, leading=11, alignment=2, textColor=colors.black)
    style_item_desc = ParagraphStyle("ItemDesc", fontName="Helvetica", fontSize=8, leading=9.5, textColor=colors.black)
    style_item_header = ParagraphStyle("ItemHdr", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.black)
    style_words = ParagraphStyle("Words", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.black)
    style_logo_subtext = ParagraphStyle("LogoSub", fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=colors.HexColor("#334155"))

    story = []

    # HEADER (logo izq + metadatos der)
    logo_container = []
    logo_container.extend(_logo_flowables())
    logo_container.append(Paragraph("Oscar Noe Castillo Zavala - CAZO670914BK8", style_logo_subtext))

    cot_number = f"CM{str(header.get('folio')).zfill(5)}"
    date_val = header.get("fecha")
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        date_str = date_val.strftime("%d/%m/%Y")
    else:
        date_str = str(date_val or "")

    autor = header.get("autor") or ""
    telefono = header.get("telefono") or "8183589075"
    author_email = f"{autor.lower().replace(' ', '.')}@ecc-sa.com.mx" if autor else ""

    meta_data = [
        [Paragraph(f"Cotizacion: {cot_number}", style_meta_label)],
        [Paragraph(f"Fecha: {date_str}", style_meta_value)],
        [Paragraph(f"Cliente: {header.get('contacto') or ''}", style_meta_value)],
        [Paragraph(f"{header.get('cliente_nombre') or ''}", style_meta_value)],
        [Paragraph(f"Elaboro: {autor}", style_meta_value)],
        [Paragraph(f"Telefono: {telefono}", style_meta_value)],
        [Paragraph(f"Email: {author_email}", style_meta_value)],
    ]
    meta_table = Table(meta_data, colWidths=[380])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    header_data = [[logo_container, meta_table]]
    header_table = Table(header_data, colWidths=[202, 380])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # TABLA DE PARTIDAS
    items_data = [[
        Paragraph("Part.", style_item_header),
        Paragraph("Cant.", style_item_header),
        Paragraph("Descripcion", style_item_header),
        Paragraph("Sub.", style_item_header),
        Paragraph("Total", style_item_header),
    ]]

    subtotal_general = 0.0
    max_delivery_days = 1

    for item in partidas or []:
        partida_num = str(item.get("partida") or "").zfill(3)
        cantidad_num = str(item.get("cantidad") or "").zfill(3)
        cant = float(item.get("cantidad") or 0)
        p_compra = float(item.get("precio_compra") or 0.0)
        factor = float(item.get("factor") or 0.0)
        flete = float(item.get("flete") or 0.0)
        delivery_days = int(item.get("tiempo_entrega") or 0)
        if delivery_days > max_delivery_days:
            max_delivery_days = delivery_days
        subtotal_temp = p_compra * (1.0 + factor)
        total_item = (subtotal_temp * cant) + flete
        unit_price_item = total_item / cant if cant > 0 else 0.0
        subtotal_general += total_item
        desc_clean = str(item.get("descripcion") or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
        diass_suffix = " Dia Laboral" if delivery_days == 1 else " Dias Laborales"
        sat_extra = ""
        articulo = " ".join(str(item.get("articulo_generico") or "").split())
        if articulo:
            articulo = articulo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            sat_extra = f" · {articulo}"
        if item.get("sat_prod_serv"):
            sat_extra += f" · SAT: {item['sat_prod_serv']}"
            if item.get("sat_unidad"):
                sat_extra += f" · Unidad: {item['sat_unidad']}"
        desc_full = (f"{desc_clean}<br/><font color='#64748B'>"
                     f"Tiempo entrega: {delivery_days}{diass_suffix}{sat_extra}</font>")
        items_data.append([
            Paragraph(partida_num, style_item_desc),
            Paragraph(cantidad_num, style_item_desc),
            Paragraph(desc_full, style_item_desc),
            Paragraph(f"${unit_price_item:,.2f}", style_item_desc),
            Paragraph(f"${total_item:,.2f}", style_item_desc),
        ])

    items_table = Table(items_data, colWidths=[30, 30, 402, 60, 60], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # TOTALES + MONTO EN LETRA
    iva_general = subtotal_general * 0.16
    total_general = subtotal_general + iva_general
    total_letras = numero_a_letras(total_general).upper()

    totals_rows = [
        [Paragraph("Subtotal", style_bold), Paragraph(f"${subtotal_general:,.2f}", style_bold)],
        [Paragraph("I.V.A. (16%)", style_bold), Paragraph(f"${iva_general:,.2f}", style_bold)],
        [Paragraph("Total", style_bold), Paragraph(f"${total_general:,.2f}", style_bold)],
    ]
    totals_table = Table(totals_rows, colWidths=[70, 70])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    totals_wrapper = Table([[Spacer(1, 1), totals_table]], colWidths=[442, 140])
    totals_wrapper.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_wrapper)
    story.append(Spacer(1, 4))

    words_table = Table([[Paragraph(total_letras, style_words)]], colWidths=[582])
    words_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(words_table)
    story.append(Spacer(1, 8))

    # QR (un solo QR, en la zona de totales)
    folio = header.get("folio", 0)
    qr_buf = _generar_qr_image(folio) if folio else None
    if qr_buf:
        qr_img = RLImage(qr_buf, width=65, height=65)
        qr_label = Paragraph("Escanea para verificar<br/>esta cotizacion", ParagraphStyle(
            "QRLabel", fontName="Helvetica", fontSize=7, leading=8,
            textColor=colors.HexColor("#64748b"), alignment=1))
        qr_table = Table([[qr_img], [qr_label]], colWidths=[65])
        qr_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        qr_wrapper = Table([[Spacer(1, 1), qr_table]], colWidths=[517, 65])
        qr_wrapper.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(qr_wrapper)
        story.append(Spacer(1, 8))

    # TERMINOS Y CONDICIONES
    cond_pago_days = header.get("condiciones_pago", 30) or 30
    te_suffix = " Dia Laboral" if max_delivery_days == 1 else " Dias Laborales"

    cond_col1_data = [
        [Paragraph(f"T.E. Max. {str(max_delivery_days).zfill(2)}{te_suffix}", style_bold)],
        [Paragraph(f"Condiciones de Pago: {str(cond_pago_days).zfill(2)} dias", style_normal)],
        [Paragraph("Precios en Moneda Nacional", style_normal)],
        [Paragraph("Stock salvo previa venta", style_normal)],
    ]
    cond_col1_table = Table(cond_col1_data, colWidths=[200])
    cond_col1_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    author_email = str(header.get("autor") or "").lower().replace(" ", ".") + "@ecc-sa.com.mx"
    cond_col2_data = [
        [Paragraph("ECCSA Automation, RFC: CAZO670914BK8", style_bold)],
        [Paragraph(f"Telefono: 8183589075, eccsa@ecc-sa.com.mx {author_email}", style_normal)],
        [Paragraph("Fray Luis de Leon 1713, Jardin Espanol, Monterrey, Nuevo Leon, Cp. 64820", style_normal)],
        [Paragraph("La cotizacion tiene una vigencia de 15 dias naturales a partir de su fecha de emision", style_normal)],
    ]
    cond_col2_table = Table(cond_col2_data, colWidths=[382])
    cond_col2_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    cond_table = Table([[cond_col1_table, cond_col2_table]], colWidths=[200, 382])
    cond_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([cond_table]))

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes