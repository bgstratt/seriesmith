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
    show_file(base, p)         a path a show's own files name, kept inside the show

A path a show's own files name (a sheet or plate, the recording, a theme, a mix item, a
take record's file) is followed only inside the show: the folder holding the episode
(its refs/, audio/, _titles/, the other episodes) or a project folder. A show handed
over by someone else can't make a render read, or upload to a hosted model, a file
elsewhere on the disk. Importing from anywhere on the PC is unchanged: an import copies
(or hard-links) the file into the show, so the show names it there.
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


class OutsideShow(ValueError):
    """A path a show names that leads outside the show and the project folders."""
    http_status = 403


# The project folders, as the editor's server knows them (api.load_roots keeps this
# current); the command line has none, so there a show's paths stay in the show.
_project_roots: list[str] = []


def _real(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:                                    # another drive
        return False


def set_project_roots(roots) -> None:
    """The project folders a show's paths may also lead into."""
    global _project_roots
    _project_roots = [_real(r) for r in roots or () if isinstance(r, str) and r]


def show_folder(base: str) -> str:
    """The show a folder of it belongs to. `base` is an episode (it has a script: the
    show is the folder holding it, with the shared refs/ and audio/ beside it) or a
    series folder (the series config's, episodes under it: the show itself)."""
    d = os.path.normpath(os.path.abspath(base))
    if (os.path.isfile(os.path.join(d, SERIES_CONFIG)) and not episode_script(d)
            and _has_episodes(d)):
        return d                                          # the series folder
    up = os.path.dirname(d)
    return d if os.path.dirname(up) == up else up         # an episode's show; never a whole drive


def _has_episodes(d: str) -> bool:
    try:
        subs = [os.path.join(d, n) for n in os.listdir(d)]
    except OSError:
        return False
    return any(os.path.isdir(s) and episode_script(s) for s in subs)


def show_file(base: str, p: str, also=()) -> str:
    """`p`, a path one of the show's own files names, made whole against `base` (the
    episode, or the series config's folder for its own paths): the path, as joined,
    when it lands inside the show (`show_folder(base)`), a project folder or one of
    `also`; OutsideShow otherwise, a link that leads out included."""
    if not isinstance(p, str) or not p or "\x00" in p:
        raise OutsideShow(f"not a path: {p!r}")
    full = os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))
    real = _real(full)
    show = show_folder(base)
    for root in (_real(show), *_project_roots, *(_real(a) for a in also if a)):
        if _inside(real, root):
            return full
    raise OutsideShow(f"{p} is outside the show ({show}): import it, or move it into "
                      "the show's folder or a project folder")


def safe_id(text: str, fallback: str = "") -> str:
    """`text` with anything but letters, digits, `_`, `.` and `-` made `_`, for
    a file or folder name; `fallback` when that leaves nothing."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(text)) or fallback
