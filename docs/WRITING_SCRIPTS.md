# Writing scripts for PyManager-Win

[Français](WRITING_SCRIPTS.fr.md)

This document is the **brief for writing a script** that PyManager-Win can run: what the tool does with
it, what to deliver, and the rules to follow. It is written to be sent as-is to an AI assistant together
with your request, next to [`script_template.py`](script_template.py) (a working example). For installing and using the
tool itself, see the [README](../README.md).

## Use it with an AI

Send this file and `script_template.py`, then describe the script you want. A prompt that works well:

```
Write a script for PyManager-Win. Follow the attached WRITING_SCRIPTS.md and base the code on script_template.py.

Goal: <what the script does, in one or two sentences>
Input: <what it reads: file types, folder, ...>
Output: <what it produces and where>
Settings I want to change from the interface: <list, with a sensible default for each>
Needs: <libraries or external tools (ffmpeg...), if you know them>
Destination: scripts/<public|private>/<topic>/

Give me: the .py file, the .txt description and the requirements.txt lines to add (if any).
Check the checklist at the end of WRITING_SCRIPTS.md before answering.
```

## What PyManager-Win does with a script

- It lists every `.py` file under `scripts/public/` and `scripts/private/` (merged in one list, sub-folders kept).
  A file name starting with `_` is an internal module and is hidden.
- It runs the script with the **shared Python environment** (Python 3.10 or newer, Windows), with the
  **script's own folder as the working directory**, in a built-in console. The script behaves as a normal
  `__main__` module: `if __name__ == "__main__":` works and `__file__` is the script path.
- Before running, it can **replace the value of some variables in memory** (the ones marked for the
  interface, see below). The file on disk is never modified, and the script still runs on its own.
- The `PYMANAGER=1` environment variable is set while running; output is read as UTF-8.

## What to deliver

| File | Where | Required |
|---|---|---|
| `my_script.py` | `scripts/public/<topic>/` (shared) or `scripts/private/<topic>/` | yes |
| `my_script.txt` | next to the script, same name | yes: description shown in PyManager |
| `requirements.txt` | in the script's folder (or a parent folder), one entry per line | only for third-party libraries |

Use `snake_case` names that say what the script does, and group scripts by topic folder (`audio`,
`video`, `file_tools`...). Never start a script name with `_`.

## Rules

### 1. Settings go at the top, as plain top-level variables

Everything the user may want to change is a variable **at the top level of the file** (not inside a function,
`if`, class or `if __name__ == "__main__":`), written as `NAME = value` with a **literal value**.
Add `@expose` in the comment of the line to make it a field in PyManager. The comment text becomes the label.

```python
INPUT_DIR = "input"    # Folder to read @expose
BITRATE = "320k"       # Audio bit rate @expose
```

A comment alone on the line above also works (`# Label @expose`), but the end-of-line form is preferred.
Write the marker exactly as `@expose`: no space inside, lowercase. Never write it in any other comment,
because every comment that contains it is read as a request to expose the next variable.

### 2. Which values give which field

| Write | Field |
|---|---|
| `"text"` | Text field |
| `42` | Whole number field |
| `3.5` | Decimal field (a comma is accepted) |
| `True` / `False` | Switch |
| `datetime(2024, 12, 31, 23, 59)` or `date(2024, 12, 31)` | One date field. The user types `2024-12-31 23:59` or `31/12/2024 23:59` (time optional) and the script receives a real `datetime` / `date`. Plain integers only, 3 to 7 arguments, no keyword arguments. |
| `(".wav", ".mp3")` or `[1, 2, 3]` | Drop-down with check boxes. Texts, whole numbers or decimals, all of the same type, 1 to 20 items. The script receives the checked ones, as a tuple (or list), in the original order. Nothing changed means the full list. |

Not exposed, and ignored with a warning by `--check`: `None`, calls (`os.path.join(...)`, `Path(...)`, `os.getcwd()`),
f-strings, expressions, dictionaries, sets, nested lists, tuples of mixed types, multiple assignment
(`A, B = 1, 2`), and any variable inside a block. Use the workarounds below.

| You need | Write |
|---|---|
| "no value" for a text | `""` and test `if not NAME:` |
| "no value" for a number | `0` (or `-1`) and test it, e.g. `if MAX_FILES:` |
| "no limit / end of file" for a time | `""` and convert it in the script |
| A path built from the script folder | expose the relative text (`"output"`) and join it in the code: `os.path.join(script_dir, OUTPUT_DIR)`. An absolute path typed by the user is kept as is by `os.path.join` |
| One choice among a few texts | a text field whose allowed values are written in the label (`# Format: "video" or "audio" @expose`), then validate it and call `sys.exit("Unknown format ...")` |
| A setting the user should not see | no `@expose` marker |

