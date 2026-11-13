"""Console intégrée : sortie en direct, saisie au clavier, copier/coller, couleurs ANSI, onglets."""
from __future__ import annotations

import queue
import re
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme as T
from .runner import Run, format_duration
from .theme import S
from .widgets import FlatButton, scrolled

CSI_RE = re.compile(r"\x1b\[([0-9;?]*)([@-~])")
CTRL_RE = re.compile(r"[\x00-\x07\x0b\x0c\x0e-\x1f\x7f]")   # on garde \t \n \r et \b

ANSI = {
    30: "#6b7280", 31: "#f87171", 32: "#4ade80", 33: "#facc15", 34: "#60a5fa", 35: "#c084fc",
    36: "#22d3ee", 37: "#e5e7eb", 90: "#9ca3af", 91: "#fca5a5", 92: "#86efac", 93: "#fde68a",
    94: "#93c5fd", 95: "#d8b4fe", 96: "#67e8f9", 97: "#ffffff",
}
NAV_KEYS = {"Left", "Right", "Prior", "Next", "Home", "End"}


def _xterm256(n: int) -> str:
    if n < 8:
        return ANSI[30 + n]
    if n < 16:
        return ANSI[90 + n - 8]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n // 6) % 6, n % 6
        lv = lambda v: 0 if v == 0 else 55 + 40 * v  # noqa: E731
        return "#%02x%02x%02x" % (lv(r), lv(g), lv(b))
    g = 8 + 10 * (n - 232)
    return "#%02x%02x%02x" % (g, g, g)


