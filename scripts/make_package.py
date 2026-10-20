"""
make_package.py
---------------
Dynamic Documentary Engine — Make a Package to Share

Builds one .zip that someone can unzip on their own Mac or Windows machine
and start by double-clicking, with nothing else to download: the engine,
its guides, every topic's clip list (with the labels typed in the Clip
library) and, unless told otherwise, the footage itself.

Left out on purpose: films generated while testing, the per-machine usage
history, Clip library backups and thumbnails, local tool settings and other
leftovers.

Works in a GitHub copy (packages exactly the project's tracked files, and
warns about unsaved changes) and in a plain unzipped copy without git
(packages everything except the leftovers above).

Usage:
    python3 scripts/make_package.py                 # engine + footage
    python3 scripts/make_package.py --no-footage    # engine only (small)
    python3 scripts/make_package.py --output ~/Desktop/DDE.zip

Author: Oluwafemisola David Ademoye
Supporting: Omotola Ajibike Ajao
Project: Dynamic Documentary Engine
Institution: Penn State University, College of IST
Supervisor: Dr. Betsy Campbell, Associate Teaching Professor
Version: 1.0.0
"""

import argparse
import fnmatch
import os
import subprocess
import sys
import zipfile
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = "dynamic-documentary-engine"

# Never packaged, whichever way files are found. Patterns are matched
# against paths relative to the project folder, using "/" separators.
EXCLUDE = (
    ".git/*", ".claude/*", "demo/*", "*/__pycache__/*", "*.pyc", "*.DS_Store",
    "metadata/collections/.backups/*", "metadata/collections/.index-*",
    "local-media/*/artifacts/*",            # generated films, manifests, usage stats
    "local-media/*/.previews/*",            # Clip library thumbnails/previews (remade on demand)
)
# ...except these placeholders, which make each topic folder exist on unzip.
KEEP = ("local-media/*/artifacts/.gitkeep",)

# Footage: the clips, and any opening/closing pieces a topic has.
FOOTAGE = ("local-media/*/assets/*/*", "local-media/*/titles/*/*")
FOOTAGE_KEEP = (".gitkeep", "README.txt")

# Already-compressed media is stored as-is; zipping it again only costs time.
STORED_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mp3", ".m4a", ".aac", ".wav",
                     ".avi", ".mkv", ".webm", ".jpg", ".png")


def _matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def _is_footage(path):
    return _matches(path, FOOTAGE) and os.path.basename(path) not in FOOTAGE_KEEP


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)


def _project_files():
    """(files, source) — every packaged non-footage file, relative to the
    project folder. Uses git's list when this is a git copy."""
    try:
        listed = _git("ls-files", "-z")
    except FileNotFoundError:
        listed = None
    if listed is not None and listed.returncode == 0 and listed.stdout:
        files = [f for f in listed.stdout.split("\0") if f]
        source = "git"
    else:
        files = []
        for folder, dirs, names in os.walk(REPO_ROOT):
            rel_folder = os.path.relpath(folder, REPO_ROOT).replace(os.sep, "/")
            dirs[:] = [d for d in dirs if d not in (".git", ".claude", "demo", "__pycache__")]
            for name in names:
                files.append(name if rel_folder == "." else f"{rel_folder}/{name}")
        source = "folder"
    keep = []
    for f in files:
        if _is_footage(f):
            continue
        if _matches(f, EXCLUDE) and not _matches(f, KEEP):
            continue
        if os.path.isfile(os.path.join(REPO_ROOT, f)):
            keep.append(f)
    return sorted(set(keep)), source


def _footage_files():
    found = []
    media_root = os.path.join(REPO_ROOT, "local-media")
    for folder, _dirs, names in os.walk(media_root):
        for name in names:
            rel = os.path.relpath(os.path.join(folder, name), REPO_ROOT).replace(os.sep, "/")
            if not name.startswith(".") and _is_footage(rel):
                found.append(rel)
    return sorted(found)


def _unsaved_changes():
    """Tracked files changed since the last commit (git copies only)."""
    try:
        status = _git("status", "--porcelain", "--untracked-files=no")
    except FileNotFoundError:
        return []
    return [line[3:] for line in status.stdout.splitlines()] if status.returncode == 0 else []


def _size(paths):
    return sum(os.path.getsize(os.path.join(REPO_ROOT, p)) for p in paths)


def _mb(n):
    return f"{n / 1_000_000:,.0f} MB" if n >= 1_000_000 else f"{n / 1000:,.0f} KB"


def build(output, include_footage=True):
    """Writes the package; returns (output, file count, engine bytes,
    footage bytes, "git" or "folder")."""
    files, source = _project_files()
    footage = _footage_files() if include_footage else []
    all_files = files + footage

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    tmp = output + ".part"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for rel in all_files:
            compress = (zipfile.ZIP_STORED if rel.lower().endswith(STORED_EXTENSIONS)
                        else zipfile.ZIP_DEFLATED)
            # write() keeps each file's permissions, so the Mac launcher
            # stays double-clickable after unzipping.
            z.write(os.path.join(REPO_ROOT, rel), f"{PACKAGE_DIR}/{rel}", compress_type=compress)
    os.replace(tmp, output)
    return output, len(all_files), _size(files), _size(footage), source


def main():
    default_out = os.path.join(os.path.dirname(REPO_ROOT),
                               f"DDE-package-{date.today().isoformat()}.zip")
    ap = argparse.ArgumentParser(description="Make a shareable package of the engine.")
    ap.add_argument("--output", default=default_out,
                    help=f"Where to write the .zip (default: {default_out}).")
    ap.add_argument("--no-footage", action="store_true",
                    help="Leave the video and audio clips out (much smaller).")
    args = ap.parse_args()
    output = os.path.abspath(os.path.expanduser(args.output))
    if os.path.commonpath([output, REPO_ROOT]) == REPO_ROOT:
        ap.error("Write the package outside the project folder, so it never packages itself.")

    unsaved = _unsaved_changes()
    if unsaved:
        print("Note: these files have changes that aren't saved to GitHub yet; the package\n"
              "includes them as they are now:\n  " + "\n  ".join(unsaved) + "\n")

    print("Building the package…")
    output, count, code_bytes, media_bytes, source = build(output, not args.no_footage)
    print(f"\nDone: {output}")
    print(f"  {count} files ({'from git' if source == 'git' else 'from this folder'})")
    print(f"  engine, guides and clip lists: {_mb(code_bytes)}")
    print(f"  footage: {_mb(media_bytes) if not args.no_footage else 'left out (--no-footage)'}")
    print(f"  zip size: {_mb(os.path.getsize(output))}")
    print("\nTo use it: unzip, then follow SETUP-GUIDE.md from Step 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
