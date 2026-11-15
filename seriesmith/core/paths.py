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
    inside(path, roots)        whether a path is in one of this PC's folders
    real(p), is_network(p)     a path with its links resolved; a network path elsewhere is
                               never looked at (Windows would sign in to its host)

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
_network_roots: list[str] = []          # the project folders that are on a network share, as written


def _lexical(p: str) -> str:
    """`p` whole and normalised by its text alone: the disk and the network aren't touched."""
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def is_network(p: str) -> bool:
    r"""Whether `p` is a Windows network or device path (`\\host\share`, `//host/share`,
    `\\?\`, `\\.\`), by its text. Looking at such a path at all (a stat, resolving its links)
    makes Windows sign in to that host, which hands it the user's NTLM hash."""
    return os.name == "nt" and isinstance(p, str) and _lexical(p).startswith("\\\\")


def real(p: str, trusted=()) -> str:
    """`p` with its links resolved, for comparing folders. A network path is resolved only
    under a project folder or one of `trusted` that is itself on that share; any other is
    returned as written, untouched, so it compares as outside every folder on this PC."""
    if foreign(p, trusted):
        return _lexical(p)
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def foreign(p: str, trusted=()) -> bool:
    """Whether `p` is a network path that isn't this PC's to look at: not under a project
    folder on that share, nor one of `trusted`."""
    if not is_network(p):
        return False
    lex = _lexical(p)
    own = [*_network_roots, *(_lexical(t) for t in trusted if t and is_network(t))]
    return not any(_inside(lex, t) for t in own)


def _real(p: str) -> str:
    return real(p)


def _inside(path: str, root: str) -> bool:
    """Whether `path` is `root` or under it; both as real() gives them (whole, normalised).
    By their text, a folder at a time: os.path.commonpath refuses a network share's own
    root, so a project folder that was one never matched."""
    root = root.rstrip("\\/")
    return path.rstrip("\\/") == root or path.startswith(root + os.sep)


def inside(path: str, roots) -> bool:
    """Whether `path` is in one of the folders `roots` (each trusted: this PC's own), links
    resolved; a network path under none of them is refused without being looked at."""
    roots = [r for r in roots or () if r]
    got = real(path, roots)
    return any(_inside(got, real(r, [r])) for r in roots)


def set_project_roots(roots) -> None:
    """The project folders a show's paths may also lead into."""
    global _project_roots, _network_roots
    roots = [r for r in roots or () if isinstance(r, str) and r]
    _network_roots = [_lexical(r) for r in roots if is_network(r)]
    _project_roots = [real(r, [r]) for r in roots]


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
    show = show_folder(base)
    own = [show, *(a for a in also if a)]
    got = real(full, own)                                 # a network path elsewhere: never touched
    for root in (*(real(r, [r]) for r in own), *_project_roots):
        if _inside(got, root):
            return full
    raise OutsideShow(f"{p} is outside the show ({show}): import it, or move it into "
                      "the show's folder or a project folder")


def safe_id(text: str, fallback: str = "") -> str:
    """`text` with anything but letters, digits, `_`, `.` and `-` made `_`, for
    a file or folder name; `fallback` when that leaves nothing, or only dots (`.`, `..`:
    a folder's own name for itself or its parent, never an id)."""
    out = re.sub(r"[^A-Za-z0-9_.-]", "_", str(text))
    return out if out.strip(".") else fallback
