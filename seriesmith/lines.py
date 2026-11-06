"""
lines.py -- an episode's dialogue from a voice model: a take per line, each in its character's
speaker, the words alone in the request, then laid in script order into the episode's recording.
From there it's a recording like an actor's (docs/RECORDED_DIALOGUE.md): `align` windows the shots
from it, using the timings the model gave in place of Whisper (`<recording>.words.json`).

The model can be a provider's, in a speaker the character was given, or a local one (LTX's voice), which
makes each line from the character's description, continuing the character's sample if it has one, else
the first line made for it, so one character keeps one voice (`local_job`).

A character's whole file (all of Crane's lines, from a voice model's site or an actor) comes in the
same way: heard, matched to that character's lines in script order, and cut into a take per line
(`cut_character`), so it mixes with lines made here and one line can still be redone alone.

    <ep>/audio/lines/lines.json                  what was asked and what's picked
    <ep>/audio/lines/<shot>.<n>_t<take>.wav      a take of a line
    <ep>/audio/lines/lines_recording.wav         the recording, and .words.json beside it
    <ep>/audio/lines/sources/<who>.wav           a character's whole file, and .words.json beside it

Nothing is paid for here: `plan` says what a generate would make, the queue makes it
(runner.enqueue_line), and a line is only asked for once its character has a speaker. A take whose
words or speaker no longer match the script is `changed`, and is never used without saying so.

The pause a silent shot gives is its `dur:`. Aligning turns `dur:` into a comment, so what was read
is kept in lines.json for the next time the recording is laid.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import threading
import wave

from seriesmith import build as BLD
from seriesmith import ff as FF
from seriesmith import takes as T
from seriesmith.core import fileio as F
from seriesmith.core import paths as P
from seriesmith.core.ir import stable_seed

DIR = os.path.join("audio", "lines")
RECORDING = "lines_recording.wav"
RATE = 44100
WITHIN_SHOT = 0.35       # seconds between two lines in one shot
BETWEEN_SHOTS = 0.60     # and between two shots that speak, one after the other
AROUND_SILENT = 0.55     # what a pause holds besides its silent shots' own length (align's LEAD + TAIL)
ENDS = 0.50              # silence before the first line, and after the last
SILENT_DEFAULT = 3.04    # a silent shot with no `dur:`, as align reads one
SILENT = "silent"        # what a silent shot's window of the recording holds (laid_sound)
MIN_HEARD = 0.5          # of a line's words, for its take to be cut from a character's file
CUT_AIR = 0.12           # seconds kept either side of a line cut from a file, within the pause
_WRITING = threading.Lock()   # takes end together on a provider's parallel lane: one edit of lines.json at a time


class LinesError(ValueError):
    pass


def folder(ep: str) -> str:
    return os.path.join(ep, DIR)


def record_path(ep: str) -> str:
    return os.path.join(folder(ep), "lines.json")


def load(ep: str) -> dict:
    got = F.read_json_or(record_path(ep), {}, want=dict)
    got.setdefault("lines", {})
    got.setdefault("pauses", {})
    return got


def save(ep: str, record: dict) -> None:
    os.makedirs(folder(ep), exist_ok=True)
    F.write_json(record_path(ep), record)


def script_shots(ep: str) -> list[dict]:
    """Every shot in script order: {"id", "dur", "lines": [{"id", "shot", "who", "text"}]}."""
    from seriesmith.core.series_config import variant_of
    cfg_path, md_path = P.episode_files(ep)
    with open(cfg_path, encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    book = cfg.get("subjects") or {}
    subjects = {k for k in book if not k.startswith("_")}
    chars = {k for k, v in book.items() if not k.startswith("_") and isinstance(v, dict)
             and v.get("kind", "character") == "character"}
    with open(md_path, encoding="utf-8-sig") as fh:
        text = fh.read()
    epi = BLD.parse_script(text, subjects, chars, variant_of(cfg))
    out = []
    for seq in epi["sequences"]:
        for sh in seq["shots"]:
            lines = [{"id": f"{sh['id']}.{i}", "shot": sh["id"], "who": d["who"], "text": d["line"]}
                     for i, d in enumerate(sh["dialogue"], 1) if str(d.get("line") or "").strip()]
            out.append({"id": sh["id"], "dur": sh.get("duration"), "lines": lines})
    return out


def _speaker(cfg: dict, who: str, service: str, target=None) -> dict | None:
    from seriesmith.targets.generic.router_audio import speaker_of
    if target is not None and not service:
        # a local model has no speakers to choose from: its voice is the model's, from the description
        return {"id": f"model:{target.id}", "name": target.short or target.label}
    book = cfg.get("subjects") or {}
    entry = book.get(who) if isinstance(book.get(who), dict) else {}
    # a variant shares its base's voice
    base = book.get(entry.get("of")) if entry.get("of") else None
    return speaker_of(base if isinstance(base, dict) else entry, service)


def _base(cfg: dict, who: str) -> str:
    """The character a variant is of: one character keeps one voice and one file."""
    entry = (cfg.get("subjects") or {}).get(who)
    return (entry.get("of") if isinstance(entry, dict) else None) or who


def _config(ep: str) -> dict:
    cfg_path, _ = P.episode_files(ep)
    with open(cfg_path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def _name(cfg: dict, who: str) -> str:
    entry = (cfg.get("subjects") or {}).get(who)
    return (entry.get("name") if isinstance(entry, dict) else None) or who


def _picked(row: dict) -> dict | None:
    return next((t for t in row.get("takes") or [] if t.get("take") == row.get("picked") and t.get("status") == "ok"), None)


def plan(ep: str, target) -> dict:
    """What the episode's lines are, and what generating would make. Costs nothing.
    {"target", "service", "lines": [{"id", "shot", "who", "name", "text", "chars", "status": "missing" |
    "ok" | "changed", "speaker", "picked", "takes"}], "characters": [{"who", "name", "lines", "chars",
    "speaker", "source"}], "to_make": {"lines", "chars"}, "no_speaker": [names, of lines still to make],
    "recording": path or None, "can_lay": whether every line has a take}. With no `target` (a voice
    model that can't make lines), the same with nothing to make them with: files still can."""
    from seriesmith import targets as TG
    cfg = _config(ep)
    service = TG.service_of(target.spec) if target is not None else ""
    record = load(ep)
    rows, people = [], {}
    for shot in script_shots(ep):
        for ln in shot["lines"]:
            speaker = _speaker(cfg, ln["who"], service, target)
            have = record["lines"].get(ln["id"]) or {}
            chosen = _picked(have)
            status = "missing"
            if chosen:
                # a take cut from a file is in that file's voice, whoever the speaker is now, and one
                # from another model was chosen as it is: only this model's speaker changing says so
                same = chosen.get("text") == ln["text"] and (
                    chosen.get("source") == "file" or chosen.get("target") != (target.id if target is not None else None)
                    or chosen.get("voice") == (speaker or {}).get("id"))
                status = "ok" if same else "changed"
            rows.append({**ln, "name": _name(cfg, ln["who"]), "chars": len(ln["text"]), "status": status,
                         "speaker": speaker, "picked": have.get("picked"), "takes": have.get("takes") or []})
            base = _base(cfg, ln["who"])
            p = people.setdefault(base, {"who": base, "name": _name(cfg, base), "lines": 0, "chars": 0,
                                         "speaker": speaker, "source": (record.get("sources") or {}).get(base),
                                         "to_make": {"lines": 0, "chars": 0}})
            p["lines"] += 1
            p["chars"] += len(ln["text"])
            if status != "ok":
                p["to_make"]["lines"] += 1
                p["to_make"]["chars"] += len(ln["text"])
    todo = [r for r in rows if r["status"] != "ok"]
    recording = os.path.join(DIR, RECORDING).replace("\\", "/")
    return {"target": target.id if target is not None else None, "label": target.label if target is not None else "",
            "service": service, "paid": bool(service), "lines": rows, "characters": list(people.values()),
            "to_make": {"lines": len(todo), "chars": sum(r["chars"] for r in todo)},
            "no_speaker": sorted({r["name"] for r in todo if not r["speaker"]}),
            "recording": recording if os.path.isfile(os.path.join(ep, recording)) else None,
            "can_lay": bool(rows) and all(_picked(record["lines"].get(r["id"]) or {}) for r in rows)}


def reserve(ep: str, line: dict, target) -> int:
    """A new take of `line` written down as running, before it's sent. Its number."""
    with _WRITING:
        record = load(ep)
        row = record["lines"].setdefault(line["id"], {"takes": []})
        n = max((t["take"] for t in row["takes"]), default=0) + 1
        speaker = line["speaker"]
        row["takes"].append({"take": n, "status": "running", "text": line["text"], "voice": speaker["id"],
                             "voice_name": speaker.get("name") or speaker["id"], "target": target.id, "chars": len(line["text"])})
        save(ep, record)
    return n


def fail(ep: str, line_id: str, n: int, error: str) -> None:
    with _WRITING:
        record = load(ep)
        for t in (record["lines"].get(line_id) or {}).get("takes") or []:
            if t["take"] == n:
                t.update(status="failed", error=error[:800])
        save(ep, record)


def call_for(ep: str, line: dict, n: int, target) -> tuple[str, dict]:
    """(the model's id, its arguments) for take `n` of a line: the words alone, in its speaker."""
    from types import SimpleNamespace as NS
    from seriesmith import targets as TG
    entry = {"voices": {TG.service_of(target.spec): line["speaker"]}}
    job = NS(prompt=line["text"], seed=stable_seed(os.path.basename(os.path.abspath(ep)), line["id"], str(n)),
             ref=NS(entry=entry, subject=line["who"]))
    model, args = target.module.router_call(target, job)
    from seriesmith.backends.router import ROUTING
    args[ROUTING]["values"]["use"] = "timed"       # its timings too, where the provider gives them
    return model, args


def held_voice(ep: str, who: str, line_id: str) -> str:
    """The file a character's other lines continue when it has no sample of its own: the first of its
    lines made with a local model, in script order. "" for the first line itself."""
    cfg = _config(ep)
    base = _base(cfg, who)
    record = load(ep)
    for shot in script_shots(ep):
        for ln in shot["lines"]:
            if _base(cfg, ln["who"]) != base or ln["id"] == line_id:
                continue
            take = _picked(record["lines"].get(ln["id"]) or {})
            if take and str(take.get("voice") or "").startswith("model:"):
                return os.path.join(ep, take["file"])
    return ""


def local_job(ep: str, line: dict, n: int, target):
    """The voice job for take `n` of a line on a local model: only the character's own words to say,
    about as long as they take, continuing the character's voice. Nothing of the ref's changes: its
    takes and its sample stay as they are. RefError as planning a voice ref's."""
    from seriesmith import refs as R
    from seriesmith.targets.audio.common import spoken_seconds
    s = R.load_series(ep)
    base = _base(s.series_cfg, line["who"])
    entry = (s.series_cfg.get("subjects") or {}).get(base) or {}
    lo, hi = target.seconds_range()[2], target.seconds_range()[1]
    secs = max(lo, min(hi, float(round(spoken_seconds(line["text"]) + 1))))
    brief = target.voice_prompt(entry.get("name", base), entry.get("voice", ""), entry.get("design", ""), line["text"], secs)
    job = R.plan_generate(s, R.GenRequest(ref=f"voice:{base}", prompt=brief, seconds=secs, target=target.id, note=line["id"],
                                          seed=stable_seed(os.path.basename(os.path.abspath(ep)), line["id"], str(n)) % (2 ** 31)))[0]
    job.line = line["text"]
    if not (job.ref.file and os.path.isfile(job.ref.file)):
        job.held_sample = held_voice(ep, line["who"], line["id"])
    return job


def words_from(alignment: dict | None) -> list[dict] | None:
    """Character timings ({"characters", "character_start_times_seconds", "character_end_times_seconds"})
    as words, as Whisper's transcript gives them: [{"word", "start", "end"}]."""
    if not isinstance(alignment, dict):
        return None
    chars = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")
    if not (isinstance(chars, list) and isinstance(starts, list) and isinstance(ends, list)) \
            or not chars or not len(chars) == len(starts) == len(ends):
        return None
    words, word, a, b = [], "", 0.0, 0.0
    for c, s, e in zip(chars, starts, ends):
        if str(c).isspace():
            if word:
                words.append({"word": word, "start": round(a, 3), "end": round(b, 3)})
            word = ""
            continue
        if not word:
            a = float(s)
        word += str(c)
        b = float(e)
    if word:
        words.append({"word": word, "start": round(a, 3), "end": round(b, 3)})
    return words or None


def _to_wav(source: str, dest: str) -> None:
    """Any recording as what the episode's recording is laid from: 44.1 kHz, mono, 16 bit."""
    if not FF.have("ffmpeg"):
        raise LinesError("laying lines needs ffmpeg")
    got = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", source, "-ac", "1", "-ar", str(RATE),
                          "-c:a", "pcm_s16le", dest], capture_output=True, text=True)
    if got.returncode != 0 or not os.path.isfile(dest):
        raise LinesError(f"that take's sound couldn't be read: {(got.stderr or '').strip()[:300]}")


def finish(ep: str, line_id: str, n: int, run, savers: list | None = None) -> dict:
    """A finished run's sound kept as take `n` of the line, with its timings; picked when the line
    has no take picked, or the one picked no longer matches its words. `savers`: the graph's save nodes,
    what a local run's sound comes from."""
    outs = [o for o in run.outputs() if o.type in ("audio", "file")]
    outs = [o for o in outs if o.node in (savers or [])] or outs
    if not outs:
        raise LinesError("the job finished but returned no sound")
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1] or ".mp3")
    os.close(fd)
    os.makedirs(folder(ep), exist_ok=True)
    name = f"{line_id}_t{n:02d}.wav"
    dest = os.path.join(folder(ep), name)
    try:
        outs[0].save(tmp)
        scratch = dest + ".tmp.wav"
        try:
            _to_wav(tmp, scratch)
            F.replace(scratch, dest)
        finally:
            if os.path.exists(scratch):
                os.remove(scratch)
    finally:
        os.remove(tmp)
    with wave.open(dest, "rb") as w:
        seconds = w.getnframes() / float(w.getframerate())
    result = getattr(run, "result", None)
    words = words_from(result.get("alignment") if isinstance(result, dict) else None)
    with _WRITING:
        record = load(ep)
        row = record["lines"].setdefault(line_id, {"takes": []})
        take = next((t for t in row["takes"] if t["take"] == n), None)
        if take is None:
            take = {"take": n}
            row["takes"].append(take)
        take.update(status="ok", file=os.path.join(DIR, name).replace("\\", "/"), seconds=round(seconds, 3),
                    **({"words": words} if words else {}))
        was = _picked(row)
        if was is None or was.get("text") != take.get("text") or was.get("voice") != take.get("voice"):
            row["picked"] = n
        save(ep, record)
    return take


def pick(ep: str, line_id: str, n: int) -> None:
    with _WRITING:
        record = load(ep)
        row = record["lines"].get(line_id) or {}
        if not any(t.get("take") == n and t.get("status") == "ok" for t in row.get("takes") or []):
            raise LinesError(f"{line_id} has no finished take {n}")
        row["picked"] = n
        save(ep, record)


def is_recording(path: str | None) -> bool:
    """Whether a path is the recording lines are laid into."""
    return bool(path) and os.path.normpath(path).endswith(os.path.join(DIR, RECORDING))


def laid_sound(ep: str, shot: str | None) -> str | None:
    """What a shot's window of the laid recording holds: its lines' takes, as last laid. Two the same
    means the same sound, wherever it now sits. None when no lines were laid for it."""
    path = record_path(ep)
    if not shot or not os.path.isfile(path):
        return None
    got = T.read_json_kept(path) if hasattr(T, "read_json_kept") else None
    if not isinstance(got, dict):
        got = F.read_json_or(path, {}, want=dict)
    return (got.get("laid") or {}).get(shot)


def source_path(ep: str, who: str) -> str:
    return os.path.join(folder(ep), "sources", f"{who}.wav")


def _source_state(ep: str, who: str, **state) -> None:
    with _WRITING:
        record = load(ep)
        record.setdefault("sources", {})[who] = state
        save(ep, record)


def place_source(ep: str, who: str, source: str, name: str = "") -> str:
    """A character's whole file kept for this episode, as what lines are cut from. LinesError for one
    that isn't a character with lines here, or a file that can't be read. Word timings already beside
    the file (`<file>.words.json`) come with it, so it needn't be heard again."""
    cfg = _config(ep)
    if not any(_base(cfg, ln["who"]) == who for s in script_shots(ep) for ln in s["lines"]):
        raise LinesError(f"{who} has no lines in this script")
    dest = source_path(ep, who)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    scratch = dest + ".tmp.wav"
    try:
        _to_wav(source, scratch)
        F.replace(scratch, dest)
    finally:
        if os.path.exists(scratch):
            os.remove(scratch)
    cache = dest + ".words.json"
    told = F.read_json_or(source + ".words.json", None, want=list)
    if told:
        F.write_json(cache, told)
    elif os.path.exists(cache):
        os.remove(cache)                               # another file's words
    _source_state(ep, who, status="running", name=name or os.path.basename(source))
    return dest


def cut_character(ep: str, who: str, words: list[dict]) -> dict:
    """A character's file cut into a take per line, from its words: matched to that character's lines
    in script order, each cut at the pauses around it. A line that can't be heard in it gets no take, and
    is said. {"who", "lines", "cut", "unheard": [ids], "notes"}."""
    from seriesmith import align as A
    cfg = _config(ep)
    lines = [dict(ln) for s in script_shots(ep) for ln in s["lines"] if _base(cfg, ln["who"]) == who]
    if not lines:
        raise LinesError(f"{who} has no lines in this script")
    if not words:
        raise LinesError(f"nothing could be heard in {who}'s file")
    A.align_lines(lines, words)
    source = source_path(ep, who)
    with wave.open(source, "rb") as w:
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    total = len(pcm) / 2 / rate
    cut, unheard, notes = 0, [], []
    for i, ln in enumerate(lines):
        if ln.get("estimated") or ln.get("coverage", 0) < MIN_HEARD:
            unheard.append(ln["id"])
            notes.append(f"{ln['id']}: couldn't hear \"{ln['text'][:50]}\" in the file")
            continue
        if ln["coverage"] < 0.85:
            notes.append(f"{ln['id']}: only {ln['coverage']:.0%} of it matched (heard: \"{ln.get('heard', '')[:60]}\")")
        # to the pause each side: halfway to the neighbours, with a little air
        before = lines[i - 1].get("end", 0.0) if i else 0.0
        after = lines[i + 1].get("start", total) if i + 1 < len(lines) else total
        a = max((before + ln["start"]) / 2, ln["start"] - CUT_AIR, 0.0)
        b = min((ln["end"] + after) / 2, ln["end"] + CUT_AIR, total)
        data = pcm[int(a * rate) * 2:int(b * rate) * 2]
        inside = [{"word": x["word"], "start": round(x["start"] - a, 3), "end": round(x["end"] - a, 3)}
                  for x in words if a <= x["start"] and x["end"] <= b]
        with _WRITING:
            record = load(ep)
            row = record["lines"].setdefault(ln["id"], {"takes": []})
            n = max((t["take"] for t in row["takes"]), default=0) + 1
            name = f"{ln['id']}_t{n:02d}.wav"
            buf = io.BytesIO()
            with wave.open(buf, "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(data)
            F.write_bytes(os.path.join(folder(ep), name), buf.getvalue())
            row["takes"].append({"take": n, "status": "ok", "source": "file", "text": ln["text"], "voice": f"file:{who}",
                                 "voice_name": f"{_name(cfg, who)}'s file", "chars": len(ln["text"]),
                                 "file": os.path.join(DIR, name).replace("\\", "/"), "seconds": round(b - a, 3),
                                 **({"words": inside} if inside else {})})
            row["picked"] = n
            save(ep, record)
        cut += 1
    return {"who": who, "lines": len(lines), "cut": cut, "unheard": unheard, "notes": notes}


def _guessed_words(text: str, data: bytes, rate: int) -> list[dict]:
    """A take with no timings of its own: its words spread by length across where it makes sound. We
    know what it says and where it was laid, and align only asks each line's start and end. Whisper
    hearing the recording instead lost a one-word line and the silent shot before it (ep10, 2026-11-05)."""
    n = len(data) // 2
    window = max(1, rate // 100)
    levels = []
    for at in range(0, n, window):
        chunk = data[at * 2:(at + window) * 2]
        levels.append(max((abs(int.from_bytes(chunk[i:i + 2], "little", signed=True)) for i in range(0, len(chunk) - 1, 8)), default=0))
    loud = max(levels, default=0) * 0.1
    heard = [i for i, x in enumerate(levels) if x > loud] if loud else []
    a = heard[0] * window / rate if heard else 0.0
    b = (heard[-1] + 1) * window / rate if heard else n / rate
    said = text.split()
    total = sum(len(w) for w in said) or 1
    out, t = [], a
    for w in said:
        end = t + (b - a) * len(w) / total
        out.append({"word": w, "start": round(t, 3), "end": round(end, 3)})
        t = end
    return out


def _silence(seconds: float) -> bytes:
    return b"\0\0" * int(round(seconds * RATE))


def lay(ep: str) -> dict:
    """Every line's picked take, in script order with the script's pauses, as the episode's recording
    and its word timings beside it, attached as the dialogue track. Paid for already: costs nothing.
    {"path", "seconds", "lines", "timed", "notes"}. LinesError when a line has no take."""
    record = load(ep)
    shots = script_shots(ep)
    missing = [ln["id"] for s in shots for ln in s["lines"] if not _picked(record["lines"].get(ln["id"]) or {})]
    if missing:
        raise LinesError(f"{len(missing)} line(s) have no take yet: {', '.join(missing[:6])}")
    if not any(s["lines"] for s in shots):
        raise LinesError("this script has no lines")
    pauses = record["pauses"]
    laid = {}
    audio, words, notes = bytearray(), [], []
    guessed = 0
    at = 0.0

    def add(data: bytes) -> None:
        nonlocal at
        audio.extend(data)
        at += len(data) / 2 / RATE

    add(_silence(ENDS))
    silent = 0.0
    spoke_last = False
    for shot in shots:
        if not shot["lines"]:
            # what this shot's `dur:` said when it still had one (align comments it out)
            secs = shot["dur"] if shot["dur"] else pauses.get(shot["id"], SILENT_DEFAULT)
            pauses[shot["id"]] = float(secs)
            laid[shot["id"]] = SILENT
            silent += float(secs)
            continue
        if silent:
            add(_silence(silent + AROUND_SILENT))
        elif spoke_last:
            add(_silence(BETWEEN_SHOTS))
        silent = 0.0
        said = []
        for i, ln in enumerate(shot["lines"]):
            take = _picked(record["lines"][ln["id"]])
            said.append([ln["id"], take["take"], take.get("voice")])
            if take.get("text") != ln["text"]:
                notes.append(f"{ln['id']}: its take says something else now: generate it again")
            if i:
                add(_silence(WITHIN_SHOT))
            with wave.open(os.path.join(ep, take["file"]), "rb") as w:
                data = w.readframes(w.getnframes())
            if not take.get("words"):
                guessed += 1
            words += [{"word": x["word"], "start": round(x["start"] + at, 3), "end": round(x["end"] + at, 3)}
                      for x in (take.get("words") or _guessed_words(ln["text"], data, RATE))]
            add(data)
        laid[shot["id"]] = hashlib.sha1(json.dumps(said).encode("utf-8")).hexdigest()
        spoke_last = True
    add(_silence(silent + (AROUND_SILENT if silent else 0) + ENDS))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(audio))
    os.makedirs(folder(ep), exist_ok=True)
    path = os.path.join(folder(ep), RECORDING)
    F.write_bytes(path, buf.getvalue())
    F.write_json(path + ".words.json", words)          # after the recording: align wants it the newer
    record["laid"] = laid
    save(ep, record)
    from seriesmith import track as K
    K.set_track(ep, os.path.join(DIR, RECORDING).replace("\\", "/"))
    return {"path": os.path.join(DIR, RECORDING).replace("\\", "/"), "seconds": round(at, 3),
            "lines": sum(len(s["lines"]) for s in shots), "timed": True, "guessed": guessed, "notes": notes}
