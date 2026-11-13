"""Détection et injection des variables exposées avec ``@expose``.

Exemple dans un script :

    INPUT_DIR = "input"                       # Dossier source @expose
    BITRATE = "320k"                          # @expose
    EXTENSIONS = (".adg", ".als", ".adv")     # menu déroulant (choix multiple) @expose
    START = datetime(2020, 2, 18, 10, 37)     # un seul champ date/heure @expose

Uniquement la bibliothèque standard : ce module est aussi chargé par le lanceur,
qui s'exécute dans l'environnement des scripts.
"""
from __future__ import annotations

import ast
import datetime
import io
import re
import tokenize
from dataclasses import dataclass

EXPOSE_RE = re.compile(r"@expose\b")
MAX_CHOICES = 20           # au-delà, une liste n'est pas proposée comme menu déroulant


@dataclass
class Param:
    name: str
    kind: str        # "str" | "int" | "float" | "bool" | "datetime" | "date" | "choice"
    default: object  # "choice" : tuple des valeurs du script ; "datetime"/"date" : objet datetime/date
    label: str
    line: int
    options: tuple = ()      # "choice" : valeurs proposées (sans doublon, dans l'ordre du script)
    container: str = ""      # "choice" : "tuple" ou "list" (type d'origine de la valeur)


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


def _choices(node):
    """Tuple ou liste non vide de textes (ou de nombres) du même type -> valeurs, sinon None."""
    if not isinstance(node, (ast.Tuple, ast.List)) or not node.elts or len(node.elts) > MAX_CHOICES:
        return None
    values = []
    for elt in node.elts:
        ok, value = _literal(elt)
        if not ok or isinstance(value, bool):
            return None
        values.append(value)
    if len({type(v) for v in values}) != 1:
        return None
    return values


def _date_call(node):
    """datetime(a, m, j[, h, min, s, µs]) ou date(a, m, j) avec des entiers -> (genre, objet), sinon None."""
    if not isinstance(node, ast.Call) or node.keywords or not 3 <= len(node.args) <= 7:
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    if name not in ("datetime", "date"):
        return None
    ints = []
    for arg in node.args:
        ok, value = _literal(arg)
        if not ok or type(value) is not int:
            return None
        ints.append(value)
    if name == "date" and len(ints) != 3:
        return None
    try:
        return name, (datetime.datetime if name == "datetime" else datetime.date)(*ints)
    except (ValueError, OverflowError):
        return None


def _exposable(node):
    """(genre, valeur, options, conteneur) si le nœud peut être exposé, sinon None."""
    ok, val = _literal(node)
    if ok:
        return _kind(val), val, (), ""
    values = _choices(node)
    if values is not None:
        return "choice", tuple(values), tuple(dict.fromkeys(values)), "tuple" if isinstance(node, ast.Tuple) else "list"
    call = _date_call(node)
    if call is not None:
        return call[0], call[1], (), ""
    return None


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
    """Assignations de premier niveau portant @expose, à valeur littérale simple, liste de choix ou date."""
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
        info = _exposable(value)
        if info is not None:
            kind, val, options, container = info
            found.append((stmt, Param(name, kind, val, targets[line], stmt.lineno, options, container)))
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


def _override_node(param: Param, value, original):
    """Nœud AST qui remplace la valeur d'origine ``original`` par la surcharge ``value``."""
    if param.kind == "choice":
        if not isinstance(value, (list, tuple)) or not all(type(v) in (str, int, float) for v in value):
            raise ValueError(f"{param.name} : liste de valeurs attendue")
        elts = [ast.Constant(value=v) for v in value]
        return ast.Tuple(elts=elts, ctx=ast.Load()) if param.container == "tuple" else ast.List(elts=elts, ctx=ast.Load())
    if param.kind in ("datetime", "date"):
        try:
            moment = datetime.datetime.fromisoformat(str(value))
        except ValueError:
            raise ValueError(f"{param.name} : date invalide « {value} »") from None
        parts = (moment.year, moment.month, moment.day)
        if param.kind == "datetime":
            parts += (moment.hour, moment.minute, moment.second)
        return ast.Call(func=original.func, args=[ast.Constant(value=n) for n in parts], keywords=[])
    return ast.Constant(value=value)


def compile_with_overrides(source: str, filename: str, overrides: dict):
    """Compile le script en remplaçant les valeurs des variables exposées.

    Le fichier sur disque n'est jamais modifié ; les numéros de ligne des erreurs
    restent ceux du script d'origine. Formats des surcharges : valeur simple pour
    texte / nombre / booléen, texte ISO « AAAA-MM-JJ HH:MM:SS » pour une date,
    liste des valeurs retenues pour un choix.
    """
    tree = ast.parse(source, filename)
    for stmt, param in _exposed_statements(tree, _comment_targets(source)):
        if param.name in overrides:
            node = _override_node(param, overrides[param.name], stmt.value)
            stmt.value = ast.copy_location(node, stmt.value)
    ast.fix_missing_locations(tree)
    return compile(tree, filename, "exec")