class ConsoleView(tk.Frame):
    """Zone de texte se comportant comme une console : la saisie se fait à la fin du texte."""

    MAX_LINES = 6000

    def __init__(self, master):
        super().__init__(master, bg=T.CONSOLE_BG)
        frame, self.text = scrolled(self, lambda parent: tk.Text(
            parent, bg=T.CONSOLE_BG, fg=T.TEXT, insertbackground=T.TEXT, font=T.F_MONO, wrap="char",
            relief="flat", bd=0, highlightthickness=0, padx=S(12), pady=S(8), undo=False,
            selectbackground="#33507f", selectforeground="#ffffff", insertwidth=0,
        ), bg=T.CONSOLE_BG)
        frame.pack(fill="both", expand=True)

        t = self.text
        t.tag_configure("meta", foreground=T.MUTED)
        t.tag_configure("err", foreground="#ff9b9b")
        t.tag_configure("ok", foreground=T.OK)
        t.tag_configure("bad", foreground=T.DANGER)
        t.tag_configure("bold", font=T.F_MONO_BOLD)
        t.mark_set("out", "1.0")
        t.mark_gravity("out", "right")      # la sortie s'insère avant ce que l'utilisateur est en train de taper

        self.run: Run | None = None
        self.finished = False
        self._on_exit = None
        self._after = None
        self._carry = ""
        self._fg = None
        self._bold = False
        self._history: list = []
        self._hist_pos = 0

        t.bind("<Key>", self._on_key)
        t.bind("<Return>", self._on_return)
        t.bind("<KP_Enter>", self._on_return)
        t.bind("<BackSpace>", self._on_backspace)
        t.bind("<Up>", lambda e: self._on_history(-1))
        t.bind("<Down>", lambda e: self._on_history(1))
        for seq in ("<Control-c>", "<Control-C>", "<Control-Insert>"):
            t.bind(seq, self._on_copy)
        for seq in ("<Control-v>", "<Control-V>", "<Shift-Insert>", "<<Paste>>"):
            t.bind(seq, self._on_paste)
        for seq in ("<Control-a>", "<Control-A>"):
            t.bind(seq, self._on_select_all)
        for seq in ("<<Cut>>", "<Control-x>", "<Control-X>", "<Delete>"):
            t.bind(seq, lambda e: "break")
        t.bind("<Button-3>", self._popup)

        self._menu = tk.Menu(self, tearoff=0, bg=T.PANEL2, fg=T.TEXT, activebackground=T.ACCENT,
                             activeforeground="#ffffff", bd=0, relief="flat")
        self._menu.add_command(label="Copier", command=self._on_copy)
        self._menu.add_command(label="Coller", command=self._on_paste)
        self._menu.add_command(label="Tout sélectionner", command=self._on_select_all)
        self._menu.add_separator()
        self._menu.add_command(label="Effacer la console", command=self.clear)

    # ------------------------------------------------------------------ cycle de vie
    def attach(self, run: Run, on_exit=None) -> None:
        self.run = run
        self.finished = False
        self.text.configure(insertwidth=S(2))
        self._on_exit = on_exit
        self._carry = ""
        self._fg, self._bold = None, False
        self._cancel()
        self._pump()

    def reset(self) -> None:
        self._cancel()
        self.run = None
        self.finished = False
        self.text.configure(insertwidth=0)
        self.clear()

    def clear(self) -> None:
        self.text.delete("1.0", "end-1c")
        self._carry = ""

    def destroy(self):
        self._cancel()
        super().destroy()

    def _cancel(self):
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    @property
    def running(self) -> bool:
        return bool(self.run and self.run.alive)

    # ------------------------------------------------------------------ sortie
    def write_meta(self, text: str, tag: str = "meta") -> None:
        t = self.text
        if t.compare("out", "!=", "out linestart"):
            t.insert("out", "\n")
        t.insert("out", text.rstrip("\n") + "\n", (tag,))
        t.see("end")

    def _pump(self):
        self._after = None
        run = self.run
        if run is None:
            return
        deadline = time.monotonic() + 0.025
        pending, exited = [], None
        while time.monotonic() < deadline:
            try:
                ev = run.events.get_nowait()
            except queue.Empty:
                break
            if ev[0] == "exit":
                exited = ev
                break
            if pending and pending[-1][0] == ev[0]:
                pending[-1][1] += ev[1]
            else:
                pending.append([ev[0], ev[1]])
        if pending:
            follow = self.text.yview()[1] >= 0.999
            for stream, data in pending:
                self._feed(data, stream)
            self._trim()
            if follow:
                self.text.see("end")
        if exited:
            self._finish(exited[1], exited[2])
            return
        self._after = self.after(10 if not run.events.empty() else 35, self._pump)

    def _finish(self, code: int, duration: float):
        self._carry = ""
        self.finished = True
        self.text.configure(insertwidth=0)
        ok = code == 0
        label = "Terminé" if ok else "Terminé avec une erreur"
        self.write_meta(f"— {label} (code {code}) en {format_duration(duration)} —", "ok" if ok else "bad")
        if self._on_exit:
            self._on_exit(self)

    def _feed(self, data: str, stream: str) -> None:
        data = self._carry + data
        self._carry = ""
        i = data.rfind("\x1b")
        if i != -1 and not CSI_RE.match(data, i) and len(data) - i < 40:
            self._carry, data = data[i:], data[:i]          # séquence ANSI coupée en deux
        if data.endswith("\r"):
            self._carry, data = "\r" + self._carry, data[:-1]  # \r\n peut être coupé en deux
        data = data.replace("\r\n", "\n")
        pos = 0
        for m in CSI_RE.finditer(data):
            self._emit(data[pos:m.start()], stream)
            self._csi(m.group(1), m.group(2))
            pos = m.end()
        self._emit(data[pos:], stream)

    def _emit(self, text: str, stream: str) -> None:
        if not text:
            return
        tags = []
        if stream == "err":
            tags.append("err")
        if self._fg:
            name = "fg" + self._fg
            if name not in self.text.tag_names():
                self.text.tag_configure(name, foreground=self._fg)
            tags.append(name)
        if self._bold:
            tags.append("bold")
        for part in re.split(r"([\r\x08])", CTRL_RE.sub("", text)):
            if not part:
                continue
            if part == "\r":
                self.text.delete("out linestart", "out")          # barres de progression : on réécrit la ligne
            elif part == "\x08":
                if self.text.compare("out", "!=", "out linestart"):
                    self.text.delete("out-1c", "out")
            else:
                self.text.insert("out", part, tuple(tags))

    def _csi(self, params: str, final: str) -> None:
        if final == "m":
            codes = [int(x) if x.isdigit() else 0 for x in (params.split(";") if params else ["0"])]
            i = 0
            while i < len(codes):
                c = codes[i]
                if c == 0:
                    self._fg, self._bold = None, False
                elif c == 1:
                    self._bold = True
                elif c == 22:
                    self._bold = False
                elif c == 39:
                    self._fg = None
                elif c in ANSI:
                    self._fg = ANSI[c]
                elif c in (38, 48):
                    if i + 2 < len(codes) and codes[i + 1] == 5:
                        if c == 38:
                            self._fg = _xterm256(codes[i + 2])
                        i += 2
                    elif i + 4 < len(codes) and codes[i + 1] == 2:
                        if c == 38:
                            self._fg = "#%02x%02x%02x" % tuple(min(255, v) for v in codes[i + 2:i + 5])
                        i += 4
                i += 1
        elif final == "K" and params == "2":
            self.text.delete("out linestart", "out")
        elif final == "J" and params in ("2", "3"):
            self.clear()

    def _trim(self) -> None:
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self.text.delete("1.0", f"{lines - self.MAX_LINES}.0")

    # ------------------------------------------------------------------ saisie
    def _can_type(self) -> bool:
        return self.running

    def _user_insert(self, s: str) -> None:
        t = self.text
        mark = t.index("out")
        t.insert("end-1c", s)
        t.mark_set("out", mark)
        t.mark_set("insert", "end-1c")
        t.see("end")

    def _on_key(self, e):
        if e.keysym in NAV_KEYS or e.keysym.startswith(("Shift", "Control", "Alt", "Meta", "Super", "Caps", "Num", "ISO_Level")):
            return None
        ch = e.char
        if ch and ch >= " " and ch != "\x7f" and self._can_type():
            self._user_insert(ch)
        return "break"

    def _on_backspace(self, _e=None):
        if self._can_type() and self.text.compare("end-1c", ">", "out"):
            self.text.delete("end-2c")
        return "break"

    def _on_return(self, _e=None):
        if not self._can_type():
            return "break"
        t = self.text
        line = t.get("out", "end-1c")
        t.insert("end-1c", "\n")
        t.mark_set("out", "end-1c")
        t.mark_set("insert", "end-1c")
        t.see("end")
        if line.strip():
            self._history.append(line)
        self._hist_pos = len(self._history)
        self.run.write(line + "\n")
        return "break"

    def _on_history(self, delta: int):
        if self._can_type() and self._history:
            self._hist_pos = max(0, min(len(self._history), self._hist_pos + delta))
            new = self._history[self._hist_pos] if self._hist_pos < len(self._history) else ""
            self.text.delete("out", "end-1c")
            self._user_insert(new)
        return "break"

    def _on_copy(self, _e=None):
        if self.text.tag_ranges("sel"):
            self.clipboard_clear()
            self.clipboard_append(self.text.get("sel.first", "sel.last"))
        elif self.running:
            self.run.interrupt()          # Ctrl+C sans sélection : interrompre, comme dans une console
        return "break"

    def _on_paste(self, _e=None):
        if not self._can_type():
            return "break"
        try:
            data = self.clipboard_get()
        except tk.TclError:
            return "break"
        parts = data.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, part in enumerate(parts):
            if part:
                self._user_insert(part.replace("\t", "    "))
            if i < len(parts) - 1:
                self._on_return()
        return "break"

    def _on_select_all(self, _e=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _popup(self, e):
        self.text.focus_set()
        self._menu.tk_popup(e.x_root, e.y_root)

    def copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))


