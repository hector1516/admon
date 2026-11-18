"""PDF de reporte de servicio — CLON EXACTO del HUB (pdf_generator.generate_service_report_pdf).

Mismas fuentes, normalización PNG (anti-crash iOS), grid compuesto, firma, fotos,
ServiceNumberedCanvas con fotos de técnicos en footer. Sin pdf_storage ni caché.
"""

import io
import datetime
import os
import base64
import time
from functools import partial

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether,
    Image as RLImage, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# --- Register DejaVu Sans fonts (fallback a Helvetica si no hay) ---
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', os.path.join(_FONTS_DIR, 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', os.path.join(_FONTS_DIR, 'DejaVuSans-Bold.ttf')))
    _PDF_FONT = 'DejaVuSans'
    _PDF_FONT_BOLD = 'DejaVuSans-Bold'
except Exception:
    _PDF_FONT = 'Helvetica'
    _PDF_FONT_BOLD = 'Helvetica-Bold'


# --- Simple PDF Cache (TTL 10 min) ---
_pdf_cache = {}
_PDF_CACHE_TTL = 600


def _get_cached_pdf(cache_key):
    if cache_key in _pdf_cache:
        data, ts = _pdf_cache[cache_key]
        if time.time() - ts < _PDF_CACHE_TTL:
            return data
        del _pdf_cache[cache_key]
    return None


def _set_cached_pdf(cache_key, data):
    _pdf_cache[cache_key] = (data, time.time())
    if len(_pdf_cache) > 50:
        oldest = min(_pdf_cache, key=lambda k: _pdf_cache[k][1])
        del _pdf_cache[oldest]


# --- Image normalization (PNG FlateDecode para iOS/WhatsApp) ---
def _normalize_image_for_pdf(raw_bytes, max_dim=250, quality=None):
    from PIL import Image as PILImage
    img_buf = io.BytesIO(raw_bytes)
    pil_img = PILImage.open(img_buf)

    if pil_img.mode == 'RGBA':
        background = PILImage.new('RGB', pil_img.size, (255, 255, 255))
        background.paste(pil_img, mask=pil_img.split()[3])
        pil_img = background
    elif pil_img.mode != 'RGB':
        pil_img = pil_img.convert('RGB')

    pil_img.thumbnail((max_dim, max_dim), PILImage.LANCZOS)

    out = io.BytesIO()
    pil_img.save(out, format='PNG', optimize=True)
    out.seek(0)
    return out


