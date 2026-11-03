"""
fx.py — a shot's effects: sync sound made from the frames of the take the cut plays, and
laid under the cut (docs/SOUND.md phase 4).

**Asked for, never automatic.** Many takes already carry their model's own effects (H3 makes
picture and sound together), so effects are made only for the shots asked for: a clip's Sound
menu, `POST /seriesmith/fx/render`, `seriesmith fx`. Under the mix's voices only (voices.py)
the takes' own effects go with their music, so that's where effects matter most. A take is made on a `foley` target
(targets/foley/: `h3_foley` the default, `ltx23_foley`, `hunyuan_xl_foley`) from the cut's take
for the shot, all of it, so the cut's trims trim the effects with the picture.

A shot's effects takes live in `<ep>/sound/fx/<pass>/<shot>/`:

    tNN.wav     the take's sound, 48 kHz 24-bit stereo, exactly as long as the picture it
                was made from (sample 0 is the take's frame 0)
    tNN.json    its sidecar: {"pass", "shot", "target", "prompt", "negative", "text" (the
                shot's words), "seed", "source": {"pass", "take", "size", "mtime"} (the
                picture it was made from: its pass, number and its mp4 as it was), "video"
                ({"frames", "fps", "seconds", "width", "height"}: as it went to the model),
                "status" (queued | ok | failed), "error", "created", "finished",
                "measured" ({"seconds", "peak_db", "rms_db"})}

The prompt (shot_text) is the shot's script `sound:` line from the story IR, else its action,
and "No dialogue, no voices, no singing, no music." (targets/foley/common.py). The seed is the
episode's, the shot's and the take number's (stable_seed). The picture goes up as a file
(LoadVideo, ComfyUI core), made the model's size and frame rate first (stage), so any backend
runs it; the sound that comes back is fitted to the picture's length (finish_take).

**Laid from the cut, as the beds are (ambience.py), never stored as items** (laid): each shot
in the cut whose pass's mix picks one of its effects takes (`fx: {shot: {take, gain_db, mute,
keep_stale, trim_in, trim_out, fade_in, fade_out, points}}`, mix.check) gets it on the Effects
track at its clip, its sample 0 at the take's frame 0, trimmed with the clip. Its own trims
silence frames at the clip's head and tail (voices creeping in at a take's end) without moving
or shortening the block: only the kept span is heard, faded in and out at its edges, its level
shaped by its points as an item's is (kept_span, render_fx, fx_lanes). **Stale** (stale_why) when the picture changed: made from
another take than the cut plays for the shot (its number or pass), or that take's mp4 has been
written since (its size or mtime). A stale take is left out of the mix and said so, unless
`keep_stale`: sound that doesn't match its picture is worse than none.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

from seriesmith import edit as E
from seriesmith import ff as FF
from seriesmith import mix as MX
from seriesmith import takes as T
from seriesmith import targets as TG
from seriesmith.core import fileio as F
from seriesmith.core.ir import stable_seed

FX_DIR = ("sound", "fx")
TAKES_MAX = 8                       # a request's takes per shot
EDGE_S = 0.005                      # a laid take's ends ramped, so a trim doesn't click
_TAKE = re.compile(r"^t(\d{2,3})\.json$")


class FxError(ValueError):
    pass


# ---------------------------------------------------------------------------
# a shot's takes
# ---------------------------------------------------------------------------

def shot_dir(root: str, pass_: str, shot: str) -> str:
    return os.path.join(root, *FX_DIR, pass_, T.safe_id(shot))


def take_paths(root: str, pass_: str, shot: str, n: int) -> dict:
    d = shot_dir(root, pass_, shot)
    return {"sidecar": os.path.join(d, f"t{n:02d}.json"), "wav": os.path.join(d, f"t{n:02d}.wav"),
            "picture": os.path.join(d, f"t{n:02d}.picture.mp4"),
            "rel": "/".join((*FX_DIR, pass_, T.safe_id(shot), f"t{n:02d}.wav"))}


def list_takes(root: str, pass_: str, shot: str) -> list[dict]:
    """Every take's sidecar (with its `take` number), by number."""
    d = shot_dir(root, pass_, shot)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = _TAKE.match(name)
        if m:
            sc = F.read_json_or(os.path.join(d, name), None)
            if isinstance(sc, dict):
                out.append({**sc, "take": int(m.group(1))})
    return out


