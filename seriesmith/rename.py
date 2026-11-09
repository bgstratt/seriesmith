"""
A character, prop, vehicle, voice or location given a new id, while nothing uses it.

The id is the series config's key, and names the ref's takes folder and each file in it, its picks
and overrides, and (by the series config's own paths) its live picture and voice sample. All of those
move together. It's refused when a script or another entry names the id, since those would break:
nothing is rewritten in a script.
"""
from __future__ import annotations

import json
import os
import re

from seriesmith import edit as E
from seriesmith import promote as P
from seriesmith import refs as R
from seriesmith import source as H
from seriesmith import takes as T
from seriesmith.core import fileio

PATH_FIELDS = ("sheet", "plate", "voice_sample")


class RenameError(ValueError):
    """Why this id can't change (said to the user as it is)."""


def _named(id_: str):
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(id_)}(?![A-Za-z0-9_])", re.IGNORECASE)


def _renamed_path(path: str, old: str, new: str) -> str:
    """A series config path with the id's folder and the id at the start of its file name changed."""
    parts = [new if p == old else p for p in path.split("/")]
    tail = parts[-1]
    if tail.startswith(old) and tail[len(old):len(old) + 1] in ("_", "."):
        parts[-1] = new + tail[len(old):]
    return "/".join(parts)


def _text_of(read) -> str:
    try:
        return read()
    except (FileNotFoundError, H.SourceError):
        return ""


def _refuse_if_named(s: R.Series, raw: dict, block: str, old: str) -> None:
    named = _named(old)
    rest = {**raw, block: {k: v for k, v in raw[block].items() if k != old}}
    if named.search(json.dumps(rest)):
        raise RenameError(f"Another entry in the series config names {old}.")
    if block == "locations" and raw[block][old].get("ambience"):
        raise RenameError(f"{old} has an ambience bed, which is kept under its id.")
    own_config = os.path.normcase(os.path.abspath(E.episode_series_config(s.ep)))
    for ep in [s.ep, *R.sibling_episodes(s.ep)]:
        if named.search(_text_of(lambda: H.read_source(ep, "script").text)):
            raise RenameError(f"The script of {os.path.basename(os.path.normpath(ep))} names {old}.")
        config = E.episode_series_config(ep)
        if config and os.path.normcase(os.path.abspath(config)) != own_config \
                and named.search(_text_of(lambda: H.read_source(ep, "series").text)):
            raise RenameError(f"The series config of {os.path.basename(os.path.normpath(ep))} names {old}.")


class _Moves:
    """Files and folders moved, and put back if the rename fails part way."""

    def __init__(self):
        self.done: list[tuple[str, str]] = []

    def __call__(self, src: str, dst: str) -> None:
        fileio.replace(src, dst)
        self.done.append((src, dst))

    def undo(self) -> None:
        for src, dst in reversed(self.done):
            fileio.replace(dst, src)


def _move_with_prefix(move: _Moves, src_dir: str, dst_dir: str, old: str, new: str) -> None:
    """A folder to its new name, and each file in it that starts with the old one."""
    if os.path.exists(dst_dir):
        raise RenameError(f"{os.path.basename(dst_dir)} is already there: {dst_dir}")
    move(src_dir, dst_dir)
    for name in os.listdir(dst_dir):
        if name.startswith(old) and name[len(old):len(old) + 1] in ("_", "."):
            move(os.path.join(dst_dir, name), os.path.join(dst_dir, new + name[len(old):]))


def _move_live(move: _Moves, home: str, path: str, renamed: str, old: str, new: str) -> None:
    src, dst = R.ref_file(home, path), R.ref_file(home, renamed)
    if src is None or dst is None or not os.path.isfile(src) or src == dst:
        return
    folder = os.path.dirname(src)
    if os.path.basename(folder) == old:
        _move_with_prefix(move, folder, os.path.dirname(dst), old, new)
        return
    if os.path.exists(dst):
        raise RenameError(f"{os.path.basename(dst)} is already there: {dst}")
    move(src, dst)


def _rewrite_sidecars(folder: str, old_id: str, new_id: str, old_key: str, new_key: str) -> None:
    for name in os.listdir(folder):
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        data = T.read_json(path)
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if v == old_id:
                data[k] = new_id
            elif isinstance(v, str) and v.startswith(old_key):
                data[k] = new_key + v[len(old_key):]
        T.write_json(path, data)


def rename(s: R.Series, old: str, new: str) -> None:
    """`old` becomes `new` in the series config and on disk. RenameError when it can't."""
    if not isinstance(new, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", new):
        raise RenameError("An id is lower case letters, digits and underscores, starting with a letter.")
    src = H.read_source(s.ep, "series")
    raw = json.loads(src.text)
    block = next((b for b in ("subjects", "locations") if old in (raw.get(b) or {})), None)
    if block is None:
        raise RenameError(f"The series config has no {old}.")
    if new == old:
        raise RenameError("That's already its id.")
    if new in (raw.get("subjects") or {}) or new in (raw.get("locations") or {}):
        raise RenameError(f"There is already something called {new}.")
    _refuse_if_named(s, raw, block, old)

    scopes = ("subject", "voice") if block == "subjects" else ("location",)
    pairs = [(f"{scope}:{old}", f"{scope}:{new}", R.ref_key(f"{scope}:{old}"), R.ref_key(f"{scope}:{new}")) for scope in scopes]
    takes = os.path.join(s.home, "refs", "_takes")
    for _, _, old_key, _ in pairs:
        folder = os.path.join(takes, old_key)
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            if name.endswith(".json") and (T.read_json(os.path.join(folder, name)) or {}).get("status") == "queued":
                raise RenameError(f"{old} has a take being made: wait for it to finish.")

    entry = raw[block][old]
    move = _Moves()
    try:
        for _, _, old_key, new_key in pairs:
            if os.path.isdir(os.path.join(takes, old_key)):
                _move_with_prefix(move, os.path.join(takes, old_key), os.path.join(takes, new_key), old_key, new_key)
        for field in PATH_FIELDS:
            path = entry.get(field)
            if isinstance(path, str) and path:
                renamed = _renamed_path(path, old, new)
                _move_live(move, s.home, path, renamed, old, new)
                entry[field] = renamed
        raw[block] = {new if k == old else k: v for k, v in raw[block].items()}
        H.write_source(src, P.dump_series(raw, src.text))
    except BaseException:
        move.undo()
        raise

    for old_id, new_id, old_key, new_key in pairs:
        folder = os.path.join(takes, new_key)
        if os.path.isdir(folder):
            _rewrite_sidecars(folder, old_id, new_id, old_key, new_key)
    for load, save in ((R.load_picks, R.save_picks), (R.load_overrides, R.save_overrides)):
        data = load(s.home)
        moved = False
        for old_id, new_id, _, _ in pairs:
            if old_id in data["refs"]:
                data["refs"][new_id] = data["refs"].pop(old_id)
                moved = True
        if moved:
            save(s.home, data)
