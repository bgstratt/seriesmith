"""
What a take's own files say, kept while they are unchanged (docs/REFACTOR.md 3.4).

An episode's status describes every take of every shot: its sidecar, which of
its files are there, whose sound the cut plays for it, its upscale and post
records and whether they're fresh. Worked out from the files on every load,
that was ~2,500 sidecars read and ~20,000 paths checked on a long episode,
seconds, though almost nothing had changed since the last load.

Here a shot's renders folder is listed once (`listing`: os.scandir gives every
name, size and modified time in one call), and a take's facts (`take_facts`)
are kept keyed on the (size, mtime) of each of its own files in that listing:
the same files give the same facts. Nothing relies on folder times or on
writes going through seriesmith: a take deleted, a sidecar edited by hand or
an upscale written by ComfyUI changes its files' stats, and is read again.

Not kept: a take whose sidecar, upscale or post is still queued (it changes
soon, and its record asks the live queue: takes.lost_job), nor one with a file
changed in the last fileio.RACY_S seconds (a file still being written can
keep its time).

Kept on disk per episode and pass (diskcache, one store each; the most recent
KEEP_STORES), so a server started again starts warm.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import time

from seriesmith import diskcache as DC
from seriesmith import peaks as PK
from seriesmith import takes as T
from seriesmith.core.fileio import RACY_S

# a take's files, in its key's order (takes.TakePaths)
SUFFIXES = (".json", ".mp4", ".jpg", "_strip.jpg", "_h3.wav",
            ".up.json", ".up.mp4", ".post.json", ".post.mp4")
VERSION = 1                          # the facts' shape: another version starts afresh
KEEP_STORES = 24                     # episode-pass stores kept on disk
PREFIX = "takes-"


def listing(d: str) -> dict[str, tuple[int, int]]:
    """{name: (size, mtime_ns)} of the files in `d`, one os.scandir; {} when
    the folder isn't there."""
    out: dict[str, tuple[int, int]] = {}
    try:
        with os.scandir(d) as it:
            for e in it:
                try:
                    if e.is_file():
                        st = e.stat()
                        out[e.name] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
    except OSError:
        pass
    return out


def looked(d: str) -> dict[str, tuple[int, int]]:
    """listing(d), once per folder within takes.one_look() (one answer)."""
    memo = T._LOOK.get()
    if memo is None:
        return listing(d)
    key = ("listing", d)
    if key not in memo:
        memo[key] = listing(d)
    return memo[key]


def sidecar(path: str, files: dict, kept: dict | None = None, name: str | None = None):
    """takes.read_sidecar(path), from `kept` while the file's (size, mtime) in
    `files` (its folder's listing) is unchanged; its own copy each time. None
    when the listing has no such file."""
    st = files.get(os.path.basename(path))
    if st is None:
        return None
    kid = os.path.normcase(path)
    key = list(st)
    hit = kept.get(kid) if kept is not None else None
    if hit is not None and hit.get("k") == key:
        return dict(hit["v"])
    data = T.read_sidecar(path)
    if (kept is not None and isinstance(data, dict) and data.get("status") != "queued"
            and not data.get("unreadable") and time.time() - st[1] / 1e9 > RACY_S):
        with DC.lock():
            kept[kid] = {"k": key, "v": data}
        if name:
            DC.touched(name)
    return dict(data) if isinstance(data, dict) else data


def store_name(root: str, pass_: str) -> str:
    key = os.path.normcase(os.path.abspath(root)) + "|" + pass_
    return PREFIX + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def store(root: str, pass_: str) -> tuple[str, dict]:
    """The episode-pass store (its name, its entries), started afresh when it
    was kept by another version; a new one drops the oldest past KEEP_STORES.
    (`pass_` "refs" with the show's folder: its references' takes.) Looked up
    once per answer within takes.one_look()."""
    memo = T._LOOK.get()
    if memo is not None and ("store", root, pass_) in memo:
        return memo[("store", root, pass_)]
    out = _store(root, pass_)
    if memo is not None:
        memo[("store", root, pass_)] = out
    return out


