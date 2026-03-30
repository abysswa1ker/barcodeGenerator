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

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

PREVIEW_W = 630   # preview panel width in pixels
PREVIEW_H = 370   # preview panel height in pixels

DEFAULTS = {
    "barcode_x":  15.5,
    "barcode_y":  47.0,
    "bar_height": 18.0,
    "bar_width":   0.40,
    "text_gap":    7,
    "font_size":   8,
}

SAMPLE_NUMBER = "5550000032822"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Avrora — Barcode Generator")
        self.geometry("1050x580")
        self.resizable(False, False)

        self._template_path     = ""
        self._certificates_path = ""
        self._output_dir        = str(Path.home() / "Desktop" / "certificates_output")
        self._preview_job       = None   # debounce timer id

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Left panel ─────────────────────────────────────────────────────
        left = ctk.CTkFrame(self, width=370)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)

        # Files
        ctk.CTkLabel(left, text="Файли", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self._template_label = self._file_row(left, "Шаблон PDF:",         self._pick_template)
        self._certs_label    = self._file_row(left, "Сертифікати:",         self._pick_certs)
        self._output_label   = self._file_row(left, "Папка виводу:",        self._pick_output, default=self._shorten(self._output_dir))

        ctk.CTkFrame(left, height=1, fg_color="#CCCCCC").pack(fill="x", padx=10, pady=8)

        # Parameters
        ctk.CTkLabel(left, text="Параметри штрихкоду", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(0, 4))

        g = ctk.CTkFrame(left, fg_color="transparent")
        g.pack(fill="x", padx=10)

        self._x_var  = self._param_row(g, 0, "Позиція X (мм):",      DEFAULTS["barcode_x"],  "↑ менше  ↓ більше")
        self._y_var  = self._param_row(g, 1, "Позиція Y (мм):",      DEFAULTS["barcode_y"],  "→ менше  ← більше")
        self._bh_var = self._param_row(g, 2, "Висота ШК (мм):",      DEFAULTS["bar_height"])
        self._bw_var = self._param_row(g, 3, "Ширина смужки (мм):",  DEFAULTS["bar_width"])
        self._tg_var = self._param_row(g, 4, "Відступ тексту (pt):", DEFAULTS["text_gap"])
        self._fs_var = self._param_row(g, 5, "Розмір шрифту (pt):", DEFAULTS["font_size"])

        # Watch every parameter entry for changes → debounce preview
        for var in (self._x_var, self._y_var, self._bh_var, self._bw_var, self._tg_var, self._fs_var):
            var.trace_add("write", self._schedule_preview)

        ctk.CTkFrame(left, height=1, fg_color="#CCCCCC").pack(fill="x", padx=10, pady=8)

        # Progress + Generate
        self._progress = ctk.CTkProgressBar(left)
        self._progress.pack(fill="x", padx=10, pady=(0, 4))
        self._progress.set(0)

        self._status = ctk.CTkLabel(left, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self._status.pack(anchor="w", padx=10)

        self._gen_btn = ctk.CTkButton(
            left,
            text="Генерувати сертифікати",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            command=self._start_generation,
        )
        self._gen_btn.pack(fill="x", padx=10, pady=(8, 4))

        # ── Right panel — preview ──────────────────────────────────────────
        right = ctk.CTkFrame(self)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)

        ctk.CTkLabel(right, text="Прев'ю", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self._preview_label = ctk.CTkLabel(right, text="Виберіть PDF шаблон\nщоб побачити прев'ю", text_color="gray")
        self._preview_label.pack(expand=True)

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _file_row(self, parent, label_text, command, default="Не вибрано"):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row, text=label_text, width=120, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        lbl = ctk.CTkLabel(row, text=default, anchor="w", text_color="gray",
                           font=ctk.CTkFont(size=11))
        lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Вибрати", width=76, height=26,
                      command=command).pack(side="right")
        return lbl

    def _param_row(self, grid, row, label, default, hint=""):
        ctk.CTkLabel(grid, text=label, anchor="w",
                     font=ctk.CTkFont(size=11)).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
        var = ctk.StringVar(value=str(default))
        ctk.CTkEntry(grid, textvariable=var, width=72,
                     height=28).grid(row=row, column=1, sticky="w", pady=2)
        if hint:
            ctk.CTkLabel(grid, text=hint, text_color="gray",
                         font=ctk.CTkFont(size=10)).grid(row=row, column=2, sticky="w", padx=8)
        return var

    @staticmethod
    def _shorten(path, max_len=35):
        return path if len(path) <= max_len else "…" + path[-(max_len - 1):]

    # ── File pickers ──────────────────────────────────────────────────────────

    def _pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self._template_path = path
            self._template_label.configure(text=Path(path).name, text_color="black")
            self._refresh_preview()

    def _pick_certs(self):
        path = filedialog.askopenfilename(filetypes=[("Excel / Text", "*.xlsx *.txt")])
        if path:
            self._certificates_path = path
            self._certs_label.configure(text=Path(path).name, text_color="black")

    def _pick_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_dir = path
            self._output_label.configure(text=self._shorten(path), text_color="black")

    # ── Preview ───────────────────────────────────────────────────────────────

    def _schedule_preview(self, *_):
        """Debounce: оновити прев'ю через 400 мс після останньої зміни параметра."""
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(400, self._refresh_preview)

    def _refresh_preview(self):
        if not self._template_path:
            return
        try:
            params = self._get_params()
        except ValueError:
            return

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

            # Fit inside preview box keeping aspect ratio
            img.thumbnail((PREVIEW_W, PREVIEW_H), Image.LANCZOS)

            self.after(0, lambda: self._show_preview(img))
        except Exception as e:
            self.after(0, lambda: self._preview_label.configure(
                image=None, text=f"Помилка прев'ю:\n{e}"
            ))

    def _show_preview(self, pil_img):
        tk_img = ImageTk.PhotoImage(pil_img)
        self._preview_label.configure(image=tk_img, text="")
        self._preview_label._image = tk_img   # prevent GC

    # ── Generation ────────────────────────────────────────────────────────────

    def _get_params(self):
        return {
            "barcode_x":  float(self._x_var.get())  * mm,
            "barcode_y":  float(self._y_var.get())  * mm,
            "bar_height": float(self._bh_var.get()) * mm,
            "bar_width":  float(self._bw_var.get()) * mm,
            "text_gap":   float(self._tg_var.get()),
            "font_size":  int(self._fs_var.get()),
        }

    def _start_generation(self):
        if not self._template_path:
            messagebox.showwarning("Увага", "Виберіть PDF шаблон.")
            return
        if not self._certificates_path:
            messagebox.showwarning("Увага", "Виберіть файл сертифікатів.")
            return
        try:
            params = self._get_params()
        except ValueError:
            messagebox.showerror("Помилка", "Перевірте числові значення параметрів.")
            return

        numbers = read_certificate_numbers(self._certificates_path)
        if not numbers:
            messagebox.showerror("Помилка", "Файл сертифікатів порожній.")
            return

        self._gen_btn.configure(state="disabled")
        self._progress.set(0)
        self._status.configure(text=f"Генерація 0 / {len(numbers)}…")

        def run():
            def on_progress(cur, total):
                self.after(0, lambda: (
                    self._progress.set(cur / total),
                    self._status.configure(text=f"Генерація {cur} / {total}…"),
                ))
            generate_certificates(self._template_path, numbers, self._output_dir, params, on_progress)
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
