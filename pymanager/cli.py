"""Commandes sans interface, appelées par start.bat."""
from __future__ import annotations

import subprocess
import sys

from . import health, paths


def _say(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def install() -> int:
    """Installe les dépendances de tous les requirements.txt trouvés dans le dossier des scripts."""
    settings = paths.load_settings()
    root = paths.scripts_root(settings)
    files = health.find_requirements_files(root)
    if not files:
        _say(f"Aucun requirements.txt dans {root} : rien a installer.")
        return 0
    py = paths.script_python()
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    for f in files:
        _say(f"  - {f}")
        cmd += ["-r", str(f)]
    _say("Installation en cours...")
    rc = subprocess.call(cmd)
    if rc == 0:
        health.snapshot_freeze(py)
    return rc


if __name__ == "__main__":
    sys.exit(install())
