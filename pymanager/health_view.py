"""Vue « Santé » : diagnostic et entretien de l'environnement Python partagé par les scripts."""
from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from . import health, paths
from . import theme as T
from .console import ConsoleView
from .runner import Run
from .theme import S
from .widgets import FlatButton, run_bg, scrolled

GROUPS = [
    ("unused_req", "Requirements inutilisés", "Entrées de requirements.txt qu'aucun script ne semble utiliser", True),
    ("orphan", "Paquets installés mais inutiles", "Ni utilisés par vos scripts, ni requis par un autre paquet", True),
    ("undeclared", "Utilisés mais non déclarés", "Importés par un script sans figurer dans un requirements.txt", True),
    ("missing", "À installer", "Listés dans un requirements.txt mais absents de l'environnement", False),
    ("update", "Mises à jour disponibles", "Versions plus récentes sur PyPI", True),
]


class HealthView(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.analysis = None
        self.updates = None            # None = pas encore recherché
        self.checked: set = set()
        self.items: dict = {}          # iid -> ("finding", Finding) | ("update", dict)
        self.busy = False
        self._first = True

        pw = tk.PanedWindow(self, orient="vertical", sashwidth=S(6), bg=T.BG, bd=0, sashrelief="flat")
        pw.pack(fill="both", expand=True)
        top = tk.Frame(pw, bg=T.BG)
        self._build_top(top)
        self.console = ConsoleView(pw)
        pw.add(top, minsize=S(300), stretch="always", height=S(520))
        pw.add(self.console, minsize=S(110), height=S(150))
        self.console.write_meta("Les opérations (installation, désinstallation, mises à jour) s'affichent ici.")

    # ------------------------------------------------------------------ construction
    def _build_top(self, top):
        head = tk.Frame(top, bg=T.PANEL)
        head.pack(fill="x", padx=S(20), pady=(S(18), S(10)))
        tk.Label(head, text="Santé de l'environnement", font=T.F_H2, fg=T.TEXT, bg=T.PANEL).pack(
            anchor="w", padx=S(16), pady=(S(12), S(2)))
        self.summary = tk.Label(head, text="", font=T.F_SMALL, fg=T.MUTED, bg=T.PANEL, anchor="w", justify="left")
        self.summary.pack(fill="x", padx=S(16), pady=(0, S(12)))

        bar1 = tk.Frame(top, bg=T.BG)
        bar1.pack(fill="x", padx=S(20))
        self.buttons = []
        for text, cmd, style in (
            ("Analyser", self.analyze, "primary"),
            ("Rechercher les mises à jour", self.check_updates, "ghost"),
            ("Vérifier les conflits", self.pip_check, "ghost"),
            ("Réparer l'installation", self.repair, "ghost"),
            ("Recréer l'environnement", self.recreate, "danger"),
        ):
            b = FlatButton(bar1, text, cmd, style=style)
            b.pack(side="left", padx=(0, S(8)), pady=(0, S(8)))
            self.buttons.append(b)

        bar2 = tk.Frame(top, bg=T.BG)
        bar2.pack(fill="x", padx=S(20))
        tk.Label(bar2, text="Sur la sélection :", font=T.F_SMALL, fg=T.MUTED, bg=T.BG).pack(side="left", padx=(0, S(8)))
        for text, cmd, style in (
            ("Supprimer", self.remove_selected, "danger"),
            ("Ajouter aux requirements", self.add_selected, "ghost"),
            ("Mettre à jour", self.update_selected, "ghost"),
            ("Tout décocher", self.uncheck_all, "ghost"),
        ):
            b = FlatButton(bar2, text, cmd, style=style, padx=12, pady=4)
            b.pack(side="left", padx=(0, S(8)), pady=(0, S(8)))
            self.buttons.append(b)

        cols = ("version", "latest", "where", "detail")
        frame, self.tree = scrolled(top, lambda parent: ttk.Treeview(
            parent, columns=cols, show="tree headings", selectmode="none", style="Health.Treeview"))
        frame.pack(fill="both", expand=True, padx=S(20), pady=(0, S(6)))
        self.tree.heading("#0", text="Paquet", anchor="w")
        for col, title, width in (("version", "Installé", 90), ("latest", "Disponible", 90),
                                  ("where", "Où", 190), ("detail", "Détail", 380)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=S(width), anchor="w", stretch=(col == "detail"))
        self.tree.column("#0", width=S(280), stretch=False)
        self.tree.tag_configure("group", foreground=T.TEXT, font=T.F_BOLD, background=T.PANEL2)
        self.tree.tag_configure("note", foreground=T.MUTED)
        self.tree.tag_configure("ok", foreground=T.OK)
        self.tree.bind("<Button-1>", self._on_click)

    # ------------------------------------------------------------------ état
    def on_show(self) -> None:
        if self._first:
            self._first = False
            self.summary.configure(text=f"Interpréteur des scripts : {paths.script_python()}")
            self.analyze()

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        self.busy = busy
        for b in self.buttons:
            b.set_enabled(not busy)
        if message:
            self.summary.configure(text=message, fg=T.ACCENT)

    def _set_summary(self):
        a = self.analysis
        if not a:
            return
        last = health.last_snapshot_time()
        self.summary.configure(
            fg=T.MUTED,
            text=(f"Python {a.python} · {a.installed} paquets installés · {len(a.req_files)} fichier(s) requirements.txt\n"
                  f"Interpréteur : {paths.script_python()}\n"
                  f"Dernier instantané de l'environnement (pip freeze) : {last or 'aucun'}"),
        )

    # ------------------------------------------------------------------ tableau
    def _render(self) -> None:
        t = self.tree
        t.delete(*t.get_children())
        self.items.clear()
        self.checked.clear()           # la sélection est réinitialisée à chaque nouveau tableau
        findings = self.analysis.findings if self.analysis else []
        total = 0
        counter = 0
        for kind, title, hint, actionable in GROUPS:
            if kind == "update":
                if self.updates is None:
                    continue
                rows = [("update", u) for u in self.updates]
            else:
                rows = [("finding", f) for f in findings if f.kind == kind]
            if not rows:
                continue
            gid = f"g:{kind}"
            t.insert("", "end", gid, text=f"{title}  ({len(rows)})", values=("", "", "", ""), open=True, tags=("group",))
            for typ, obj in rows:
                counter += 1
                iid = f"i:{counter}"
                self.items[iid] = (typ, obj)
                if typ == "finding":
                    vals = (obj.version, "", obj.where, obj.detail)
                    name = obj.display
                else:
                    pin = self._pin_info(obj["name"])
                    vals = (obj["version"], obj["latest_version"], pin[1] if pin else "—",
                            "Version épinglée : la mise à jour peut casser vos scripts" if pin else "")
                    name = obj["name"]
                t.insert(gid, "end", iid, text=self._label(iid, name, actionable), values=vals)
                total += 1
        if not total and self.analysis:
            t.insert("", "end", text="Aucun problème détecté ✓", tags=("ok",))
        elif not self.analysis:
            t.insert("", "end", text="Lancez « Analyser » pour examiner l'environnement.", tags=("note",))
        self._set_summary()

    def _pin_info(self, name: str):
        norm = health.normalize(name)
        for r in (self.analysis.reqs if self.analysis else []):
            if r.norm == norm and r.pinned:
                return r, f"{r.raw_name}=={r.pinned}"
        return None

    def _label(self, iid, name, actionable=True):
        if not actionable:
            return "    " + name
        return ("☑  " if iid in self.checked else "☐  ") + name

    def _on_click(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return "break"
        if iid.startswith("g:"):
            kind = iid[2:]
            if not next(g for g in GROUPS if g[0] == kind)[3]:
                return "break"
            kids = self.tree.get_children(iid)
            check = not all(k in self.checked for k in kids)
            for k in kids:
                self._set_check(k, check)
        elif iid in self.items:
            kind = self.tree.parent(iid)[2:]
            if next(g for g in GROUPS if g[0] == kind)[3]:
                self._set_check(iid, iid not in self.checked)
        return "break"

    def _set_check(self, iid, value: bool) -> None:
        (self.checked.add if value else self.checked.discard)(iid)
        typ, obj = self.items[iid]
        name = obj.display if typ == "finding" else obj["name"]
        self.tree.item(iid, text=self._label(iid, name))

    def uncheck_all(self) -> None:
        for iid in list(self.checked):
            self._set_check(iid, False)

    def _selected(self, *kinds):
        out = []
        for iid in self.checked:
            typ, obj = self.items[iid]
            kind = obj.kind if typ == "finding" else "update"
            if kind in kinds:
                out.append(obj)
        return out

    # ------------------------------------------------------------------ diagnostics
    def analyze(self) -> None:
        if self.busy:
            return
        self.set_busy(True, "Analyse en cours…")
        root, py = self.app.root_dir, paths.script_python()

        def done(ok, value):
            self.set_busy(False)
            if not ok:
                self.summary.configure(text=f"Analyse impossible : {value}", fg=T.DANGER)
                return
            self.checked.clear()
            self.analysis = value
            self._render()

        run_bg(self, lambda: health.analyze(root, py), done)

    def check_updates(self) -> None:
        if self.busy:
            return
        self.set_busy(True, "Recherche des mises à jour (connexion à PyPI)…")
        py = paths.script_python()

        def done(ok, value):
            self.set_busy(False)
            if not ok:
                self.summary.configure(text=f"Recherche impossible : {value}", fg=T.DANGER)
                return
            self.updates = sorted(value, key=lambda u: u["name"].lower())
            self.checked = {c for c in self.checked if not c.startswith("i:")}
            self._render()
            if not self.updates:
                self.summary.configure(text="Tous les paquets sont à jour ✓", fg=T.OK)

        run_bg(self, lambda: health.outdated(py), done)

    # ------------------------------------------------------------------ pip dans la console
    def _pip(self, args, then=None, snapshot=True) -> None:
        if self.busy:
            return
        py = paths.script_python()
        self.console.reset()
        self.console.write_meta("▶ pip " + " ".join(args))
        run = Run([py, "-m", "pip"] + args + ["--disable-pip-version-check"], str(paths.ROOT), paths.script_env())
        self.set_busy(True, "Opération en cours…")
        run.start()
        self.console.attach(run, on_exit=lambda v: self._pip_done(v, then, snapshot))

    def _pip_done(self, view, then, snapshot) -> None:
        ok = view.run.exit_code == 0
        self.set_busy(False)
        if ok and snapshot:
            py = paths.script_python()
            run_bg(self, lambda: health.snapshot_freeze(py), lambda *_: then(ok) if then else None)
        elif then:
            then(ok)

    def pip_check(self) -> None:
        self._pip(["check"], snapshot=False)

    def repair(self) -> None:
        files = health.find_requirements_files(self.app.root_dir)
        if not files:
            messagebox.showinfo("Réparer", "Aucun fichier requirements.txt dans le dossier des scripts.", parent=self)
            return
        args = ["install"]
        for f in files:
            args += ["-r", str(f)]
        self._pip(args, then=lambda ok: self.analyze())

    def remove_selected(self) -> None:
        sel = self._selected("unused_req", "orphan")
        if not sel or self.busy:
            if not sel:
                messagebox.showinfo("Supprimer", "Cochez d'abord des éléments dans « Requirements inutilisés » "
                                    "ou « Paquets installés mais inutiles ».", parent=self)
            return
        names = "\n".join(f"  • {f.display}  ({f.where})" for f in sel[:15]) + ("\n  …" if len(sel) > 15 else "")
        if not messagebox.askyesno(
                "Supprimer", f"{len(sel)} élément(s) sélectionné(s) :\n\n{names}\n\nLes lignes seront retirées des "
                "requirements.txt et les paquets désinstallés s'ils ne servent plus à rien.\nContinuer ?", parent=self):
            return
        a = self.analysis
        remove_from: dict = {}
        orphans = []
        for f in sel:
            if f.kind == "unused_req":
                remove_from.setdefault(f.norm, set()).update(f.files)
            else:
                orphans.append(f.norm)
        for norm, files in remove_from.items():
            for file in files:
                health.remove_from_requirements(file, {norm})
        uninstall = health.safe_to_uninstall(a, set(remove_from), remove_from) + orphans
        names_to_remove = [a.dists[n]["name"] for n in uninstall if n in a.dists]
        if names_to_remove:
            self._pip(["uninstall", "-y"] + names_to_remove, then=lambda ok: self.analyze())
        else:
            self.analyze()

    def add_selected(self) -> None:
        sel = self._selected("undeclared")
        if not sel:
            messagebox.showinfo("Ajouter", "Cochez d'abord des éléments dans « Utilisés mais non déclarés ».", parent=self)
            return
        for f in sel:
            for file in f.files:
                health.add_to_requirements(file, [f.display])
        self.analyze()

    def update_selected(self) -> None:
        sel = self._selected("update")
        if not sel or self.busy:
            if not sel:
                messagebox.showinfo("Mettre à jour", "Lancez « Rechercher les mises à jour » puis cochez des paquets.", parent=self)
            return
        specs, pinned = [], []
        for u in sel:
            pin = self._pin_info(u["name"])
            if pin:
                pinned.append((u, pin[0]))
                specs.append(f"{u['name']}=={u['latest_version']}")
            else:
                specs.append(u["name"])
        if pinned:
            warn = "\n".join(f"  • {u['name']} : {r.pinned} → {u['latest_version']}" for u, r in pinned)
            if not messagebox.askyesno("Versions épinglées",
                                       f"Ces paquets sont épinglés dans vos requirements :\n\n{warn}\n\n"
                                       "La mise à jour peut casser des scripts. Mettre à jour quand même ?\n"
                                       "(les requirements.txt seront modifiés)", parent=self):
                return

        def after(ok):
            if ok:
                for u, req in pinned:
                    for r in self.analysis.reqs:
                        if r.norm == req.norm and r.pinned:
                            health.set_pin(r.file, r.norm, u["latest_version"])
                self.updates = None
            self.analyze()

        self._pip(["install", "-U"] + specs, then=after)

    def recreate(self) -> None:
        if not paths.IS_WINDOWS:
            messagebox.showinfo("Recréer", "Cette action est disponible sous Windows (via start.bat).", parent=self)
            return
        if not messagebox.askyesno(
                "Recréer l'environnement",
                "Le dossier .venv va être supprimé puis recréé, et toutes les dépendances réinstallées.\n"
                "PyManager va se fermer et redémarrer automatiquement (cela peut prendre quelques minutes).\n\nContinuer ?",
                parent=self):
            return
        py = paths.script_python()
        self.set_busy(True, "Sauvegarde de l'état actuel (pip freeze)…")

        def go(*_):
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(paths.START_BAT), "--reset"], cwd=str(paths.ROOT),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            self.app.quit_now()

        run_bg(self, lambda: health.snapshot_freeze(py), go)
