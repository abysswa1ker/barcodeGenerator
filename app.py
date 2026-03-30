#!/usr/bin/env python3
"""
Avrora Gift Certificate Barcode Generator — UI
"""

import os
import threading
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pypdfium2 as pdfium
from PIL import Image, ImageTk
from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm

from barcode_core import (
    generate_certificates,
    merge_barcode_on_page,
    read_certificate_numbers,
)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

PREVIEW_W = 630
PREVIEW_H = 380

# Physical card size in mm (used to convert intuitive X/Y to internal coords)
CARD_W = 94.0
CARD_H = 54.0

# User-facing defaults (X = horizontal from left, Y = vertical from bottom)
UI_DEFAULTS = {
    "x":          47.0,   # мм від лівого краю
    "y":          38.5,   # мм від нижнього краю
    "bar_height": 18.0,   # мм
    "bar_width":   0.40,  # мм
    "text_gap":    7.0,   # pt
    "font_size":   8.0,   # pt
}

SAMPLE_NUMBER = "5550000032822"


def ui_to_internal(ui_x, ui_y, bar_height, bar_width, text_gap, font_size):
    """Convert intuitive UI coords → internal raw PDF coords."""
    return {
        "barcode_x": (CARD_H - ui_y) * mm,   # Y from bottom → raw X
        "barcode_y": (CARD_W - ui_x) * mm,   # X from left   → raw Y (inverted)
        "bar_height": bar_height * mm,
        "bar_width":  bar_width  * mm,
        "text_gap":   text_gap,
        "font_size":  int(font_size),
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Avrora — Barcode Generator")
        self.geometry("1060x600")
        self.resizable(False, False)

        self._template_path     = ""
        self._certificates_path = ""
        self._output_dir        = str(Path.home() / "Desktop" / "certificates_output")
        self._preview_job       = None

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Left panel
        left = ctk.CTkFrame(self, width=385)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)

        # Files section
        ctk.CTkLabel(left, text="Файли",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self._template_lbl = self._file_row(left, "Шаблон PDF:",       self._pick_template)
        self._certs_lbl    = self._file_row(left, "Сертифікати:",       self._pick_certs)
        self._output_lbl   = self._file_row(left, "Папка виводу:",      self._pick_output,
                                            default=self._shorten(self._output_dir))

        self._divider(left)

        # Barcode parameters section
        ctk.CTkLabel(left, text="Параметри штрихкоду",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 6))

        self._x_var  = self._slider_row(left, "X — горизонталь (мм)",
                                        UI_DEFAULTS["x"],  0, CARD_W, decimals=1)
        self._y_var  = self._slider_row(left, "Y — вертикаль (мм)",
                                        UI_DEFAULTS["y"],  0, CARD_H, decimals=1)
        self._bh_var = self._slider_row(left, "Висота смужок (мм)",
                                        UI_DEFAULTS["bar_height"], 5, 40, decimals=1)
        self._bw_var = self._slider_row(left, "Ширина смужки (мм)",
                                        UI_DEFAULTS["bar_width"], 0.10, 1.00, decimals=2)
        self._tg_var = self._slider_row(left, "Відступ тексту (pt)",
                                        UI_DEFAULTS["text_gap"], 0, 30, decimals=0)
        self._fs_var = self._slider_row(left, "Розмір шрифту (pt)",
                                        UI_DEFAULTS["font_size"], 6, 18, decimals=0)

        for var in (self._x_var, self._y_var, self._bh_var,
                    self._bw_var, self._tg_var, self._fs_var):
            var.trace_add("write", self._schedule_preview)

        self._divider(left)

        # Progress + Generate
        self._progress = ctk.CTkProgressBar(left)
        self._progress.pack(fill="x", padx=10, pady=(0, 4))
        self._progress.set(0)

        self._status = ctk.CTkLabel(left, text="", text_color="gray",
                                    font=ctk.CTkFont(size=11))
        self._status.pack(anchor="w", padx=10)

        self._gen_btn = ctk.CTkButton(
            left, text="Генерувати сертифікати",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42, command=self._start_generation,
        )
        self._gen_btn.pack(fill="x", padx=10, pady=(6, 4))

        # Right panel — preview
        right = ctk.CTkFrame(self)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)

        ctk.CTkLabel(right, text="Прев'ю",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self._preview_lbl = ctk.CTkLabel(
            right, text="Виберіть PDF шаблон\nщоб побачити прев'ю", text_color="gray"
        )
        self._preview_lbl.pack(expand=True)

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _divider(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color="#CCCCCC").pack(fill="x", padx=10, pady=8)

    def _file_row(self, parent, label_text, command, default="Не вибрано"):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text=label_text, width=115, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        lbl = ctk.CTkLabel(row, text=default, anchor="w",
                           text_color="gray", font=ctk.CTkFont(size=11))
        lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Вибрати", width=76, height=26,
                      command=command).pack(side="right")
        return lbl

    def _slider_row(self, parent, label, default, from_, to, decimals=1):
        var = ctk.DoubleVar(value=default)
        fmt = f"{{:.{decimals}f}}"

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 2))

        header = ctk.CTkFrame(row, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=label, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        val_lbl = ctk.CTkLabel(header, text=fmt.format(default),
                               anchor="e", width=48, font=ctk.CTkFont(size=11))
        val_lbl.pack(side="right")

        ctk.CTkSlider(row, variable=var, from_=from_, to=to).pack(fill="x")

        var.trace_add("write", lambda *_: val_lbl.configure(text=fmt.format(var.get())))
        return var

    @staticmethod
    def _shorten(path, n=36):
        return path if len(path) <= n else "…" + path[-(n - 1):]

    # ── File pickers ──────────────────────────────────────────────────────────

    def _pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self._template_path = path
            self._template_lbl.configure(text=Path(path).name, text_color="black")
            self._refresh_preview()

    def _pick_certs(self):
        path = filedialog.askopenfilename(filetypes=[("Excel / Text", "*.xlsx *.txt")])
        if path:
            self._certificates_path = path
            self._certs_lbl.configure(text=Path(path).name, text_color="black")

    def _pick_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_dir = path
            self._output_lbl.configure(text=self._shorten(path), text_color="black")

    # ── Preview ───────────────────────────────────────────────────────────────

    def _schedule_preview(self, *_):
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(400, self._refresh_preview)

    def _refresh_preview(self):
        if not self._template_path:
            return
        params = self._get_params()
        threading.Thread(target=self._render_preview, args=(params,), daemon=True).start()

    def _render_preview(self, params):
        try:
            reader        = PdfReader(self._template_path)
            template_page = reader.pages[0]
            merged        = merge_barcode_on_page(template_page, SAMPLE_NUMBER, params)

            writer = PdfWriter()
            writer.add_page(merged)
            buf = BytesIO()
            writer.write(buf)
            buf.seek(0)

            pdf    = pdfium.PdfDocument(buf.read())
            page   = pdf[0]
            scale  = PREVIEW_W / page.get_width()
            bitmap = page.render(scale=scale)
            img    = bitmap.to_pil().convert("RGB")
            img.thumbnail((PREVIEW_W, PREVIEW_H), Image.LANCZOS)

            self.after(0, lambda: self._show_preview(img))
        except Exception as e:
            self.after(0, lambda: self._preview_lbl.configure(image=None,
                                                               text=f"Помилка:\n{e}"))

    def _show_preview(self, pil_img):
        tk_img = ImageTk.PhotoImage(pil_img)
        self._preview_lbl.configure(image=tk_img, text="")
        self._preview_lbl._image = tk_img

    # ── Params ────────────────────────────────────────────────────────────────

    def _get_params(self):
        return ui_to_internal(
            ui_x       = self._x_var.get(),
            ui_y       = self._y_var.get(),
            bar_height = self._bh_var.get(),
            bar_width  = self._bw_var.get(),
            text_gap   = self._tg_var.get(),
            font_size  = self._fs_var.get(),
        )

    # ── Generation ────────────────────────────────────────────────────────────

    def _start_generation(self):
        if not self._template_path:
            messagebox.showwarning("Увага", "Виберіть PDF шаблон.")
            return
        if not self._certificates_path:
            messagebox.showwarning("Увага", "Виберіть файл сертифікатів.")
            return

        numbers = read_certificate_numbers(self._certificates_path)
        if not numbers:
            messagebox.showerror("Помилка", "Файл сертифікатів порожній.")
            return

        params = self._get_params()
        self._gen_btn.configure(state="disabled")
        self._progress.set(0)
        self._status.configure(text=f"Генерація 0 / {len(numbers)}…")

        def run():
            def on_progress(cur, total):
                self.after(0, lambda: (
                    self._progress.set(cur / total),
                    self._status.configure(text=f"Генерація {cur} / {total}…"),
                ))
            generate_certificates(
                self._template_path, numbers, self._output_dir, params, on_progress
            )
            self.after(0, lambda: self._done(len(numbers)))

        threading.Thread(target=run, daemon=True).start()

    def _done(self, total):
        self._gen_btn.configure(state="normal")
        self._status.configure(text=f"Готово! {total} PDF збережено.")
        messagebox.showinfo("Готово", f"{total} сертифікатів збережено у:\n{self._output_dir}")
        os.startfile(self._output_dir)


if __name__ == "__main__":
    app = App()
    app.mainloop()
