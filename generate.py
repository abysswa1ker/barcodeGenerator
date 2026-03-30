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


# ── Configuration — adjust values to fit the white rectangle ─────────────────

TEMPLATE_PATH     = "template.pdf"
CERTIFICATES_FILE = "certificates.txt"
OUTPUT_DIR        = "output"

# BARCODE_X / BARCODE_Y — center of the barcode on the page.
# X=0, Y=0 is the BOTTOM-LEFT corner of the page.
# Increase X → moves right   |   Increase Y → moves up
BARCODE_X = 42 * mm   # horizontal center of barcode

# The barcode is rotated 90°, so BARCODE_Y is the vertical center.
BARCODE_Y = 40 * mm   # vertical center of barcode

# Visual width of the barcode (after rotation) — fits inside the white rectangle
BARCODE_VISUAL_WIDTH  = 38 * mm  # how wide the barcode looks on the card
BARCODE_VISUAL_HEIGHT = 16 * mm  # how tall the barcode looks on the card

# ─────────────────────────────────────────────────────────────────────────────


def _make_barcode(number: str):
    """Create a Code128 barcode object sized to fit the visual dimensions."""
    # After 90° rotation: bar_height → visual width, bw → visual height
    # So bar_height = BARCODE_VISUAL_WIDTH, and we derive barWidth from VISUAL_HEIGHT
    bar_height = BARCODE_VISUAL_WIDTH

    # Estimate number of bar units for a 13-digit Code128C barcode (~123 units)
    bar_units = 123
    bar_width = BARCODE_VISUAL_HEIGHT / bar_units

    return code128.Code128(
        number,
        barWidth=bar_width,
        barHeight=bar_height,
        humanReadable=True,
        fontSize=7,
        quiet=False,
    )


def create_barcode_overlay(
    number: str,
    page_width: float,
    page_height: float,
    debug: bool = False,
) -> bytes:
    """Return bytes of a transparent PDF overlay containing the rotated barcode."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    barcode = _make_barcode(number)
    bw = barcode.width  # actual width in raw (pre-rotation) units

    # Rotate -90° (clockwise) so bars become horizontal.
    # After rotation the barcode occupies:
    #   visual width  = bar_height = BARCODE_VISUAL_WIDTH
    #   visual height = bw         ≈ BARCODE_VISUAL_HEIGHT
    # We position it so its center lands on (BARCODE_X, BARCODE_Y).
    tx = BARCODE_X - BARCODE_VISUAL_WIDTH / 2   # left edge after rotation
    ty = BARCODE_Y + bw / 2                      # top edge after rotation

    if debug:
        # Red cross-hair at anchor point
        c.setStrokeColorRGB(1, 0, 0)
        c.setLineWidth(0.5)
        c.line(BARCODE_X - 5 * mm, BARCODE_Y, BARCODE_X + 5 * mm, BARCODE_Y)
        c.line(BARCODE_X, BARCODE_Y - 5 * mm, BARCODE_X, BARCODE_Y + 5 * mm)
        # Blue bounding box showing where the barcode will appear
        c.setStrokeColorRGB(0, 0.4, 1)
        c.setLineWidth(0.4)
        c.rect(
            BARCODE_X - BARCODE_VISUAL_WIDTH / 2,
            BARCODE_Y - bw / 2,
            BARCODE_VISUAL_WIDTH,
            bw,
        )

    c.saveState()
    c.translate(tx, ty)
    c.rotate(-90)
    barcode.drawOn(c, 0, 0)
    c.restoreState()

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
    print(f"Template size  : {pw/mm:.1f} x {ph/mm:.1f} mm")
    print(f"Barcode center : X={BARCODE_X/mm:.1f} mm  Y={BARCODE_Y/mm:.1f} mm")
    print(f"Barcode size   : {BARCODE_VISUAL_WIDTH/mm:.1f} x {BARCODE_VISUAL_HEIGHT/mm:.1f} mm")
    print(f"Saved          : {out_path}")
    print()
    print("Open CALIBRATE.pdf and check the blue rectangle — that is the barcode area.")
    print("Adjust BARCODE_X / BARCODE_Y / BARCODE_VISUAL_WIDTH / BARCODE_VISUAL_HEIGHT")
    print("in generate.py, then re-run --calibrate.")


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
