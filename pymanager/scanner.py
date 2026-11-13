"""Découverte des scripts et lecture de leurs métadonnées (description, paramètres exposés)."""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path

from .literals import Param, find_exposed, read_source

# Dossiers jamais parcourus (en plus de ceux qui commencent par un point)
IGNORED_DIRS = {"__pycache__", "input", "output", "venv", "node_modules", "site-packages"}

GUI_MODULES = {
    "tkinter", "customtkinter", "ttkbootstrap", "PySide2", "PySide6", "PyQt5", "PyQt6",
    "pyqtgraph", "pygame", "wx", "kivy", "dearpygui",
}


DEFAULT_SOURCES = ("public", "private")


@dataclass(frozen=True)
class ScriptInfo:
    path: Path
    rel: str                      # identifiant unique : chemin POSIX relatif à la racine des scripts
    source: str = ""              # dossier source d'origine ("public", "private"…) ou ""

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def display(self) -> str:
        """Chemin affiché dans l'arbre : le dossier source est retiré, les sources sont fusionnées."""
        return self.rel.split("/", 1)[1] if self.source else self.rel


@dataclass
class Details:
    description: str
    has_description_file: bool
    params: list = field(default_factory=list)
    is_gui: bool = False
    stamp: tuple = (0.0, 0.0)     # (mtime du .py, mtime du .txt) pour détecter les changements
    issues: list = field(default_factory=list)   # [(ligne, message)] : @expose ignorés ou mal écrits


def walk_python_files(root: Path, include_private: bool = False):
    """Génère les chemins des .py sous root, en ignorant dossiers techniques et cachés."""
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            (d for d in dirnames if not d.startswith(".") and d.lower() not in IGNORED_DIRS),
            key=str.lower,
        )
        for name in filenames:
            if name.lower().endswith(".py") and (include_private or not name.startswith("_")):
                yield Path(dirpath) / name


def scan(root: Path, sources=DEFAULT_SOURCES) -> list:
    """Scripts visibles. Les fichiers dont le nom commence par « _ » sont des modules internes (masqués).

    Les sous-dossiers de ``root`` listés dans ``sources`` (par défaut « public » et « private »)
    sont fusionnés : ``public/video/a.py`` et ``private/video/b.py`` apparaissent dans le même dossier « video ».
    """
    if isinstance(sources, str):
        sources = [sources]
    names = {str(s).lower() for s in (sources if sources is not None else ()) if s}
    scripts = []
    for p in walk_python_files(root):
        rel = p.relative_to(root).as_posix()
        first, _, rest = rel.partition("/")
        scripts.append(ScriptInfo(p, rel, first if rest and first.lower() in names else ""))
    scripts.sort(key=lambda s: (s.display.lower(), s.rel.lower()))
    return scripts


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def imports_of(source: str) -> set:
    """Noms de modules de premier niveau importés par un code source."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def stamp_of(info: ScriptInfo) -> tuple:
    def mt(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    return (mt(info.path), mt(info.path.with_suffix(".txt")))


def load_details(info: ScriptInfo) -> Details:
    try:
        source = read_source(info.path)
    except OSError:
        source = ""
    txt = info.path.with_suffix(".txt")
    description, has_txt = "", False
    if txt.is_file():
        try:
            description, has_txt = read_text_file(txt).strip(), True
        except OSError:
            pass
    if not description:
        try:
            description = (ast.get_docstring(ast.parse(source)) or "").strip()
        except (SyntaxError, ValueError):
            description = ""
    from .check import check_source
    params, issues = check_source(source)
    return Details(
        description=description,
        has_description_file=has_txt,
        params=params,
        issues=issues,
        is_gui=bool(imports_of(source) & GUI_MODULES),
        stamp=stamp_of(info),
    )
