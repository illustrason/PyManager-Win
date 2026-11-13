# Scripts folder

[Français](README.fr.md)

| Folder | Content | Git |
|---|---|---|
| `public/` | Base scripts shipped with PyManager-Win | Part of the public repository |
| `private/` | Your own scripts | Ignored here; can be a separate private repository cloned in this folder |

PyManager merges both folders into a single list. Scripts can be organized in sub-folders;
a sub-folder name that exists in both appears once.

## What is recognized

| File | Role |
|---|---|
| `my_script.py` | The script, shown in the list (a name starting with `_` is an internal module and stays hidden) |
| `my_script.txt` | Description shown in PyManager (otherwise: the script's docstring) |
| `requirements.txt` | Libraries needed by the scripts of the same folder and its sub-folders |

Folders named `input`, `output`, `venv`, `__pycache__` and those starting with a dot are ignored.

## Expose a variable in the interface

Add `@expose` in the comment of the line:

```python
INPUT_DIR = "input"   # Source folder @expose
BITRATE = "320k"      # Bit rate @expose
TARGET_SIZE_MB = 19   # @expose
```

PyManager then shows one field per variable. An empty field means the script's value.
Text, numbers and booleans give one field each. A `datetime(...)` or `date(...)` value gives a single date field,
and a tuple or list such as `(".adg", ".als")` gives a drop-down with check boxes (see the main README).
