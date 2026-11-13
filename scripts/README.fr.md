# Dossier des scripts

[English](README.md)

| Dossier | Contenu | Git |
|---|---|---|
| `public/` | Scripts de base livrés avec PyManager-Win | Fait partie du dépôt public |
| `private/` | Vos propres scripts | Ignoré ici ; peut être un dépôt privé séparé cloné dans ce dossier |

PyManager fusionne les deux dossiers dans une seule liste. Les scripts peuvent être rangés dans des sous-dossiers ;
un sous-dossier de même nom présent des deux côtés n'apparaît qu'une fois.

## Ce qui est reconnu

| Fichier | Rôle |
|---|---|
| `mon_script.py` | Le script, affiché dans la liste (un nom commençant par `_` est un module interne et reste masqué) |
| `mon_script.txt` | Description affichée dans PyManager (à défaut : le docstring du script) |
| `requirements.txt` | Bibliothèques nécessaires aux scripts du même dossier et de ses sous-dossiers |

Les dossiers nommés `input`, `output`, `venv`, `__pycache__` et ceux qui commencent par un point sont ignorés.

## Exposer une variable dans l'interface

Ajoutez `@expose` dans le commentaire de la ligne :

```python
INPUT_DIR = "input"   # Dossier source @expose
BITRATE = "320k"      # Débit binaire @expose
TARGET_SIZE_MB = 19   # @expose
```

PyManager affiche alors un champ par variable. Champ vide = valeur du script.
Seules les valeurs simples (texte, nombre entier ou décimal, booléen) peuvent être exposées.
