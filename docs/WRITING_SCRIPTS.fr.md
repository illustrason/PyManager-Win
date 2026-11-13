# Écrire des scripts pour PyManager-Win

[English](WRITING_SCRIPTS.md)

Ce document est le **cahier des charges pour écrire un script** que PyManager-Win sait lancer : ce que l'outil
en fait, ce qu'il faut livrer et les règles à suivre. Il est écrit pour être envoyé tel quel à une IA, avec votre
demande, à côté de [`script_template.py`](script_template.py) (un exemple qui fonctionne). Pour installer et utiliser
l'outil lui-même, voir le [README](../README.fr.md).

## L'utiliser avec une IA

Envoyez ce fichier et `script_template.py`, puis décrivez le script voulu. Un prompt qui fonctionne bien :

```
Écris un script pour PyManager-Win. Suis le fichier WRITING_SCRIPTS.fr.md joint et pars de script_template.py.

Objectif : <ce que fait le script, en une ou deux phrases>
Entrée : <ce qu'il lit : types de fichiers, dossier, ...>
Sortie : <ce qu'il produit et où>
Réglages que je veux modifier depuis l'interface : <liste, avec une valeur par défaut raisonnable pour chacun>
Besoins : <bibliothèques ou outils externes (ffmpeg...), si tu les connais>
Destination : scripts/<public|private>/<thème>/

Donne-moi : le fichier .py, la description .txt et les lignes à ajouter au requirements.txt (s'il y en a).
Vérifie la checklist en fin de WRITING_SCRIPTS.fr.md avant de répondre.
```

## Ce que PyManager-Win fait d'un script

- Il liste tous les fichiers `.py` de `scripts/public/` et `scripts/private/` (fusionnés dans une seule liste, sous-dossiers conservés).
  Un nom de fichier qui commence par `_` est un module interne et reste masqué.
- Il lance le script avec l'**environnement Python partagé** (Python 3.10 ou plus récent, Windows), avec le
  **dossier du script comme dossier courant**, dans une console intégrée. Le script se comporte comme un module
  `__main__` normal : `if __name__ == "__main__":` fonctionne et `__file__` est le chemin du script.
- Avant le lancement, il peut **remplacer en mémoire la valeur de certaines variables** (celles marquées pour
  l'interface, voir plus bas). Le fichier sur disque n'est jamais modifié et le script reste exécutable seul.
- La variable d'environnement `PYMANAGER=1` est définie pendant l'exécution ; la sortie est lue en UTF-8.

## Ce qu'il faut livrer

| Fichier | Où | Obligatoire |
|---|---|---|
| `mon_script.py` | `scripts/public/<thème>/` (partagé) ou `scripts/private/<thème>/` | oui |
| `mon_script.txt` | à côté du script, même nom | oui : description affichée dans PyManager |
| `requirements.txt` | dans le dossier du script (ou un dossier parent), une entrée par ligne | seulement pour les bibliothèques tierces |

Utilisez des noms en `snake_case` qui disent ce que fait le script, et rangez les scripts par thème (`audio`,
`video`, `file_tools`...). Un nom de script ne commence jamais par `_`.

## Règles

### 1. Les réglages sont en haut, en variables de premier niveau

Tout ce que l'utilisateur peut vouloir changer est une variable **au premier niveau du fichier** (pas dans une
fonction, un `if`, une classe ni `if __name__ == "__main__":`), écrite `NOM = valeur` avec une **valeur littérale**.
Ajoutez `@expose` dans le commentaire de la ligne pour en faire un champ dans PyManager. Le texte du commentaire sert de libellé.

```python
INPUT_DIR = "input"    # Dossier à lire @expose
BITRATE = "320k"       # Débit audio @expose
```

Un commentaire seul sur la ligne du dessus fonctionne aussi (`# Libellé @expose`), mais la forme en fin de ligne est préférable.
Écrivez le marqueur exactement `@expose` : sans espace, en minuscules. Ne l'écrivez dans aucun autre commentaire,
car tout commentaire qui le contient est lu comme une demande d'exposer la variable suivante.

