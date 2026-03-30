#!/usr/bin/env python3
"""
Avrora Gift Certificate Barcode Generator — UI
"""

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
from reportlab.lib.units import mm

from barcode_core import generate_certificates, read_certificate_numbers

# ── App theme ─────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ── Default barcode parameters ────────────────────────────────────────────────
DEFAULTS = {
    "barcode_x": 15.5,   # mm
    "barcode_y": 47.0,   # mm
    "bar_height": 18.0,  # mm
    "bar_width":  0.40,  # mm
    "text_gap":   7,     # points
    "font_size":  8,     # points
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Avrora — Barcode Generator")
        self.geometry("700x600")
        self.resizable(False, False)

        self._template_path    = ""
        self._certificates_path = ""
        self._output_dir       = str(Path.home() / "Desktop" / "certificates_output")

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}

        # ── Files section ──────────────────────────────────────────────────
        files_frame = ctk.CTkFrame(self)
        files_frame.pack(fill="x", **pad)

        ctk.CTkLabel(files_frame, text="Файли", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(8, 2))

        self._template_label = self._file_row(files_frame, "Шаблон PDF:", self._pick_template)
        self._certs_label    = self._file_row(files_frame, "Сертифікати (.xlsx/.txt):", self._pick_certs)
        self._output_label   = self._file_row(files_frame, "Папка виводу:", self._pick_output, default=self._output_dir)

        # ── Barcode parameters ─────────────────────────────────────────────
        params_frame = ctk.CTkFrame(self)
        params_frame.pack(fill="x", **pad)

        ctk.CTkLabel(params_frame, text="Параметри штрихкоду", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=12, pady=(8, 2))

        grid = ctk.CTkFrame(params_frame, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 10))
        grid.columnconfigure((1, 3), weight=1)

        self._x_var  = self._param_row(grid, 0, "Позиція X (мм):",  DEFAULTS["barcode_x"], "менше = вище,  більше = нижче")
        self._y_var  = self._param_row(grid, 1, "Позиція Y (мм):",  DEFAULTS["barcode_y"], "менше = правіше, більше = лівіше")
        self._bh_var = self._param_row(grid, 2, "Висота ШК (мм):",  DEFAULTS["bar_height"])
        self._bw_var = self._param_row(grid, 3, "Ширина смужки (мм):", DEFAULTS["bar_width"])
        self._tg_var = self._param_row(grid, 4, "Відступ тексту (pt):", DEFAULTS["text_gap"])
        self._fs_var = self._param_row(grid, 5, "Розмір шрифту (pt):", DEFAULTS["font_size"])

        # ── Generate button + progress ─────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=8)

        self._progress = ctk.CTkProgressBar(bottom)
        self._progress.pack(fill="x", pady=(0, 8))
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(bottom, text="", text_color="gray")
        self._status_label.pack(anchor="w")

        self._gen_btn = ctk.CTkButton(
            bottom,
            text="Генерувати сертифікати",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            command=self._start_generation,
        )
        self._gen_btn.pack(fill="x", pady=(8, 0))

    def _file_row(self, parent, label_text, command, default="Не вибрано"):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(row, text=label_text, width=200, anchor="w").pack(side="left")
        value_label = ctk.CTkLabel(row, text=default, anchor="w", text_color="gray")
        value_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Вибрати", width=90, command=command).pack(side="right")
        return value_label

    def _param_row(self, grid, row, label, default, hint=""):
        ctk.CTkLabel(grid, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        var = ctk.StringVar(value=str(default))
        entry = ctk.CTkEntry(grid, textvariable=var, width=90)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        if hint:
            ctk.CTkLabel(grid, text=hint, text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=row, column=2, columnspan=2, sticky="w", padx=12
            )
        return var

    # ── File pickers ──────────────────────────────────────────────────────────

    def _pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self._template_path = path
            self._template_label.configure(text=Path(path).name, text_color="black")

    def _pick_certs(self):
        path = filedialog.askopenfilename(filetypes=[("Excel/Text", "*.xlsx *.txt")])
        if path:
            self._certificates_path = path
            self._certs_label.configure(text=Path(path).name, text_color="black")

    def _pick_output(self):
        path = filedialog.askdirectory()
        if path:
            self._output_dir = path
            self._output_label.configure(text=path, text_color="black")

    # ── Generation ────────────────────────────────────────────────────────────

    def _get_params(self):
        return {
            "barcode_x": float(self._x_var.get())  * mm,
            "barcode_y": float(self._y_var.get())  * mm,
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
        self._status_label.configure(text=f"Генерація 0 / {len(numbers)}...")

        def run():
            def on_progress(current, total):
                self.after(0, lambda: self._update_progress(current, total))

            generate_certificates(
                self._template_path, numbers, self._output_dir, params, on_progress
            )
            self.after(0, lambda: self._generation_done(len(numbers)))

        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, current, total):
        self._progress.set(current / total)
        self._status_label.configure(text=f"Генерація {current} / {total}...")

    def _generation_done(self, total):
        self._gen_btn.configure(state="normal")
        self._status_label.configure(text=f"Готово! {total} PDF збережено у: {self._output_dir}")
        messagebox.showinfo("Готово", f"{total} сертифікатів збережено у:\n{self._output_dir}")
        os.startfile(self._output_dir)


if __name__ == "__main__":
    app = App()
    app.mainloop()