def _store(root: str, pass_: str) -> tuple[str, dict]:
    name = store_name(root, pass_)
    path = DC._file(name)
    new = not os.path.isfile(path)
    data = DC.store(name)
    with DC.lock():
        if data.get("_v") != VERSION:
            data.clear()
            data["_v"] = VERSION
    if new:
        _drop_old(os.path.dirname(path), keep=path)
    return name, data


def _drop_old(d: str, keep: str) -> None:
    try:
        files = sorted(glob.glob(os.path.join(d, PREFIX + "*.json")), key=os.path.getmtime)
    except OSError:
        return
    for f in files[:max(0, len(files) - KEEP_STORES)]:
        if os.path.normcase(f) != os.path.normcase(keep):
            try:
                os.remove(f)
            except OSError:
                pass


def _key(stem_: str, files: dict) -> list:
    return [list(files[stem_ + s]) if stem_ + s in files else None for s in SUFFIXES]


def take_facts(tp: T.TakePaths, shot: str, take: int, pass_: str, files: dict,
               kept: dict | None = None, name: str | None = None) -> dict:
    """{"sidecar", "up", "post", "audio"} for one take: its sidecar as
    takes.read_sidecar reads it (None: none), its upscale and post records as
    takes.upscale_of / post_of give them (with `fresh`; None: none), and the
    file the cut plays for its sound ("mp4", "h3" or None: peaks.clip_audio).
    From `kept` (a store) when its files are as they were; `name` is the
    store's, marked changed when an entry is added."""
    key = _key(tp.stem, files)
    kid = os.path.normcase(os.path.join(tp.dir, tp.stem))
    hit = kept.get(kid) if kept is not None else None
    if hit is not None and hit.get("k") == key:
        return hit["v"]
    t = T.Take(shot, take, pass_, tp, T.read_sidecar(tp.sidecar) if key[0] else None, files=files)
    up = T.upscale_of(t) if key[5] else None
    post = T.post_of(t, up) if key[7] else None
    sound = PK.clip_audio(tp.mp4 if key[1] else None, tp.h3_wav if key[4] else None)
    facts = {"sidecar": t.sidecar, "up": up, "post": post,
             "audio": None if sound is None else ("mp4" if sound == tp.mp4 else "h3")}
    if kept is not None and _keepable(facts, key):
        with DC.lock():
            kept[kid] = {"k": key, "v": facts}
        if name:
            DC.touched(name)
    return facts


def _keepable(facts: dict, key: list) -> bool:
    if any((r or {}).get("status") == "queued" or (r or {}).get("unreadable")
           for r in (facts["sidecar"], facts["up"], facts["post"])):
        return False
    newest = max((k[1] for k in key if k), default=0)
    return time.time() - newest / 1e9 > RACY_S


def list_takes(root: str, pass_: str, shot_id: str, folder: str | None = None,
               kept: dict | None = None, name: str | None = None) -> list[T.Take]:
    """takes.list_takes from one listing of the shot's folder, each take's
    facts from `kept` while its files are unchanged. Each Take carries its
    listing (`files`) and its facts (`facts`)."""
    d = T.shot_dir(root, pass_, shot_id, folder)
    files = listing(d)
    pat = re.compile(rf"{re.escape(T.safe_id(shot_id))}_t(\d+)\.(?:json|mp4)")
    nums = sorted({int(m.group(1)) for n in files if (m := pat.fullmatch(n))})
    out = []
    for n in nums:
        tp = T.TakePaths(d, T.stem(shot_id, n))
        facts = take_facts(tp, shot_id, n, pass_, files, kept, name)
        # its own copy of the sidecar: a caller that changes it can't change the kept one
        sc = dict(facts["sidecar"]) if facts["sidecar"] is not None else None
        out.append(T.Take(shot_id, n, pass_, tp, sc, files=files, facts=facts))
    return out
