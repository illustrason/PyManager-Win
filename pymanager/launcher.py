"""Exécute un script en remplaçant les variables @expose (le fichier n'est pas modifié).

Usage : python -u launcher.py <script.py> <overrides.json> [arguments du script...]
"""
import json
import os
import sys
import traceback
import types


def main() -> int:
    script = os.path.abspath(sys.argv[1])
    params_file = sys.argv[2]
    extra = sys.argv[3:]

    try:
        with open(params_file, encoding="utf-8") as f:
            overrides = json.load(f)
    finally:
        try:
            os.remove(params_file)
        except OSError:
            pass

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    try:
        from pymanager.literals import compile_with_overrides, read_source
    finally:
        sys.path.remove(root)

    script_dir = os.path.dirname(script)
    os.chdir(script_dir)
    sys.path[0] = script_dir          # comme si le script était lancé directement
    sys.argv = [script] + extra

    code = compile_with_overrides(read_source(script), script, overrides)

    module = types.ModuleType("__main__")
    module.__file__ = script
    sys.modules["__main__"] = module
    try:
        exec(code, module.__dict__)
    except SystemExit:
        raise
    except BaseException as exc:
        # On retire la première entrée (ce lanceur) pour garder une trace identique à un lancement direct
        traceback.print_exception(type(exc), exc, exc.__traceback__.tb_next if exc.__traceback__ else None)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
