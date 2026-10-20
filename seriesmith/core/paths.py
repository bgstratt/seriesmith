"""
Where an episode's files are, as every part of seriesmith finds them: the
series config in the episode folder, else in its parent (a series folder that
every episode under it shares), and the script beside it. It was a dozen
inline copies, two of which (align, and the stage commands behind `seriesmith
build`) never looked in the parent. Standard library only: the build and the
targets use it.

    series_home(root)          the folder holding the series config, or None
    series_config_path(root)   that series.json, or None
    episode_script(root)       the episode's script, or None
    episode_files(root)        (series.json, script), or ValueError saying what's missing
    safe_id(text, fallback)    an id made safe for a file or folder name
"""
from __future__ import annotations

import os
import re

SERIES_CONFIG = "series.json"
# .md files beside a script that aren't one
SCRIPT_SKIP = ("refs_todo", "readme", "notes", "align_report")


def series_home(root: str) -> str | None:
    """The folder with the series config: the episode folder, else its parent."""
    for d in (root, os.path.dirname(os.path.normpath(root))):
        if os.path.isfile(os.path.join(d, SERIES_CONFIG)):
            return d
    return None


def series_config_path(root: str) -> str | None:
    """series.json in the episode folder, else in its parent (a series folder)."""
    home = series_home(root)
    return os.path.join(home, SERIES_CONFIG) if home else None


def script_candidates(root: str) -> list[str]:
    """The .md files in `root` that may be its script (not refs_todo, notes, ...)."""
    return [os.path.join(root, f) for f in sorted(os.listdir(root))
            if f.lower().endswith(".md") and not f.lower().startswith(SCRIPT_SKIP)]


def episode_script(root: str) -> str | None:
    """The episode's script: <folder name>.md, else the only other .md there."""
    base = os.path.basename(os.path.normpath(root))
    md = os.path.join(root, f"{base}.md")
    if os.path.isfile(md):
        return md
    cands = script_candidates(root)
    return cands[0] if len(cands) == 1 else None


def episode_files(root: str) -> tuple[str, str]:
    """(series.json, the script) of an episode; ValueError saying which is
    missing, or which scripts it can't choose between."""
    cfg = series_config_path(root)
    if not cfg:
        raise ValueError(f"no {SERIES_CONFIG} in {root} or its parent folder")
    md = episode_script(root)
    if not md:
        cands = script_candidates(root) if os.path.isdir(root) else []
        raise ValueError(f"can't tell which script to use in {root}: "
                         f"{[os.path.basename(c) for c in cands] or 'no .md found'}")
    return cfg, md


def safe_id(text: str, fallback: str = "") -> str:
    """`text` with anything but letters, digits, `_`, `.` and `-` made `_`, for
    a file or folder name; `fallback` when that leaves nothing."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(text)) or fallback