### 2. Quelle valeur donne quel champ

| Écrire | Champ |
|---|---|
| `"texte"` | Champ texte |
| `42` | Champ nombre entier |
| `3.5` | Champ décimal (la virgule est acceptée) |
| `True` / `False` | Interrupteur |
| `datetime(2024, 12, 31, 23, 59)` ou `date(2024, 12, 31)` | Un seul champ date. L'utilisateur saisit `2024-12-31 23:59` ou `31/12/2024 23:59` (heure facultative) et le script reçoit un vrai `datetime` / `date`. Entiers simples uniquement, de 3 à 7 arguments, sans argument nommé. |
| `(".wav", ".mp3")` ou `[1, 2, 3]` | Menu déroulant à cases à cocher. Textes, entiers ou décimaux, tous du même type, de 1 à 20 éléments. Le script reçoit les éléments cochés, sous forme de tuple (ou de liste), dans l'ordre d'origine. Sans modification, c'est la liste complète. |

Non exposables, et ignorés avec un avertissement par `--check` : `None`, les appels (`os.path.join(...)`, `Path(...)`, `os.getcwd()`),
les f-strings, les expressions, les dictionnaires, les ensembles, les listes imbriquées, les tuples de types mélangés,
l'affectation multiple (`A, B = 1, 2`) et toute variable dans un bloc. Utilisez les solutions ci-dessous.

| Vous avez besoin de | Écrivez |
|---|---|
| « aucune valeur » pour un texte | `""` et testez `if not NOM:` |
| « aucune valeur » pour un nombre | `0` (ou `-1`) et testez-le, par exemple `if MAX_FILES:` |
| « pas de limite / jusqu'à la fin » pour un temps | `""` et convertissez-le dans le script |
| Un chemin construit depuis le dossier du script | exposer le texte relatif (`"output"`) et le joindre dans le code : `os.path.join(script_dir, OUTPUT_DIR)`. Un chemin absolu saisi par l'utilisateur est conservé tel quel par `os.path.join` |
| Un choix parmi quelques textes | un champ texte dont les valeurs permises sont écrites dans le libellé (`# Format : "video" ou "audio" @expose`), puis le valider et appeler `sys.exit("Format inconnu ...")` |
| Un réglage que l'utilisateur ne doit pas voir | pas de marqueur `@expose` |

### 3. Comportement des champs (pour choisir de bonnes valeurs par défaut)

- **Un champ vide signifie « utiliser la valeur écrite dans le script »** ; elle s'affiche en gris. Un réglage texte
  ne peut donc pas être mis à une chaîne vide depuis l'interface, et le script doit fonctionner avec ses valeurs par défaut.
- Le texte saisi est utilisé **tel quel**, comme une chaîne brute : `C:\Users\moi\Docs` fonctionne sans doubler les antislashs,
  et les guillemets ajoutés par « Copier en tant que chemin » sont retirés.
- Les dernières valeurs saisies sont mémorisées par script.
- Donnez à chaque réglage exposé une valeur par défaut raisonnable, qui permet de lancer le script dès que les fichiers sont en place.
- Ne lisez pas les valeurs exposées dans `sys.argv`, les variables d'environnement ou des fichiers : utilisez les variables.

### 4. Fichiers et dossiers

- Le dossier courant est celui du script. Par défaut, lisez dans `input/` et écrivez dans `output/` à côté du script
  (`INPUT_DIR = "input"`, `OUTPUT_DIR = "output"`), et créez le dossier de sortie avec
  `os.makedirs(OUTPUT_DIR, exist_ok=True)`.
- Ne modifiez ni ne supprimez jamais les fichiers d'entrée de l'utilisateur, sauf si c'est tout l'objet du script (dites-le dans le `.txt`).
- Les fichiers temporaires vont dans un dossier `temp/` que le script supprime à la fin.
- N'écrivez pas de chemins personnels en dur (`C:\Users\...`, `D:\...`), ni de chemins d'outils propres à votre machine.
- N'utilisez pas `multiprocessing` : les processus enfants ne verraient pas les valeurs remplacées.

