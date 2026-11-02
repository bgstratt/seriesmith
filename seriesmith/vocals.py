"""
vocals.py — a recording's vocal stem (docs/SOUND.md phase 7: a song as the episode's recording).

A song's singing, split from the band by Hybrid Demucs (torchaudio's HDEMUCS_HIGH_MUSDB_PLUS)
in seriesmith's node pack (comfy_nodes/audio.py SeriesmithVocals), run as a job on this
machine's ComfyUI: LoadAudio -> SeriesmithVocals -> SaveAudio. Nothing is installed for it:
torchaudio comes with ComfyUI, and the weights are read from models/demucs/ (the Features
window's "Vocal stem") or downloaded once by torchaudio.

The stem lands beside the recording as `<recording>.vocals.wav` and is kept while it's at
least as new as the recording (as align's `<recording>.words.json`). It's **optional and off
by default**: CupsMV's H3 Ref2VA shots lip-synced as well to the full song as to the stem
(docs/SOUND.md phase 7), so two things may use it when asked:

- `align --vocals` transcribes the stem instead of the mix (the words Whisper hears under a
  band are the stem's anyway);
- the series config's `audio.dub_from: "vocals"` sends each dub shot's window from the stem
  (build writes the shotlist's `defaults.dub_track`, held_audio.dub_recording reads it); the
  episode's sound (assemble --audio master, the mix) stays the recording.
"""
from __future__ import annotations

import os

SUFFIX = ".vocals.wav"
# Hybrid Demucs's weights, as torchaudio's HDEMUCS_HIGH_MUSDB_PLUS downloads them; the node
# reads them from ComfyUI's models/demucs/ when they're there (comfy_nodes/audio.py)
WEIGHTS_FILE = "hdemucs_high_trained.pt"
WEIGHTS_FOLDER = "demucs"
WEIGHTS_URL = "https://download.pytorch.org/torchaudio/models/hdemucs_high_trained.pt"
DUB_FROM = ("recording", "vocals")      # the series config's audio.dub_from


def stem_path(recording: str) -> str:
    """Where `recording`'s vocal stem goes: beside it, `<recording>.vocals.wav`."""
    return recording + SUFFIX


def fresh(recording: str) -> str | None:
    """The stem's path when it's there and at least as new as the recording, else None."""
    stem = stem_path(recording)
    try:
        if os.path.getmtime(stem) >= os.path.getmtime(recording) and os.path.getsize(stem) > 0:
            return stem
    except OSError:
        pass
    return None


def dub_from(series_cfg: dict | None) -> str:
    """The series config's `audio.dub_from`: "vocals" or "recording" (the default)."""
    audio = (series_cfg or {}).get("audio") or {}
    return "vocals" if isinstance(audio, dict) and audio.get("dub_from") == "vocals" else "recording"


def graph(recording: str) -> dict:
    """The job: the recording loaded (uploaded by the backend), split, the vocals saved."""
    from seriesmith.backends import File
    return {
        "load": {"class_type": "LoadAudio", "inputs": {"audio": File(recording)},
                 "_meta": {"title": "The recording"}},
        "split": {"class_type": "SeriesmithVocals",
                  "inputs": {"audio": ["load", 0], "segment": 10.0, "overlap": 0.1}},
        "save": {"class_type": "SaveAudio",
                 "inputs": {"audio": ["split", 0], "filename_prefix": "seriesmith/vocals"},
                 "_meta": {"title": "The vocal stem"}},
    }


NODE = "SeriesmithVocals"


def check_backend(backend) -> None:
    """RuntimeError when `backend`'s ComfyUI hasn't loaded seriesmith's vocal-stem node (a
    backend that can't say is given the job)."""
    has = getattr(backend, "has_node", None)
    if has is not None and has(NODE) is False:
        raise RuntimeError(f"this ComfyUI ({backend.name}) hasn't seriesmith's {NODE} node: "
                           f"restart ComfyUI to load it (it's in seriesmith's node pack)")


def collect(recording: str, run, status: str, dest: str | None = None) -> str:
    """The run, ended with `status`: its audio written as the stem (24-bit wav at the rate
    it came at), at `dest` (default: beside the recording, stem_path; a take's voice stem
    goes beside the take, voices.py). Returns the stem's path; RuntimeError when there's
    nothing to keep."""
    import subprocess
    import tempfile

    from seriesmith import ff as FF
    from seriesmith.core import fileio as F
    if status != "succeeded":
        raise RuntimeError(getattr(run, "error", None) or f"the job ended {status}")
    outs = [o for o in run.outputs() if o.type == "audio"]
    if not outs:
        raise RuntimeError("the job finished but returned no audio")
    fd, raw = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1] or ".flac")
    os.close(fd)
    stem = dest or stem_path(recording)
    tmp = F.temp_beside(stem, ".wav")
    try:
        outs[0].save(raw)
        r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", raw, "-vn",
                            "-c:a", "pcm_s24le", tmp], capture_output=True, timeout=1800)
        if r.returncode != 0 or not os.path.isfile(tmp):
            raise RuntimeError("the vocal stem that came back couldn't be read: "
                               + r.stderr.decode("utf-8", "replace")[-300:])
        F.replace(tmp, stem)
    finally:
        for p in (raw, tmp):
            if os.path.exists(p):
                os.remove(p)
    return stem


def make(backend, recording: str, progress=None) -> str:
    """The stem made now on `backend` (submitted and watched here): its path."""
    check_backend(backend)
    run = backend.submit(graph(recording))
    status = run.watch(on_progress=progress)
    return collect(recording, run, status)


def ensure(recording: str, runner=None, backend: str = "local", log=print) -> str:
    """The recording's stem: the one beside it when it's fresh, else made on a queue
    (`runner`'s, or the command line's own: runner.cli_runner) and waited for.
    RuntimeError when it can't be made."""
    have = fresh(recording)
    if have:
        return have
    from seriesmith import runner as RN
    if runner is None:
        try:
            runner = RN.cli_runner(backend, log=log)
        except ValueError as e:
            raise RuntimeError(str(e)) from None
    if log:
        log(f"  making the vocal stem of {os.path.basename(recording)} on {backend} "
            f"(Hybrid Demucs)")
    job = runner.enqueue_vocals(recording, backend)
    status = RN.wait(runner.queue, [job]).get(job)
    qjob = runner.queue.jobs.get(job)
    have = fresh(recording)
    if status != "succeeded" or not have:
        raise RuntimeError(f"the vocal stem wasn't made: "
                           f"{(qjob.error if qjob is not None else '') or status}")
    return have
