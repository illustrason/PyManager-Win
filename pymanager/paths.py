"""Chemins du projet, réglages utilisateur et petits utilitaires JSON."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
PARAMS_FILE = DATA_DIR / "params.json"
FREEZE_DIR = DATA_DIR / "freeze"
LOG_FILE = DATA_DIR / "pymanager.log"
LAUNCHER = ROOT / "pymanager" / "launcher.py"
START_BAT = ROOT / "start.bat"

IS_WINDOWS = os.name == "nt"
# Évite qu'une fenêtre de console clignote à chaque sous-processus lancé depuis pythonw.exe
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DEFAULT_SETTINGS = {
    "scripts_dir": "scripts",   # relatif à la racine de PyManager, ou chemin absolu
    "source_dirs": ["public", "private"],   # sous-dossiers de scripts_dir fusionnés dans une seule liste
    "geometry": "1200x760",
    "last_script": None,
}


def load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    """Écriture atomique : on n'abîme jamais un fichier existant en cas d'arrêt brutal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def load_settings() -> dict:
    data = load_json(SETTINGS_FILE, {})
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    return settings


def save_settings(settings: dict) -> None:
    save_json(SETTINGS_FILE, settings)


def scripts_root(settings: dict) -> Path:
    p = Path(str(settings.get("scripts_dir") or "scripts")).expanduser()
    return p if p.is_absolute() else ROOT / p


def script_python() -> str:
    """Interpréteur utilisé pour exécuter les scripts : celui du .venv du projet."""
    sub = Path("Scripts") / "python.exe" if IS_WINDOWS else Path("bin") / "python"
    cand = ROOT / ".venv" / sub
    if cand.exists():
        return str(cand)
    exe = Path(sys.executable)
    if IS_WINDOWS and exe.name.lower() == "pythonw.exe":
        alt = exe.with_name("python.exe")
        if alt.exists():
            return str(alt)
    return str(exe)


def script_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYMANAGER"] = "1"
    return env
