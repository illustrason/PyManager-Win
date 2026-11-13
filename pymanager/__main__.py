"""Point d'entrée : ``python -m pymanager`` ouvre l'interface, ``--install`` installe les dépendances,
``--check [script…]`` contrôle les variables exposées (voir check.py)."""
import sys


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--check":
        from .check import main as check
        return check(args[1:])
    if "--install" in args:
        from .cli import install
        return install()
    from .app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
