"""Formulaire des variables exposées (@expose) d'un script."""
from __future__ import annotations

import tkinter as tk

from . import theme as T
from .params import DATE_FORMAT_HINT, DATE_ONLY_HINT, display_default, parse_value
from .theme import S
from .widgets import ChoiceField, PlaceholderEntry, Switch


class _Row:
    def __init__(self, parent, param, saved, on_change):
        self.param = param
        self.on_change = on_change
        self.frame = tk.Frame(parent, bg=T.PANEL)
        head = tk.Frame(self.frame, bg=T.PANEL)
        head.pack(fill="x", pady=(0, S(5)))
        tk.Label(head, text=param.name, font=T.F_MONO_BOLD, fg=T.TEXT, bg=T.PANEL).pack(side="left")
        if param.label:
            tk.Label(head, text="   " + param.label, font=T.F_SMALL, fg=T.MUTED, bg=T.PANEL,
                     anchor="w").pack(side="left")
        self.reset = tk.Label(head, text="↺ valeur du script", font=T.F_SMALL, fg=T.ACCENT, bg=T.PANEL, cursor="hand2")
        self.reset.bind("<Button-1>", lambda e: self.clear())

        self.override = None            # booléens : None = valeur du script
        self.entry = self.switch = self.state = self.picker = None
        if param.kind == "choice":
            self.picker = ChoiceField(self.frame, param.options, param.default, command=self._changed)
            if isinstance(saved, list):
                self.picker.set(saved)
            self.picker.pack(fill="x")
        elif param.kind == "bool":
            if isinstance(saved, bool):
                self.override = saved
            line = tk.Frame(self.frame, bg=T.PANEL)
            line.pack(fill="x")
            self.switch = Switch(line, value=self._effective(), command=self._toggled, bg=T.PANEL)
            self.switch.pack(side="left")
            self.state = tk.Label(line, font=T.F_UI, fg=T.TEXT, bg=T.PANEL)
            self.state.pack(side="left", padx=S(10))
        else:
            self.entry = PlaceholderEntry(self.frame, placeholder=display_default(param), mono=True)
            if isinstance(saved, str):
                self.entry.var.set(saved)
            self.entry.pack(fill="x")
            self.entry.var.trace_add("write", lambda *_: self._changed())
            if param.kind in ("datetime", "date"):
                hint = DATE_ONLY_HINT if param.kind == "date" else DATE_FORMAT_HINT
                tk.Label(self.frame, text="Format : " + hint, font=T.F_SMALL, fg=T.MUTED, bg=T.PANEL,
                         anchor="w").pack(fill="x", pady=(S(3), 0))
        self.error = tk.Label(self.frame, font=T.F_SMALL, fg=T.DANGER, bg=T.PANEL, anchor="w")
        self._refresh()

    def _effective(self) -> bool:
        return self.override if self.override is not None else bool(self.param.default)

    def _toggled(self, value):
        self.override = value
        self._changed()

    def _changed(self):
        self._refresh()
        self.on_change()

    def clear(self):
        if self.entry is not None:
            self.entry.var.set("")
        elif self.picker is not None:
            self.picker.set(None)
        else:
            self.override = None
            self.switch.set(self._effective())
        self._changed()

    def _refresh(self):
        if self.picker is not None:
            has = self.picker.selected is not None
            if self.picker.selected == []:
                self.error.configure(text="Choisissez au moins une valeur")
                self.error.pack(fill="x", pady=(S(3), 0))
            else:
                self.error.pack_forget()
        elif self.entry is not None:
            has = self.entry.var.get() != ""
            ok, msg = (True, "") if not has else parse_value(self.param.kind, self.entry.var.get())
            self.entry.set_invalid(not ok)
            if ok:
                self.error.pack_forget()
            else:
                self.error.configure(text=msg)
                self.error.pack(fill="x", pady=(S(3), 0))
        else:
            has = self.override is not None
            self.state.configure(text="Activé" if self._effective() else "Désactivé")
            self.switch.set(self._effective())
        if has:
            self.reset.pack(side="right")
        else:
            self.reset.pack_forget()

    def result(self):
        """(a_une_valeur, valeur_typée, texte_à_mémoriser, erreur)"""
        if self.picker is not None:
            chosen = self.picker.selected
            if chosen is None:
                return False, None, None, None
            if not chosen:
                return False, None, None, "Choisissez au moins une valeur"
            return True, chosen, chosen, None
        if self.entry is None:
            if self.override is None:
                return False, None, None, None
            return True, self.override, self.override, None
        text = self.entry.var.get()
        if text == "":
            return False, None, None, None
        ok, value = parse_value(self.param.kind, text)
        return (True, value, text, None) if ok else (False, None, text, value)


class ParamsForm(tk.Frame):
    def __init__(self, master, on_change=None):
        super().__init__(master, bg=T.PANEL)
        self.rows: dict = {}
        self.on_change = on_change or (lambda: None)

    @property
    def has_params(self) -> bool:
        return bool(self.rows)

    def set_params(self, params, saved: dict, keep_current: bool = False) -> None:
        if keep_current:
            saved = {**saved, **self.raw_values()}
        for child in self.winfo_children():
            child.destroy()
        self.rows = {}
        for p in params:
            if p.name in self.rows:
                continue
            value = saved.get(p.name)
            expected = bool if p.kind == "bool" else list if p.kind == "choice" else str
            if not isinstance(value, expected):
                value = None
            row = _Row(self, p, value, self.on_change)
            row.frame.pack(fill="x", pady=(0, S(14)))
            self.rows[p.name] = row

    def raw_values(self) -> dict:
        """Valeurs à mémoriser (uniquement celles que l'utilisateur a renseignées)."""
        out = {}
        for name, row in self.rows.items():
            has, _value, raw, _err = row.result()
            if raw is not None:
                out[name] = raw
        return out

    def collect(self):
        """(surcharges typées, erreurs) — les erreurs : {variable: message}."""
        overrides, errors = {}, {}
        for name, row in self.rows.items():
            has, value, _raw, err = row.result()
            if err:
                errors[name] = err
            elif has:
                overrides[name] = value
        return overrides, errors

    def focus_first_error(self, errors: dict) -> None:
        for name in errors:
            row = self.rows.get(name)
            if row and row.entry:
                row.entry.focus()
                return