### 5. Comportement dans la console

- Utilisez `print()` pour indiquer l'avancement ; la sortie s'affiche en direct. Le retour chariot (`\r`) et les couleurs ANSI fonctionnent.
- `input()` fonctionne (l'utilisateur tape dans la console), mais préférez des réglages : un script qui ne pose pas de question se relance plus facilement.
- Échouez clairement : laissez remonter les exceptions ou utilisez `sys.exit("message clair")`. Un code de sortie non nul s'affiche comme une erreur.
- N'utilisez pas `pause`, `os.system("cls")` ni rien qui attende une fenêtre de terminal visible.
- Un script peut ouvrir sa propre fenêtre (tkinter, PySide...) ; PyManager l'indique.

### 6. Dépendances

- Préférez la bibliothèque standard. Les bibliothèques tierces vont dans le `requirements.txt` du dossier du script,
  avec leur nom pip, une par ligne. N'épinglez une version (`==`) que si le script exige cette version précise.
- Les programmes externes (ffmpeg, Deno...) **ne sont pas installés** par PyManager : ils doivent être dans le `PATH`.
  Dites-le dans le `.txt` et échouez avec un message clair s'ils manquent (`shutil.which("ffmpeg")`).

### 7. La description `.txt`

Même nom que le script, affichée dans PyManager au-dessus des champs. Une à quatre phrases courtes : ce que fait le script,
ce qu'il lit et écrit, et ce que l'utilisateur doit avoir installé. **Ne listez pas les réglages exposés** : les champs
les montrent déjà, avec leurs libellés. Ne mentionnez que les réglages non exposés qui valent la peine d'être connus.
Rédigez-la en anglais pour `scripts/public/`.

### 8. Scripts publics

Les scripts de `scripts/public/` sont publiés : rédigez commentaires, messages et descriptions en anglais, et
ne mettez aucun nom, chemin, URL personnels ni aucun secret (jetons, cookies, mots de passe).

## Contrôler le script

```
python -m pymanager --check scripts\public\video\mon_script.py
```

(à lancer depuis le dossier du projet, avec un Python 3.10+ quelconque ou `.venv\Scripts\python` ; sans chemin, tous les scripts sont contrôlés). La commande liste les champs que PyManager
affichera et, pour chaque `@expose` qui ne donne rien, la ligne et la raison. Collez le résultat à l'IA pour qu'elle corrige. Les mêmes
avertissements apparaissent sous les paramètres dans PyManager. Exemple :

```
scripts/private/audio/mon_script.py
  Champs exposés (1) :
    ligne 4    OUTPUT_DIR               texte                              'output'  — Dossier de sortie
  Avertissements (1) :
    ligne 9    @expose ignoré : variable dans un bloc (fonction, if, boucle, classe, ...)
```

## Checklist avant de répondre

- [ ] Chaque réglage est un `NOM = littéral` de premier niveau, et chaque réglage destiné à l'utilisateur porte `@expose` avec un libellé court.
- [ ] Ni `None`, ni appel, ni f-string, ni dictionnaire, ni expression derrière un `@expose`.
- [ ] Le marqueur `@expose` n'apparaît que sur les lignes de réglages.
- [ ] Les valeurs par défaut sont raisonnables et le script tourne avec ; « vide = valeur du script » est respecté.
- [ ] Les chemins sont relatifs (`input`, `output`), sans chemin personnel ; le dossier de sortie est créé ; les entrées ne sont pas modifiées.
- [ ] Les erreurs se terminent par une exception ou `sys.exit("message")` ; rien n'attend un terminal.
- [ ] `mon_script.txt` est fourni, court, et ne liste pas les réglages exposés.
- [ ] Les bibliothèques tierces sont listées pour `requirements.txt` ; les programmes externes sont vérifiés au démarrage.
- [ ] Script public : anglais uniquement et rien de personnel.
- [ ] Le fichier passe `python -m pymanager --check` sans avertissement.
