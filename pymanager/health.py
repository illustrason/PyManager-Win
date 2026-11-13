"""Entretien de l'environnement : paquets inutilisés, manquants, non déclarés, mises à jour.

Tout est calculé à partir de l'analyse des ``import`` des scripts et des métadonnées des
paquets installés. C'est une heuristique : d'où une validation par l'utilisateur avant
toute suppression.
"""
from __future__ import annotations

import codecs
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .scanner import imports_of, walk_python_files
from .literals import read_source

PROTECTED = {"pip", "setuptools", "wheel", "pkg-resources"}

# Paquets dont le nom d'import ne se déduit pas du nom du paquet
IMPORT_ALIASES = {
    "pillow": "PIL", "opencv-python": "cv2", "opencv-python-headless": "cv2",
    "opencv-contrib-python": "cv2", "pyyaml": "yaml", "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn", "python-dateutil": "dateutil", "pyserial": "serial",
    "pycryptodome": "Crypto", "python-dotenv": "dotenv", "ffmpeg-python": "ffmpeg",
    "attrs": "attr", "pyside6": "PySide6", "pyside2": "PySide2", "pyqt5": "PyQt5",
    "pyqt6": "PyQt6", "pywin32": "win32api", "msgpack-python": "msgpack",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# --------------------------------------------------------------------------- requirements
@dataclass
class Req:
    raw_name: str
    norm: str
    extras: frozenset
    spec: str
    file: Path
    index: int

    @property
    def pinned(self):
        m = re.search(r"(?<![=!<>~])==\s*([^\s,;#]+)", self.spec)
        return m.group(1) if m else None


_LINE_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?\s*(.*)$")


def parse_requirement_line(line: str):
    s = re.split(r"\s#", line, maxsplit=1)[0].strip()
    if not s or s.startswith(("#", "-", ".", "/", "git+", "http")):
        return None
    s = s.split(";", 1)[0].strip()
    m = _LINE_RE.match(s)
    if not m:
        return None
    extras = frozenset(normalize(e) for e in (m.group(2) or "").split(",") if e.strip())
    return m.group(1), extras, m.group(3).strip()


def read_requirements_text(path: Path):
    """Retourne (texte, encodage). Gère l'UTF-16 produit par « pip freeze > fichier » sous PowerShell."""
    raw = Path(path).read_bytes()
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252"


def parse_requirements(path: Path) -> list:
    try:
        text, _ = read_requirements_text(path)
    except OSError:
        return []
    out = []
    for i, line in enumerate(text.splitlines()):
        parsed = parse_requirement_line(line)
        if parsed:
            name, extras, spec = parsed
            out.append(Req(name, normalize(name), extras, spec, Path(path), i))
    return out


def find_requirements_files(root: Path) -> list:
    return sorted(
        (p.parent / "requirements.txt" for p in _dirs_with_requirements(root)),
        key=lambda p: str(p).lower(),
    )


def _dirs_with_requirements(root: Path):
    import os
    from .scanner import IGNORED_DIRS
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in IGNORED_DIRS]
        if "requirements.txt" in filenames:
            yield Path(dirpath) / "requirements.txt"


def _rewrite(path: Path, transform) -> None:
    text, enc = read_requirements_text(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    lines = transform(lines)
    out = newline.join(lines) + (newline if lines else "")
    Path(path).write_bytes(out.encode(enc if enc != "utf-8-sig" else "utf-8-sig"))


def remove_from_requirements(path: Path, norms: set) -> None:
    def keep(lines):
        result = []
        for line in lines:
            parsed = parse_requirement_line(line)
            if parsed and normalize(parsed[0]) in norms:
                continue
            result.append(line)
        return result
    _rewrite(path, keep)


def add_to_requirements(path: Path, names: list) -> None:
    path = Path(path)
    if not path.exists():
        path.write_text("\n".join(names) + "\n", encoding="utf-8")
        return
    existing = {normalize(p[0]) for p in map(parse_requirement_line, read_requirements_text(path)[0].splitlines()) if p}
    new = [n for n in names if normalize(n) not in existing]
    if new:
        _rewrite(path, lambda lines: lines + new)


def set_pin(path: Path, norm: str, version: str) -> None:
    def bump(lines):
        out = []
        for line in lines:
            parsed = parse_requirement_line(line)
            if parsed and normalize(parsed[0]) == norm:
                line = re.sub(r"(?<![=!<>~])==\s*[^\s,;#]+", "==" + version, line, count=1)
            out.append(line)
        return out
    _rewrite(path, bump)


# --------------------------------------------------------------------------- inventaire
_INVENTORY_CODE = r"""
import json, sys
import importlib.metadata as md
dists = {}
for d in md.distributions():
    name = d.metadata["Name"]
    if name:
        dists[name] = {"version": d.version, "requires": list(d.requires or [])}
print(json.dumps({
    "dists": dists,
    "modules": {k: list(v) for k, v in md.packages_distributions().items()},
    "stdlib": sorted(sys.stdlib_module_names),
    "python": sys.version.split()[0],
}))
"""


def inventory(py: str) -> dict:
    r = subprocess.run(
        [py, "-c", _INVENTORY_CODE], capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
        errors="replace", timeout=120, creationflags=paths.NO_WINDOW,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "Impossible de lire l'environnement").strip()[-500:])
    return json.loads(r.stdout)


