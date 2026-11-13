"""Contrôle d'un script : champs exposés par @expose et raisons des @expose ignorés.

    python -m pymanager --check scripts/public/video/mon_script.py
    python -m pymanager --check                  (tous les scripts du dossier des scripts)

Uniquement la bibliothèque standard.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

from . import literals
from .literals import MAX_CHOICES, EXPOSE_RE

KIND_NAMES = {
    "str": "texte", "int": "entier", "float": "décimal", "bool": "booléen",
    "datetime": "date et heure", "date": "date", "choice": "menu déroulant (choix multiple)",
}

# Fautes de frappe courantes : « @exp ose », « @expos », « @Expose », « @exposé »…
_TYPO_RE = re.compile(r"@\s*e\s*x\s*p\s*o\s*s\w*", re.IGNORECASE)


def _ignored_reason(stmt, value) -> str:
    """Pourquoi la valeur d'une affectation de premier niveau n'est pas exposable."""
    if isinstance(value, ast.Constant):
        if value.value is None:
            return ('None ne peut pas être exposé : utilisez "" (texte) ou 0 (nombre) pour dire « aucune valeur » '
                    "et testez-le dans le script")
        return f"type {type(value.value).__name__} non géré (texte, entier, décimal et booléen seulement)"
    if isinstance(value, (ast.Tuple, ast.List)):
        if not value.elts:
            return "liste vide : rien à proposer dans le menu déroulant"
        if len(value.elts) > MAX_CHOICES:
            return f"plus de {MAX_CHOICES} éléments : trop pour un menu déroulant"
        if any(isinstance(e, (ast.Tuple, ast.List, ast.Dict, ast.Set)) for e in value.elts):
            return "liste imbriquée non gérée"
        if all(isinstance(e, ast.Constant) for e in value.elts):
            return ("les éléments doivent être tous des textes, ou tous des entiers, ou tous des décimaux "
                    "(pas de booléens ni de types mélangés)")
        return "les éléments d'une liste exposée doivent être des valeurs littérales"
    if isinstance(value, ast.Call):
        name = getattr(value.func, "id", None) or getattr(value.func, "attr", None)
        if name in ("datetime", "date"):
            return ("datetime(...) / date(...) doit avoir 3 à 7 entiers positionnels, sans argument nommé, "
                    "et former une date valide")
        return f"appel de fonction ({name or '...'}) : écrivez une valeur littérale"
    if isinstance(value, ast.Dict):
        return "dictionnaire non géré"
    if isinstance(value, ast.Set):
        return "ensemble (set) non géré : utilisez un tuple ou une liste"
    if isinstance(value, ast.JoinedStr):
        return "f-string : écrivez un texte littéral"
    return "expression non littérale : écrivez une valeur littérale (texte, nombre, booléen, date, liste)"


def _line_issue(tree, line: int) -> str:
    """Raison pour laquelle le @expose visant ``line`` n'a donné aucun champ."""
    top = {id(s) for s in tree.body}
    nested = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            end = getattr(node, "end_lineno", None) or node.lineno
            if node.lineno <= line <= end:
                if id(node) in top:
                    return _top_level_issue(node)
                nested = node
    if nested is not None:
        return ("variable dans un bloc (fonction, if, boucle, classe, « if __name__ == '__main__' ») : "
                "déplacez-la au premier niveau du fichier, puis utilisez-la dans le bloc")
    return "aucune affectation sur cette ligne (ou sur la suivante pour un commentaire placé seul au-dessus)"


def _top_level_issue(stmt) -> str:
    if isinstance(stmt, ast.AugAssign):
        return "opération « += » : écrivez une affectation simple « NOM = valeur »"
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return "une seule variable par ligne (pas d'affectation multiple ni de déballage)"
        return _ignored_reason(stmt, stmt.value)
    if stmt.value is None:
        return "variable annotée sans valeur"
    if not isinstance(stmt.target, ast.Name):
        return "la cible doit être un simple nom de variable"
    return _ignored_reason(stmt, stmt.value)


def check_source(source: str):
    """(champs exposés, avertissements) ; les avertissements sont des couples (ligne, message)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None) or 1
        return [], [(line, f"erreur de syntaxe : {exc.msg if hasattr(exc, 'msg') else exc}")]
    issues = []
    typo_lines = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and not EXPOSE_RE.search(tok.string) and _TYPO_RE.search(tok.string):
                typo_lines.add(tok.start[0])
                issues.append((tok.start[0], f"« {_TYPO_RE.search(tok.string).group(0)} » : faute de frappe probable, "
                                              "écrivez exactement @expose (en minuscules, sans espace)"))
    except (tokenize.TokenError, IndentationError):
        pass

    targets = literals._comment_targets(source)
    found = literals._exposed_statements(tree, targets)
    params = [p for _, p in found]
    covered = set()
    for stmt, _ in found:
        end = getattr(stmt, "end_lineno", None) or stmt.lineno
        covered.update(range(stmt.lineno, end + 1))
    for line in sorted(targets):
        if line not in covered:
            issues.append((line, "@expose ignoré : " + _line_issue(tree, line)))
    seen = {}
    for p in params:
        if p.name in seen:
            issues.append((p.line, f"{p.name} est déjà exposée ligne {seen[p.name]} : un seul champ sera affiché"))
        else:
            seen[p.name] = p.line
    issues.sort()
    return params, issues


def format_report(path, params, issues) -> str:
    lines = [str(path)]
    if params:
        lines.append(f"  Champs exposés ({len(params)}) :")
        for p in params:
            shown = literals_display(p)
            label = f"  — {p.label}" if p.label else ""
            lines.append(f"    ligne {p.line:<4} {p.name:<24} {KIND_NAMES.get(p.kind, p.kind):<34} {shown}{label}")
    else:
        lines.append("  Aucun champ exposé.")
    if issues:
        lines.append(f"  Avertissements ({len(issues)}) :")
        lines += [f"    ligne {n:<4} {msg}" for n, msg in issues]
    else:
        lines.append("  Aucun avertissement.")
    return "\n".join(lines)


def literals_display(p) -> str:
    from .params import display_default
    return display_default(p) if p.kind != "str" else repr(p.default)


def main(args) -> int:
    from . import paths, scanner
    targets = []
    for arg in args:
        path = Path(arg)
        if path.is_dir():
            targets += list(scanner.walk_python_files(path, include_private=True))
        else:
            targets.append(path)
    if not targets:
        root = paths.scripts_root(paths.load_settings())
        targets = list(scanner.walk_python_files(root))
    if not targets:
        print("Aucun script à contrôler.")
        return 0
    warnings = 0
    for path in sorted(targets):
        try:
            source = literals.read_source(path)
        except OSError as exc:
            print(f"{path}\n  Lecture impossible : {exc}\n")
            warnings += 1
            continue
        params, issues = check_source(source)
        warnings += len(issues)
        text = format_report(path, params, issues)
        try:
            print(text + "\n")
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii") + "\n")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
