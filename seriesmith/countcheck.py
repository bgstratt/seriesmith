"""
countcheck.py — a take check (takecheck.register, as `count`): more people or faces in the
take than its shot has (docs/DAILIES.md, checklist 9).

**What the shot has:** its cast (the script's `who:` and `with:`, each character once, a
variant as the character it's a variant of) and its `extras:`, counted from their words: "a
night nurse" is one, "two paramedics" two, "a nurse and a porter" two. Extras whose number the
words don't say ("day-shift nurses", "a few", "a dozen") leave the number open, and the take
isn't checked (`why` says so). A `continuous: multishot` group's take isn't either (its shots
each have their own).

**What the take has:** people (YOLOv8m person segmentation) and faces (YOLOv8m face) in each
frame at SAMPLE_FPS, on the CPU, in a Python that has ultralytics (helpers/counts.py: ComfyUI's,
where the Impact Subpack installs it), at confidence CONF.

**Flagged** when either is over the shot's number for RUN seconds or more running. Never on the
take's median, which hid LAST LIGHT-style duplicates that come and go (Porchlights sh1570 t02:
5 people at the peak against 4 asked, 4 on the median). Fewer is never flagged: a face turned
away, a person out of frame, are the shot working. Measured 2026-11-12 (DAILIES.md,
"Detectors"): caught Porchlights sh1190 (one man, two heads), sh1420 (a hooded third person),
sh1510 (two Emilys), and flagged none of eight clean takes.

The weights are PyTorch pickles: each is loaded only when its sha256 is the one WEIGHTS records
(the helper checks, just before loading). The Features window downloads them (`Count check`).

    expected(root, shot) -> (n | None, why)    the people the shot has
    extras_count(text) -> n | None             the people an extras line names
    check(root, take, frozen_shot) -> {...}    the take check
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

SAMPLE_FPS = 8.0
CONF = 0.5
RUN = 0.25                  # seconds over the shot's number, running, to flag
TIMEOUT = 600
FOLDER = "ultralytics"      # ComfyUI's models folder (the Impact Subpack's)
WEIGHTS = {
    "person": {"name": "segm/person_yolov8m-seg.pt",
               "url": "https://huggingface.co/Bingsu/adetailer/resolve/main/person_yolov8m-seg.pt",
               "sha256": "c8ab26f517173b1fe8342d336a09f443eb61cb08dcbfc78d53fff4c2547ae81e"},
    "face": {"name": "bbox/face_yolov8m.pt",
             "url": "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt",
             "sha256": "717923c19b3f4bbf5250b728f1fa6b2cb72a33aed1d236ea9caf0e21ad943e5f"},
}
FEATURE = "Count check (people and faces)"

_NUMBERS = {"a": 1, "an": 1, "one": 1, "another": 1, "single": 1, "lone": 1, "two": 2,
            "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "pair": 2, "couple": 2}
# a number of people the words leave open
_OPEN = {"few", "several", "some", "many", "dozen", "dozens", "crowd", "crowds", "group",
         "groups", "handful", "line", "row", "rows", "number", "lots", "hundreds", "scores"}
_PART = re.compile(r"\s*(?:;|,?\s+and\s+|,\s+(?=(?:a|an|one|two|three|four|five|six|seven|eight|"
                   r"nine|ten|another)\b))\s*", re.I)


def extras_count(text: str | None) -> int | None:
    """How many people an `extras:` line names: 0 for none, None when its words leave it open.
    Each part ("a night nurse", "two porters"; parts joined by "and", ";" or a comma before
    "a"/"two"/...) starts with how many."""
    text = (text or "").strip()
    if not text:
        return 0
    total = 0
    for part in _PART.split(text):
        words = re.findall(r"[a-z]+|\d+", part.lower())
        if not words:
            continue
        if any(w in _OPEN for w in words[:3]):
            return None
        first = words[0]
        if first.isdigit():
            total += int(first)
        elif first in _NUMBERS:
            n = _NUMBERS[first]
            if first in ("a", "an") and len(words) > 1 and words[1] in ("pair", "couple"):
                n = 2
            total += n
        else:
            return None                         # "nurses passing", "the shoulders of ..."
    return total


def _shot(root: str, shot_id: str) -> tuple[dict | None, dict, set]:
    """(the script's shot as it is now, {variant: what it's a variant of}, the characters)."""
    from seriesmith import build as BLD
    from seriesmith.core import paths as P
    from seriesmith.core.series_config import variant_of
    cfg_path, md_path = P.episode_files(root)
    with open(cfg_path, encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    book = cfg.get("subjects") or {}
    subjects = {k for k in book if not k.startswith("_")}
    chars = {k for k, v in book.items() if not k.startswith("_") and isinstance(v, dict)
             and v.get("kind", "character") == "character"}
    with open(md_path, encoding="utf-8-sig") as fh:
        text = fh.read()
    variants = variant_of(cfg)
    epi = BLD.parse_script(text, subjects, chars, variants)
    for seq in epi["sequences"]:
        for sh in seq["shots"]:
            if sh.get("id") == shot_id:
                return sh, variants, chars
    return None, variants, chars


def expected(root: str, shot_id: str) -> tuple[int | None, str]:
    """(how many people the shot has, "") or (None, why it can't be said)."""
    from seriesmith.core.story import ScriptError
    try:
        sh, variants, chars = _shot(root, shot_id)
    except (OSError, ValueError, KeyError, ScriptError) as e:
        return None, f"the script can't be read: {str(e)[:160]}"
    if sh is None:
        return None, f"{shot_id} isn't in the script now"
    # who: and with: (the parse files with: under props): the characters among them, once each
    named = (sh.get("cast") or []) + (sh.get("props") or [])
    cast = {variants.get(c, c) for c in named if variants.get(c, c) in chars}
    extra = extras_count(sh.get("extras"))
    if extra is None:
        return None, f"its extras don't say how many ({str(sh.get('extras'))[:60]})"
    return len(cast) + extra, ""


def weights() -> tuple[dict | None, str]:
    """({kind: path}, "") or (None, why they aren't there)."""
    from seriesmith import hubcache as HC
    models_dir = HC.local_models_dir()
    d = models_dir(FOLDER) if models_dir else None
    if not d:
        return None, "ComfyUI's models folder isn't known here"
    paths = {k: os.path.join(d, *w["name"].split("/")) for k, w in WEIGHTS.items()}
    gone = [os.path.basename(p) for p in paths.values() if not os.path.isfile(p)]
    if gone:
        return None, f"{', '.join(gone)} isn't downloaded: the Features window's {FEATURE}"
    return paths, ""


_PYTHON: list = []


def python() -> tuple[str | None, str]:
    """(a Python with ultralytics and PyAV, "") or (None, why there's none): ComfyUI's first,
    then the one running this. Found once."""
    if _PYTHON:
        return _PYTHON[0]
    from seriesmith import installer as INS
    cands = []
    try:
        import folder_paths  # noqa: F401  inside ComfyUI: its own Python
        cands.append(sys.executable)
    except ImportError:
        from seriesmith import settings as S
        st = S.load_settings()
        try:
            cands.append(INS.place_from_url(st.local_comfyui, st.comfyui_dir).python)
        except Exception:                       # noqa: BLE001  no ComfyUI to ask
            pass
        cands.append(sys.executable)
    for py in [p for p in cands if p]:
        if INS.python_has(py, "ultralytics") and INS.python_has(py, "av"):
            _PYTHON.append((py, ""))
            return _PYTHON[0]
    return None, (f"no Python here has ultralytics (ComfyUI's gets it with the Impact Subpack): "
                  f"the Features window's {FEATURE}")


def measure(mp4: str, paths: dict, py: str, timeout: int = TIMEOUT) -> list[list]:
    """[[t, people, faces], ...] for the take. RuntimeError when the helper fails."""
    from seriesmith import edit as E
    cmd = [py, E.RUNNER, "seriesmith.helpers.counts", mp4, "--person", paths["person"],
           "--face", paths["face"], "--fps", str(SAMPLE_FPS), "--conf", str(CONF)]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                       creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    out = r.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        got = json.loads(out[-1])
    except (IndexError, ValueError):
        raise RuntimeError(f"the count helper said nothing ({r.stderr.decode('utf-8', 'replace')[-200:]})")
    if got.get("error"):
        raise RuntimeError(got["error"])
    return got.get("frames") or []


def over(rows: list[list], want: int, col: int, fps: float = SAMPLE_FPS) -> tuple[float, float] | None:
    """The first span of frames whose count (column `col`) is over `want` for RUN s or more,
    as (start, end) seconds; None when there's none."""
    need = max(1, round(RUN * fps))
    start = run = 0
    for i, row in enumerate(rows):
        if row[col] > want:
            if run == 0:
                start = i
            run += 1
            if run >= need:
                end = i
                while end + 1 < len(rows) and rows[end + 1][col] > want:
                    end += 1
                return rows[start][0], rows[end][0]
        else:
            run = 0
    return None


def judge(rows: list[list], want: int) -> dict:
    """The check's record from the counts: {"flag", "why", "want", "people", "faces", "at"}."""
    people = max((r[1] for r in rows), default=0)
    faces = max((r[2] for r in rows), default=0)
    out = {"flag": False, "why": "", "want": want, "people": people, "faces": faces,
           "fps": SAMPLE_FPS}
    for col, what in ((1, "people"), (2, "faces")):
        span = over(rows, want, col)
        if span:
            n = max(r[col] for r in rows if span[0] <= r[0] <= span[1])
            out.update(flag=True, at=list(span),
                       why=f"{n} {what} for {want} ({span[0]:.1f}-{span[1]:.1f} s)")
            break
    return out


def check(root: str, take, frozen_shot: dict | None) -> dict | None:
    """takecheck's `count`: None when there's nothing to say (a multishot group), else the
    record, `why` alone when it can't be checked here."""
    shot = frozen_shot or {}
    if shot.get("multishot"):
        return None
    want, why = expected(root, take.shot)
    if want is None:
        return {"flag": False, "why": why}
    paths, why = weights()
    if paths is None:
        return {"flag": False, "why": why}
    py, why = python()
    if py is None:
        return {"flag": False, "why": why}
    return judge(measure(take.paths.mp4, paths, py), want)


__all__ = ["CONF", "FEATURE", "FOLDER", "RUN", "SAMPLE_FPS", "WEIGHTS", "check", "expected",
           "extras_count", "judge", "measure", "over", "python", "weights"]
