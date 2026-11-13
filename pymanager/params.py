"""Conversion des valeurs saisies dans l'interface et mémorisation de la dernière utilisation."""
from __future__ import annotations

import datetime
import re

from . import paths

DATE_FORMAT_HINT = "AAAA-MM-JJ HH:MM:SS  ou  JJ/MM/AAAA HH:MM  (l'heure est facultative)"
DATE_ONLY_HINT = "AAAA-MM-JJ  ou  JJ/MM/AAAA"

_YEAR_FIRST = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_DAY_FIRST = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def parse_date(kind: str, text: str):
    """Date saisie -> (ok, texte ISO normalisé) ou (False, message). Sans heure : minuit."""
    t = text.strip()
    hint = DATE_ONLY_HINT if kind == "date" else DATE_FORMAT_HINT
    m = _YEAR_FIRST.match(t)
    if m:
        year, month, day = (int(m.group(i)) for i in (1, 2, 3))
    else:
        m = _DAY_FIRST.match(t)
        if not m:
            return False, "Date attendue : " + hint
        day, month, year = (int(m.group(i)) for i in (1, 2, 3))
    hour, minute, second = (int(g) if g else 0 for g in m.group(4, 5, 6))
    if kind == "date" and m.group(4):
        return False, "Date attendue : " + hint
    try:
        moment = datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False, "Date ou heure invalide"
    return True, moment.strftime("%Y-%m-%d" if kind == "date" else "%Y-%m-%d %H:%M:%S")


def parse_value(kind: str, text: str):
    """Retourne (ok, valeur) ou (False, message d'erreur).

    Le texte saisi est pris tel quel (équivalent d'un r"..." : les \\ ne sont pas interprétés).
    Les guillemets qui entourent toute la saisie sont retirés, ce qui permet de coller un
    chemin issu de « Copier en tant que chemin » de l'Explorateur Windows.
    """
    if kind == "str":
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1]
        return True, text
    if kind in ("datetime", "date"):
        return parse_date(kind, text)
    t = text.strip()
    try:
        if kind == "int":
            return True, int(t)
        if kind == "float":
            return True, float(t.replace(",", "."))
    except ValueError:
        return False, "Nombre entier attendu" if kind == "int" else "Nombre attendu"
    return False, "Type inconnu"


def display_default(param) -> str:
    """Valeur du script telle qu'elle est affichée dans le champ vide."""
    if param.kind == "str" and param.default == "":
        return "(vide)"
    if param.kind == "datetime":
        return param.default.strftime("%Y-%m-%d %H:%M:%S")
    if param.kind == "date":
        return param.default.strftime("%Y-%m-%d")
    if param.kind == "choice":
        return ", ".join(str(v) for v in param.default)
    return str(param.default)


class ParamStore:
    """Dernières valeurs saisies, par script : {chemin relatif: {variable: texte | booléen | liste}}."""

    def __init__(self, path=None):
        self.path = path or paths.PARAMS_FILE
        data = paths.load_json(self.path, {})
        self.data = data if isinstance(data, dict) else {}

    def get(self, key: str) -> dict:
        value = self.data.get(key)
        return dict(value) if isinstance(value, dict) else {}

    def set(self, key: str, values: dict) -> None:
        if values:
            if self.data.get(key) == values:
                return
            self.data[key] = values
        elif key in self.data:
            del self.data[key]
        else:
            return
        paths.save_json(self.path, self.data)
