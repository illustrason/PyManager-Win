# PyManager-Win

[Français](README.fr.md)

A Windows interface to run your own Python scripts without a code editor.
PyManager finds your scripts, sets up the Python environment by itself, shows form fields for the
variables you choose to expose, displays the output in a built-in console and keeps the installed
libraries tidy.

This repository contains the **tool** plus a few **base scripts** (`scripts/public/`).
You add your own scripts next to them.

> The interface is in French for now. Translated labels are given below where it matters.

## Install

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) (with tkinter, which is ticked by default).
2. Download this repository (*Code → Download ZIP*) and unzip it anywhere, or clone it with git.
3. Double-click **`start.bat`**.

On first launch, `start.bat` creates the environment (`.venv`), installs the dependencies of your scripts
(`requirements.txt` files) and opens PyManager. Later launches are immediate.

> The `.python-version` file (default `3.10`) tells which Python to prefer when several are installed.
> Delete it to use the most recent one.

## Use

- **Scripts**: the left list mirrors the `scripts/` folder (refreshed automatically when the window regains focus).
  Select a script, fill in its parameters, then **Run** (or press `F5`).
- **Console**: the output appears live, with one tab per run. You can type in it to answer an `input()`,
  copy (`Ctrl+C` with a selection), paste (`Ctrl+V`), and interrupt with `Ctrl+C` without a selection
  or with the stop button. Several scripts can run at the same time.
- **Santé** (Health): diagnosis of the environment, see below.

## Add a script

Drop a `.py` file in `scripts/public/` or `scripts/private/` (or in a sub-folder of them). Optional files:

| File | Role |
|---|---|
| `my_script.txt` | Description shown in PyManager (otherwise the script's docstring is used) |
| `requirements.txt` | Libraries required by the scripts of the same folder and its sub-folders |
| `_name.py` | A name starting with `_` is an internal module: it does not appear in the list |

Scripts run with their own folder as the working directory, so `"input"` and `"output"` are relative to it.

### Public and private scripts

`scripts/public/` and `scripts/private/` are **merged into one list**: `public/video/a.py` and
`private/video/b.py` both appear in the same `video` folder. If two scripts end up at the same place with
the same name, the source is shown in brackets, for example `convert (private)`.

- `scripts/public/` is part of this repository.
- `scripts/private/` is ignored by this repository (see `.gitignore`). It can be a **separate private git
  repository** that you clone there, see [Private scripts](#private-scripts).

The merged folders are set by `source_dirs` in `data/settings.json` (see [Settings](#settings)).

## Expose variables in the interface

Add `@expose` in the comment of the line (or on the line just above):

```python
INPUT_DIR = "input"      # Input folder @expose
BITRATE = "320k"         # Bit rate @expose
TARGET_SIZE_MB = 19      # @expose
NORMALIZE = True         # Normalize the volume @expose
```

- One field is created per variable; the comment text is used as its label.
- **An empty field means the script's value**. It is shown in grey and re-read live if you edit the file.
- The text you type is taken as is: `C:\Users\me\Documents\test` works without quotes or doubled `\`
  (the quotes added by "Copy as path" are removed).
- Text, integer, decimal and boolean (switch) values are supported; the type comes from the script's value.
- The last values you typed are remembered per script (`data/params.json`).
- The script file is never modified: PyManager replaces the value in memory at launch.
  The script stays runnable on its own, with its original values.

Limits: only top-level assignments of a literal value can be exposed (no list, dictionary or expression
such as `Path(...)`). A script that starts Python sub-processes (`multiprocessing`) does not see the
replaced values in its child processes.

## Environment health

The **Santé** tab analyses the `import`s of your scripts and the installed environment:

| Category | Meaning | Action |
|---|---|---|
| Requirements inutilisés | A `requirements.txt` entry that no script of the folder uses | Remove (deletes the line and uninstalls if nothing else needs it) |
| Paquets installés mais inutiles | Installed, but neither used by a script nor required by another package | Remove (uninstalls) |
| Utilisés mais non déclarés | Imported by a script but missing from every `requirements.txt` | Add to the requirements |
| À installer | Listed but not installed | *Réparer l'installation* |
| Mises à jour disponibles | Newer versions on PyPI (dedicated button, needs Internet) | Update (asks for confirmation on `==` pinned versions) |

Other buttons: **Vérifier les conflits** (`pip check`), **Réparer l'installation** (`pip install -r …`),
**Recréer l'environnement** (deletes `.venv` and reinstalls everything).

The analysis is heuristic: a package used only from the command line or through a dynamic import may be
reported as unused. Nothing is removed without your confirmation. A `pip freeze` snapshot is saved in
`data/freeze/` after every successful install or uninstall (the 10 latest are kept).

## Settings

`data/settings.json` (created on first launch):

```json
{ "scripts_dir": "scripts", "source_dirs": ["public", "private"] }
```

- `scripts_dir`: the scripts folder. It can be an absolute path to use a folder located elsewhere.
- `source_dirs`: sub-folders of `scripts_dir` that are merged into one list. Use `[]` to show the folders as they are.

## Private scripts

To keep some scripts private while sharing the tool, make `scripts/private/` its own git repository:

```
cd scripts
git clone https://github.com/<you>/<your-private-repo>.git private
```

This repository ignores `scripts/private/`, so nothing from it can reach the public repository by accident.
Everyone you give access to the private repository clones it the same way, then opens the **Santé** tab and
clicks **Réparer l'installation** so that the libraries of the private scripts get installed.

Anyone with access to the private repository can read its whole history: never commit secrets there.

## Troubleshooting

- *Python not found*: install Python 3.10+ with "tcl/tk and IDLE" ticked, then run `start.bat` again.
- *PyManager does not open*: check `data/pymanager.log`.
- *A script crashes at launch*: read the console; the traceback is shown in red.

## Development

The code is in `pymanager/` and uses the standard library only, with no dependency.

## License

[MIT](LICENSE)
