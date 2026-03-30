#!/usr/bin/env python3
"""
Avrora Gift Certificate Barcode Generator

Usage:
  python generate.py              — generate all certificates
  python generate.py --calibrate  — generate a single test PDF to check barcode position
"""

import os
import sys
from pathlib import Path
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import code128


# ── Configuration ─────────────────────────────────────────────────────────────

TEMPLATE_PATH     = "template.pdf"
CERTIFICATES_FILE = "certificates.txt"
OUTPUT_DIR        = "output"

# Position of barcode center on the page.
# NOTE: axes are swapped due to 90° rotation:
#   BARCODE_X — менше = вище,    більше = нижче
#   BARCODE_Y — менше = правіше, більше = лівіше
BARCODE_X = 16 * mm
BARCODE_Y = 47 * mm

# Size of barcode
BAR_HEIGHT = 18 * mm   # висота смужок штрихкоду
BAR_WIDTH  = 0.40 * mm  # товщина тонкої смужки (більше = довший штрихкод)

# Gap between bars and the number text below
TEXT_GAP   = 2 * mm
FONT_SIZE  = 8  # points

# ─────────────────────────────────────────────────────────────────────────────


def create_barcode_overlay(
    number: str,
    page_width: float,
    page_height: float,
    debug: bool = False,
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    bc = code128.Code128(
        number,
        barWidth=BAR_WIDTH,
        barHeight=BAR_HEIGHT,
        humanReadable=False,  # text is drawn manually below with a gap
        quiet=False,
    )
    bw = bc.width  # total barcode length (before rotation)

    tx = BARCODE_X + BAR_HEIGHT / 2
    ty = BARCODE_Y - bw / 2

    c.saveState()
    c.translate(tx, ty)
    c.rotate(90)

    # Draw barcode bars
    bc.drawOn(c, 0, 0)

    # Draw number text below bars with a small gap
    c.setFont("Helvetica", FONT_SIZE)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(bw / 2, -TEXT_GAP, number)

    c.restoreState()

    c.save()
    buf.seek(0)
    return buf.read()


def overlay_barcode(template_page, number: str, debug: bool = False):
    page_width  = float(template_page.mediabox.width)
    page_height = float(template_page.mediabox.height)

    overlay_bytes = create_barcode_overlay(number, page_width, page_height, debug=debug)
    overlay_page  = PdfReader(BytesIO(overlay_bytes)).pages[0]

    writer = PdfWriter()
    writer.add_page(template_page)
    writer.pages[0].merge_page(overlay_page)

    out_buf = BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return PdfReader(out_buf).pages[0]


def calibrate():
    if not Path(TEMPLATE_PATH).exists():
        sys.exit(f"ERROR: '{TEMPLATE_PATH}' not found.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    reader        = PdfReader(TEMPLATE_PATH)
    template_page = reader.pages[0]

    merged = overlay_barcode(template_page, "5550000032822", debug=True)

    writer = PdfWriter()
    writer.add_page(merged)
    out_path = Path(OUTPUT_DIR) / "CALIBRATE.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)

    pw = float(template_page.mediabox.width)
    ph = float(template_page.mediabox.height)
    print(f"Template size  : {pw/mm:.1f} x {ph/mm:.1f} mm")
    print(f"Barcode center : X={BARCODE_X/mm:.1f} mm  Y={BARCODE_Y/mm:.1f} mm")
    print(f"Saved          : {out_path}")
    print()
    print("Open CALIBRATE.pdf — the BLUE rectangle shows the barcode area.")
    print("Adjust BARCODE_X / BARCODE_Y in generate.py, then re-run --calibrate.")


def generate_all():
    for path, label in [(TEMPLATE_PATH, "template"), (CERTIFICATES_FILE, "certificates list")]:
        if not Path(path).exists():
            sys.exit(f"ERROR: {label} file '{path}' not found.")

    with open(CERTIFICATES_FILE, encoding="utf-8") as f:
        numbers = [line.strip() for line in f if line.strip()]

    if not numbers:
        sys.exit("ERROR: certificates.txt is empty.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    reader        = PdfReader(TEMPLATE_PATH)
    template_page = reader.pages[0]

    print(f"Generating {len(numbers)} certificate(s)...\n")

    for i, number in enumerate(numbers, 1):
        merged = overlay_barcode(template_page, number)

        writer = PdfWriter()
        writer.add_page(merged)
        out_path = Path(OUTPUT_DIR) / f"{number}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)

        print(f"  [{i:>4}/{len(numbers)}]  {number}  →  {out_path}")

    print(f"\nDone! {len(numbers)} PDF(s) saved to '{OUTPUT_DIR}/'")


if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        calibrate()
    else:
        generate_all()
