"""Office document generator — JSON intermediate layer → file bytes.

Each function takes a validated JSON dict and returns (bytes, mime_type).
"""
import io
import logging

logger = logging.getLogger("v2.office_gen.generator")


# ── DOCX generator ──────────────────────────────────────────────────────

def generate_docx(params: dict) -> bytes:
    try:
        from docx import Document
        from docx.shared import Pt, Inches, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
    except ImportError:
        raise RuntimeError("python-docx is not installed. Run: pip install python-docx")

    doc = Document()
    filename = params.get("filename", "未命名文档")
    content = params.get("content", [])

    for block in content:
        block_type = block.get("type", "段落")
        text = block.get("text", "")
        bold = block.get("bold", False)
        align = block.get("align", "left")
        level = block.get("level", 1)

        if block_type == "标题":
            p = doc.add_heading(text, level=min(level, 4))
        elif block_type == "段落":
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.bold = bold
            run.font.size = Pt(12)
            _set_alignment(p, align)
        elif block_type == "表格":
            header = block.get("表头", block.get("header", []))
            rows = block.get("行", block.get("rows", []))
            if header:
                rows = [header] + rows
            if rows:
                table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows) if rows else 0)
                table.style = "Light Grid Accent 1"
                for i, row_data in enumerate(rows):
                    for j, cell_text in enumerate(row_data):
                        if j < len(table.rows[i].cells):
                            table.rows[i].cells[j].text = str(cell_text)
        elif block_type == "图片":
            _add_image_block(doc, block)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _set_alignment(paragraph, align: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    mapping = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
               "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
    paragraph.alignment = mapping.get(align, WD_ALIGN_PARAGRAPH.LEFT)


def _add_image_block(doc, block: dict):
    image_data = block.get("image_data")
    image_path = block.get("image_path")
    width = block.get("width", 14)
    height = block.get("height")

    try:
        if image_data and isinstance(image_data, str):
            import base64
            raw = base64.b64decode(image_data)
            buf = io.BytesIO(raw)
            if height:
                doc.add_picture(buf, width=Cm(width), height=Cm(height))
            else:
                doc.add_picture(buf, width=Cm(width))
        elif image_path:
            doc.add_picture(image_path, width=Cm(width))
    except Exception as exc:
        logger.warning("Failed to add image: %s", exc)


# ── XLSX generator ──────────────────────────────────────────────────────

def generate_xlsx(params: dict) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        raise RuntimeError("openpyxl is not installed. Run: pip install openpyxl")

    wb = Workbook()
    # Keep the default sheet if no sheets specified
    sheets = params.get("工作表", params.get("sheets", []))
    if not sheets:
        ws = wb.active
        ws.title = "Sheet"
    else:
        wb.remove(wb.active)
    for sheet_spec in sheets:
        ws = wb.create_sheet(title=sheet_spec.get("表名", sheet_spec.get("name", "Sheet")))
        columns = sheet_spec.get("列", sheet_spec.get("columns", []))
        rows = sheet_spec.get("行", sheet_spec.get("rows", []))

        if columns:
            ws.append(columns)
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="2395BC", end_color="2395BC", fill_type="solid")
                cell.alignment = Alignment(horizontal="center")

        for row_data in rows:
            ws.append(list(row_data))

        for col in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ── PPTX generator ──────────────────────────────────────────────────────

def generate_pptx(params: dict) -> bytes:
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
    except ImportError:
        raise RuntimeError("python-pptx is not installed. Run: pip install python-pptx")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slides = params.get("幻灯片", params.get("slides", []))
    if not slides:
        layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(layout)
        title = slide.shapes.title
        if title:
            title.text = params.get("filename", "Empty Presentation")
    for slide_spec in slides:
        layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(layout)
        title = slide.shapes.title
        title_text = slide_spec.get("标题", slide_spec.get("title", ""))
        if title:
            title.text = title_text

        bullets = slide_spec.get("要点", slide_spec.get("bullets", []))
        if bullets:
            body = slide.shapes.placeholders[1]
            tf = body.text_frame
            tf.word_wrap = True
            for i, bullet in enumerate(bullets):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                if isinstance(bullet, str):
                    p.text = bullet
                elif isinstance(bullet, dict):
                    p.text = bullet.get("text", "")
                    p.level = bullet.get("level", 0)

        notes_text = slide_spec.get("备注", slide_spec.get("notes", ""))
        if notes_text:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = notes_text

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ── PDF generator ───────────────────────────────────────────────────────

def generate_pdf(params: dict) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm, cm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    except ImportError:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    _register_cn_font(styles)

    content = params.get("content", [])
    elements = []

    for block in content:
        block_type = block.get("类型", block.get("type", "段落"))
        text = block.get("文本", block.get("text", ""))
        bold = block.get("加粗", block.get("bold", False))
        align = block.get("对齐", block.get("align", "left"))
        level = block.get("级别", block.get("level", 1))

        align_map = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
        para_align = align_map.get(align, TA_LEFT)

        if block_type == "标题":
            font_size = {1: 22, 2: 18, 3: 16, 4: 14}.get(level, 18)
            style = ParagraphStyle(f"heading{level}", parent=styles["Heading1"],
                                   fontSize=font_size, alignment=para_align,
                                   spaceAfter=12, spaceBefore=18,
                                   fontName="STSong" if bold else "STSong",
                                   textColor=HexColor("#2395bc"))
            elements.append(Paragraph(text, style))
            elements.append(Spacer(1, 6))

        elif block_type == "段落":
            font_name = "STSong-Bold" if bold else "STSong"
            style = ParagraphStyle("body", parent=styles["Normal"],
                                   fontSize=12, alignment=para_align,
                                   spaceAfter=8, leading=20,
                                   fontName=font_name)
            elements.append(Paragraph(text, style))

        elif block_type in ("表格", "table"):
            header = block.get("表头", block.get("header", []))
            rows = block.get("行", block.get("rows", []))
            if header:
                rows = [header] + rows
            if rows:
                col_count = max(len(r) for r in rows) if rows else 1
                table_data = [[str(c) if c else "" for c in r] + [""] * (col_count - len(r)) for r in rows]
                table = Table(table_data, colWidths=[4.5*cm] * col_count)
                header_color = HexColor("#2395bc")
                style_cmds = [
                    ("FONTNAME", (0, 0), (-1, 0), "STSong-Bold"),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
                    ("BACKGROUND", (0, 0), (-1, 0), header_color),
                    ("FONTNAME", (0, 1), (-1, -1), "STSong"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
                table.setStyle(TableStyle(style_cmds))
                elements.append(table)
                elements.append(Spacer(1, 12))

        elif block_type == "分页":
            elements.append(PageBreak())

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def _register_cn_font(styles):
    """Register Chinese-supporting fonts for reportlab."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os

        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STSong.ttf",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
        ]
        registered = False
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont("STSong", fp))
                    pdfmetrics.registerFont(TTFont("STSong-Bold", fp))
                    registered = True
                    break
                except Exception:
                    continue

        if not registered:
            logger.warning("No Chinese font found for PDF, using Helvetica (Chinese text may be blank)")
    except Exception as exc:
        logger.warning("Font registration failed: %s", exc)
