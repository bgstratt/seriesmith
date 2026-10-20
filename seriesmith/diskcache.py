"""
Caches kept on disk between server runs, in the settings folder's cache/ (one
JSON file each). What they hold is worked out from files and keyed by those
files' own stamps (path, size, modified time), so a stale entry is never used:
it is simply worked out again. Losing the folder costs one slow first load.

  sha1        a file's sha1 (takes.file_sha1): every live reference picture is
              hashed on a listing, hundreds of megabytes on a big show
  live_paths  the live files each episode of a show names (refs._live_paths):
              read from every sibling's series config on a listing

A store is read on first use and written by save(), which a load that added
to it calls when it ends, and the process at exit. Stdlib only.
"""
from __future__ import annotations

import atexit
import json
import os
import threading
from seriesmith.core import fileio as F

_LOCK = threading.Lock()
_STORES: dict[str, dict] = {}            # the store's file -> its entries
_DIRTY: set[str] = set()
MAX_ENTRIES = 50000                      # past this a store starts again


def _file(name: str) -> str:
    """$SERIESMITH_CACHE_DIR (the tests' scratch folder), else the settings folder's cache/."""
    d = os.environ.get("SERIESMITH_CACHE_DIR")
    if not d:
        from seriesmith.settings import settings_path
        d = os.path.join(os.path.dirname(settings_path()), "cache")
    return os.path.join(d, f"{name}.json")


def store(name: str) -> dict:
    """The entries of store `name` (read from disk the first time). Change it
    under lock(), then call touched(name)."""
    path = _file(name)
    with _LOCK:
        data = _STORES.get(path)
        if data is None:
            _STORES[path] = data = F.read_json_or(path, {}, want=dict)
        return data


def lock() -> threading.Lock:
    return _LOCK


def touched(name: str) -> None:
    """Store `name` has changed: the next save() writes it."""
    path = _file(name)
    with _LOCK:
        data = _STORES.get(path)
        if data is not None and len(data) > MAX_ENTRIES:
            data.clear()
        _DIRTY.add(path)


def save() -> None:
    """Write every store that changed (atomically: a reader never sees half)."""
    with _LOCK:
        todo = [(p, json.dumps(_STORES.get(p) or {}, separators=(",", ":"))) for p in _DIRTY]
        _DIRTY.clear()
    for path, text in todo:
        try:
            F.write_text(path, text)
        except OSError:
            pass                                  # a cache that can't be written is just slower


atexit.register(save)
