"""PDF de cotización de materiales — rediseño Apple HIG.

Diseño sobrio, coherente con los colores de ECCSA (naranja #FF6B00 + azul #1E40AF).
Mejor aprovechamiento del espacio, tipografía clara, tablas limpias.
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


# === ECCSA Corporate Colors ===
ECCSA_ORANGE = colors.HexColor("#FF6B00")
ECCSA_ORANGE_LIGHT = colors.HexColor("#FFF3E0")
ECCSA_BLUE = colors.HexColor("#1E40AF")
ECCSA_BLUE_LIGHT = colors.HexColor("#EFF6FF")
ECCSA_DARK = colors.HexColor("#0F172A")
ECCSA_GRAY = colors.HexColor("#475569")
ECCSA_GRAY_LIGHT = colors.HexColor("#F1F5F9")
ECCSA_BORDER = colors.HexColor("#CBD5E1")
ECCSA_TEXT = colors.HexColor("#1E293B")


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
        # === FOOTER: términos + empresa + QR + página ===
        # Línea superior del footer
        self.setStrokeColor(ECCSA_BORDER)
        self.setLineWidth(0.5)
        self.line(20, 75, 592, 75)

        # Términos y condiciones (izquierda)
        self.setFont("Helvetica", 7)
        self.setFillColor(ECCSA_GRAY)
        y = 68
        if self._terms_text:
            self.drawString(20, y, self._terms_text)
            y -= 10

        # Info de empresa
        if self._empresa_info:
            for line in self._empresa_info.split("\n"):
                self.drawString(20, y, line)
                y -= 9

        # QR code (derecha)
        if self._qr_image:
            try:
                from reportlab.lib.utils import ImageReader
                qr_reader = ImageReader(self._qr_image)
                self.drawImage(qr_reader, 532, 30, width=55, height=55)
                self.setFont("Helvetica", 6)
                self.drawCentredString(559.5, 24, "Verificar")
            except Exception:
                pass

        # Línea inferior
        self.line(20, 22, 592, 22)
        # Dirección
        self.setFont("Helvetica", 6.5)
        self.drawString(20, 12, "Fray Luis de Leon 1713, Jardin Espanol, Monterrey, N.L., Cp. 64820  |  www.ecc-sa.com.mx")
        # Número de página
        page_text = f"Pagina {self._pageNumber} de {page_count}"
        self.drawRightString(592, 12, page_text)
        self.restoreState()


def _logo_flowables():
    """Logo ECCSA normalizado."""
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
            return [RLImage(data, width=140, height=42), Spacer(1, 2)]
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
        img = qr.make_image(fill_color="#1E40AF", back_color="white")
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
        bottomMargin=85,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle("Norm", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=ECCSA_TEXT)
    style_bold = ParagraphStyle("Bld", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=ECCSA_DARK)
    style_meta_label = ParagraphStyle("MLbl", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, alignment=2, textColor=ECCSA_DARK)
    style_meta_value = ParagraphStyle("MVal", fontName="Helvetica", fontSize=8.5, leading=10.5, alignment=2, textColor=ECCSA_GRAY)
    style_item_desc = ParagraphStyle("ItemDesc", fontName="Helvetica", fontSize=8, leading=9.5, textColor=ECCSA_TEXT)
    style_item_header = ParagraphStyle("ItemHdr", fontName="Helvetica-Bold", fontSize=8, leading=9.5, textColor=colors.white)
    style_words = ParagraphStyle("Words", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=ECCSA_GRAY, alignment=0)
    style_logo_subtext = ParagraphStyle("LogoSub", fontName="Helvetica", fontSize=7, leading=8.5, textColor=ECCSA_GRAY)
    style_title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=ECCSA_ORANGE, alignment=0, spaceAfter=2)
    style_subtitle = ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=8, leading=9.5, textColor=ECCSA_GRAY, alignment=0)
    style_section = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ECCSA_BLUE, spaceBefore=10, spaceAfter=4)
    style_cond = ParagraphStyle("Cond", fontName="Helvetica", fontSize=8, leading=9.5, textColor=ECCSA_GRAY)

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

    meta_data = [
        [Paragraph("Cotizacion", style_meta_label), Paragraph(cot_number, style_meta_value)],
        [Paragraph("Fecha", style_meta_label), Paragraph(date_str, style_meta_value)],
        [Paragraph("Cliente", style_meta_label), Paragraph(header.get("contacto") or "", style_meta_value)],
        [Paragraph("", style_meta_label), Paragraph(header.get("cliente_nombre") or "", style_meta_value)],
        [Paragraph("Elaboro", style_meta_label), Paragraph(autor, style_meta_value)],
        [Paragraph("Telefono", style_meta_label), Paragraph(telefono, style_meta_value)],
        [Paragraph("Email", style_meta_label), Paragraph(author_email, style_meta_value)],
    ]
    meta_table = Table(meta_data, colWidths=[75, 305])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, ECCSA_BORDER),
    ]))

    # Línea de acento naranja bajo el título
    header_data = [[logo_container, meta_table]]
    header_table = Table(header_data, colWidths=[180, 380])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Paragraph("COTIZACION", style_title))
    story.append(Paragraph("Cotizacion de materiales y servicios", style_subtitle))
    # Línea de acento
    accent_line = Table([[""]], colWidths=[560])
    accent_line.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 2, ECCSA_ORANGE),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(accent_line)
    story.append(Spacer(1, 8))
    story.append(header_table)
    story.append(Spacer(1, 10))

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
        desc_full = (f"{desc_clean}<br/><font size='7' color='#64748B'>"
                     f"Entrega: {delivery_days}{diass_suffix}{sat_extra}</font>")
        items_data.append([
            Paragraph(partida_num, style_item_desc),
            Paragraph(cantidad_num, style_item_desc),
            Paragraph(desc_full, style_item_desc),
            Paragraph(f"${unit_price_item:,.2f}", style_item_desc),
            Paragraph(f"${total_item:,.2f}", style_item_desc),
        ])

    items_table = Table(items_data, colWidths=[35, 35, 340, 75, 75], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, ECCSA_BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), ECCSA_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ECCSA_GRAY_LIGHT]),
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
    totals_table = Table(totals_rows, colWidths=[90, 90])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 2), (1, 2), 1.5, ECCSA_ORANGE),
        ("BACKGROUND", (0, 2), (1, 2), ECCSA_ORANGE_LIGHT),
    ]))
    totals_wrapper = Table([[Spacer(1, 1), totals_table]], colWidths=[380, 180])
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
        ("LINEABOVE", (0, 0), (-1, -1), 0.3, ECCSA_BORDER),
    ]))
    totals_block.append(words_table)

    # QR de verificacion (debajo de los totales)
    folio = header.get("folio", 0)
    qr_buf = _generar_qr_image(folio) if folio else None
    if qr_buf:
        qr_img = RLImage(qr_buf, width=60, height=60)
        qr_label = Paragraph("Escanea para verificar<br/>esta cotizacion", ParagraphStyle(
            "QRLabel", fontName="Helvetica", fontSize=7, leading=8,
            textColor=ECCSA_GRAY, alignment=1))
        qr_table = Table([[qr_img], [qr_label]], colWidths=[60])
        qr_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        qr_wrapper = Table([[Spacer(1, 1), qr_table]], colWidths=[500, 60])
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
    story.append(Spacer(1, 8))

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

    # QR image
    folio = header.get("folio", 0)
    qr_buf = _generar_qr_image(folio) if folio else None

    # Build with custom canvas that includes footer
    def canvas_maker(*args, **kwargs):
        kwargs["qr_image"] = qr_buf
        kwargs["terms_text"] = terms_text
        kwargs["empresa_info"] = empresa_info
        return NumberedCanvas(*args, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes