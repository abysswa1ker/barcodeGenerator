"""
Core barcode generation logic.
Used by both generate.py (CLI) and app.py (UI).
"""

from io import BytesIO
from pathlib import Path

import openpyxl
from pypdf import PdfReader, PdfWriter
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def read_certificate_numbers(filepath: str) -> list[str]:
    ext = Path(filepath).suffix.lower()
    if ext == ".xlsx":
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        numbers = [str(row[0].value).strip() for row in ws.iter_rows() if row[0].value is not None]
        wb.close()
    else:
        with open(filepath, encoding="utf-8") as f:
            numbers = [line.strip() for line in f if line.strip()]
    return numbers


def create_barcode_overlay(
    number: str,
    page_width: float,
    page_height: float,
    barcode_x: float,
    barcode_y: float,
    bar_height: float,
    bar_width: float,
    text_gap: float,
    font_size: int,
) -> bytes:
    """Return bytes of a PDF overlay with the barcode placed on a blank page."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    bc = code128.Code128(
        number,
        barWidth=bar_width,
        barHeight=bar_height,
        humanReadable=False,
        quiet=False,
    )
    bw = bc.width

    tx = barcode_x + bar_height / 2
    ty = barcode_y - bw / 2

    c.saveState()
    c.translate(tx, ty)
    c.rotate(90)
    bc.drawOn(c, 0, 0)
    c.setFont("Helvetica", font_size)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(bw / 2, -text_gap, number)
    c.restoreState()

    c.save()
    buf.seek(0)
    return buf.read()


def merge_barcode_on_page(template_page, number: str, params: dict):
    """Overlay barcode onto template_page and return the merged page."""
    page_width  = float(template_page.mediabox.width)
    page_height = float(template_page.mediabox.height)

    overlay_bytes = create_barcode_overlay(
        number, page_width, page_height,
        barcode_x=params["barcode_x"],
        barcode_y=params["barcode_y"],
        bar_height=params["bar_height"],
        bar_width=params["bar_width"],
        text_gap=params["text_gap"],
        font_size=params["font_size"],
    )
    overlay_page = PdfReader(BytesIO(overlay_bytes)).pages[0]

    writer = PdfWriter()
    writer.add_page(template_page)
    writer.pages[0].merge_page(overlay_page)

    out_buf = BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return PdfReader(out_buf).pages[0]


def generate_certificates(
    template_path: str,
    cert_numbers: list[str],
    output_dir: str,
    params: dict,
    progress_callback=None,
) -> list[str]:
    """
    Generate one PDF per certificate number.
    progress_callback(current, total) is called after each file if provided.
    Returns list of output file paths.
    """
    from pathlib import Path
    import os

    os.makedirs(output_dir, exist_ok=True)
    reader        = PdfReader(template_path)
    template_page = reader.pages[0]
    output_paths  = []

    for i, number in enumerate(cert_numbers, 1):
        merged   = merge_barcode_on_page(template_page, number, params)
        writer   = PdfWriter()
        writer.add_page(merged)
        out_path = Path(output_dir) / f"{number}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)
        output_paths.append(str(out_path))
        if progress_callback:
            progress_callback(i, len(cert_numbers))

    return output_paths