def get_take(root: str, pass_: str, shot: str, n: int) -> dict | None:
    sc = F.read_json_or(take_paths(root, pass_, shot, n)["sidecar"], None)
    return {**sc, "take": n} if isinstance(sc, dict) else None


def reserve(root: str, pass_: str, shot: str, record: dict) -> int:
    """The next take number, its sidecar written `queued` with `record`."""
    os.makedirs(shot_dir(root, pass_, shot), exist_ok=True)
    n = max([t["take"] for t in list_takes(root, pass_, shot)] + [0]) + 1
    F.write_json(take_paths(root, pass_, shot, n)["sidecar"],
                 {**record, "status": "queued", "created": T.now()})
    return n


def update(root: str, pass_: str, shot: str, n: int, **fields) -> dict:
    path = take_paths(root, pass_, shot, n)["sidecar"]
    sc = F.read_json_or(path, {}) or {}
    sc.update(fields)
    F.write_json(path, sc)
    return sc


def seed_for(root: str, shot: str, n: int) -> int:
    """A take's seed: the episode's, the shot's and its number's."""
    return stable_seed(os.path.basename(os.path.normpath(root)), "fx", shot, str(n))


# ---------------------------------------------------------------------------
# the cut's take and staleness
# ---------------------------------------------------------------------------

def cut_takes(root: str, pass_: str) -> dict[str, T.Take]:
    """{shot: the take the pass's cut plays} for every shot in the cut with a usable one
    (orphans and shots left out skipped)."""
    out = {}
    for e in E.cut_entries(root, pass_):
        if e.orphan or e.out:
            continue
        chosen, _, ok = E.cut_take(root, e)
        if ok and chosen is not None:
            out[e.shot] = chosen
    return out


def source_of(take: T.Take) -> dict:
    """What an effects take records of the picture it was made from."""
    st = os.stat(take.paths.mp4)
    return {"pass": take.pass_, "take": take.take, "size": st.st_size,
            "mtime": round(st.st_mtime, 3)}


def stale_why(sc: dict, take: T.Take | None) -> str | None:
    """Why an effects take no longer matches the cut's picture for its shot, in words; None
    when it does. `take`: the take the cut plays (None: the shot has none)."""
    if take is None:
        return "the shot has no take in the cut"
    src = sc.get("source") or {}
    if src.get("take") != take.take or src.get("pass", take.pass_) != take.pass_:
        was = f"t{int(src['take']):02d}" if isinstance(src.get("take"), int) else "another take"
        if src.get("pass") and src.get("pass") != take.pass_:
            was += f" ({src['pass']})"
        return f"made from {was}; the cut plays t{take.take:02d}"
    try:
        st = os.stat(take.paths.mp4)
    except OSError:
        return f"t{take.take:02d}'s video isn't there"
    if st.st_size != src.get("size") or abs(round(st.st_mtime, 3) - float(src.get("mtime") or 0)) > 0.002:
        return f"t{take.take:02d} was rendered again since"
    return None


# ---------------------------------------------------------------------------
# what a take is asked
# ---------------------------------------------------------------------------

def shot_text(root: str, shot: str) -> tuple[str, str]:
    """(the words a shot's effects are made from, where they came from: "sound" or
    "action"): its script `sound:` line, else its action, from the story IR
    (shotlist/shots.json); ("", "") when neither is there."""
    try:
        with open(os.path.join(root, "shotlist", "shots.json"), encoding="utf-8") as fh:
            story = json.load(fh)
    except (OSError, ValueError):
        return "", ""
    for sq in story.get("sequences") or []:
        for sh in sq.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id") == shot:
                if (sh.get("sound") or "").strip():
                    return sh["sound"].strip(), "sound"
                return (sh.get("action") or "").strip(), "action"
    return "", ""


def model_for(root: str, series: dict | None, asked: str | None = None) -> str:
    """The foley target: the one asked for, else the series config's `sound.effects_model`,
    else this machine's default (h3_foley)."""
    if asked:
        return asked
    own = ((series or {}).get("sound") or {}).get("effects_model")
    return own or TG.machine_default("foley")


