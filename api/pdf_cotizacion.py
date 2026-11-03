"""PDF de cotizacion de materiales — rediseño sobrio y equilibrado.

Diseño limpio, sin colores llamativos. Solo grises y negro.
Mejor aprovechamiento del espacio, sin informacion repetida.
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
from reportlab.lib.units import mm
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


# === Colores sobrios (solo grises + negro) ===
C_DARK = colors.HexColor("#1a1a1a")
C_TEXT = colors.HexColor("#333333")
C_GRAY = colors.HexColor("#666666")
C_GRAY_LIGHT = colors.HexColor("#f5f5f5")
C_BORDER = colors.HexColor("#cccccc")
C_BORDER_LIGHT = colors.HexColor("#e5e5e5")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._qr_image = kwargs.pop("qr_image", None)
        self._terms_text = kwargs.pop("terms_text", "")
        self._empresa_info = kwargs.pop("empresa_info", "")
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
        # Línea superior del footer
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.5)
        self.line(20, 72, 592, 72)

        # Términos y condiciones
        self.setFont("Helvetica", 7)
        self.setFillColor(C_GRAY)
        y = 65
        if self._terms_text:
            self.drawString(20, y, self._terms_text)
            y -= 9

        # Info de empresa
        if self._empresa_info:
            for line in self._empresa_info.split("\n"):
                self.drawString(20, y, line)
                y -= 8.5

        # QR code (derecha)
        if self._qr_image:
            try:
                from reportlab.lib.utils import ImageReader
                qr_reader = ImageReader(self._qr_image)
                self.drawImage(qr_reader, 535, 28, width=52, height=52)
                self.setFont("Helvetica", 6)
                self.drawCentredString(561, 22, "Verificar")
            except Exception:
                pass

        # Línea inferior
        self.line(20, 18, 592, 18)
        # Dirección
        self.setFont("Helvetica", 6.5)
        self.setFillColor(C_GRAY)
        self.drawString(20, 9, "Fray Luis de Leon 1713, Jardin Espanol, Monterrey, N.L., Cp. 64820  |  www.ecc-sa.com.mx")
        # Número de página
        page_text = f"Pagina {self._pageNumber} de {page_count}"
        self.drawRightString(592, 9, page_text)
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
                im.save(buf, format="JPEG", quality=70)
                buf.seek(0)
                data = buf
            except Exception:
                data = io.BytesIO(raw)
            return [RLImage(data, width=130, height=39), Spacer(1, 2)]
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
        img = qr.make_image(fill_color="#333333", back_color="white")
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
        leftMargin=20,
        rightMargin=20,
        topMargin=15,
        bottomMargin=80,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle("Norm", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=C_TEXT)
    style_bold = ParagraphStyle("Bld", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=C_DARK)
    style_meta_label = ParagraphStyle("MLbl", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=0, textColor=C_GRAY)
    style_meta_value = ParagraphStyle("MVal", fontName="Helvetica", fontSize=8.5, leading=10, alignment=0, textColor=C_DARK)
    style_item_desc = ParagraphStyle("ItemDesc", fontName="Helvetica", fontSize=8, leading=9.5, textColor=C_TEXT)
    style_item_header = ParagraphStyle("ItemHdr", fontName="Helvetica-Bold", fontSize=8, leading=9.5, textColor=colors.white)
    style_words = ParagraphStyle("Words", fontName="Helvetica", fontSize=8, leading=10, textColor=C_GRAY)
    style_logo_subtext = ParagraphStyle("LogoSub", fontName="Helvetica", fontSize=7, leading=8.5, textColor=C_GRAY)
    style_title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=15, leading=17, textColor=C_DARK, alignment=0, spaceAfter=1)
    style_subtitle = ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=8, leading=9.5, textColor=C_GRAY, alignment=0)
    style_cond = ParagraphStyle("Cond", fontName="Helvetica", fontSize=7, leading=8.5, textColor=C_GRAY)

    story = []

    # === HEADER ===
    logo_container = []
    logo_container.extend(_logo_flowables())
    logo_container.append(Paragraph("Oscar Noe Castillo Zavala  |  RFC: CAZO670914BK8", style_logo_subtext))

    cot_number = f"CM{str(header.get('folio')).zfill(5)}"
    date_val = header.get("fecha")
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        date_str = date_val.strftime("%d/%m/%Y")
    else:
        date_str = str(date_val or "")

    autor = header.get("autor") or ""
    author_email = f"{autor.lower().replace(' ', '.')}@ecc-sa.com.mx" if autor else ""
    telefono = header.get("telefono") or "8183589075"
    cliente = header.get("contacto") or ""
    cliente_nombre = header.get("cliente_nombre") or ""

    # Título + línea de acento sobria
    story.append(Paragraph("COTIZACION", style_title))
    story.append(Paragraph("Cotizacion de materiales y servicios", style_subtitle))
    accent_line = Table([[""]], colWidths=[560])
    accent_line.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, C_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(accent_line)
    story.append(Spacer(1, 8))

    # Metadatos en dos columnas: izquierda (cotización) y derecha (cliente)
    meta_left = [
        [Paragraph("Cotizacion", style_meta_label), Paragraph(cot_number, style_meta_value)],
        [Paragraph("Fecha", style_meta_label), Paragraph(date_str, style_meta_value)],
        [Paragraph("Elaboro", style_meta_label), Paragraph(autor, style_meta_value)],
        [Paragraph("Email", style_meta_label), Paragraph(author_email, style_meta_value)],
    ]
    meta_right = [
        [Paragraph("Cliente", style_meta_label), Paragraph(cliente, style_meta_value)],
        [Paragraph("", style_meta_label), Paragraph(cliente_nombre, style_meta_value)],
        [Paragraph("Telefono", style_meta_label), Paragraph(telefono, style_meta_value)],
    ]

    meta_left_table = Table(meta_left, colWidths=[65, 200])
    meta_left_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    meta_right_table = Table(meta_right, colWidths=[65, 200])
    meta_right_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    header_data = [[logo_container, meta_left_table, meta_right_table]]
    header_table = Table(header_data, colWidths=[135, 215, 210])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # === TABLA DE PARTIDAS ===
    items_data = [[
        Paragraph("Part.", style_item_header),
        Paragraph("Cant.", style_item_header),
        Paragraph("Descripcion", style_item_header),
        Paragraph("P. Unit.", style_item_header),
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
            sat_extra = f"  {articulo}"
        if item.get("sat_prod_serv"):
            sat_extra += f"  SAT: {item['sat_prod_serv']}"
            if item.get("sat_unidad"):
                sat_extra += f"  Unidad: {item['sat_unidad']}"
        desc_full = (f"{desc_clean}<br/><font size='7' color='#808080'>"
                     f"Entrega: {delivery_days}{diass_suffix}{sat_extra}</font>")
        items_data.append([
            Paragraph(partida_num, style_item_desc),
            Paragraph(cantidad_num, style_item_desc),
            Paragraph(desc_full, style_item_desc),
            Paragraph(f"${unit_price_item:,.2f}", style_item_desc),
            Paragraph(f"${total_item:,.2f}", style_item_desc),
        ])

    items_table = Table(items_data, colWidths=[35, 35, 310, 90, 90], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GRAY_LIGHT]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # === TOTALES ===
    iva_general = subtotal_general * 0.16
    total_general = subtotal_general + iva_general
    total_letras = numero_a_letras(total_general).upper()

    totals_rows = [
        [Paragraph("Subtotal", style_normal), Paragraph(f"${subtotal_general:,.2f}", style_normal)],
        [Paragraph("I.V.A. (16%)", style_normal), Paragraph(f"${iva_general:,.2f}", style_normal)],
        [Paragraph("Total", style_bold), Paragraph(f"${total_general:,.2f}", style_bold)],
    ]
    totals_table = Table(totals_rows, colWidths=[100, 100])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 2), (1, 2), 1, C_DARK),
        ("BACKGROUND", (0, 2), (1, 2), C_GRAY_LIGHT),
    ]))
    totals_wrapper = Table([[Spacer(1, 1), totals_table]], colWidths=[360, 200])
    totals_wrapper.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))

    totals_block = []
    totals_block.append(totals_wrapper)
    totals_block.append(Spacer(1, 4))
    words_table = Table([[Paragraph(total_letras, style_words)]], colWidths=[560])
    words_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    totals_block.append(words_table)

    # QR de verificacion
    folio = header.get("folio", 0)
    qr_buf = _generar_qr_image(folio) if folio else None
    if qr_buf:
        qr_img = RLImage(qr_buf, width=55, height=55)
        qr_label = Paragraph("Verificar<br/>cotizacion", ParagraphStyle(
            "QRLabel", fontName="Helvetica", fontSize=6.5, leading=7.5,
            textColor=C_GRAY, alignment=1))
        qr_table = Table([[qr_img], [qr_label]], colWidths=[55])
        qr_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        qr_wrapper = Table([[Spacer(1, 1), qr_table]], colWidths=[505, 55])
        qr_wrapper.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        totals_block.append(Spacer(1, 6))
        totals_block.append(qr_wrapper)

    story.append(KeepTogether(totals_block))

    # === PREPARAR DATOS PARA EL FOOTER ===
    cond_pago_days = header.get("condiciones_pago", 30) or 30
    te_suffix = " Dia Laboral" if max_delivery_days == 1 else " Dias Laborales"

    cond_items = [
        f"T.E. Max. {str(max_delivery_days).zfill(2)}{te_suffix}",
        f"Condiciones de Pago: {str(cond_pago_days).zfill(2)} dias",
        "Precios en Moneda Nacional",
        "Stock salvo previa venta",
        "Vigencia: 15 dias naturales",
    ]
    terms_text = "  |  ".join(cond_items)

    author_email = f"{autor.lower().replace(' ', '.')}@ecc-sa.com.mx" if autor else ""
    empresa_info = (
        f"ECCSA Automation  |  RFC: CAZO670914BK8\n"
        f"Tel: 8183589075  |  {author_email}  |  eccsa@ecc-sa.com.mx"
    )

    def canvas_maker(*args, **kwargs):
        kwargs["qr_image"] = qr_buf
        kwargs["terms_text"] = terms_text
        kwargs["empresa_info"] = empresa_info
        return NumberedCanvas(*args, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes