"""Fenêtre principale de PyManager."""
from __future__ import annotations

import re
import sys
import time
import tkinter as tk
import traceback
from tkinter import messagebox

from . import __version__, paths, theme as T
from .theme import S
from .widgets import FlatButton, install_wheel


def log(text: str) -> None:
    try:
        paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(paths.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()                         # on construit hors écran pour éviter tout clignotement
        self.configure(bg=T.BG)
        T.init(self)
        install_wheel(self)
        self.settings = paths.load_settings()
        self.root_dir = paths.scripts_root(self.settings)
        self._errors_shown = 0
        self.title("PyManager")
        self.minsize(S(940), S(600))
        self._apply_geometry()
        self.report_callback_exception = self._on_error

        self._build_topbar()
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x")
        self.body = tk.Frame(self, bg=T.BG)
        self.body.pack(fill="both", expand=True)

        from .scripts_view import ScriptsView
        self.views = {"scripts": ScriptsView(self.body, self), "health": None}
        self.current_view = None
        self.show("scripts")

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F5>", lambda e: self._on_f5())
        self.bind("<Control-Return>", lambda e: self._on_f5())
        self.bind("<FocusIn>", self._on_focus, add="+")
        self.deiconify()
        self.update_idletasks()
        self._dark_titlebar()

    # ------------------------------------------------------------------ construction
    def _apply_geometry(self) -> None:
        geo = str(self.settings.get("geometry") or "")
        m = re.match(r"^(\d{3,5})x(\d{3,5})", geo)
        w, h = (int(m.group(1)), int(m.group(2))) if m else (1200, 760)
        w, h = min(w, self.winfo_screenwidth()), min(h, self.winfo_screenheight() - S(80))
        x, y = (self.winfo_screenwidth() - w) // 2, max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_topbar(self) -> None:
        bar = tk.Frame(self, bg=T.PANEL, height=S(54))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="PyManager", font=T.F_H2, fg=T.TEXT, bg=T.PANEL).pack(side="left", padx=(S(20), S(26)))
        self.nav = {}
        for key, label in (("scripts", "Scripts"), ("health", "Santé")):
            b = tk.Label(bar, text=label, font=T.F_BOLD, fg=T.MUTED, bg=T.PANEL, cursor="hand2", padx=S(14))
            b.pack(side="left", fill="y")
            b.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.nav[key] = b
        FlatButton(bar, "Actualiser", lambda: self.views["scripts"].refresh(force=True), padx=12, pady=5).pack(
            side="right", padx=(S(8), S(18)))
        FlatButton(bar, "Dossier des scripts", self._open_scripts_dir, padx=12, pady=5).pack(side="right")

    def _dark_titlebar(self) -> None:
        if not paths.IS_WINDOWS:
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):                # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+ / ancien)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:  # noqa: BLE001 - purement esthétique
            pass

    # ------------------------------------------------------------------ navigation
    def show(self, key: str) -> None:
        if self.views.get(key) is None and key == "health":
            from .health_view import HealthView
            self.views["health"] = HealthView(self.body, self)
        if self.current_view:
            self.views[self.current_view].pack_forget()
        self.current_view = key
        view = self.views[key]
        view.pack(fill="both", expand=True)
        for k, label in self.nav.items():
            label.configure(fg=T.TEXT if k == key else T.MUTED)
        if hasattr(view, "on_show"):
            view.on_show()

    def _on_f5(self) -> None:
        if self.current_view == "scripts":
            self.views["scripts"].run_current()

    def _on_focus(self, event) -> None:
        if event.widget is self and self.current_view == "scripts":
            self.views["scripts"].on_focus()

    def _open_scripts_dir(self) -> None:
        from .scripts_view import open_path
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            open_path(str(self.root_dir))
        except OSError as exc:
            messagebox.showerror("Dossier des scripts", str(exc), parent=self)

    # ------------------------------------------------------------------ fermeture / erreurs
    def close(self) -> None:
        scripts = self.views["scripts"]
        if scripts.console.any_running():
            if not messagebox.askyesno("Quitter PyManager",
                                       "Des scripts sont encore en cours d'exécution.\nLes arrêter et quitter ?", parent=self):
                return
        self.quit_now()

    def quit_now(self) -> None:
        try:
            self.views["scripts"].shutdown()
            self.settings["geometry"] = f"{self.winfo_width()}x{self.winfo_height()}"
            paths.save_settings(self.settings)
        finally:
            self.destroy()

    def _on_error(self, exc, val, tb) -> None:
        text = "".join(traceback.format_exception(exc, val, tb))
        log(text)
        if self._errors_shown < 3:
            self._errors_shown += 1
            messagebox.showerror("Erreur inattendue", f"{val}\n\nDétails enregistrés dans {paths.LOG_FILE}", parent=self)


def _enable_dpi_awareness() -> None:
    if paths.IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:  # noqa: BLE001
                pass


def run() -> int:
    _enable_dpi_awareness()
    try:
        App().mainloop()
        return 0
    except Exception:  # noqa: BLE001
        text = traceback.format_exc()
        log(text)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("PyManager", f"PyManager n'a pas pu démarrer.\n\n{text[-900:]}\n\nJournal : {paths.LOG_FILE}")
        except Exception:  # noqa: BLE001
            print(text, file=sys.stderr)
        return 1
