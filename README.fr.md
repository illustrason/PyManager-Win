# PyManager-Win

[English](README.md)

Une interface Windows pour lancer vos propres scripts Python sans éditeur de code.
PyManager détecte les scripts, prépare l'environnement Python tout seul, affiche des champs pour
les variables que vous choisissez d'exposer, montre la sortie dans une console intégrée et
entretient les bibliothèques installées.

Ce dépôt contient **l'outil** et quelques **scripts de base** (`scripts/public/`).
Vous y ajoutez vos propres scripts.

## Installation

1. Installez [Python 3.10 ou plus récent](https://www.python.org/downloads/) (avec tkinter, coché par défaut).
2. Téléchargez ce dépôt (*Code → Download ZIP*) et décompressez-le où vous voulez, ou clonez-le avec git.
3. Double-cliquez sur **`start.bat`**.

Au premier lancement, `start.bat` crée l'environnement (`.venv`), installe les dépendances de vos scripts
(fichiers `requirements.txt`) puis ouvre PyManager. Les lancements suivants sont immédiats.

> Le fichier `.python-version` (par défaut `3.10`) indique la version de Python à préférer si
> plusieurs sont installées. Supprimez-le pour prendre la plus récente.

## Utilisation

- **Scripts** : la liste de gauche reflète le dossier `scripts/` (mise à jour automatique quand la fenêtre reprend le focus).
  Sélectionnez un script, renseignez ses paramètres, puis **Exécuter** (ou `F5`).
- **Console** : la sortie s'affiche en direct, avec un onglet par exécution. Vous pouvez y taper pour répondre à un
  `input()`, copier (`Ctrl+C` avec une sélection), coller (`Ctrl+V`), et interrompre avec `Ctrl+C` sans sélection
  ou le bouton d'arrêt. Plusieurs scripts peuvent tourner en parallèle.
- **Santé** : diagnostic de l'environnement (voir plus bas).

## Ajouter un script

Déposez un `.py` dans `scripts/public/` ou `scripts/private/` (ou dans un sous-dossier). Fichiers optionnels :

| Fichier | Rôle |
|---|---|
| `mon_script.txt` | Description affichée dans PyManager (sinon : le docstring) |
| `requirements.txt` | Bibliothèques requises par les scripts du dossier et de ses sous-dossiers |
| `_nom.py` | Un nom qui commence par `_` est un module interne : il n'apparaît pas dans la liste |

Les scripts s'exécutent avec leur propre dossier comme dossier courant : `"input"` et `"output"` y sont relatifs.

### Scripts publics et privés

`scripts/public/` et `scripts/private/` sont **fusionnés dans une seule liste** : `public/video/a.py` et
`private/video/b.py` apparaissent dans le même dossier `video`. Si deux scripts se retrouvent au même endroit
avec le même nom, la source est indiquée entre parenthèses, par exemple `convert (private)`.

- `scripts/public/` fait partie de ce dépôt.
- `scripts/private/` est ignoré par ce dépôt (voir `.gitignore`). Ce peut être un **dépôt git privé séparé**
  que vous clonez à cet endroit, voir [Scripts privés](#scripts-privés).

Les dossiers fusionnés se règlent avec `source_dirs` dans `data/settings.json` (voir [Réglages](#réglages)).

## Exposer des variables dans l'interface

Ajoutez `@expose` dans le commentaire de la ligne (ou sur la ligne juste au-dessus) :

```python
INPUT_DIR = "input"      # Dossier d'entrée @expose
BITRATE = "320k"         # Débit binaire @expose
TARGET_SIZE_MB = 19      # @expose
NORMALIZE = True         # Normaliser le volume @expose
```

- Un champ est créé par variable ; le texte du commentaire sert de libellé.
- **Champ vide = valeur du script**, affichée en gris et relue en direct si vous modifiez le fichier.
- Le texte saisi est pris tel quel : `C:\Users\moi\Documents\test` fonctionne sans guillemets ni double `\`
  (les guillemets de « Copier en tant que chemin » sont retirés).
- Texte, entier, décimal et booléen (interrupteur) sont gérés ; le type vient de la valeur du script.
- Les dernières valeurs saisies sont mémorisées par script (`data/params.json`).
- Le fichier du script n'est jamais modifié : PyManager remplace la valeur au lancement, en mémoire.
  Le script reste exécutable seul, avec ses valeurs d'origine.

Limites : seules les affectations de premier niveau à valeur littérale sont exposables (pas de liste, de
dictionnaire ni d'expression comme `Path(...)`). Un script qui crée des sous-processus Python
(`multiprocessing`) ne voit pas les valeurs remplacées dans ses processus enfants.

## Santé de l'environnement

L'onglet **Santé** analyse les `import` de vos scripts et l'environnement installé :

| Catégorie | Signification | Action |
|---|---|---|
| Requirements inutilisés | Entrée de `requirements.txt` qu'aucun script du dossier n'utilise | Supprimer (retire la ligne et désinstalle si plus rien n'en a besoin) |
| Paquets installés mais inutiles | Installé mais ni utilisé par un script ni requis par un autre paquet | Supprimer (désinstalle) |
| Utilisés mais non déclarés | Importé par un script mais absent de tous les `requirements.txt` | Ajouter aux requirements |
| À installer | Listé mais absent de l'environnement | *Réparer l'installation* |
| Mises à jour disponibles | Versions plus récentes sur PyPI (bouton dédié, nécessite Internet) | Mettre à jour (demande confirmation pour les versions épinglées `==`) |

Autres boutons : **Vérifier les conflits** (`pip check`), **Réparer l'installation** (`pip install -r …`),
**Recréer l'environnement** (supprime `.venv` et réinstalle tout).

C'est une analyse heuristique : un paquet appelé uniquement en ligne de commande ou par import dynamique peut apparaître
comme inutilisé. Rien n'est supprimé sans votre validation. Un instantané `pip freeze` est enregistré dans
`data/freeze/` après chaque installation ou désinstallation réussie (les 10 derniers sont conservés).

## Réglages

`data/settings.json` (créé au premier lancement) :

```json
{ "scripts_dir": "scripts", "source_dirs": ["public", "private"] }
```

- `scripts_dir` : le dossier des scripts. Ce peut être un chemin absolu pour utiliser un dossier situé ailleurs.
- `source_dirs` : sous-dossiers de `scripts_dir` fusionnés dans une seule liste. `[]` affiche les dossiers tels quels.

## Scripts privés

Pour garder certains scripts privés tout en partageant l'outil, faites de `scripts/private/` son propre dépôt git :

```
cd scripts
git clone https://github.com/<vous>/<votre-depot-prive>.git private
```

Ce dépôt ignore `scripts/private/` : rien de son contenu ne peut arriver par erreur dans le dépôt public.
Chaque personne qui a accès au dépôt privé le clone de la même façon, ouvre l'onglet **Santé** et clique sur
**Réparer l'installation** pour installer les bibliothèques des scripts privés.

Toute personne ayant accès au dépôt privé peut lire tout son historique : n'y commitez jamais de secrets.

## Dépannage

- *Python introuvable* : installez Python 3.10+ en cochant « tcl/tk and IDLE », puis relancez `start.bat`.
- *PyManager ne s'ouvre pas* : consultez `data/pymanager.log`.
- *Un script plante au lancement* : lisez la console ; la trace d'erreur y est affichée en rouge.

## Développement

Le code est dans `pymanager/` (bibliothèque standard uniquement, aucune dépendance).

## Licence

[MIT](LICENSE)
