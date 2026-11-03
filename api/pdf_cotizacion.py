"""PDF de cotizacion de materiales — diseño sobrio y equilibrado.

Diseño limpio. Subtotal/IVA/Total en fila horizontal. QR en esquina inferior derecha.
Terminos y datos de empresa en pie de pagina unificado.
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


# === Colores sobrios ===
C_DARK = colors.HexColor("#1a1a1a")
C_TEXT = colors.HexColor("#333333")
C_GRAY = colors.HexColor("#666666")
C_GRAY_LIGHT = colors.HexColor("#f5f5f5")
C_BORDER = colors.HexColor("#cccccc")
C_ECCSA_BLUE = colors.HexColor("#1E40AF")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._qr_image = kwargs.pop("qr_image", None)
        self._terms_text = kwargs.pop("terms_text", "")
        self._empresa_text = kwargs.pop("empresa_text", "")
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
        # === FOOTER UNIFICADO ===
        # Línea divisoria única (arriba)
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.5)
        self.line(20, 58, 592, 58)

        # Texto del footer (izquierda)
        self.setFont("Helvetica", 6.5)
        self.setFillColor(C_GRAY)
        self.drawString(20, 48, self._terms_text)
        self.drawString(20, 38, self._empresa_text)
        self.setFont("Helvetica", 6)
        self.drawString(20, 28, "Fray Luis de Leon 1713, Jardin Espanol, Monterrey, N.L., Cp. 64820  |  www.ecc-sa.com.mx")
        page_text = f"Pagina {self._pageNumber} de {page_count}"
        self.drawRightString(540, 28, page_text)

        # QR en esquina inferior derecha (debajo de la línea divisoria, en la esquina)
        if self._qr_image:
            try:
                from reportlab.lib.utils import ImageReader
                qr_reader = ImageReader(self._qr_image)
                self.drawImage(qr_reader, 550, 2, width=40, height=40)
                self.setFont("Helvetica", 5)
                self.drawCentredString(570, -3, "Verificar")
            except Exception:
                pass
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
        img = qr.make_image(fill_color="#666666", back_color="white")
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
        bottomMargin=65,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle("Norm", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=C_TEXT, alignment=1)
    style_bold = ParagraphStyle("Bld", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=C_DARK, alignment=1)
    style_meta_label = ParagraphStyle("MLbl", fontName="Helvetica-Bold", fontSize=8, leading=10, alignment=2, textColor=C_GRAY)
    style_meta_value = ParagraphStyle("MVal", fontName="Helvetica", fontSize=8.5, leading=10, alignment=2, textColor=C_DARK)
    style_item_desc = ParagraphStyle("ItemDesc", fontName="Helvetica", fontSize=8, leading=9.5, textColor=C_TEXT, alignment=0)
    style_item_desc_center = ParagraphStyle("ItemDescC", fontName="Helvetica", fontSize=8, leading=9.5, textColor=C_TEXT, alignment=1)
    style_item_header = ParagraphStyle("ItemHdr", fontName="Helvetica-Bold", fontSize=8, leading=9.5, textColor=colors.white, alignment=1)
    style_words = ParagraphStyle("Words", fontName="Helvetica", fontSize=8, leading=10, textColor=C_GRAY, alignment=1)
    style_logo_subtext = ParagraphStyle("LogoSub", fontName="Helvetica", fontSize=7, leading=8.5, textColor=C_GRAY)
    style_title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=C_GRAY, alignment=2, spaceAfter=2)
    style_cotnum = ParagraphStyle("CotNum", fontName="Helvetica-Bold", fontSize=20, leading=22, textColor=C_ECCSA_BLUE, alignment=2, spaceAfter=4)
    style_cond = ParagraphStyle("Cond", fontName="Helvetica", fontSize=7, leading=8.5, textColor=C_GRAY)

    story = []

    # === HEADER ===
    logo_container = []
    logo_container.extend(_logo_flowables())
    logo_container.append(Paragraph("Oscar Noe Castillo Zavala", style_logo_subtext))
    logo_container.append(Paragraph("RFC: CAZO670914BK8", style_logo_subtext))

    cot_number = f"CM{str(header.get('folio')).zfill(5)}"
    date_val = header.get("fecha")
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        date_str = date_val.strftime("%d/%m/%Y")
    else:
        date_str = str(date_val or "")

    autor = header.get("autor") or ""
    telefono = header.get("telefono") or "8183589075"
    author_email = f"{autor.lower().replace(' ', '.')}@ecc-sa.com.mx" if autor else ""
    cliente = header.get("contacto") or ""
    cliente_nombre = header.get("cliente_nombre") or ""

    # Título pequeño "COTIZACION" arriba de CM00... grande en azul ECCSA, alineado a la derecha
    header_title_data = [[
        Paragraph("COTIZACION", style_title),
    ], [
        Paragraph(cot_number, style_cotnum),
    ]]
    header_title_table = Table(header_title_data, colWidths=[560])
    header_title_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_title_table)
    story.append(Spacer(1, 8))

    # Metadatos: Fecha y Cliente alineados a la derecha
    meta_right = [
        [Paragraph("Fecha", style_meta_label), Paragraph(date_str, style_meta_value)],
        [Paragraph("Cliente", style_meta_label), Paragraph(cliente, style_meta_value)],
        [Paragraph("", style_meta_label), Paragraph(cliente_nombre, style_meta_value)],
    ]
    meta_right_table = Table(meta_right, colWidths=[65, 200])
    meta_right_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
    ]))

    header_data = [[logo_container, meta_right_table]]
    header_table = Table(header_data, colWidths=[135, 385])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
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
        desc_full = (f"{desc_clean}<br/><font size='7' color='#64748B'>"
                     f"Entrega: {delivery_days}{diass_suffix}{sat_extra}</font>")
        items_data.append([
            Paragraph(partida_num, style_item_desc_center),
            Paragraph(cantidad_num, style_item_desc_center),
            Paragraph(desc_full, style_item_desc),
            Paragraph(f"${unit_price_item:,.2f}", style_item_desc_center),
            Paragraph(f"${total_item:,.2f}", style_item_desc_center),
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
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (1, -1), "CENTER"),
        ("ALIGN", (3, 1), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GRAY_LIGHT]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # Empujar totales hacia el final de la página (justo arriba del footer)
    story.append(Spacer(1, 350))

    # === TOTALES EN FILA HORIZONTAL ===
    iva_general = subtotal_general * 0.16
    total_general = subtotal_general + iva_general
    total_letras = numero_a_letras(total_general).upper()

    # Fila horizontal: Subtotal | IVA | Total
    totals_row = [
        Paragraph(f"Subtotal: ${subtotal_general:,.2f}", style_normal),
        Paragraph(f"I.V.A. (16%): ${iva_general:,.2f}", style_normal),
        Paragraph(f"Total: ${total_general:,.2f}", style_bold),
    ]
    totals_table = Table([totals_row], colWidths=[186, 187, 187])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), C_GRAY_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEAFTER", (0, 0), (1, -1), 0.5, C_BORDER),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 4))

    # Monto en letra centrado debajo
    words_table = Table([[Paragraph(total_letras, style_words)]], colWidths=[560])
    words_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(words_table)

    # QR en esquina inferior derecha (sobre el footer, no en el cuerpo)
    # Se pasa al canvas para que se dibuje en el pie de página

    # === PREPARAR DATOS PARA EL FOOTER ===
    cond_pago_days = header.get("condiciones_pago", 30) or 30
    te_suffix = " Dia Laboral" if max_delivery_days == 1 else " Dias Laborales"

    cond_items = [
        f"T.E. Max. {str(max_delivery_days).zfill(2)}{te_suffix}",
        f"Cond. Pago: {str(cond_pago_days).zfill(2)} dias",
        "Precios en M.N.",
        "Stock salvo previa venta",
        "Vigencia: 15 dias",
    ]
    terms_text = "  |  ".join(cond_items)

    author_email = f"{autor.lower().replace(' ', '.')}@ecc-sa.com.mx" if autor else ""
    # Footer: términos + empresa + elaboro + email (todo unificado)
    cond_items = [
        f"T.E. Max. {str(max_delivery_days).zfill(2)}{te_suffix}",
        f"Cond. Pago: {str(cond_pago_days).zfill(2)} dias",
        "Precios en M.N.",
        "Stock salvo previa venta",
        "Vigencia: 15 dias",
    ]
    terms_text = "  |  ".join(cond_items)
    empresa_text = f"Elaboro: {autor}  |  {author_email}  |  Tel: {telefono}  |  ECCSA Automation  |  RFC: CAZO670914BK8"

    folio = header.get("folio", 0)
    qr_buf = _generar_qr_image(folio) if folio else None

    def canvas_maker(*args, **kwargs):
        kwargs["qr_image"] = qr_buf
        kwargs["terms_text"] = terms_text
        kwargs["empresa_text"] = empresa_text
        return NumberedCanvas(*args, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes