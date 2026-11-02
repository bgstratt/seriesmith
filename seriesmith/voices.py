"""
voices.py — a take's voice stem, and the mix's "voices only" (docs/SOUND.md, the Dialogue track).

A video model that makes sound with its picture (H3, Seedance, FastH3 Omni) bakes its own
music and room tone into each take, different at every cut, so a bed, effects or a score
laid under the cut fight it. The take's sound is split by Hybrid Demucs into the voices and
the rest, by the same job a song's vocal stem is (vocals.py: seriesmith's `SeriesmithVocals`
node on this machine's ComfyUI, LoadAudio -> SeriesmithVocals -> SaveAudio), and the mix's
Dialogue track can play the voices alone.

**The stem**, beside the take: `<shot>_t01.voice.wav` (the take's sound as the cut plays it,
peaks.clip_audio: the mp4's own, else its `_h3.wav`; 44.1 kHz stereo as Demucs gives it,
sample 0 the take's first) and `<shot>_t01.voice.json`, its record: {"status" (queued | ok |
failed), "source": {"file" (the basename split), "size", "mtime"}, "queue_id", "error",
"created", "finished", "seconds" (the split, the job's own time), "measured": {"whole_rms_db",
"voice_rms_db", "rest_rms_db" (the whole less the voices, by energy)}}. **Stale** when the
take's sound has changed since (its file, size or mtime: re-rendered, a take imported over
it), as an effects take is (fx.stale_why); made again by asking again. A take discarded takes
them with it (edit.take_files: they share its stem).

**The mix** (mix.py): the `dialogue` track's `voices_only`, and a shot's own way in `voices:
{shot: {"voices_only": bool}}`. With it on, each clip of the cut whose take has a stem that's
there and fresh plays the stem in place of its whole sound: assemble's clips (so the mix, its
stems and the ducking hear the voices), the FCP7 XML (the clip's sound item is the stem's
wav), Play all (the clip's <video> muted, the stem played on the Dialogue track in its place)
and the ducking's speech curve. A clip whose stem is missing or stale plays its whole sound and
is said so: a missing stem is never silence. A shot the script gives no lines is silent on the
Dialogue track under voices only, unless it asks for voices only itself (plays(): what its
stem holds is the model's ad-libs and walla, or nothing). A clip with sound of its own from the
cut (`audio`: another take's, a file, silence) is left as it is (`sourced`).

**Made only when asked** (POST /seriesmith/voices, `seriesmith voices`, the editor's Make voice
stems): one queued `vocals` job a take, on the local backend (Demucs runs on this machine's
ComfyUI only).
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import time

from seriesmith import edit as E
from seriesmith import ff as FF
from seriesmith import mix as MX
from seriesmith import peaks as PK
from seriesmith import takes as T
from seriesmith.core import fileio as F

STATES = ("ok", "missing", "stale", "queued", "failed", "sourced", "silent")


class VoiceError(ValueError):
    pass


# ---------------------------------------------------------------------------
# a take's stem and its record
# ---------------------------------------------------------------------------

def source_file(take: T.Take) -> str | None:
    """The file whose sound the take plays in the cut (peaks.clip_audio): its mp4's own,
    else its `_h3.wav`; None when it has none."""
    h3 = take.paths.h3_wav
    return PK.clip_audio(take.paths.mp4, h3 if os.path.isfile(h3) else None)


def signature(path: str) -> dict:
    st = os.stat(path)
    return {"file": os.path.basename(path), "size": st.st_size, "mtime": round(st.st_mtime, 3)}


def record(take: T.Take) -> dict:
    return F.read_json_or(take.paths.voice_record, {}, dict) or {}


def update(take: T.Take, **fields) -> dict:
    rec = {**record(take), **fields}
    F.write_json(take.paths.voice_record, rec)
    return rec


def state(take: T.Take | None, alive=None) -> tuple[str, str | None]:
    """(one of STATES, why in words or None) for `take`'s voice stem. `alive(queue_id)` says
    whether a queued job is still on the queue (None: a queued record is believed)."""
    if take is None:
        return "missing", "the shot has no take in the cut"
    src = source_file(take)
    if src is None:
        return "silent", f"t{take.take:02d} has no sound"
    rec = record(take)
    status = rec.get("status")
    if status == "queued":
        if alive is None or alive(rec.get("queue_id")):
            return "queued", None
        return "missing", "its job was lost (seriesmith restarted): make it again"
    if status == "failed":
        return "failed", rec.get("error") or "the split failed"
    if status != "ok" or not os.path.isfile(take.paths.voice):
        return "missing", f"t{take.take:02d} hasn't been split"
    was = rec.get("source") or {}
    try:
        now = signature(src)
    except OSError:
        return "missing", f"t{take.take:02d}'s sound isn't there"
    if (was.get("file") != now["file"] or was.get("size") != now["size"]
            or abs(float(was.get("mtime") or 0) - now["mtime"]) > 0.002):
        return "stale", f"t{take.take:02d} was rendered again since it was split"
    return "ok", None


def stage(take: T.Take) -> tuple[str, dict]:
    """The take's sound as a wav to send (a temp file: the caller removes it) and the
    signature of the file it came from. VoiceError when it has none."""
    src = source_file(take)
    if src is None:
        raise VoiceError(f"t{take.take:02d} has no sound to split")
    sig = signature(src)
    fd, tmp = tempfile.mkstemp(prefix="seriesmith_voice_", suffix=".wav")
    os.close(fd)
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, "-vn", "-map", "0:a:0",
                        "-c:a", "pcm_s24le", tmp], capture_output=True, timeout=600)
    if r.returncode != 0 or not os.path.getsize(tmp):
        os.remove(tmp)
        raise VoiceError(f"t{take.take:02d}'s sound couldn't be read: "
                         + r.stderr.decode("utf-8", "replace")[-300:])
    return tmp, sig


def _rms_db(buf) -> float | None:
    np = MX._np()
    if not len(buf):
        return None
    v = float(np.sqrt(np.mean(buf.astype("float64") ** 2)))
    return round(20 * math.log10(v), 1) if v > 0 else -120.0


def measure(whole: str, voice: str) -> dict:
    """The take's whole sound, its voices and the rest (the whole less the voices, by
    energy), each as dBFS RMS."""
    w, v = MX.decode(whole), MX.decode(voice)
    n = min(len(w), len(v))
    out = {"whole_rms_db": _rms_db(w), "voice_rms_db": _rms_db(v)}
    if n:
        out["rest_rms_db"] = _rms_db(w[:n] - v[:n])
    return out


def collect(take: T.Take, run, status: str, sig: dict, started: float) -> dict:
    """The run, ended with `status`: its audio written as the take's stem, the record made
    ok (with what it was split from and the levels). Returns the record; RuntimeError when
    there's nothing to keep."""
    from seriesmith import vocals as VOC
    VOC.collect(take.paths.mp4, run, status, dest=take.paths.voice)
    src = os.path.join(take.paths.dir, sig["file"])
    try:
        measured = measure(src, take.paths.voice)
    except Exception:                                    # noqa: BLE001  levels are a nicety
        measured = {}
    return update(take, status="ok", source=sig, error=None, finished=T.now(),
                  seconds=round(time.monotonic() - started, 1), measured=measured)


# ---------------------------------------------------------------------------
# the cut's takes, and their stems' state
# ---------------------------------------------------------------------------

def cut_shots(root: str, pass_: str) -> list[tuple[T.CutEntry, T.Take | None]]:
    """Each shot in the pass's cut (orphans and shots left out skipped) with the take it
    plays (None: no usable one)."""
    out = []
    for e in E.cut_entries(root, pass_):
        if e.orphan or e.out:
            continue
        chosen, _, ok = E.cut_take(root, e)
        out.append((e, chosen if ok else None))
    return out


def take_of(paths_mp4: str, number: int, pass_: str) -> T.Take:
    """A take from its mp4's path (an assemble plan's), enough to find its stem."""
    d, name = os.path.split(paths_mp4)
    stem = name[:-4] if name.lower().endswith(".mp4") else name
    return T.Take(shot="", take=number, pass_=pass_, paths=T.TakePaths(d, stem))


def shots(root: str, pass_: str, mix: dict | None, alive=None) -> list[dict]:
    """Each cut shot's voice stem and what voices only does to it: [{"shot", "pass", "take",
    "path" (the stem, relative to the episode; null without a take), "state" (STATES), "why",
    "voices_only" (the shot's, with the track's under it), "override" (its own: true, false, or
    null), "plays" ("voice" | "whole": what the Dialogue track plays for it), "lines" (the
    script gives it dialogue), "measured"}] in cut order. Nothing decoded."""
    mix = mix or {}
    lines = _lines(root)
    out = []
    for e, take in cut_shots(root, pass_):
        own = ((mix.get("voices") or {}).get(e.shot) or {}).get("voices_only")
        want = MX.voices_only(mix, e.shot)
        if e.audio:
            st, why = "sourced", "the cut gives it sound of its own"
        else:
            st, why = state(take, alive)
        rel = None
        if take is not None:
            rel = os.path.relpath(take.paths.voice, root).replace(os.sep, "/")
        rec = record(take) if take is not None else {}
        own = own if isinstance(own, bool) else None
        out.append({"shot": e.shot, "pass": take.pass_ if take else e.pass_,
                    "take": take.take if take else None, "path": rel, "state": st, "why": why,
                    "voices_only": want, "override": own,
                    "plays": plays(want, own, st, e.shot in lines),
                    "lines": e.shot in lines, "measured": rec.get("measured") or None,
                    "seconds": rec.get("seconds")})
    return out


def plays(want: bool, own: bool | None, st: str, lines: bool) -> str:
    """What the Dialogue track plays for a clip: "voice" (its stem), "whole" (its take's
    whole sound) or "silence". Voices only on a shot the script gives no lines is silence
    (decided 2026-11-02 on Ballroom ep02: the stems of its six shots with no lines were near
    silence, -70 to -78 dBFS RMS, or the model's own ad-libs and walla, Whisper hearing "Yes.",
    "Okay.", "Yeah." at -32 to -49 dB), unless the shot itself asks for voices only (`own`
    true: a gasp or a shriek the model gave it). A clip with sound of its own from the cut,
    or with no sound, is left whole; a stem that isn't there or is stale plays whole."""
    if not want or st in ("sourced", "silent"):
        return "whole"
    if not lines and own is not True:
        return "silence"
    return "voice" if st == "ok" else "whole"


def _lines(root: str) -> set[str]:
    """The shots the script gives a line of dialogue (the story IR)."""
    data = F.read_json_or(os.path.join(root, "shotlist", "shots.json"), {}, dict) or {}
    return {s.get("id") for sq in data.get("sequences") or [] for s in sq.get("shots") or []
            if s.get("dialogue")}


def summary(rows: list[dict], mix: dict | None) -> dict:
    """What GET /seriesmith/mix says of voices only: the track's setting, the shots, and the
    counts the editor shows ("8/10 shots split")."""
    can = [r for r in rows if r["state"] not in ("sourced", "silent")]
    return {"voices_only": MX.voices_only(mix), "shots": rows,
            "split": sum(1 for r in can if r["state"] == "ok"), "of": len(can),
            "queued": sum(1 for r in can if r["state"] == "queued")}


def on_layout(root: str, pass_: str, layout: list[dict], mix: dict | None) -> list[dict]:
    """cue.cut_layout's clips with voices only applied to their `sound`: a clip that plays its
    stem has it (from the same `sound_start`: the stem's sample 0 is the take's), a silent one
    None; the rest as they were. What the ducking's speech curve hears (mix.speech_of)."""
    if not MX.voices_any(mix):
        return layout
    rows = {r["shot"]: r for r in shots(root, pass_, mix)}
    out = []
    for x in layout:
        r = rows.get(x["id"])
        if r and r["plays"] == "voice":
            x = {**x, "sound": os.path.join(root, *r["path"].split("/"))}
        elif r and r["plays"] == "silence":
            x = {**x, "sound": None}
        out.append(x)
    return out


def for_plan(root: str, pass_: str, plan: list[dict], mix: dict | None) -> dict[str, dict]:
    """assemble's plan with voices only: {shot: {"plays" (plays()), "path" (the stem,
    absolute, when it plays), "state", "why"}} for each clip the mix asks voices only of (a
    clip with its own `audio` left out: it keeps that). Clips voices only doesn't touch
    aren't in it."""
    out = {}
    lines = _lines(root)
    for p in plan:
        if p.get("audio_spec") or not MX.voices_only(mix, p["id"]):
            continue
        own = ((mix.get("voices") or {}).get(p["id"]) or {}).get("voices_only")
        take = take_of(p["base"], p["take"], p["src"])
        st, why = state(take)
        how = plays(True, own if isinstance(own, bool) else None, st, p["id"] in lines)
        out[p["id"]] = {"plays": how, "path": take.paths.voice if how == "voice" else None,
                        "state": st, "why": why}
    return out


def said(voices: dict[str, dict]) -> list[str]:
    """assemble's lines on voices only: how many play their stem, how many are silent (no
    lines), and each that plays whole because its stem can't."""
    if not voices:
        return []
    ok = [s for s, v in voices.items() if v["plays"] == "voice"]
    hush = [s for s, v in voices.items() if v["plays"] == "silence"]
    out = [f"  sound: voices only: {len(ok)} of {len(voices)} shot(s) play their voice stem"
           + (f", {len(hush)} with no lines silent ({', '.join(hush)})" if hush else "")]
    for s, v in voices.items():
        if v["plays"] == "whole" and v["state"] != "silent":
            out.append(f"  ! sound: {s}'s voice stem is {v['state']} ({v['why']}); its whole "
                       f"sound plays (seriesmith voices makes it)")
    return out


# ---------------------------------------------------------------------------
# making them
# ---------------------------------------------------------------------------

def queue(runner, root: str, pass_: str, shots_: list[str] | None = None, redo: bool = False,
          backend: str = "local") -> tuple[list[dict], list[dict]]:
    """Ask `runner` to split the take the pass's cut plays for each of `shots_` (None: every
    shot in the cut): one job a take. A stem that's fresh is skipped unless `redo`, one queued
    is skipped. Returns (queued: [{"shot", "take", "job"}], skipped: [{"shot", "why"}])."""
    alive = alive_of(runner)
    rows = {e.shot: (e, t) for e, t in cut_shots(root, pass_)}
    want = list(rows) if shots_ is None else shots_
    queued, skipped = [], []
    for shot in want:
        if shot not in rows:
            skipped.append({"shot": shot, "why": "it isn't in the cut"})
            continue
        e, take = rows[shot]
        if take is None:
            skipped.append({"shot": shot, "why": "it has no take in the cut"})
            continue
        st, why = state(take, alive)
        if st == "silent":
            skipped.append({"shot": shot, "why": why})
            continue
        if st == "queued":
            skipped.append({"shot": shot, "why": "its split is queued"})
            continue
        if st == "ok" and not redo:
            skipped.append({"shot": shot, "why": "its voice stem is made"})
            continue
        job = runner.enqueue_voice(root, pass_, shot, take, backend)
        queued.append({"shot": shot, "take": take.take, "job": job})
    return queued, skipped


def alive_of(runner):
    """A queued record's check: whether its job is still on `runner`'s queue (None: no queue to ask)."""
    from seriesmith.queue import DONE
    q = getattr(runner, "queue", None)
    if q is None or not hasattr(q, "jobs"):
        return None
    return lambda qid: bool(qid) and qid in q.jobs and q.jobs[qid].status not in DONE


# ---------------------------------------------------------------------------
# `seriesmith voices`
# ---------------------------------------------------------------------------

def cmd_voices(root: str, argv: list[str]) -> int:
    """`seriesmith voices <episode> [--pass proxy|final] [--shots sh010,sh020] [--redo]
    [--list]`: split the takes the pass's cut plays into their voice stems on this machine's
    ComfyUI (a queue of the command line's own), and wait; --list says each shot's stem."""
    import argparse

    from seriesmith import runner as RN
    ap = argparse.ArgumentParser(prog="seriesmith voices")
    ap.add_argument("--pass", dest="pass_", choices=list(T.PASSES), default="final")
    ap.add_argument("--proxy", action="store_const", const="proxy", dest="pass_")
    ap.add_argument("--shots", default="")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    try:
        mix = MX.check(MX.load(root).get(a.pass_))
    except ValueError:
        mix = {}
    if a.list:
        for r in shots(root, a.pass_, mix):
            m = r["measured"] or {}
            lvl = (f"  whole {m.get('whole_rms_db')} dB, voice {m.get('voice_rms_db')} dB"
                   if m else "")
            print(f"  {r['shot']:10} t{r['take'] or 0:02d}  {r['state']:8}"
                  f"{'  ' + r['why'] if r['why'] else ''}{lvl}")
        return 0
    want = [s.strip() for s in a.shots.split(",") if s.strip()] or None
    try:
        runner = RN.cli_runner("local")
    except ValueError as e:
        print(f"  ! {e}")
        return 1
    queued, skipped = queue(runner, root, a.pass_, want, a.redo)
    for s in skipped:
        print(f"  {s['shot']}: {s['why']}")
    if not queued:
        print("  nothing to split")
        return 0
    print(f"  splitting {len(queued)} take(s) on local ComfyUI (Hybrid Demucs)")
    got = RN.wait(runner.queue, [q["job"] for q in queued])
    bad = 0
    for q in queued:
        take = T.get_take(root, a.pass_, q["shot"], q["take"])
        rec = record(take) if take else {}
        if got.get(q["job"]) == "succeeded":
            m = rec.get("measured") or {}
            print(f"  {q['shot']} t{q['take']:02d}: {rec.get('seconds')} s, whole "
                  f"{m.get('whole_rms_db')} dB, voice {m.get('voice_rms_db')} dB, rest "
                  f"{m.get('rest_rms_db')} dB")
        else:
            bad += 1
            print(f"  ! {q['shot']} t{q['take']:02d}: {rec.get('error') or got.get(q['job'])}")
    return 1 if bad else 0