# --- Photo grid composite (1 XObject = anti-crash iOS) ---
# CLON EXACTO de pdf_generator._build_photo_grid_composite
def _build_photo_grid_composite(fotos, max_photos=6):
    from PIL import Image as PILImage, ImageDraw, ImageFont

    # Configuración del grid (idéntico al HUB)
    CELL_W, CELL_H = 250, 250
    CAPTION_H = 30
    MARGIN = 20
    GAP = 10
    COLS = 2
    ROWS = 3

    canvas_w = MARGIN * 2 + COLS * CELL_W + (COLS - 1) * GAP
    canvas_h = MARGIN * 2 + ROWS * (CELL_H + CAPTION_H) + (ROWS - 1) * GAP

    # Canvas blanco
    canvas = PILImage.new('RGB', (canvas_w, canvas_h), 'white')
    draw = ImageDraw.Draw(canvas)

    # Fuente para captions
    try:
        font = ImageFont.truetype(os.path.join(_FONTS_DIR, 'DejaVuSans.ttf'), 14)
    except Exception:
        font = ImageFont.load_default()

    # Procesar máximo 6 fotos
    for idx, foto in enumerate(fotos[:max_photos]):
        try:
            # Obtener base64 (puede venir como 'FotoComprimida' o 'base64')
            b64 = foto.get('FotoComprimida') or foto.get('base64')
            if not b64:
                raise ValueError("No base64 data")
            
            # Manejar tanto string (base64) como bytes
            if isinstance(b64, str):
                raw = base64.b64decode(b64)
            elif isinstance(b64, bytes):
                raw = b64
            else:
                raise ValueError(f"Unexpected type: {type(b64)}")
            
            # Normalizar imagen (PNG, 250px max)
            normalized = _normalize_image_for_pdf(raw, max_dim=CELL_W)
            pil_img = PILImage.open(normalized)

            # Calcular posición en grid
            col = idx % COLS
            row = idx // COLS
            x = MARGIN + col * (CELL_W + GAP)
            y = MARGIN + row * (CELL_H + CAPTION_H + GAP)

            # Centrar imagen en celda (mantener aspect ratio)
            img_x = x + (CELL_W - pil_img.width) // 2
            img_y = y + (CELL_H - pil_img.height) // 2

            # Pegar imagen
            canvas.paste(pil_img, (img_x, img_y))

            # Dibujar caption "Foto N" centrado
            caption = f"Foto {foto['Orden']}"
            bbox = draw.textbbox((0, 0), caption, font=font)
            text_w = bbox[2] - bbox[0]
            text_x = x + (CELL_W - text_w) // 2
            text_y = y + CELL_H + 5
            draw.text((text_x, text_y), caption, fill='#475569', font=font)

        except Exception as e:
            # Si falla una foto, dibujar placeholder con error visible
            col = idx % COLS
            row = idx // COLS
            x = MARGIN + col * (CELL_W + GAP)
            y = MARGIN + row * (CELL_H + CAPTION_H + GAP)
            draw.rectangle([x, y, x + CELL_W, y + CELL_H], outline='#CBD5E1', width=1)
            draw.text((x + 10, y + CELL_H // 2 - 10), f"Foto {foto.get('Orden', idx+1)}", fill='#EF4444', font=font)
            draw.text((x + 10, y + CELL_H // 2 + 10), f"Error: {str(e)[:30]}", fill='#EF4444', font=font)

    # Guardar como JPEG baseline (más pequeño que PNG para canvas grande)
    out = io.BytesIO()
    canvas.save(out, format='JPEG', quality=80, progressive=False, optimize=True)
    out.seek(0)
    return out


# --- Placeholder photo ---
def _make_placeholder_photo(size=80):
    from PIL import Image as PILImage, ImageDraw
    img = PILImage.new('RGB', (size, size), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180), width=1)
    return img


# --- NumberedCanvas with technician photos in footer ---
class ServiceNumberedCanvas(canvas.Canvas):
    def __init__(self, *args, tech_photos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.tech_photos = tech_photos or []

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
        # Footer address
        self.drawString(20, 12, "Fray Luis de Leon 1713, Jardin Español, Monterrey, Nuevo Leon, Cp. 64820 | www.ecc-sa.com.mx")
        # Page number
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(595, 12, page_text)
        # Technician photos (bottom right area)
        if self.tech_photos and self._pageNumber == page_count:
            x_start = 420
            y_pos = 12
            ph_w = 30
            ph_h = 30
            gap = 4
            for i, ph in enumerate(self.tech_photos[:5]):
                try:
                    if hasattr(ph, 'read'):
                        # It's a BytesIO from _normalize_image_for_pdf
                        ph.seek(0)
                        self.drawInlineImage(ph, x_start + i * (ph_w + gap), y_pos, width=ph_w, height=ph_h)
                    else:
                        # It's a PIL Image from _make_placeholder_photo
                        buf = io.BytesIO()
                        ph.save(buf, format='PNG')
                        buf.seek(0)
                        self.drawInlineImage(buf, x_start + i * (ph_w + gap), y_pos, width=ph_w, height=ph_h)
                except Exception:
                    pass
        self.restoreState()


# --- Main PDF Builder (CLON EXACTO del HUB) ---
def build_service_report_pdf(report: dict, tecnicos_adicionales: list = None, fotos: list = None, cliente_nombre: str = None) -> bytes:
    folio = report.get('Folio', '')
    cached = _get_cached_pdf(f"srv_{folio}")
    if cached:
        return cached

    def _txt(v, fallback="N/A"):
        if v is None:
            return fallback
        if isinstance(v, float) and v != v:
            return fallback
        s = str(v)
        return s.replace('&', '&').replace('<', '<').replace('>', '>')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=30
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('Norm', fontName=_PDF_FONT, fontSize=10.5, leading=14, textColor=colors.black)
    style_bold = ParagraphStyle('Bld', fontName=_PDF_FONT_BOLD, fontSize=10.5, leading=14, textColor=colors.black)
    style_title = ParagraphStyle('Title', fontName=_PDF_FONT_BOLD, fontSize=16, leading=18, textColor=colors.HexColor('#1E293B'))
    style_subtitle = ParagraphStyle('SubTitle', fontName=_PDF_FONT_BOLD, fontSize=11.5, leading=14, textColor=colors.HexColor('#475569'))

    story = []

    # 1. Header (Logo + Title)
    logo_path = "/eccsa_logo.png" if os.path.exists("/eccsa_logo.png") else "eccsa_logo.png"
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_norm = _normalize_image_for_pdf(f.read(), max_dim=300, quality=50)
        logo_img = RLImage(logo_norm, width=120, height=45)
    else:
        logo_img = Paragraph("<b>ECCSA</b>", style_title)

    header_data = [
        [logo_img,
         Paragraph(f"REPORTE DE SERVICIO DE CAMPO<br/><font size=9.5 color='#64748B'>FIELD SERVICE REPORT</font>", style_title),
         Paragraph(f"<b>FOLIO:</b><br/><font color='#EF4444' size=12.5><b>{report['Folio']}</b></font>", style_bold)]
    ]
    header_table = Table(header_data, colWidths=[130, 310, 132])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    # 2. Secciones de datos
    _ACCENT = colors.HexColor('#FF6B00')
    _BG_LIGHT = colors.HexColor('#F8FAFC')
    _BG_HEADER = colors.HexColor('#1E293B')
    _BORDER = colors.HexColor('#E2E8F0')
    style_section = ParagraphStyle('Section', fontName=_PDF_FONT_BOLD, fontSize=11, leading=14, textColor=colors.white)
    style_field_label = ParagraphStyle('FieldLabel', fontName=_PDF_FONT_BOLD, fontSize=9, leading=11, textColor=colors.HexColor('#475569'))
    style_field_value = ParagraphStyle('FieldValue', fontName=_PDF_FONT, fontSize=10, leading=13, textColor=colors.black)

    t_ini = report['FechaHoraInicio'].strftime('%d/%m/%Y %H:%M') if isinstance(report['FechaHoraInicio'], datetime.datetime) else str(report['FechaHoraInicio'] or 'N/A')
    t_fin = report['FechaHoraFin'].strftime('%d/%m/%Y %H:%M') if isinstance(report['FechaHoraFin'], datetime.datetime) else str(report['FechaHoraFin'] or 'N/A')
    t_traslado = f"{report['TiempoTraslado']} horas" if report['TiempoTraslado'] is not None else "0.0 horas"
    t_comida = "Sí" if report['TiempoComida'] else "No"

    _tecnicos_adic = tecnicos_adicionales or []
    _eq_text = ', '.join(_tecnicos_adic) if _tecnicos_adic else '—'
    _correo = report['CorreoContacto'] or '—'

    _cliente_id = _txt(report['Cliente'])
    _cliente_display = f"{_cliente_id} — {cliente_nombre}" if cliente_nombre else _cliente_id

    def _build_section(title, data_rows, col_widths, spans=None):
        sec_data = [[Paragraph(f"<b>{title}</b>", style_section)] + [Paragraph("", style_section)] * (len(col_widths) - 1)]
        for row in data_rows:
            sec_data.append(row)
        sec_table = Table(sec_data, colWidths=col_widths)
        sec_style = [
            ('SPAN', (0, 0), (len(col_widths) - 1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), _BG_HEADER),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), _BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, _BORDER),
            ('INNERGRID', (0, 1), (-1, -1), 0.25, colors.HexColor('#CBD5E1')),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, _ACCENT),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, 0), 2),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ]
        if spans:
            sec_style += spans
        sec_table.setStyle(TableStyle(sec_style))
        return sec_table

    # --- DATOS DEL CLIENTE ---
    story.append(_build_section('DATOS DEL CLIENTE', [
        [Paragraph("<b>Cliente:</b>", style_field_label), Paragraph("", style_field_label)],
        [Paragraph(_txt(_cliente_display), style_field_value), Paragraph("", style_field_value)],
        [Paragraph("<b>Contacto:</b>", style_field_label), Paragraph("<b>Correo:</b>", style_field_label)],
        [Paragraph(_txt(report['Contacto']), style_field_value), Paragraph(_txt(_correo), style_field_value)],
    ], [286, 286], [
        ('SPAN', (0, 1), (1, 1)),
        ('SPAN', (0, 2), (1, 2)),
    ]))
    story.append(Spacer(1, 2))

    # --- DATOS DEL SERVICIO ---
    _w_servicio = [172, 400]
    story.append(_build_section('DATOS DEL SERVICIO', [
        [Paragraph("<b>Ingeniero:</b>", style_field_label), Paragraph("<b>Equipo:</b>", style_field_label)],
        [Paragraph(_txt(report['Tecnico']), style_field_value), Paragraph(_txt(_eq_text), style_field_value)],
    ], _w_servicio))
    story.append(Spacer(1, 2))

    # --- TIEMPOS ---
    _w_tiempos = [172, 172, 114, 114]
    story.append(_build_section('TIEMPOS', [
        [Paragraph("<b>Inicio:</b>", style_field_label), Paragraph("<b>Fin:</b>", style_field_label),
         Paragraph("<b>Traslado:</b>", style_field_label), Paragraph("<b>Comida:</b>", style_field_label)],
        [Paragraph(_txt(t_ini), style_field_value), Paragraph(_txt(t_fin), style_field_value),
         Paragraph(_txt(t_traslado), style_field_value), Paragraph(_txt(t_comida), style_field_value)],
    ], _w_tiempos))
    story.append(Spacer(1, 2))

    # --- MÁQUINA / LÍNEA ---
    story.append(_build_section('MÁQUINA / LÍNEA', [
        [Paragraph("<b>Línea / Máquina:</b>", style_field_label)],
        [Paragraph(_txt(report.get('MaquinaLinea', ''), '—'), style_field_value)],
    ], [572]))
    story.append(Spacer(1, 4))

    # 3. Service Description Block
    story.append(Paragraph("DESCRIPCIÓN DEL SERVICIO REALIZADO / SERVICE DESCRIPTION", style_subtitle))
    story.append(Spacer(1, 6))

    desc_p = Paragraph(_txt(report['DescripcionServicio'], "Sin descripción del servicio.").replace(chr(10), '<br/>'), style_normal)
    desc_table = Table([[desc_p]], colWidths=[572])
    desc_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('MINHEIGHT', (0, 0), (-1, -1), 150),
    ]))
    story.append(desc_table)
    story.append(Spacer(1, 20))

    # 5. Signatures Block (Client Signature image)
    client_sig_img = None
    if report.get('FirmaConformidad') and isinstance(report['FirmaConformidad'], str):
        try:
            sig_data = report['FirmaConformidad'].split(',')[1]
            sig_bytes = base64.b64decode(sig_data)
            sig_norm = _normalize_image_for_pdf(sig_bytes, max_dim=400, quality=50)
            client_sig_img = RLImage(sig_norm, width=150, height=60)
        except Exception as e:
            print("Error rendering signature on PDF:", e)

    sig_story = []
    if client_sig_img:
        sig_img_table = Table([[client_sig_img]], colWidths=[572])
        sig_img_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        sig_story.append(sig_img_table)
    else:
        sig_story.append(Spacer(1, 45))

    sig_story.append(Paragraph("________________________________________<br/><b>Firma de Aceptación del Cliente</b>",
                               ParagraphStyle('Sig', fontName=_PDF_FONT, fontSize=10, alignment=1)))
    story.append(KeepTogether(sig_story))

    # 6. Photos Page (if any)
    if fotos:
        try:
            story.append(PageBreak())
            story.append(Paragraph("EVIDENCIA FOTOGRÁFICA / PHOTO EVIDENCE", style_subtitle))
            story.append(Spacer(1, 10))
            composite_buf = _build_photo_grid_composite(fotos)
            if composite_buf:
                img = RLImage(composite_buf, width=540, height=650)
                story.append(img)
                story.append(Spacer(1, 10))
        except Exception as e:
            print(f"build_service_report_pdf: fotos omitidas para {folio}: {e}")

    # Build PDF - collect technician photos for footer
    _tech_photos = []
    _all_techs = [report.get('Tecnico', '')] + _tecnicos_adic
    for _tech_name in _all_techs:
        if not _tech_name or not _tech_name.strip():
            continue
        _tech_photos.append(_make_placeholder_photo())  # Simplificado: sin BD para foto de usuario

    doc.build(story, canvasmaker=partial(ServiceNumberedCanvas, tech_photos=_tech_photos))
    pdf_bytes = buffer.getvalue()
    buffer.close()
    _set_cached_pdf(f"srv_{folio}", pdf_bytes)
    return pdf_bytes