_REQUIRES_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")
_EXTRA_MARKER_RE = re.compile(r"""extra\s*==\s*['"]([^'"]+)['"]""")


def _parse_requires(line: str):
    head, _, marker = line.partition(";")
    m = _REQUIRES_RE.match(head)
    if not m:
        return None
    extras = frozenset(normalize(e) for e in (m.group(2) or "").split(",") if e.strip())
    needed = {normalize(e) for e in _EXTRA_MARKER_RE.findall(marker)}
    return normalize(m.group(1)), extras, needed


def closure(dists: dict, seeds) -> set:
    """Tous les paquets nécessaires à partir de ``seeds`` [(nom normalisé, extras)], dépendances comprises."""
    result, visited, stack = set(), set(), list(seeds)
    while stack:
        name, extras = stack.pop()
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        result.add(name)
        info = dists.get(name)
        if not info:
            continue
        for line in info["requires"]:
            parsed = _parse_requires(line)
            if not parsed:
                continue
            dep, dep_extras, needed = parsed
            if needed and not (needed & extras):
                continue
            stack.append((dep, dep_extras))
    return result


# --------------------------------------------------------------------------- analyse
@dataclass
class Finding:
    kind: str                 # unused_req | orphan | undeclared | missing
    norm: str
    display: str
    version: str = ""
    where: str = ""
    detail: str = ""
    files: list = field(default_factory=list)


@dataclass
class Analysis:
    python: str
    installed: int
    req_files: list
    findings: list
    dists: dict
    reqs: list
    used: set                 # paquets utilisés par au moins un script
    scripts_root: Path