def take_seconds(take: T.Take) -> tuple[int, float, float]:
    """(frames, fps, seconds) of a take: its sidecar's, else its file's length at 24 fps.
    FxError when neither says."""
    frames, fps = E.take_frames(take), E.take_fps(take) or 24.0
    if frames:
        return frames, fps, frames / fps
    from seriesmith import peaks as PK
    d = PK.media_info(take.paths.mp4).get("duration") if os.path.isfile(take.paths.mp4) else None
    if not d:
        raise FxError(f"{take.shot} t{take.take:02d}'s length can't be read")
    return round(d * fps), fps, float(d)


def video_for(target, frames: int, fps: float, seconds: float, size: tuple[int, int]) -> dict:
    """The take's picture as it goes to `target` (its capabilities: a frame rate, a size,
    a frame grid): {"frames", "fps", "seconds", "width", "height"}. `size` is the take's."""
    caps = target.capabilities()
    out_fps = float(caps.get("fps") or fps)
    n = max(1, int(seconds * out_fps + 1e-6))
    grid = caps.get("frame_grid")
    if grid:
        step, base = int(grid[0]), int(grid[1])
        n = base + step * max(0, (n - base) // step)
    w, h = int(caps.get("width") or size[0]), int(caps.get("height") or 0)
    if not h:
        h = max(2, round(w * size[1] / max(1, size[0]) / 2) * 2)
    return {"frames": n, "fps": out_fps, "seconds": round(n / out_fps, 4), "width": w, "height": h}


def plan(root: str, pass_: str, shot: str, target_id: str | None = None,
         takes: dict[str, T.Take] | None = None) -> dict:
    """What a new effects take of `shot` is asked, against the pass's cut: {"shot", "target",
    "take" (the cut's T.Take), "source", "text", "text_from", "video", "brief" (the target's
    prompt: {"prompt", "negative", "values"})}. FxError when the shot has no usable take in
    the cut, or no words to make its effects from."""
    takes = cut_takes(root, pass_) if takes is None else takes
    take = takes.get(shot)
    if take is None:
        raise FxError(f"{shot} has no take in the {pass_} cut to make effects from")
    text, where = shot_text(root, shot)
    if not text:
        raise FxError(f"{shot} has neither a sound: line nor an action to make its effects from")
    try:
        target = TG.load_target(model_for(root, _series(root), target_id), "foley")
    except TG.TargetError as e:
        raise FxError(str(e))
    frames, fps, seconds = take_seconds(take)
    sc = take.sidecar or {}
    size = (int(sc.get("width") or 16), int(sc.get("height") or 9))
    video = video_for(target, frames, fps, seconds, size)
    return {"shot": shot, "target": target.id, "take": take, "source": source_of(take),
            "text": text, "text_from": where, "video": video,
            "take_seconds": round(seconds, 4), "brief": target.foley_prompt(text, video)}


def _series(root: str) -> dict | None:
    from seriesmith import jobs as J
    try:
        return J.series_config(root)
    except (OSError, ValueError):                          # none, or one that doesn't read: the defaults
        return None


def record(p: dict, seed: int, pass_: str) -> dict:
    """A plan as the new take's sidecar holds it."""
    return {"pass": pass_, "shot": p["shot"], "target": p["target"], "seed": seed,
            "text": p["text"], "text_from": p["text_from"], "prompt": p["brief"]["prompt"],
            "negative": p["brief"].get("negative"), "values": p["brief"].get("values") or {},
            "source": p["source"], "video": p["video"], "take_seconds": p["take_seconds"]}


# ---------------------------------------------------------------------------
# the picture staged, the graph, the sound back
# ---------------------------------------------------------------------------

def stage(src: str, dst: str, video: dict) -> None:
    """`src` (a take's mp4) as the picture a foley model is given, in `dst`: its frame rate
    and size, cut to its frame count, no sound (libx264, near lossless)."""
    vf = f"fps={video['fps']:g},scale={video['width']}:{video['height']}:flags=bicubic"
    tmp = F.temp_beside(dst, ".mp4")
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, "-an", "-vf", vf,
                        "-frames:v", str(int(video["frames"])), "-c:v", "libx264", "-crf", "12",
                        "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp],
                       capture_output=True, timeout=600)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"staging {os.path.basename(src)}: "
                           f"{r.stderr.decode('utf-8', 'replace')[-300:]}")
    F.replace(tmp, dst)