### 3. How the fields behave (so the defaults make sense)

- **An empty field means "use the value written in the script"**; it is shown in grey. So a text setting
  cannot be set to an empty string from the interface, and the script must work with its defaults.
- Typed text is used **as is**, like a raw string: `C:\Users\me\Docs` works without doubling the backslashes,
  and the quotes added by "Copy as path" are removed.
- The last values typed are remembered per script.
- Give every exposed setting a sensible default that lets the script run as soon as the files are in place.
- Do not read the exposed values from `sys.argv`, environment variables or files: use the variables.

### 4. Files and folders

- The working directory is the script's folder. By default, read from `input/` and write to `output/` next to the
  script (`INPUT_DIR = "input"`, `OUTPUT_DIR = "output"`), and create the output folder with
  `os.makedirs(OUTPUT_DIR, exist_ok=True)`.
- Never modify or delete the user's input files unless that is the whole point of the script (say so in the `.txt`).
- Scratch files go in a `temp/` folder that the script removes at the end.
- Do not hard-code personal paths (`C:\Users\...`, `D:\...`). Do not hard-code machine-specific tools paths either.
- Do not use `multiprocessing`: child processes would not see the replaced values.

### 5. Console behavior

- Use `print()` to report progress; the output is shown live. Carriage-return progress (`\r`) and ANSI colors work.
- `input()` works (the user types in the console), but prefer settings: a script that asks nothing is easier to run again.
- Fail loudly: let exceptions propagate, or use `sys.exit("clear message")`. A non-zero exit code is shown as an error.
- Do not use `pause`, `os.system("cls")` or anything that expects a visible terminal window.
- A script may open its own window (tkinter, PySide...); PyManager marks it as such.

### 6. Dependencies

- Prefer the standard library. Third-party libraries go in the `requirements.txt` of the script's folder, as
  pip names, one per line. Pin a version (`==`) only when the script needs that exact version.
- External programs (ffmpeg, Deno...) are **not installed** by PyManager: they must be on the `PATH`. Say so in the
  `.txt` and fail with a clear message when they are missing (`shutil.which("ffmpeg")`).

### 7. The `.txt` description

Same name as the script, shown in PyManager above the fields. One to four short sentences: what the script does,
what it reads and writes, and anything the user must have installed. **Do not list the exposed settings**: the
fields already show them, with their labels. Mention only settings that are not exposed and still worth knowing.
Write it in English for `scripts/public/`.

### 8. Public scripts

Scripts in `scripts/public/` are published: write comments, messages and descriptions in English, and
leave out personal names, paths, URLs and any secret (tokens, cookies, passwords).

## Check your script

```
python -m pymanager --check scripts\public\video\my_script.py
```

(run it from the project folder, with any Python 3.10+ or `.venv\Scripts\python`; without a path it checks every script). It lists the fields PyManager will
show and, for every `@expose` that gives nothing, the line and the reason. Paste the output to the AI to have it fixed. The same
warnings appear under the parameters in PyManager. Example:

```
scripts/private/audio/my_script.py
  Champs exposés (1) :
    ligne 4    OUTPUT_DIR               texte                              'output'  — Output folder
  Avertissements (1) :
    ligne 9    @expose ignoré : variable dans un bloc (fonction, if, boucle, classe, ...)
```

## Checklist before answering

- [ ] Every setting is a top-level `NAME = literal`, and every user-facing one has `@expose` with a short label.
- [ ] No `None`, call, f-string, dictionary or expression behind an `@expose`.
- [ ] The marker `@expose` appears only on the settings lines.
- [ ] Defaults are sensible and the script runs with them; empty means "script value" is respected.
- [ ] Paths are relative (`input`, `output`), no personal path; the output folder is created; inputs are not modified.
- [ ] Errors end with an exception or `sys.exit("message")`; nothing waits on a terminal.
- [ ] `my_script.txt` is provided, short, and does not list the exposed settings.
- [ ] Third-party libraries are listed for `requirements.txt`; external programs are checked at start.
- [ ] Public script: English only and nothing personal.
- [ ] The file passes `python -m pymanager --check` with no warning.