def _mentions(norm: str, source_lower: str) -> bool:
    for variant in {norm, norm.replace("-", "_")}:
        if re.search(r"(?<![\w-])" + re.escape(variant) + r"(?![\w-])", source_lower):
            return True
    return False


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def analyze(root: Path, py: str) -> Analysis:
    inv = inventory(py)
    dists = {normalize(n): {"name": n, **v} for n, v in inv["dists"].items()}
    mod2dist = {m.lower(): [normalize(d) for d in ds] for m, ds in inv["modules"].items()}
    stdlib = {s.lower() for s in inv["stdlib"]} | {"__future__"}

    req_files = find_requirements_files(root)
    reqs = [r for f in req_files for r in parse_requirements(f)]

    scripts = []   # (chemin, source en minuscules, imports en minuscules)
    local = set()
    for p in walk_python_files(root, include_private=True):
        try:
            src = read_source(p)
        except OSError:
            continue
        scripts.append((p, src.lower(), {i.lower() for i in imports_of(src)}))
        local.add(p.stem.lower())
        local.update(parent.name.lower() for parent in p.parents if parent != root and root in parent.parents)

    def third_party(imports: set) -> set:
        return {i for i in imports if i not in stdlib and i not in local}

    def dists_for(imports: set, unique_only=False) -> set:
        found = set()
        for i in third_party(imports):
            cands = mod2dist.get(i, [])
            if cands and (not unique_only or len(cands) == 1):
                found.update(cands)
        return found

    findings: list = []

    # 1) Entrées de requirements qu'aucun script de leur portée n'utilise
    unused_keys = set()
    for f in req_files:
        scope = [s for s in scripts if f.parent in s[0].parents]
        scope_imports = set().union(*[s[2] for s in scope]) if scope else set()
        scope_dists = dists_for(scope_imports)
        scope_wanted = closure(dists, [(d, frozenset()) for d in scope_dists])
        for r in (x for x in reqs if x.file == f):
            candidates = {r.norm.replace("-", "_"), IMPORT_ALIASES.get(r.norm, "").lower()} - {""}
            used = (
                r.norm in scope_wanted
                or bool(candidates & scope_imports)
                or any(_mentions(r.norm, s[1]) for s in scope)
            )
            if not used:
                unused_keys.add((f, r.norm))
                where = _rel(f, root)
                findings.append(Finding(
                    "unused_req", r.norm, r.raw_name, dists.get(r.norm, {}).get("version", ""),
                    where, "Aucun script de ce dossier ne l'utilise", [f],
                ))

    # 2) Entrées non installées (et utiles)
    for r in reqs:
        if (r.file, r.norm) not in unused_keys and r.norm not in dists:
            findings.append(Finding("missing", r.norm, r.raw_name, "", _rel(r.file, root),
                                    "Listé dans les requirements mais non installé — utilisez « Réparer l'installation »", [r.file]))

    # 3) Paquets utilisés par les scripts mais déclarés nulle part
    undeclared = {}
    for p, _, imps in scripts:
        applicable = [r for r in reqs if r.file.parent in p.parents or r.file.parent == p.parent]
        declared = closure(dists, [(r.norm, r.extras) for r in applicable])
        for d in dists_for(imps, unique_only=True) - declared - PROTECTED:
            slot = undeclared.setdefault(d, {"files": set(), "scripts": set()})
            slot["files"].add(p.parent / "requirements.txt")
            slot["scripts"].add(p.name)
    for d, slot in sorted(undeclared.items()):
        findings.append(Finding(
            "undeclared", d, dists[d]["name"], dists[d]["version"],
            ", ".join(sorted(_rel(f, root) for f in slot["files"])),
            "Importé par " + ", ".join(sorted(slot["scripts"])[:3]) + ("…" if len(slot["scripts"]) > 3 else ""),
            sorted(slot["files"]),
        ))

    # 4) Paquets installés dont plus rien n'a besoin
    all_imports = set().union(*[s[2] for s in scripts]) if scripts else set()
    used_dists = dists_for(all_imports)
    seeds = [(r.norm, r.extras) for r in reqs] + [(d, frozenset()) for d in used_dists | PROTECTED]
    wanted = closure(dists, seeds)
    for norm, info in sorted(dists.items()):
        if norm not in wanted:
            findings.append(Finding("orphan", norm, info["name"], info["version"], "environnement",
                                    "Ni utilisé par vos scripts ni requis par un autre paquet"))

    return Analysis(inv["python"], len(dists), req_files, findings, dists, reqs, used_dists, root)


def safe_to_uninstall(a: Analysis, remove_norms: set, remove_from: dict) -> list:
    """Paquets qu'on peut réellement désinstaller après retrait d'entrées de requirements.

    ``remove_from`` : {nom normalisé: {fichiers dont on retire l'entrée}}. Un paquet encore
    nécessaire (autre fichier, autre paquet, import d'un script) est conservé.
    """
    remaining = [r for r in a.reqs if r.file not in remove_from.get(r.norm, set())]
    wanted = closure(a.dists, [(r.norm, r.extras) for r in remaining] +
                     [(d, frozenset()) for d in a.used | PROTECTED])
    return sorted(n for n in remove_norms if n in a.dists and n not in wanted)


# --------------------------------------------------------------------------- réseau / pip
def outdated(py: str) -> list:
    r = subprocess.run(
        [py, "-m", "pip", "list", "--outdated", "--format=json", "--disable-pip-version-check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        timeout=300, creationflags=paths.NO_WINDOW,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "pip a échoué").strip()[-500:])
    try:
        return json.loads(r.stdout or "[]")
    except ValueError:
        return []


def snapshot_freeze(py: str, keep: int = 10):
    """Enregistre l'état exact de l'environnement (pip freeze) dans data/freeze/."""
    try:
        r = subprocess.run(
            [py, "-m", "pip", "freeze", "--disable-pip-version-check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
            timeout=120, creationflags=paths.NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    paths.FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    target = paths.FREEZE_DIR / time.strftime("freeze-%Y%m%d-%H%M%S.txt")
    target.write_text(r.stdout, encoding="utf-8")
    (paths.FREEZE_DIR / "latest.txt").write_text(r.stdout, encoding="utf-8")
    old = sorted(paths.FREEZE_DIR.glob("freeze-*.txt"))[:-keep]
    for p in old:
        try:
            p.unlink()
        except OSError:
            pass
    return target


def last_snapshot_time():
    latest = paths.FREEZE_DIR / "latest.txt"
    try:
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(latest.stat().st_mtime))
    except OSError:
        return None
