"""Conversion des valeurs saisies dans l'interface et mémorisation de la dernière utilisation."""
from __future__ import annotations

from . import paths


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
    return str(param.default)


class ParamStore:
    """Dernières valeurs saisies, par script : {chemin relatif: {variable: texte | booléen}}."""

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
