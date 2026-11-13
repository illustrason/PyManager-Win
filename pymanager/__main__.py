"""Point d'entrée : ``python -m pymanager`` ouvre l'interface, ``--install`` installe les dépendances."""
import sys


def main() -> int:
    if "--install" in sys.argv[1:]:
        from .cli import install
        return install()
    from .app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