def generate_horas_extras_reporte_pdf(nombre, registros, total_horas, sueldo_semana, periodo_inicio, periodo_fin, notas=None, folio=None):
    """Genera PDF de reporte de horas extras replicando formato Excel 'Tiempo Extra'.

    Columnas: Dia, Fecha, Hora Extra, Hora Acc, Descripcion, Entrada, Salida,
    Comida, Viaje, Cliente, Calificacion, Nota.
    Incluye firma fisica y monto informativo.
    """
    import io
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    buffer = io.BytesIO()
    # Landscape for wide table
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=20,
        rightMargin=20,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle('HETitle', fontName='Helvetica-Bold', fontSize=14, leading=17, textColor=colors.HexColor('#EB6C24'), alignment=1)
    style_body = ParagraphStyle('HEBody', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.black)
    style_bold = ParagraphStyle('HEBold', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black)
    style_th = ParagraphStyle('HETH', fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor('#1E293B'))
    style_td = ParagraphStyle('HETD', fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#334155'))
    style_sig = ParagraphStyle('HESig', fontName='Helvetica', fontSize=8, leading=11, alignment=1)

    story = []

    # Header
    logo_path = "/eccsa_logo.png" if os.path.exists("/eccsa_logo.png") else "eccsa_logo.png"
    left_cell = []
    if os.path.exists(logo_path):
        try:
            left_cell.append(RLImage(logo_path, width=140, height=42))
            left_cell.append(Spacer(1, 2))
        except Exception:
            pass
    left_cell.append(Paragraph("<b>Oscar Noe Castillo Zavala - CAZO670914BK8</b>", ParagraphStyle('OwnerHE', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6, leading=7, textColor=colors.HexColor('#1E293B'))))

    title_text = "REPORTE DE HORAS EXTRAS<br/><font size=8 color='#64748B'>ECCSA Automation</font>"
    if folio:
        title_text = "REPORTE DE HORAS EXTRAS<br/><font size=8 color='#64748B'>" + str(folio) + " - ECCSA Automation</font>"
    title_cell = Paragraph(title_text, style_title)

    header_table = Table([[left_cell, title_cell]], colWidths=[200, 560])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(header_table)

    divider = Table([[""]], colWidths=[760])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 1.5, colors.HexColor('#EB6C24')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(divider)
    story.append(Spacer(1, 10))

    # Employee info
    gen_ts = datetime.datetime.now()
    if isinstance(periodo_inicio, str):
        try:
            periodo_inicio = datetime.datetime.strptime(periodo_inicio[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    if isinstance(periodo_fin, str):
        try:
            periodo_fin = datetime.datetime.strptime(periodo_fin[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    pi_str = periodo_inicio.strftime("%d/%m/%Y") if hasattr(periodo_inicio, 'strftime') else str(periodo_inicio)
    pf_str = periodo_fin.strftime("%d/%m/%Y") if hasattr(periodo_fin, 'strftime') else str(periodo_fin)

    info_data = [
        [Paragraph("<b>Colaborador:</b>", style_bold), Paragraph(str(nombre), style_body)],
        [Paragraph("<b>Periodo:</b>", style_bold), Paragraph(pi_str + " al " + pf_str, style_body)],
        [Paragraph("<b>Total horas extras:</b>", style_bold), Paragraph(f"{total_horas:.2f} horas", style_body)],
        [Paragraph("<b>Fecha de generacion:</b>", style_bold), Paragraph(gen_ts.strftime("%d/%m/%Y %H:%M:%S"), style_body)],
    ]
    if notas:
        info_data.append([Paragraph("<b>Notas:</b>", style_bold), Paragraph(str(notas), style_body)])
    info_table = Table(info_data, colWidths=[150, 610])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))

    # Records table (Excel format)
    def _fmt_fecha(f):
        try:
            if isinstance(f, datetime.datetime):
                return f.strftime("%d/%m/%Y")
            if isinstance(f, datetime.date):
                return f.strftime("%d/%m/%Y")
            return datetime.datetime.strptime(str(f)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return str(f)[:10]

    def _fmt_hora(t):
        if t is None:
            return "-"
        try:
            if isinstance(t, str):
                return t[:5]
            return t.strftime("%H:%M")
        except Exception:
            return str(t)[:5]

    def _fmt_num(v, default=0.0):
        try:
            return float(v if v is not None else default)
        except Exception:
            return default

    # Build rows with accumulated hours
    rows = []
    acc = 0.0
    tot_d = 0.0  # dobles
    tot_t = 0.0  # triples
    for r in registros:
        he = _fmt_num(r.get('HorasExtrasCalculadas') or r.get('HoraExtra'))
        acc += he
        dia = ""
        try:
            f = r.get('Fecha')
            if isinstance(f, (datetime.datetime, datetime.date)):
                dia = f.strftime("%A")
            else:
                dia = datetime.datetime.strptime(str(f)[:10], "%Y-%m-%d").strftime("%A")
        except Exception:
            dia = ""
        # Map English day names to Spanish
        dias_map = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miercoles',
                    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sabado', 'Sunday': 'Domingo'}
        dia = dias_map.get(dia, dia)

        comida = r.get('HorasComida') or r.get('Comida')
        comida_str = "NA" if comida is None or str(comida).upper() == 'NA' else f"{_fmt_num(comida):.2f}"
        viaje = r.get('HorasTraslado') or r.get('Viaje')
        viaje_str = str(viaje) if viaje is not None else "-"
        calif = r.get('Calificacion')
        calif_str = str(calif) if calif is not None else ""
        nota = r.get('Nota') or r.get('Notas') or ""
        desc = r.get('Descripcion') or r.get('descripcion') or ""
        cliente = r.get('Cliente') or r.get('cliente') or ""

        rows.append([
            Paragraph(dia, style_td),
            Paragraph(_fmt_fecha(r.get('Fecha')), style_td),
            Paragraph(f"{he:.2f}", style_td),
            Paragraph(f"{acc:.2f}", style_td),
            Paragraph(str(desc)[:40], style_td),
            Paragraph(_fmt_hora(r.get('HoraEntrada') or r.get('Entrada')), style_td),
            Paragraph(_fmt_hora(r.get('HoraSalida') or r.get('Salida')), style_td),
            Paragraph(comida_str, style_td),
            Paragraph(viaje_str[:15], style_td),
            Paragraph(str(cliente)[:12], style_td),
            Paragraph(calif_str, style_td),
            Paragraph(str(nota)[:20], style_td),
        ])
        tot_d += he

    # Totals row
    rows.append([
        Paragraph("<b>TOTAL</b>", ParagraphStyle('HETot', parent=style_td, fontName='Helvetica-Bold')),
        Paragraph("", style_td), Paragraph(f"<b>{tot_d:.2f}</b>", style_td),
        Paragraph(f"<b>{acc:.2f}</b>", style_td),
        Paragraph("", style_td), Paragraph("", style_td), Paragraph("", style_td),
        Paragraph("", style_td), Paragraph("", style_td), Paragraph("", style_td),
        Paragraph("", style_td), Paragraph("", style_td),
    ])

    header_row = [
        Paragraph("Dia", style_th), Paragraph("Fecha", style_th),
        Paragraph("Hora Extra", style_th), Paragraph("Hora Acc", style_th),
        Paragraph("Descripcion", style_th), Paragraph("Entrada", style_th),
        Paragraph("Salida", style_th), Paragraph("Comida", style_th),
        Paragraph("Viaje", style_th), Paragraph("Cliente", style_th),
        Paragraph("Calif.", style_th), Paragraph("Nota", style_th),
    ]
    table_data = [header_row] + rows

    col_widths = [55, 60, 45, 45, 120, 40, 40, 40, 50, 55, 30, 80]
    reg_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    reg_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#FFF7ED')),
        ('LINEABOVE', (0,-1), (-1,-1), 1, colors.HexColor('#EB6C24')),
    ]))
    story.append(reg_table)
    story.append(Spacer(1, 12))

    # Summary (solo horas extras, sin salario)
    resumen_data = [
        [Paragraph("<b>Numero de registros:</b>", style_bold), Paragraph(str(len(registros)), style_body)],
        [Paragraph("<b>Horas extras totales:</b>", style_bold), Paragraph(f"{total_horas:.2f} horas", style_body)],
    ]
    resumen_table = Table(resumen_data, colWidths=[200, 560])
    resumen_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FFF7ED')),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#EB6C24')),
        ('INNERGRID', (0,0), (-1,-1), 0.25, colors.HexColor('#FDBA74')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(resumen_table)
    story.append(Spacer(1, 20))

    # Signature block (physical signature)
    sig_story = []
    sig_story.append(Paragraph("________________________________________", style_sig))
    sig_story.append(Paragraph("<b>Firma del Colaborador</b>", style_sig))
    sig_story.append(Paragraph(f"Nombre: {nombre}", ParagraphStyle('SigName', parent=style_sig, fontSize=8, textColor=colors.HexColor('#475569'))))
    sig_story.append(Paragraph("Fecha: _______________", ParagraphStyle('SigDate', parent=style_sig, fontSize=8, textColor=colors.HexColor('#475569'))))
    story.append(KeepTogether(sig_story))
    story.append(Spacer(1, 15))

    # LFT reference note
    lft_note = Paragraph(
        "<font size=7 color='#64748B'>Conforme a la Ley Federal del Trabajo (LFT) vigente. "
        "Jornada maxima: 8h diurnas, 7h nocturnas, 7.5h mixtas (Art. 60-61). "
        "Horas extras: max 3h/dia, 3 veces/semana (Art. 66). "
        "Pago: dobles las primeras 9h/semana, triples las siguientes (Art. 68). "
        "Prima dominical: 25% adicional (Art. 71). "
        "Calculo informativo - el pago real se determina al firmar este documento.</font>",
        ParagraphStyle('LFTNote', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, textColor=colors.HexColor('#64748B'))
    )
    story.append(lft_note)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