class _Tab:
    def __init__(self, key, title, view):
        self.key, self.title, self.view = key, title, view
        self.status = "idle"            # idle | run | ok | bad
        self.frame = self.dot = self.name = self.close = None


class ConsolePanel(tk.Frame):
    """Onglets de consoles (un par exécution) avec barre d'état et boutons."""

    DOT = {"idle": T.MUTED, "run": T.ACCENT, "ok": T.OK, "bad": T.DANGER}

    def __init__(self, master, on_change=None):
        super().__init__(master, bg=T.PANEL)
        self.on_change = on_change
        self.tabs: list = []
        self.current: _Tab | None = None

        self.tabbar = tk.Frame(self, bg=T.PANEL)
        self.tabbar.pack(fill="x")
        bar = tk.Frame(self, bg=T.PANEL)
        bar.pack(fill="x")
        self.status = tk.Label(bar, text="", bg=T.PANEL, fg=T.MUTED, font=T.F_SMALL, anchor="w")
        self.status.pack(side="left", padx=S(12), pady=S(5))
        self.btn_close = FlatButton(bar, "Fermer l'onglet", self.close_current, padx=10, pady=3)
        self.btn_clear = FlatButton(bar, "Effacer", self._clear, padx=10, pady=3)
        self.btn_copy = FlatButton(bar, "Copier tout", self._copy, padx=10, pady=3)
        self.btn_stop = FlatButton(bar, "■  Arrêter", self.stop_current, style="danger", padx=10, pady=3)
        for b in (self.btn_close, self.btn_clear, self.btn_copy, self.btn_stop):
            b.pack(side="right", padx=(0, S(6)), pady=S(3))
        tk.Frame(self, bg=T.BORDER, height=1).pack(fill="x")

        self.stack = tk.Frame(self, bg=T.CONSOLE_BG)
        self.stack.pack(fill="both", expand=True)
        self.stack.grid_rowconfigure(0, weight=1)
        self.stack.grid_columnconfigure(0, weight=1)
        self.empty = tk.Label(self.stack, bg=T.CONSOLE_BG, fg=T.MUTED, font=T.F_UI, justify="center",
                              text="La sortie des scripts s'affiche ici.\nLancez un script avec « Exécuter ».")
        self.empty.grid(row=0, column=0)
        self._refresh()
        self.after(500, self._tick)

    # ------------------------------------------------------------------ API
    def start(self, key, title, cmd, cwd, env, header=()):
        tab = next((t for t in self.tabs if t.key == key and not t.view.running), None)
        if tab is None:
            same = sum(1 for t in self.tabs if t.key == key)
            tab = self._new_tab(key, title if same == 0 else f"{title} ({same + 1})")
        else:
            tab.view.reset()
        for line in header:
            tab.view.write_meta(line)
        run = Run(cmd, cwd, env)
        tab.status = "run"
        run.start()
        tab.view.attach(run, on_exit=lambda v, t=tab: self._exited(t))
        self.select(tab)
        if run.start_error:
            tab.status = "bad"
        self._changed()
        return tab.view

    def running_keys(self) -> list:
        return [t.key for t in self.tabs if t.view.running]

    def any_running(self) -> bool:
        return any(t.view.running for t in self.tabs)

    def stop_all(self) -> None:
        for t in self.tabs:
            if t.view.running:
                t.view.run.stop()

    # ------------------------------------------------------------------ onglets
    def _new_tab(self, key, title) -> _Tab:
        view = ConsoleView(self.stack)
        view.grid(row=0, column=0, sticky="nsew")
        tab = _Tab(key, title, view)
        f = tk.Frame(self.tabbar, bg=T.PANEL, cursor="hand2")
        f.pack(side="left", padx=(S(6), 0), pady=(S(6), 0))
        tab.frame = f
        tab.dot = tk.Label(f, text="●", bg=T.PANEL, fg=T.MUTED, font=T.F_SMALL)
        tab.dot.pack(side="left", padx=(S(8), S(4)), pady=S(4))
        tab.name = tk.Label(f, text=title if len(title) <= 24 else title[:23] + "…", bg=T.PANEL, fg=T.TEXT, font=T.F_UI)
        tab.name.pack(side="left", pady=S(4))
        tab.close = tk.Label(f, text="×", bg=T.PANEL, fg=T.MUTED, font=T.F_BOLD, padx=S(8))
        tab.close.pack(side="left")
        for w in (f, tab.dot, tab.name):
            w.bind("<Button-1>", lambda e, t=tab: self.select(t))
            w.bind("<Button-2>", lambda e, t=tab: self.close(t))
        tab.close.bind("<Button-1>", lambda e, t=tab: self.close(t))
        tab.close.bind("<Enter>", lambda e, t=tab: t.close.configure(fg=T.DANGER))
        tab.close.bind("<Leave>", lambda e, t=tab: t.close.configure(fg=T.MUTED))
        self.tabs.append(tab)
        return tab

    def select(self, tab) -> None:
        self.current = tab
        tab.view.tkraise()
        self._refresh()

    def close_current(self):
        if self.current:
            self.close(self.current)

    def close(self, tab) -> None:
        if tab.view.running:
            if not messagebox.askyesno("Fermer l'onglet", f"« {tab.title} » est en cours d'exécution.\nL'arrêter et fermer l'onglet ?",
                                       parent=self.winfo_toplevel()):
                return
            tab.view.run.stop()
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        tab.frame.destroy()
        tab.view.destroy()
        if self.current is tab:
            self.current = self.tabs[min(index, len(self.tabs) - 1)] if self.tabs else None
            if self.current:
                self.current.view.tkraise()
        self._refresh()
        self._changed()

    def stop_current(self):
        if self.current and self.current.view.running:
            self.current.view.run.stop()

    def _clear(self):
        if self.current:
            self.current.view.clear()

    def _copy(self):
        if self.current:
            self.current.view.copy_all()

    def _exited(self, tab):
        run = tab.view.run
        tab.status = "ok" if run and run.exit_code == 0 else "bad"
        self._refresh()
        self._changed()

    def _changed(self):
        self._refresh()
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------ affichage
    def _refresh(self):
        for t in self.tabs:
            selected = t is self.current
            bg = T.CONSOLE_BG if selected else T.PANEL
            for w in (t.frame, t.dot, t.name, t.close):
                w.configure(bg=bg)
            t.dot.configure(fg=self.DOT.get(t.status, T.MUTED))
            t.name.configure(fg=T.TEXT if selected else T.MUTED)
        self.empty.lift() if not self.tabs else self.empty.lower()
        cur = self.current
        for b in (self.btn_close, self.btn_clear, self.btn_copy):
            b.set_enabled(cur is not None)
        self.btn_stop.set_enabled(bool(cur and cur.view.running))
        self._update_status()

    def _update_status(self):
        cur = self.current
        if not cur:
            self.status.configure(text="", fg=T.MUTED)
            return
        run = cur.view.run
        if cur.view.running:
            self.status.configure(text=f"En cours · {format_duration(run.elapsed)}  —  tapez dans la console pour répondre au script",
                                  fg=T.ACCENT)
        elif run and run.exit_code is not None:
            ok = run.exit_code == 0
            self.status.configure(text=f"{'Terminé' if ok else 'Erreur'} (code {run.exit_code}) · {format_duration(run.duration or 0)}",
                                  fg=T.OK if ok else T.DANGER)
        else:
            self.status.configure(text="", fg=T.MUTED)

    def _tick(self):
        try:
            if self.current and self.current.view.running:
                self._update_status()
            self.after(500, self._tick)
        except tk.TclError:
            pass