def graph(target, sc: dict, picture) -> dict:
    """The API graph for one take: the target's workflow, its preset's files, steps and
    negative, the sidecar's prompt, values and seed, `picture` (a backends.File of the
    staged picture) as the take, pruned to the saver."""
    import copy

    from seriesmith import jobs as J
    base, _ = J.target_workflow(target, None, None, required=True, prefer_repo=True)
    g = copy.deepcopy(base)
    b = target.binding
    preset = target.presets.get("final")
    vals: dict = {}
    if preset is not None:
        if preset.model:
            vals["model"] = preset.model
        if preset.steps:
            vals["steps"] = preset.steps
        vals.update({k: v for k, v in preset.extra.items() if not k.startswith("_")})
    vals["prompt"] = sc["prompt"]
    if sc.get("negative") is not None:
        vals["negative"] = sc["negative"]
    vals.update(sc.get("values") or {})
    vals["seed"] = sc["seed"]
    vals["video"] = picture
    for name, v in vals.items():
        if v is not None and b.specs(name):
            J.patch_param(g, b, name, v)
    saver = J.node_of(g, b.saver_class or "SaveAudio")
    if b.prune:
        J.prune(g, saver)
    return g


def prepare(root: str, pass_: str, shot: str, n: int, backend=None) -> tuple[dict, str]:
    """When a take's job starts: its picture staged from the take it records (FxError when
    that take has changed since it was asked: the request is made again), and its graph.
    With `backend`, RuntimeError first when what the target's node pack would fetch by
    itself isn't downloaded (hubcache.check_target). Returns (the graph, the staged
    picture's path: removed when the job ends)."""
    from seriesmith.backends import File
    sc = get_take(root, pass_, shot, n)
    if sc is None:
        raise FxError(f"{shot}'s effects t{n:02d} has no sidecar")
    src = sc.get("source") or {}
    take = T.get_take(root, src.get("pass") or pass_, shot, int(src.get("take") or 0))
    if take is None or not os.path.isfile(take.paths.mp4):
        raise FxError(f"{shot} t{int(src.get('take') or 0):02d} isn't there any more")
    why = stale_why(sc, take)
    if why:
        raise FxError(f"{shot}'s picture changed since this take was asked ({why}): ask again")
    target = TG.load_target(sc["target"], "foley")
    if backend is not None:
        from seriesmith import hubcache as HC
        HC.check_target(target, backend)
    picture = take_paths(root, pass_, shot, n)["picture"]
    stage(take.paths.mp4, picture, sc["video"])
    return graph(target, sc, File(picture)), picture


def finish_take(root: str, pass_: str, shot: str, n: int, raw: str) -> dict:
    """The sound is back: decoded, fitted to the picture's length (cut, or silence after
    it), written as tNN.wav, measured, the sidecar closed."""
    np = MX._np()
    sc = get_take(root, pass_, shot, n) or {}
    buf = MX.decode(raw)
    if len(buf) == 0:
        raise RuntimeError("the sound that came back has nothing in it")
    want = round(float(sc.get("take_seconds") or len(buf) / MX.RATE) * MX.RATE)
    out = np.zeros((want, 2), dtype=np.float32)
    out[: min(want, len(buf))] = buf[:want]
    paths = take_paths(root, pass_, shot, n)
    MX.write_wav(paths["wav"], out)
    peak = float(np.abs(out).max()) if len(out) else 0.0
    rms = float(np.sqrt(np.mean(out ** 2))) if len(out) else 0.0
    m = {"seconds": round(want / MX.RATE, 4), "came": round(len(buf) / MX.RATE, 4),
         "peak_db": round(20 * np.log10(peak), 1) if peak > 0 else None,
         "rms_db": round(20 * np.log10(rms), 1) if rms > 0 else None}
    return update(root, pass_, shot, n, status="ok", finished=T.now(), file=paths["rel"], measured=m)


