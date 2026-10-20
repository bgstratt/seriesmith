"""
Files written so a reader never sees half of one, and read back: the one place
for it (it was a dozen near-copies, some without the Windows retry below, some
sharing a temp name between threads, some writing CRLF). Standard library
only: the build uses it.

    write_json(path, data)           atomic; UTF-8, LF, a trailing newline
    write_text(path, text) / write_bytes(path, data) / copy(src, dst)
    replace(src, dst)                os.replace, waiting out a file in use
    temp_beside(path)                a temp name of its own beside `path`
    read_json(path, default)         `default` when the file isn't there
    read_json_kept(path)             parsed once while the file is unchanged (shared)
    read_json_copy(path, default)    a private copy of that, to change and save
    file_digest(path, algo)          a file's hash, read in chunks
"""
from __future__ import annotations

import copy as _copy
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from seriesmith.core import fileio as F

# Windows: a file being replaced (os.replace) can't be opened for a moment,
# and one held open by a reader can't be replaced -- PermissionError, both
# ways. seriesmith's queue writes a take's record on its own threads while the
# editor's routes read it, so each side waits that moment out and tries again.
SHARING_TRIES, SHARING_WAIT = 80, 0.025          # about 2 s


def shared(fn):
    """fn(), tried again while Windows says the file is in use (about 2 s)."""
    for i in range(SHARING_TRIES):
        try:
            return fn()
        except PermissionError:
            if i == SHARING_TRIES - 1:
                raise
            time.sleep(SHARING_WAIT)


def replace(src: str, dst: str) -> None:
    """os.replace, waiting out a reader holding `dst` open (Windows)."""
    shared(lambda: os.replace(src, dst))


def temp_beside(path: str, suffix: str | None = None) -> str:
    """A name no other writer uses, in `path`'s folder (which is made): for a
    file a tool writes before it's put in place with replace(). It ends in
    `suffix`, else in `path`'s own name (a tool that reads the extension)."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tail = suffix if suffix is not None else "_" + os.path.basename(path)
    return os.path.join(d, f".tmp_{uuid.uuid4().hex}{tail}")


def _atomic(path: str, write) -> None:
    """write(tmp) into a temp file beside `path`, then put it in place; the
    temp file is removed when anything fails."""
    tmp = temp_beside(path)
    try:
        write(tmp)
        replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_bytes(path: str, data: bytes) -> None:
    def write(tmp):
        with open(tmp, "wb") as fh:
            fh.write(data)
    _atomic(path, write)


def write_text(path: str, text: str) -> None:
    """UTF-8, the line ends as given (LF on every system)."""
    def write(tmp):
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    _atomic(path, write)


def write_json(path: str, data, indent: int | None = 2, end: str = "\n",
               ensure_ascii: bool = False, default=None, separators=None) -> None:
    """`data` as JSON (json.dumps' own options), then `end`."""
    write_text(path, json.dumps(data, indent=indent, ensure_ascii=ensure_ascii,
                                default=default, separators=separators) + end)


def copy(src: str, dst: str) -> None:
    _atomic(dst, lambda tmp: shutil.copyfile(src, tmp))


def read_json(path: str, default=None):
    """The JSON in `path`; `default` when the file isn't there. A file that
    doesn't parse raises ValueError (json.load's)."""
    def read():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return shared(read)
    except FileNotFoundError:
        return default


def read_json_or(path: str, default=None, want: type | None = None):
    """The JSON in `path`, or `default` when it can't be had: not there,
    unreadable, broken, or (with `want`) not that type. For caches, journals
    and locks, which are only ever a convenience."""
    try:
        data = read_json(path, default)
    except (OSError, ValueError):
        return default
    return default if want is not None and not isinstance(data, want) else data


# Files read over and over in one request and between them (a shotlist: one
# Refs listing of a 324-shot episode parsed it 378 times). Kept parsed while
# size and mtime hold, and not while it may still be written to (RACY_S:
# Windows stamps writes at timer resolution, so a second write could share an
# mtime). The parsed value is SHARED by every caller: read it, never change it.
RACY_S = 2.0
_KEPT: dict[str, tuple[int, int, object]] = {}
_KEPT_MAX = 256
_KEPT_LOCK = threading.Lock()


def read_json_kept(path: str):
    """The JSON in `path`, parsed once while the file is unchanged; the same
    object to every caller, so read-only. FileNotFoundError when it's gone,
    ValueError when it doesn't parse (neither is kept), as json.load."""
    st = os.stat(path)
    key = os.path.normcase(os.path.abspath(path))
    with _KEPT_LOCK:
        hit = _KEPT.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]

    def read():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    data = shared(read)
    if time.time() - st.st_mtime_ns / 1e9 > RACY_S:
        with _KEPT_LOCK:
            if len(_KEPT) >= _KEPT_MAX:
                _KEPT.clear()
            _KEPT[key] = (st.st_size, st.st_mtime_ns, data)
    return data


def read_json_copy(path: str, default=None):
    """read_json, for a small file read often and then changed and saved
    (overrides, picks, the cut): its own copy of the kept parse, which is
    cheaper than opening and parsing the file again. `default` when it's gone;
    ValueError when it doesn't parse, as read_json."""
    try:
        return _copy.deepcopy(read_json_kept(path))
    except FileNotFoundError:
        return default


def forget_kept() -> None:
    with _KEPT_LOCK:
        _KEPT.clear()


def file_digest(path: str, algo: str = "sha1") -> str:
    """The hex digest of a file, read a megabyte at a time (a video isn't held
    in memory to hash it)."""
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
