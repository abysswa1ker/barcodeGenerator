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


# ── Configuration — adjust BARCODE_X / BARCODE_Y to fit the white rectangle ──

TEMPLATE_PATH    = "template.pdf"
CERTIFICATES_FILE = "certificates.txt"
OUTPUT_DIR       = "output"

# Position of the barcode on the page.
# X=0, Y=0 is the BOTTOM-LEFT corner of the page.
# Increase X  → moves barcode to the right
# Increase Y  → moves barcode up
BARCODE_X      = 42 * mm   # horizontal center of barcode
BARCODE_Y      = 22 * mm   # bottom edge of barcode (from bottom of page)
BARCODE_HEIGHT = 16 * mm   # height of the bars (without the number text)
BAR_WIDTH      = 0.35 * mm # width of the thinnest bar (controls overall barcode width)

# ─────────────────────────────────────────────────────────────────────────────


def create_barcode_overlay(
    number: str,
    page_width: float,
    page_height: float,
    debug: bool = False,
) -> bytes:
    """Return bytes of a transparent PDF overlay containing the barcode."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    barcode = code128.Code128(
        number,
        barWidth=BAR_WIDTH,
        barHeight=BARCODE_HEIGHT,
        humanReadable=True,
        fontSize=8,
        quiet=False,
    )

    # Center the barcode horizontally around BARCODE_X
    bw = barcode.width
    x = BARCODE_X - bw / 2

    if debug:
        # Draw a red cross-hair so you can see the anchor point
        c.setStrokeColorRGB(1, 0, 0)
        c.setLineWidth(0.5)
        c.line(BARCODE_X - 5 * mm, BARCODE_Y, BARCODE_X + 5 * mm, BARCODE_Y)
        c.line(BARCODE_X, BARCODE_Y - 5 * mm, BARCODE_X, BARCODE_Y + 5 * mm)
        # Draw the bounding box of the barcode
        c.setStrokeColorRGB(0, 0.5, 1)
        c.rect(x, BARCODE_Y, bw, BARCODE_HEIGHT + 3 * mm)

    barcode.drawOn(c, x, BARCODE_Y)
    c.save()
    buf.seek(0)
    return buf.read()


def overlay_barcode(template_page, number: str, debug: bool = False):
    """Merge a barcode overlay onto a copy of template_page and return new page."""
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
    """Generate output/CALIBRATE.pdf with a single test barcode + visual guides."""
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
    print(f"Template size : {pw/mm:.1f} x {ph/mm:.1f} mm")
    print(f"Barcode anchor: X={BARCODE_X/mm:.1f} mm  Y={BARCODE_Y/mm:.1f} mm")
    print(f"Saved          : {out_path}")
    print()
    print("Open CALIBRATE.pdf and check the barcode position.")
    print("Adjust BARCODE_X and BARCODE_Y in generate.py, then re-run --calibrate.")


def generate_all():
    """Read certificates.txt and produce one PDF per certificate number."""
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
