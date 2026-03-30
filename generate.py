#!/usr/bin/env python3
"""
Avrora Gift Certificate Barcode Generator — CLI

Usage:
  python generate.py              — generate all certificates
  python generate.py --calibrate  — generate a single test PDF to check barcode position
"""

import os
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm

from barcode_core import (
    create_barcode_overlay,
    generate_certificates,
    read_certificate_numbers,
)


# ── Configuration ─────────────────────────────────────────────────────────────

TEMPLATE_PATH     = "template.pdf"
CERTIFICATES_FILE = "certificates.xlsx"
OUTPUT_DIR        = "output"

# Position of barcode center on the page.
# NOTE: axes are swapped due to 90° rotation:
#   BARCODE_X — менше = вище,    більше = нижче
#   BARCODE_Y — менше = правіше, більше = лівіше
BARCODE_X = 15.5 * mm
BARCODE_Y = 47 * mm

# Size of barcode
BAR_HEIGHT = 18 * mm    # висота смужок штрихкоду
BAR_WIDTH  = 0.40 * mm  # товщина тонкої смужки (більше = довший штрихкод)

# Gap between bars and the number text below
TEXT_GAP  = 7
FONT_SIZE = 8  # points

# ─────────────────────────────────────────────────────────────────────────────

PARAMS = {
    "barcode_x": BARCODE_X,
    "barcode_y": BARCODE_Y,
    "bar_height": BAR_HEIGHT,
    "bar_width":  BAR_WIDTH,
    "text_gap":   TEXT_GAP,
    "font_size":  FONT_SIZE,
}


def calibrate():
    if not Path(TEMPLATE_PATH).exists():
        sys.exit(f"ERROR: '{TEMPLATE_PATH}' not found.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    reader        = PdfReader(TEMPLATE_PATH)
    template_page = reader.pages[0]
    page_width    = float(template_page.mediabox.width)
    page_height   = float(template_page.mediabox.height)

    overlay_bytes = create_barcode_overlay(
        "5550000032822", page_width, page_height, **PARAMS
    )
    overlay_page = PdfReader(BytesIO(overlay_bytes)).pages[0]

    writer = PdfWriter()
    writer.add_page(template_page)
    writer.pages[0].merge_page(overlay_page)

    out_path = Path(OUTPUT_DIR) / "CALIBRATE.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)

    print(f"Template size  : {page_width/mm:.1f} x {page_height/mm:.1f} mm")
    print(f"Barcode center : X={BARCODE_X/mm:.1f} mm  Y={BARCODE_Y/mm:.1f} mm")
    print(f"Saved          : {out_path}")


def main():
    for path, label in [(TEMPLATE_PATH, "template"), (CERTIFICATES_FILE, "certificates list")]:
        if not Path(path).exists():
            sys.exit(f"ERROR: {label} file '{path}' not found.")

    numbers = read_certificate_numbers(CERTIFICATES_FILE)
    if not numbers:
        sys.exit("ERROR: no certificate numbers found.")

    print(f"Generating {len(numbers)} certificate(s)...\n")

    def progress(current, total):
        print(f"  [{current:>4}/{total}]  done")

    generate_certificates(TEMPLATE_PATH, numbers, OUTPUT_DIR, PARAMS, progress)
    print(f"\nDone! PDFs saved to '{OUTPUT_DIR}/'")


if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        calibrate()
    else:
        main()
