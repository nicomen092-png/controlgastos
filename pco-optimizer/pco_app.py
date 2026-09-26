"""PCO OPTIMIZATION APP - interfaz.

Uso:
    PCO_Optimization_App.exe            abre la app
    PCO_Optimization_App.exe --restore  restaura la configuración original (lo usa la tarea al reiniciar)
"""

import ctypes
import os
import sys
import threading
import tkinter as tk

import optimizer as opt

BG = "#0b0f14"
CARD = "#131a23"
BORDER = "#1f2a36"
TEXT = "#eef3f8"
MUTED = "#8a98a8"
CYAN = "#0ccbf5"
CYAN_HOVER = "#3fd9fa"
GREEN = "#19e619"
ORANGE = "#f7890a"
RED = "#f01010"
FONT = "Segoe UI"


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def relaunch_as_admin():
    """En modo desarrollo (python pco_app.py) pide permisos de administrador."""
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)


class FlatButton(tk.Label):
    def __init__(self, master, text, command, bg, hover, fg="#001018", font=(FONT, 11, "bold"), **kw):
        super().__init__(master, text=text, bg=bg, fg=fg, font=font, cursor="hand2", **kw)
        self._bg, self._hover, self._command, self._enabled = bg, hover, command, True
        self.bind("<Enter>", lambda e: self._enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg if self._enabled else BORDER))
        self.bind("<Button-1>", lambda e: self._enabled and self._command())

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.config(bg=self._bg if enabled else BORDER, cursor="hand2" if enabled else "arrow")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(opt.APP_NAME)
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            self.iconbitmap(resource("icon.ico"))
        except tk.TclError:
            pass

        self.extra_vars = {t.id: tk.BooleanVar(value=t.default) for t in opt.EXTRA_TWEAKS}
        self._build()
        self._refresh_state()
        self._center(560, 700)

        # Si se reinició pero la tarea no pudo restaurar (p. ej. se movió el .exe), restaurar ahora.
        if opt.is_optimized() and opt.rebooted_since_optimize():
            self._run_async(self._do_restore, "Restaurando configuración anterior al reinicio…")

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = tk.Frame(self, bg=BG, padx=24, pady=20)
        root.pack(fill="both", expand=True)

        # Cabecera con el logo en la esquina
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x")
        self.logo_img = tk.PhotoImage(file=resource("badge_96.png"))
        tk.Label(header, image=self.logo_img, bg=BG).pack(side="left")
        titles = tk.Frame(header, bg=BG, padx=16)
        titles.pack(side="left", fill="y")
        tk.Label(titles, text="PCO", font=(FONT, 12, "bold"), fg=CYAN, bg=BG).pack(anchor="w", pady=(10, 0))
        tk.Label(titles, text="OPTIMIZATION APP", font=(FONT, 20, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(titles, text="Menos delay. Más FPS. Un solo clic.", font=(FONT, 10), fg=MUTED, bg=BG).pack(anchor="w")

        # Estado
        self.status = tk.Label(root, font=(FONT, 10, "bold"), bg=CARD, padx=12, pady=8, anchor="w")
        self.status.pack(fill="x", pady=(20, 12))

        # Botones
        self.btn_opt = FlatButton(root, "⚡  OPTIMIZAR", self.on_optimize, CYAN, CYAN_HOVER,
                                  font=(FONT, 16, "bold"), pady=14)
        self.btn_opt.pack(fill="x")
        self.btn_restore = FlatButton(root, "Restaurar ahora", self.on_restore, CARD, BORDER,
                                      fg=MUTED, font=(FONT, 10), pady=6)
        self.btn_restore.pack(fill="x", pady=(8, 0))

        # Qué incluye
        card = self._card(root, "SIEMPRE INCLUIDO")
        for t in opt.REQUIRED_TWEAKS:
            self._item(card, "✔", t.title, t.description, GREEN)

        card = self._card(root, "EXTRAS RECOMENDADOS")
        for t in opt.EXTRA_TWEAKS:
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", pady=3)
            tk.Checkbutton(row, variable=self.extra_vars[t.id], text=t.title, font=(FONT, 10, "bold"),
                           bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT,
                           selectcolor=BG, highlightthickness=0, bd=0, anchor="w").pack(fill="x")
            tk.Label(row, text=t.description, font=(FONT, 9), fg=MUTED, bg=CARD, anchor="w",
                     justify="left", wraplength=460).pack(fill="x", padx=(24, 0))

        # Registro
        self.log = tk.Label(root, text="", font=(FONT, 9), fg=MUTED, bg=BG, anchor="w", justify="left",
                            wraplength=500)
        self.log.pack(fill="x", pady=(12, 0))
        tk.Label(root, text="Todo vuelve a la normalidad al reiniciar el PC.", font=(FONT, 8),
                 fg=MUTED, bg=BG).pack(side="bottom", pady=(8, 0))

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1, padx=14, pady=10)
        outer.pack(fill="x", pady=(14, 0))
        tk.Label(outer, text=title, font=(FONT, 8, "bold"), fg=CYAN, bg=CARD).pack(anchor="w", pady=(0, 4))
        return outer

    def _item(self, parent, icon, title, desc, color):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=icon, font=(FONT, 10, "bold"), fg=color, bg=CARD, width=2).pack(side="left", anchor="n")
        box = tk.Frame(row, bg=CARD)
        box.pack(side="left", fill="x")
        tk.Label(box, text=title, font=(FONT, 10, "bold"), fg=TEXT, bg=CARD, anchor="w").pack(fill="x")
        tk.Label(box, text=desc, font=(FONT, 9), fg=MUTED, bg=CARD, anchor="w", justify="left",
                 wraplength=460).pack(fill="x")

    def _center(self, w, h):
        self.update_idletasks()
        scale = self.winfo_fpixels("1i") / 96.0  # pantallas con escala 125 %, 150 %…
        w = max(int(w * scale), self.winfo_reqwidth())
        h = max(int(h * scale), self.winfo_reqheight())
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (self.winfo_screenheight() - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------ acciones
    def _refresh_state(self):
        if opt.is_optimized():
            self.status.config(text="●  OPTIMIZADO — se revertirá al reiniciar", fg=GREEN)
            self.btn_opt.config(text="⚡  VOLVER A OPTIMIZAR")
            self.btn_restore.set_enabled(True)
        else:
            self.status.config(text="●  Sin optimizar", fg=ORANGE)
            self.btn_opt.config(text="⚡  OPTIMIZAR")
            self.btn_restore.set_enabled(False)

    def _report(self, line):
        self.after(0, lambda: self.log.config(text=line))

    def _run_async(self, fn, busy_text):
        self.btn_opt.set_enabled(False)
        self.btn_restore.set_enabled(False)
        self.status.config(text=f"●  {busy_text}", fg=CYAN)

        def worker():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                self._report(opt.log(f"Error: {e}"))
            self.after(0, self._done)

        threading.Thread(target=worker, daemon=True).start()

    def _done(self):
        self.btn_opt.set_enabled(True)
        self._refresh_state()

    def _do_optimize(self):
        extras = [k for k, v in self.extra_vars.items() if v.get()]
        ok, total = opt.optimize(extras, self._report)
        self._report(f"Listo: {ok}/{total} optimizaciones aplicadas. ¡A jugar! Se revierte al reiniciar.")

    def _do_restore(self):
        opt.restore(self._report)

    def on_optimize(self):
        self._run_async(self._do_optimize, "Optimizando…")

    def on_restore(self):
        self._run_async(self._do_restore, "Restaurando…")


def main():
    if "--restore" in sys.argv:
        # Modo silencioso: lo lanza la tarea programada al iniciar sesión tras reiniciar.
        opt.restore(report=lambda _l: None)
        return
    if not opt.is_admin():
        relaunch_as_admin()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    App().mainloop()


if __name__ == "__main__":
    main()
