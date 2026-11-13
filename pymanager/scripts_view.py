"""Vue principale : liste des scripts, description, paramètres exposés et console."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import tkinter as tk
from collections import Counter
from tkinter import messagebox, ttk

from . import paths, scanner
from . import theme as T
from .console import ConsolePanel
from .params import ParamStore
from .params_form import ParamsForm
from .theme import S
from .widgets import FlatButton, PlaceholderEntry, ScrollFrame, scrolled

NO_PARAMS_HINT = (
    "Aucune variable exposée dans ce script.\n"
    "Pour modifier une variable depuis PyManager, ajoutez @expose dans un commentaire de sa ligne :\n\n"
    '    INPUT_DIR = "input"   # Dossier source @expose'
)


def open_path(path: str) -> None:
    if paths.IS_WINDOWS:
        os.startfile(path)  # noqa: S606 - ouverture par l'explorateur Windows
    else:
        subprocess.Popen(["xdg-open", path])


def _fmt_value(value) -> str:
    if isinstance(value, str):
        return ('r"%s"' if "\\" in value else '"%s"') % value
    return str(value)


class ScriptsView(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.store = ParamStore()
        self.scripts: dict = {}
        self.current = None
        self.details = None
        self._sig = None
        self._open: set = set()
        self._seen: set = set()
        self._last_scan = 0.0
        self.running: Counter = Counter()
        self._dups: set = set()

        pw = tk.PanedWindow(self, orient="horizontal", sashwidth=S(6), bg=T.BG, bd=0, sashrelief="flat")
        pw.pack(fill="both", expand=True)
        side = self._build_sidebar(pw)
        right = tk.PanedWindow(pw, orient="vertical", sashwidth=S(6), bg=T.BG, bd=0, sashrelief="flat")
        pw.add(side, minsize=S(230), width=S(300))
        pw.add(right, minsize=S(480), stretch="always")
        self.detail = self._build_detail(right)
        self.console = ConsolePanel(right, on_change=self._console_changed)
        right.add(self.detail, minsize=S(200), stretch="always", height=S(400))
        right.add(self.console, minsize=S(150), height=S(280))

        self.refresh(force=True)
        last = self.app.settings.get("last_script")
        if last and last in self.scripts:
            self.select_script(last)
        self.after(1000, self._poll)

    # ------------------------------------------------------------------ construction
    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=T.PANEL)
        head = tk.Frame(side, bg=T.PANEL)
        head.pack(fill="x", padx=S(12), pady=S(12))
        self.search = PlaceholderEntry(head, placeholder="Rechercher un script…")
        self.search.pack(fill="x")
        self.search.var.trace_add("write", lambda *_: self._rebuild_tree())
        body, self.tree = scrolled(side, lambda parent: ttk.Treeview(
            parent, show="tree", selectmode="browse", style="Side.Treeview"))
        body.pack(fill="both", expand=True, padx=(S(6), 0), pady=(0, S(6)))
        self.tree.tag_configure("folder", foreground=T.MUTED)
        self.tree.tag_configure("running", foreground=T.ACCENT)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Return>", lambda e: self.run_current())
        self.tree.bind("<<TreeviewOpen>>", lambda e: self._folder_state(True))
        self.tree.bind("<<TreeviewClose>>", lambda e: self._folder_state(False))
        return side

    def _card(self, parent, title, hint=""):
        outer = tk.Frame(parent, bg=T.PANEL)
        outer.pack(fill="x", pady=(0, S(14)), padx=(0, S(12)))
        head = tk.Frame(outer, bg=T.PANEL)
        head.pack(fill="x", padx=S(16), pady=(S(12), S(8)))
        tk.Label(head, text=title, font=T.F_H2, fg=T.TEXT, bg=T.PANEL).pack(side="left")
        if hint:
            tk.Label(head, text=hint, font=T.F_SMALL, fg=T.MUTED, bg=T.PANEL).pack(side="right")
        body = tk.Frame(outer, bg=T.PANEL)
        body.pack(fill="x", padx=S(16), pady=(0, S(12)))
        return outer, body

    def _build_detail(self, parent):
        detail = tk.Frame(parent, bg=T.BG)
        detail.grid_rowconfigure(0, weight=1)
        detail.grid_columnconfigure(0, weight=1)
        self.empty = tk.Label(detail, bg=T.BG, fg=T.MUTED, font=T.F_UI, justify="center")
        self.empty.grid(row=0, column=0)
        self.content = tk.Frame(detail, bg=T.BG)
        self.content.grid(row=0, column=0, sticky="nsew")

        header = tk.Frame(self.content, bg=T.BG)
        header.pack(fill="x", padx=S(24), pady=(S(18), S(10)))
        left = tk.Frame(header, bg=T.BG)
        left.pack(side="left", fill="x", expand=True)
        title_row = tk.Frame(left, bg=T.BG)
        title_row.pack(fill="x")
        self.title = tk.Label(title_row, font=T.F_H1, fg=T.TEXT, bg=T.BG, anchor="w")
        self.title.pack(side="left")
        self.badge = tk.Label(title_row, text="fenêtre propre", font=T.F_SMALL, fg=T.ACCENT, bg=T.SELECT,
                              padx=S(8), pady=S(1))
        self.path = tk.Label(left, font=T.F_SMALL, fg=T.MUTED, bg=T.BG, anchor="w")
        self.path.pack(fill="x")
        buttons = tk.Frame(header, bg=T.BG)
        buttons.pack(side="right")
        FlatButton(buttons, "Modifier", self.edit_current).pack(side="right", padx=(S(8), 0))
        FlatButton(buttons, "Ouvrir le dossier", self.open_folder).pack(side="right", padx=(S(8), 0))
        FlatButton(buttons, "▶  Exécuter", self.run_current, style="primary", padx=18, pady=7).pack(side="right")

        scroll = ScrollFrame(self.content, bg=T.BG)
        scroll.pack(fill="both", expand=True, padx=(S(24), S(12)))
        inner = scroll.inner
        _, body = self._card(inner, "Description")
        self.desc = tk.Label(body, font=T.F_UI, fg=T.TEXT, bg=T.PANEL, justify="left", anchor="w")
        self.desc.pack(fill="x")
        self.params_card, pbody = self._card(inner, "Paramètres", "champ vide = valeur du script")
        self.form = ParamsForm(pbody)
        self.form.pack(fill="x")
        self.no_params = tk.Label(pbody, text=NO_PARAMS_HINT, font=T.F_SMALL, fg=T.MUTED, bg=T.PANEL,
                                  justify="left", anchor="w")
        inner.bind("<Configure>", lambda e: self._wrap(inner.winfo_width()), add="+")
        self._show_empty()
        return detail

    def _wrap(self, width: int) -> None:
        wrap = max(S(240), width - S(100))
        self.desc.configure(wraplength=wrap)
        self.no_params.configure(wraplength=wrap)

    def _show_empty(self, text=None):
        if text is None:
            text = ("Aucun script trouvé.\n\nDéposez vos fichiers .py dans « scripts/public » ou « scripts/private »\n"
                    "(bouton « Dossier des scripts » en haut à droite).") if not self.scripts else \
                "Choisissez un script dans la liste."
        self.empty.configure(text=text)
        self.empty.tkraise()

    # ------------------------------------------------------------------ liste des scripts
    def refresh(self, force: bool = False) -> None:
        self._last_scan = time.monotonic()
        found = scanner.scan(self.app.root_dir, self.app.settings.get("source_dirs"))
        sig = tuple(s.rel for s in found)
        if sig == self._sig and not force:
            return
        self._sig = sig
        self.scripts = {s.rel: s for s in found}
        counts = Counter(s.display for s in found)
        self._dups = {s.rel for s in found if counts[s.display] > 1}      # même chemin dans plusieurs sources
        self._rebuild_tree()
        if self.current and self.current.rel not in self.scripts:
            self.current = self.details = None
            self._show_empty()
        elif not self.current:
            self._show_empty()

    def _folder_text(self, name: str, opened: bool) -> str:
        return f"{'▾' if opened else '▸'}  {name}"

    def _script_text(self, info) -> str:
        suffix = f"   ({info.source})" if info.rel in self._dups and info.source else ""
        return ("●  " if self.running.get(info.rel) else "") + info.name + suffix

    def _rebuild_tree(self) -> None:
        query = self.search.var.get().strip().lower()
        t = self.tree
        t.delete(*t.get_children())
        root: dict = {"dirs": {}, "files": []}
        for rel, info in self.scripts.items():
            if query and query not in info.display.lower():
                continue
            node = root
            for part in info.display.split("/")[:-1]:
                node = node["dirs"].setdefault(part, {"dirs": {}, "files": []})
            node["files"].append(info)

        def fill(parent, node, prefix):
            for name in sorted(node["dirs"], key=str.lower):
                path = prefix + name
                if path not in self._seen:
                    self._seen.add(path)
                    self._open.add(path)
                opened = bool(query) or path in self._open
                iid = "d:" + path
                t.insert(parent, "end", iid, text=self._folder_text(name, opened), open=opened, tags=("folder",))
                fill(iid, node["dirs"][name], path + "/")
            for info in sorted(node["files"], key=lambda s: s.name.lower()):
                tags = ("running",) if self.running.get(info.rel) else ()
                t.insert(parent, "end", "s:" + info.rel, text=self._script_text(info), tags=tags)

        fill("", root, "")
        if self.current and t.exists("s:" + self.current.rel):
            t.selection_set("s:" + self.current.rel)
            t.see("s:" + self.current.rel)

    def _set_folder(self, iid: str, opened: bool) -> None:
        path = iid[2:]
        self.tree.item(iid, open=opened, text=self._folder_text(path.rsplit("/", 1)[-1], opened))
        (self._open.add if opened else self._open.discard)(path)

    def _on_click(self, e):
        iid = self.tree.identify_row(e.y)
        if iid and iid.startswith("d:"):
            self._set_folder(iid, not bool(self.tree.item(iid, "open")))
            return "break"
        return None

    def _folder_state(self, opened: bool) -> None:
        iid = self.tree.focus()
        if iid.startswith("d:"):
            path = iid[2:]
            self.tree.item(iid, text=self._folder_text(path.rsplit("/", 1)[-1], opened))
            (self._open.add if opened else self._open.discard)(path)

    def _on_select(self, _e=None) -> None:
        sel = self.tree.selection()
        if sel and sel[0].startswith("s:") and not (self.current and self.current.rel == sel[0][2:]):
            self.select_script(sel[0][2:])

    # ------------------------------------------------------------------ script courant
    def select_script(self, rel: str) -> None:
        if self.current and self.current.rel != rel:
            self._save_form()
        info = self.scripts.get(rel)
        if info is None:
            return
        same = self.current is not None and self.current.rel == rel
        self.current = info
        self.details = scanner.load_details(info)
        self._apply_details(keep=same)
        self.app.settings["last_script"] = rel
        if self.tree.exists("s:" + rel) and self.tree.selection() != ("s:" + rel,):
            self.tree.selection_set("s:" + rel)

    def _apply_details(self, keep: bool) -> None:
        info, det = self.current, self.details
        self.title.configure(text=info.name)
        self.path.configure(text=info.rel)
        if det.is_gui:
            self.badge.pack(side="left", padx=(S(10), 0))
        else:
            self.badge.pack_forget()
        self.desc.configure(text=det.description or
                            f"Aucune description. Créez {info.path.stem}.txt à côté du script pour en ajouter une.")
        self.form.set_params(det.params, self.store.get(info.rel), keep_current=keep)
        if det.params:
            self.no_params.pack_forget()
            self.form.pack(fill="x")
        else:
            self.form.pack_forget()
            self.no_params.pack(fill="x")
        self.content.tkraise()

    def _save_form(self) -> None:
        if self.current:
            self.store.set(self.current.rel, self.form.raw_values())

    def _poll(self) -> None:
        try:
            if self.current and self.details and scanner.stamp_of(self.current) != self.details.stamp:
                self.details = scanner.load_details(self.current)
                self._apply_details(keep=True)
            self.after(1000, self._poll)
        except tk.TclError:
            pass

    def on_focus(self) -> None:
        if time.monotonic() - self._last_scan > 1.5:
            self.refresh()

    # ------------------------------------------------------------------ actions
    def run_current(self) -> None:
        info = self.current
        if info is None:
            return
        overrides, errors = self.form.collect()
        if errors:
            self.form.focus_first_error(errors)
            messagebox.showwarning("Paramètres invalides", "\n".join(f"{k} : {v}" for k, v in errors.items()),
                                   parent=self.winfo_toplevel())
            return
        self._save_form()
        py = paths.script_python()
        header = [f"▶ {info.rel}"]
        if overrides:
            fd, tmp = tempfile.mkstemp(prefix="pm_", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(overrides, f)
            cmd = [py, "-u", str(paths.LAUNCHER), str(info.path), tmp]
            header.append("Paramètres : " + ", ".join(f"{k} = {_fmt_value(v)}" for k, v in overrides.items()))
        else:
            cmd = [py, "-u", str(info.path)]
        view = self.console.start(info.rel, info.name, cmd, str(info.path.parent), paths.script_env(), header)
        view.text.focus_set()

    def edit_current(self) -> None:
        if not self.current:
            return
        path = str(self.current.path)
        try:
            if paths.IS_WINDOWS:
                try:
                    os.startfile(path, "edit")
                except OSError:
                    subprocess.Popen(["notepad", path])
            else:
                open_path(path)
        except OSError as exc:
            messagebox.showerror("Modifier", str(exc), parent=self.winfo_toplevel())

    def open_folder(self) -> None:
        if self.current:
            try:
                open_path(str(self.current.path.parent))
            except OSError as exc:
                messagebox.showerror("Ouvrir le dossier", str(exc), parent=self.winfo_toplevel())

    def _console_changed(self) -> None:
        self.running = Counter(self.console.running_keys())
        for rel, info in self.scripts.items():
            iid = "s:" + rel
            if self.tree.exists(iid):
                self.tree.item(iid, text=self._script_text(info),
                               tags=("running",) if self.running.get(rel) else ())

    def shutdown(self) -> None:
        self._save_form()
        self.console.stop_all()