def collect(root: str, pass_: str, shot: str, n: int, run, status: str) -> dict:
    """A take's run, ended with `status`, collected: its sound fitted and kept
    (finish_take). Returns the sidecar; RuntimeError when there's nothing to keep."""
    import tempfile
    if status != "succeeded":
        raise RuntimeError(run.error or f"the job ended {status}")
    outs = [o for o in run.outputs() if o.type == "audio"]
    if not outs:
        raise RuntimeError("the job finished but returned no audio")
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1] or ".flac")
    os.close(fd)
    try:
        outs[0].save(tmp)
        sc = finish_take(root, pass_, shot, n, tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    pick_new(root, pass_, shot, n)
    return sc


def pick_new(root: str, pass_: str, shot: str, n: int) -> bool:
    """Take `n`, just made, into the pass's mix (its level, mute, trims, fades and points kept): made and asked for,
    it's heard and shown (the lane and the Refs tab list what's picked); an earlier take is a
    pick away. A mix that doesn't read is left alone. True when picked."""
    try:
        pick(root, pass_, shot, n)
    except (ValueError, FxError):
        return False
    return True


# ---------------------------------------------------------------------------
# asking for takes (the route and the command)
# ---------------------------------------------------------------------------

def queue(runner, root: str, pass_: str, shots: list[str], target_id: str | None = None,
          count: int = 1, backend: str = "local") -> tuple[list[dict], list[dict]]:
    """Ask `runner` for `count` effects takes of each of `shots` from the pass's cut: each
    planned (FxError for a shot that can't be: no take in the cut, no words), reserved and
    queued. Returns (queued: [{"shot", "take", "job", "seed", "target"}], skipped: [{"shot",
    "why"}])."""
    from seriesmith import hubcache as HC
    takes = cut_takes(root, pass_)
    queued, skipped = [], []
    try:
        on = runner.backend_for(backend)
    except (AttributeError, ValueError):
        on = None                                         # enqueue_fx says why
    for shot in shots:
        try:
            p = plan(root, pass_, shot, target_id, takes)
            if on is not None:
                # what its node pack would fetch by itself, not downloaded: never queued
                HC.check_target(TG.load_target(p["target"], "foley"), on)
        except (FxError, RuntimeError) as e:
            skipped.append({"shot": shot, "why": str(e)})
            continue
        for _ in range(count):
            n_next = max([t["take"] for t in list_takes(root, pass_, shot)] + [0]) + 1
            seed = seed_for(root, shot, n_next)
            n = reserve(root, pass_, shot, record(p, seed, pass_))
            if n != n_next:                                # another took it: its own seed
                seed = seed_for(root, shot, n)
                update(root, pass_, shot, n, seed=seed)
            job = runner.enqueue_fx(root, pass_, shot, n, backend)
            queued.append({"shot": shot, "take": n, "job": job, "seed": seed, "target": p["target"]})
    return queued, skipped


# ---------------------------------------------------------------------------
# picking, and what a shot's takes say
# ---------------------------------------------------------------------------

def picked(mix: dict, shot: str) -> dict:
    """A shot's settings in a pass's mix ({} when none is picked)."""
    return ((mix or {}).get("fx") or {}).get(shot) or {}


def pick(root: str, pass_: str, shot: str, n: int | None) -> dict:
    """Take `n` of the shot's effects into the pass's mix (`fx`), its level, mute, trims,
    fades and points kept (MX.FX_KEEP), a keep_stale dropped (a new pick is judged afresh); None takes the shot's effects out.
    FxError for a take that isn't finished. Returns the mix as written."""
    mix = MX.check(MX.load(root).get(pass_))
    fx = dict(mix.get("fx") or {})
    if n is None:
        fx.pop(shot, None)
    else:
        sc = get_take(root, pass_, shot, n)
        if sc is None or sc.get("status") != "ok":
            raise FxError(f"{shot} has no finished effects take {n}")
        own = {k: v for k, v in (fx.get(shot) or {}).items() if k in MX.FX_KEEP}
        fx[shot] = {"take": n, **own}
    mix["fx"] = fx
    if not fx:
        del mix["fx"]
    return MX.write(root, pass_, mix)


def shots(root: str, pass_: str, mix: dict | None = None) -> list[dict]:
    """The shots with effects takes in a pass, in shot order: {"shot", "takes", "ok",
    "queued", "failed", "picked"} from their sidecars (no audio read, no staleness: that's
    shot_takes, when a row opens). What the Refs tab's Effects section lists."""
    mix = MX.check(MX.load(root).get(pass_)) if mix is None else mix
    base = os.path.join(root, "sound", "fx", pass_)
    try:
        names = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    except OSError:
        return []
    out = []
    for shot in names:
        tk = list_takes(root, pass_, shot)
        if not tk:
            continue
        st = [t.get("status") for t in tk]
        out.append({"shot": shot, "takes": len(tk), "ok": st.count("ok"), "queued": st.count("queued"),
                    "failed": st.count("failed"), "picked": picked(mix, shot).get("take")})
    return out


def shot_takes(root: str, pass_: str, shot: str, mix: dict | None = None) -> dict:
    """A shot's effects takes, newest first, each with `stale` (stale_why, None when it
    matches the cut's picture) and `picked`; the take the cut plays; the words a new take
    would be made from. What a block's menu fetches when it opens."""
    mix = MX.check(MX.load(root).get(pass_)) if mix is None else mix
    takes = cut_takes(root, pass_)
    cut = takes.get(shot)
    own = picked(mix, shot)
    out = []
    for sc in sorted(list_takes(root, pass_, shot), key=lambda t: -t["take"]):
        sc["stale"] = stale_why(sc, cut) if sc.get("status") == "ok" else None
        sc["picked"] = own.get("take") == sc["take"]
        sc["path"] = take_paths(root, pass_, shot, sc["take"])["rel"]
        out.append(sc)
    text, where = shot_text(root, shot)
    return {"shot": shot, "pass": pass_,
            "cut_take": {"pass": cut.pass_, "take": cut.take} if cut else None,
            "picked": own.get("take"), "settings": own, "text": text, "text_from": where,
            "takes": out}


# ---------------------------------------------------------------------------
# under the cut
# ---------------------------------------------------------------------------

def laid(root: str, pass_: str, layout: list[dict], mix: dict | None) -> list[dict]:
    """The picked effects under a cut (`layout`: [{"id", "trim_in", "used", "dissolve_in"}]
    as assemble lays it), one per shot in the cut with a pick: [{"shot", "take", "model",
    "path" (absolute), "rel", "exists", "origin" (the cut frame of the take's frame 0),
    "start", "end" (cut frames: the clip), "in" / "out" (anchors), "gain_db", "mute",
    "keep_stale", "stale" (why, or None), "heard" (exists, not muted, and not stale unless
    kept), "trim_in", "trim_out", "fade_in", "fade_out" (frames), "points" ([(cut frame,
    dB)], in time order)}]. Nothing decoded: cheap enough for every GET of the mix."""
    own = (mix or {}).get("fx") or {}
    if not own or not layout:
        return []
    origins = MX.shot_origins(layout)
    takes = cut_takes(root, pass_)
    out = []
    for x in layout:
        s = own.get(x["id"])
        if not s or not s.get("take"):
            continue
        n = int(s["take"])
        paths = take_paths(root, pass_, x["id"], n)
        sc = get_take(root, pass_, x["id"], n) or {}
        exists = sc.get("status") == "ok" and os.path.isfile(paths["wav"])
        why = stale_why(sc, takes.get(x["id"])) if sc else "its sidecar isn't there"
        o = origins[x["id"]]
        start = o["origin"] + o["first"]
        mute, keep = bool(s.get("mute")), bool(s.get("keep_stale"))
        out.append({"shot": x["id"], "take": n, "model": sc.get("target") or "",
                    "path": paths["wav"], "rel": paths["rel"], "exists": exists,
                    "origin": o["origin"], "start": start, "end": start + x["used"],
                    "in": {"shot": x["id"], "frame": x["trim_in"]},
                    "out": {"shot": x["id"], "frame": x["trim_in"] + x["used"]},
                    "gain_db": float(s.get("gain_db") or 0.0), "mute": mute,
                    "keep_stale": keep, "stale": why,
                    "heard": exists and not mute and (why is None or keep),
                    **{k: int(s.get(k) or 0) for k in MX.FX_FRAMES},
                    "points": sorted((o["origin"] + p["at"]["frame"], p["db"])
                                     for p in s.get("points") or [])})
    return out


def kept_span(f: dict) -> tuple[int, int]:
    """The cut frames a laid effects take is heard over: its clip less its trims (empty,
    start >= end, when they meet)."""
    return f["start"] + f.get("trim_in", 0), f["end"] - f.get("trim_out", 0)


def render_fx(fx: list[dict], total: int, fps: float, log=print):
    """The laid effects as one stereo buffer of the cut's length at mix.RATE: each heard
    one from its clip's first frame of the take to its last, silent outside its kept span
    (its trims), at its gain shaped by its points (as an item's: dB at anchors, linear
    between, held beyond), faded in and out over its fades at the kept span's edges, and
    those edges ramped over EDGE_S. A stale one (not kept), a muted one, or one not there
    is left out (the last said so)."""
    np = MX._np()
    n = round(total / fps * MX.RATE)
    out = np.zeros((n, 2), dtype=np.float32)
    edge = max(1, int(EDGE_S * MX.RATE))
    for f in fx:
        if f["mute"]:
            continue
        if not f["exists"]:
            log(f"  ! sound: {f['shot']}'s effects t{f['take']:02d} ({f['rel']}) isn't there; left out")
            continue
        if f["stale"] and not f["keep_stale"]:
            continue                                       # assemble says so, once
        s0 = round(f["start"] / fps * MX.RATE)
        s1 = min(n, round(f["end"] / fps * MX.RATE))
        first = (f["start"] - f["origin"]) / fps
        src = MX.decode(f["path"], first, (f["end"] - f["start"]) / fps)
        k = min(len(src), s1 - s0)
        if k <= 0:
            continue
        # the kept span, in samples from the clip's first (the trims silent)
        a, b = kept_span(f)
        ka = max(0, round(a / fps * MX.RATE) - s0) if f.get("trim_in") else 0
        kb = min(k, round(b / fps * MX.RATE) - s0) if f.get("trim_out") else k
        if kb <= ka:
            continue
        m = kb - ka
        if f.get("points"):
            xs = [round(pf / fps * MX.RATE) - s0 - ka for pf, _ in f["points"]]
            db = f["gain_db"] + np.interp(np.arange(m), xs, [d for _, d in f["points"]])
            kept = MX._db(db).astype(np.float32)
        else:
            kept = np.full(m, MX._db(f["gain_db"]), dtype=np.float32)
        for key, head in (("fade_in", True), ("fade_out", False)):
            nf = min(m, round(f.get(key, 0) / fps * MX.RATE))
            if nf > 0:
                ramp = np.linspace(0.0, 1.0, nf, dtype=np.float32)
                if head:
                    kept[:nf] *= ramp
                else:
                    kept[-nf:] *= ramp[::-1]
        e = min(edge, m // 2)
        if e:
            ramp = np.linspace(0.0, 1.0, e, dtype=np.float32)
            kept[:e] *= ramp
            kept[-e:] *= ramp[::-1]
        env = np.zeros(k, dtype=np.float32)
        env[ka:kb] = kept
        skip = max(0, -s0)                                 # before the cut's first frame
        if skip < k:
            out[s0 + skip: s0 + k] += src[skip:k] * env[skip:, None]
    return out


def fx_lanes(fx: list[dict], length) -> list[dict]:
    """The heard effects as clips on the XML's effects lane (mix.placed's shape, without the
    track's fader): each its file from the clip's first frame of the take, the clip trimmed
    to its kept span (its trims: an editor sees a shorter clip whose handles hold the rest),
    its fades and its points (those in the span) as an item's. `length(path)`: a file's
    length in the cut's frames (None: unreadable)."""
    out = []
    for f in fx:
        if not f["heard"]:
            continue
        n = length(f["path"]) if os.path.isfile(f["path"]) else None
        if not n:
            continue
        start, end = kept_span(f)
        first = start - f["origin"]
        end = min(end, start + max(0, n - first))
        if end <= start:
            continue
        out.append({"id": f"fx_{f['shot']}", "label": f"{f['shot']} effects", "path": f["path"],
                    "start": start, "end": end, "in": first, "frames": n,
                    "gain_db": f["gain_db"],
                    "points": [(pf, d) for pf, d in f.get("points") or [] if start <= pf < end],
                    "fade_in": min(f.get("fade_in", 0), end - start),
                    "fade_out": min(f.get("fade_out", 0), end - start)})
    return out


# ---------------------------------------------------------------------------
# `seriesmith fx`
# ---------------------------------------------------------------------------

def cmd_fx(root: str, argv: list[str]) -> int:
    """`seriesmith fx <episode> [--pass proxy|final] [--shots sh010,sh020] [--target ID]
    [--takes N] [--backend NAME] [--pick] [--list]`: make effects for those shots from the
    takes the pass's cut plays, on a queue of the command line's own, and wait; --pick puts
    each shot's new take in the pass's mix; --list says each shot's takes and which are stale."""
    import argparse
    ap = argparse.ArgumentParser(prog="seriesmith fx", description=(
        "A shot's effects (sync sound) made from the frames of the take the cut plays: "
        "only the shots asked for (docs/SOUND.md phase 4)."))
    ap.add_argument("--pass", dest="pass_", choices=("final", "proxy"), default=None)
    ap.add_argument("--proxy", action="store_true", help="the same as --pass proxy")
    ap.add_argument("--shots", default="", help="the shots, comma-separated (sh010,sh020)")
    ap.add_argument("--target", default=None,
                    help="a foley target: h3_foley (the default), ltx23_foley, hunyuan_xl_foley")
    ap.add_argument("--takes", type=int, default=1, help=f"takes a shot, 1 to {TAKES_MAX}")
    ap.add_argument("--backend", default="local", help="where they run (default: local)")
    ap.add_argument("--pick", action="store_true", help="put each shot's new take in the mix")
    ap.add_argument("--list", action="store_true", help="each shot's takes; nothing is made")
    args = ap.parse_args(argv)
    pass_ = args.pass_ or ("proxy" if args.proxy else "final")
    shots = [x.strip() for x in args.shots.split(",") if x.strip()]
    if not os.path.isdir(root):
        print(f"seriesmith fx: no episode folder {root}")
        return 1
    if args.list:
        cut = cut_takes(root, pass_)
        for shot in shots or list(cut):
            info = shot_takes(root, pass_, shot)
            if not info["takes"]:
                continue
            ct = info["cut_take"]
            print(f"  {shot}  (the cut plays {('t%02d' % ct['take']) if ct else 'nothing'}"
                  f"{'' if info['picked'] is None else ', picked t%02d' % info['picked']})")
            for t in info["takes"]:
                print(f"    t{t['take']:02d} {t.get('status', '?'):7} {t.get('target', ''):18} "
                      f"seed {t.get('seed')}" + (f"  stale: {t['stale']}" if t.get("stale") else "")
                      + (f"  {t.get('error')}" if t.get("status") == "failed" else ""))
        return 0
    if not shots:
        print("seriesmith fx: say which shots (--shots sh010,sh020): effects are made only "
              "for the shots asked for")
        return 2
    if not 1 <= args.takes <= TAKES_MAX:
        print(f"seriesmith fx: --takes is 1 to {TAKES_MAX}")
        return 2
    from seriesmith import runner as RN
    try:
        runner = RN.cli_runner(args.backend)
    except ValueError as e:
        print(f"seriesmith fx: {e}")
        return 1
    queued, skipped = queue(runner, root, pass_, shots, args.target, args.takes, args.backend)
    for x in skipped:
        print(f"  !! {x['shot']}: {x['why']}")
    if not queued:
        return 1
    for q in queued:
        print(f"  .. {q['shot']} effects t{q['take']:02d} on {q['target']} ({args.backend}), "
              f"seed {q['seed']}")
    import time
    t0 = time.time()
    done = RN.wait(runner.queue, [q["job"] for q in queued])
    failed = 0
    last: dict[str, int] = {}
    for q in queued:
        sc = get_take(root, pass_, q["shot"], q["take"]) or {}
        if sc.get("status") == "ok":
            m = sc.get("measured") or {}
            print(f"  ok {q['shot']} t{q['take']:02d}: {m.get('seconds')} s, peak "
                  f"{m.get('peak_db')} dB, rms {m.get('rms_db')} dB  -> {take_paths(root, pass_, q['shot'], q['take'])['rel']}")
            last[q["shot"]] = q["take"]
        else:
            failed += 1
            print(f"  !! {q['shot']} t{q['take']:02d}: {sc.get('error') or done.get(q['job'])}")
    print(f"  {len(queued) - failed} of {len(queued)} made in {time.time() - t0:.0f} s")
    if args.pick:
        for shot, n in last.items():
            pick(root, pass_, shot, n)
            print(f"  picked {shot} t{n:02d} into the {pass_} mix")
    return 1 if failed or skipped else 0
