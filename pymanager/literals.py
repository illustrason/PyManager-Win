"""Détection et injection des variables exposées avec ``@expose``.

Exemple dans un script :

    INPUT_DIR = "input"   # Dossier source @expose
    BITRATE = "320k"      # @expose

Uniquement la bibliothèque standard : ce module est aussi chargé par le lanceur,
qui s'exécute dans l'environnement des scripts.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass

EXPOSE_RE = re.compile(r"@expose\b")


@dataclass
class Param:
    name: str
    kind: str        # "str" | "int" | "float" | "bool"
    default: object
    label: str
    line: int


def read_source(path) -> str:
    """Lit un script en respectant son encodage (BOM, déclaration coding:)."""
    try:
        with tokenize.open(str(path)) as f:
            return f.read()
    except (SyntaxError, UnicodeDecodeError):
        with open(path, encoding="latin-1") as f:
            return f.read()


def _literal(node):
    try:
        value = ast.literal_eval(node)
    except Exception:
        return False, None
    if type(value) in (bool, int, float, str):
        return True, value
    return False, None


def _kind(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _comment_targets(source: str) -> dict:
    """{numéro de ligne visée: libellé} pour chaque commentaire contenant @expose.

    Un commentaire en fin de ligne vise sa propre ligne ; un commentaire seul sur sa
    ligne vise l'instruction suivante.
    """
    targets = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type != tokenize.COMMENT or not EXPOSE_RE.search(tok.string):
                continue
            inline = bool(tok.line[: tok.start[1]].strip())
            line = tok.start[0] if inline else tok.start[0] + 1
            label = EXPOSE_RE.sub("", tok.string).strip(" \t#-:–—")
            targets[line] = label
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return targets


def _exposed_statements(tree, targets):
    """Assignations de premier niveau, à valeur littérale simple, portant @expose."""
    found = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            name, value = stmt.targets[0].id, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
            name, value = stmt.target.id, stmt.value
        else:
            continue
        end = getattr(stmt, "end_lineno", None) or stmt.lineno
        line = next((n for n in range(stmt.lineno, end + 1) if n in targets), None)
        if line is None:
            continue
        ok, val = _literal(value)
        if ok:
            found.append((stmt, Param(name, _kind(val), val, targets[line], stmt.lineno)))
    return found


def find_exposed(source: str) -> list:
    targets = _comment_targets(source)
    if not targets:
        return []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    return [p for _, p in _exposed_statements(tree, targets)]


def compile_with_overrides(source: str, filename: str, overrides: dict):
    """Compile le script en remplaçant les valeurs des variables exposées.

    Le fichier sur disque n'est jamais modifié ; les numéros de ligne des erreurs
    restent ceux du script d'origine.
    """
    tree = ast.parse(source, filename)
    for stmt, param in _exposed_statements(tree, _comment_targets(source)):
        if param.name in overrides:
            stmt.value = ast.copy_location(ast.Constant(value=overrides[param.name]), stmt.value)
    return compile(tree, filename, "exec")
