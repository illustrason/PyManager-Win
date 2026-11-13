"""Couleurs, polices et styles ttk de l'interface (thème sombre)."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#15171c"
PANEL = "#1c1f26"
PANEL2 = "#252932"
BORDER = "#323845"
TEXT = "#e7e9ee"
MUTED = "#8b92a3"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#6aa0ff"
SELECT = "#2a3552"
DANGER = "#ff6b6b"
OK = "#3ecf8e"
WARN = "#f5b94a"
CONSOLE_BG = "#101216"

SCALE = 1.0
F_UI = F_BOLD = F_SMALL = F_H1 = F_H2 = F_MONO = F_MONO_BOLD = ("TkDefaultFont", 10)


def S(n: float) -> int:
    """Taille en pixels adaptée à l'écran (écrans à forte densité)."""
    return max(1, int(round(n * SCALE)))


def _pick(candidates, available, fallback):
    for name in candidates:
        if name in available:
            return name
    return fallback


def init(root: tk.Tk) -> None:
    global SCALE, F_UI, F_BOLD, F_SMALL, F_H1, F_H2, F_MONO, F_MONO_BOLD
    try:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        SCALE = 1.0
    families = set(tkfont.families(root))
    ui = _pick(("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Arial"), families, "TkDefaultFont")
    mono = _pick(("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"), families, "TkFixedFont")
    F_UI = (ui, 10)
    F_BOLD = (ui, 10, "bold")
    F_SMALL = (ui, 9)
    F_H1 = (ui, 16, "bold")
    F_H2 = (ui, 11, "bold")
    F_MONO = (mono, 10)
    F_MONO_BOLD = (mono, 10, "bold")
    _style(root)


def _style(root: tk.Tk) -> None:
    st = ttk.Style(root)
    st.theme_use("clam")

    # -- barres de défilement fines, sans flèches
    for orient, layout in (("Vertical", "ns"), ("Horizontal", "ew")):
        name = f"Dark.{orient}.TScrollbar"
        st.layout(name, [(f"{orient}.Scrollbar.trough", {
            "sticky": layout,
            "children": [(f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
        })])
        st.configure(name, troughcolor=PANEL, background=BORDER, bordercolor=PANEL,
                     lightcolor=BORDER, darkcolor=BORDER, gripcount=0, width=S(10), relief="flat")
        st.map(name, background=[("pressed", MUTED), ("active", MUTED)])

    # -- arbre des scripts (sans pictogrammes +/-, la flèche est dans le texte)
    st.layout("Side.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.layout("Side.Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Treeitem.text", {"side": "left", "sticky": ""})]})])
    st.configure("Side.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                 borderwidth=0, rowheight=S(30), font=F_UI, indent=S(12), relief="flat")
    st.map("Side.Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])

    # -- tableau de la vue Santé
    st.layout("Health.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    st.configure("Health.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                 borderwidth=0, rowheight=S(28), font=F_UI, relief="flat")
    st.map("Health.Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    st.configure("Health.Treeview.Heading", background=PANEL2, foreground=MUTED, relief="flat",
                 font=F_SMALL, borderwidth=0, padding=(S(8), S(6)))
    st.map("Health.Treeview.Heading", background=[("active", PANEL2)])
