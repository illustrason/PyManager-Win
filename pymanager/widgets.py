"""Petits composants graphiques réutilisables (boutons plats, champs avec valeur de repli, interrupteur…)."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from . import theme as T
from .theme import S


class FlatButton(tk.Label):
    STYLES = {
        "primary": (T.ACCENT, "#ffffff", T.ACCENT_HOVER),
        "ghost": (T.PANEL2, T.TEXT, T.BORDER),
        "danger": (T.PANEL2, T.DANGER, T.BORDER),
    }

    def __init__(self, master, text, command=None, style="ghost", padx=14, pady=6):
        self._bg, self._fg, self._hover = self.STYLES[style]
        super().__init__(master, text=text, bg=self._bg, fg=self._fg, cursor="hand2",
                         font=T.F_BOLD if style == "primary" else T.F_UI,
                         padx=S(padx), pady=S(pady))
        self.command = command
        self._enabled = True
        self.bind("<Enter>", lambda e: self._enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self._enabled and self.configure(bg=self._bg))
        self.bind("<Button-1>", self._click)

    def _click(self, _event):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self.configure(bg=self._bg, fg=self._fg, cursor="hand2")
        else:
            self.configure(bg="#2b3d63" if self._bg == T.ACCENT else T.PANEL, fg="#7f8aa3" if self._bg == T.ACCENT else T.BORDER,
                           cursor="arrow")


class PlaceholderEntry(tk.Frame):
    """Champ de saisie dont la valeur de repli reste visible (en gris) tant qu'il est vide."""

    def __init__(self, master, placeholder="", textvariable=None, mono=False, bg=T.PANEL2):
        super().__init__(master, bg=T.BORDER, padx=1, pady=1)
        self.var = textvariable or tk.StringVar()
        font = T.F_MONO if mono else T.F_UI
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="x")
        self.entry = tk.Entry(inner, textvariable=self.var, bg=bg, fg=T.TEXT, insertbackground=T.TEXT,
                              relief="flat", bd=0, highlightthickness=0, font=font,
                              selectbackground=T.ACCENT, selectforeground="#ffffff")
        self.entry.pack(fill="x", padx=S(8), pady=S(7))
        self.ph = tk.Label(self.entry, text=placeholder, fg=T.MUTED, bg=bg, font=font, anchor="w")
        self._invalid = False
        self._focused = False
        self.ph.bind("<Button-1>", lambda e: (self.entry.focus_set(), self.entry.icursor(0), "break")[-1])
        self.var.trace_add("write", lambda *_: self._sync())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._focus(False))
        self._sync()

    def _sync(self):
        if self.var.get():
            self.ph.place_forget()
        else:
            self.ph.place(x=0, rely=0.5, anchor="w")

    def _focus(self, focused: bool):
        self._focused = focused
        self._paint()

    def _paint(self):
        if self._invalid:
            self.configure(bg=T.DANGER)
        else:
            self.configure(bg=T.ACCENT if self._focused else T.BORDER)

    def set_placeholder(self, text: str) -> None:
        self.ph.configure(text=text)

    def set_invalid(self, invalid: bool) -> None:
        self._invalid = invalid
        self._paint()

    def focus(self):
        self.entry.focus_set()


class Switch(tk.Canvas):
    """Interrupteur on/off."""

    def __init__(self, master, value=False, command=None, bg=T.PANEL):
        w, h = S(40), S(22)
        super().__init__(master, width=w, height=h, bg=bg, highlightthickness=0, cursor="hand2")
        self._sw, self._sh = w, h
        self.value = bool(value)
        self.command = command
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self._sw, self._sh
        color = T.ACCENT if self.value else T.BORDER
        self.create_oval(0, 0, h, h, fill=color, outline=color)
        self.create_oval(w - h, 0, w, h, fill=color, outline=color)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=color, outline=color)
        pad = S(3)
        x = w - h + pad if self.value else pad
        self.create_oval(x, pad, x + h - 2 * pad, h - pad, fill="#ffffff", outline="#ffffff")

    def _toggle(self, _event):
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)

    def set(self, value: bool) -> None:
        self.value = bool(value)
        self._draw()


class AutoScrollbar(ttk.Scrollbar):
    """Barre de défilement qui disparaît quand tout le contenu est visible (à placer avec grid)."""

    def __init__(self, master, **kw):
        kw.setdefault("style", "Dark.Vertical.TScrollbar")
        super().__init__(master, orient="vertical", **kw)

    def set(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(first, last)


def scrolled(master, widget_factory, bg=T.PANEL):
    """Crée un widget défilant (Text, Treeview…) dans un cadre avec barre auto-masquée.

    Retourne (cadre, widget). Le cadre doit être placé par l'appelant.
    """
    frame = tk.Frame(master, bg=bg)
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)
    widget = widget_factory(frame)
    widget.grid(row=0, column=0, sticky="nsew")
    bar = AutoScrollbar(frame, command=widget.yview)
    bar.grid(row=0, column=1, sticky="ns")
    widget.configure(yscrollcommand=bar.set)
    return frame, widget


class ScrollFrame(tk.Frame):
    """Zone verticalement défilante ; placer les widgets dans ``self.inner``."""

    def __init__(self, master, bg=T.BG):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", style="Dark.Vertical.TScrollbar",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._update())
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)
        self._update()

    def _update(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        needs = self.inner.winfo_reqheight() > self.canvas.winfo_height()
        if needs and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        elif not needs and self.bar.winfo_ismapped():
            self.bar.pack_forget()

    def _on_scroll(self, first, last):
        self.bar.set(first, last)

    def scroll(self, units: int) -> None:
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")


def install_wheel(root: tk.Tk) -> None:
    """Molette de la souris pour les ScrollFrame (Text et Treeview ont déjà la leur)."""
    def handler(event, direction=None):
        w = event.widget
        if isinstance(w, (tk.Text, ttk.Treeview)) or not isinstance(w, tk.Misc):
            return None
        units = direction if direction is not None else (-1 if event.delta > 0 else 1) * 3
        while w is not None:
            if isinstance(w, ScrollFrame):
                w.scroll(units)
                return "break"
            w = w.master
        return None

    root.bind_all("<MouseWheel>", handler)
    root.bind_all("<Button-4>", lambda e: handler(e, -3))
    root.bind_all("<Button-5>", lambda e: handler(e, 3))


def run_bg(widget: tk.Misc, fn, done) -> None:
    """Exécute ``fn`` dans un thread ; ``done(ok, résultat_ou_exception)`` est appelé dans l'interface."""
    q: queue.Queue = queue.Queue()

    def work():
        try:
            q.put((True, fn()))
        except BaseException as exc:  # noqa: BLE001 - remonté à l'appelant
            q.put((False, exc))

    threading.Thread(target=work, daemon=True).start()

    def poll():
        try:
            ok, value = q.get_nowait()
        except queue.Empty:
            try:
                widget.after(60, poll)
            except tk.TclError:
                pass
            return
        try:
            done(ok, value)
        except tk.TclError:
            pass

    widget.after(60, poll)


def divider(master, vertical=False, color=T.BORDER):
    return tk.Frame(master, bg=color, width=1 if vertical else 0, height=0 if vertical else 1)
