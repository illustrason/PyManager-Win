"""Template for a PyManager-Win script: copies files from a folder into another one.

Copy this file to scripts/public/<topic>/ or scripts/private/<topic>/, rename it, and replace the
body. Keep the layout: settings first (top level, literal values, an "@expose" marker in the comment
of the ones the user may change), then the code, then the entry point.

PyManager shows one field per "@expose" line. An empty field means "use the value written here".
The file itself is never modified; the values are replaced in memory when the script is started.
Never write the marker in any other comment: every comment that contains it is read as a request.
"""
import os
import shutil
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Settings: top level, one variable per line, plain literal values only.
# The marker at the end of a comment makes the setting a field in PyManager;
# the rest of that comment becomes the label of the field.
# ---------------------------------------------------------------------------
INPUT_DIR = "input"                      # Folder to read (relative to this script, or absolute) @expose
OUTPUT_DIR = "output"                    # Folder where the results are written @expose
EXTENSIONS = (".txt", ".md", ".csv")     # Extensions to process (tick the ones you want) @expose
PREFIX = "copy_"                         # Text added in front of each file name @expose
MAX_FILES = 0                            # Maximum number of files (0 = no limit) @expose
MIN_SIZE_KB = 0.5                        # Skip files smaller than this size, in kB @expose
MODIFIED_AFTER = datetime(2000, 1, 1)    # Only files modified after this date and time @expose
DRY_RUN = False                          # True = only list what would be done @expose

# Not exposed: without the marker, a setting never appears in the interface.
PROGRESS_EVERY = 10


def list_files():
    """Files of INPUT_DIR (sub-folders included) that match the settings, in a stable order."""
    found = []
    for folder, _dirs, names in os.walk(INPUT_DIR):
        for name in sorted(names):
            path = os.path.join(folder, name)
            if not name.lower().endswith(tuple(EXTENSIONS)):
                continue
            if os.path.getsize(path) < MIN_SIZE_KB * 1024:
                continue
            if datetime.fromtimestamp(os.path.getmtime(path)) < MODIFIED_AFTER:
                continue
            found.append(path)
    return found[:MAX_FILES] if MAX_FILES else found


def main():
    if not os.path.isdir(INPUT_DIR):
        # A clear message and a non-zero exit code show up as an error in PyManager.
        sys.exit(f"Input folder not found: {INPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = list_files()
    print(f"{len(files)} file(s) to process")
    for index, path in enumerate(files, start=1):
        target = os.path.join(OUTPUT_DIR, PREFIX + os.path.basename(path))
        if DRY_RUN:
            print(f"[dry run] {path} -> {target}")
        else:
            shutil.copy2(path, target)       # the originals are never modified
            print(f"{path} -> {target}")
        if index % PROGRESS_EVERY == 0:
            print(f"  {index}/{len(files)} done")
    print("Done.")


if __name__ == "__main__":
    main()
