"""
A video model on Comfy Router, described by data: `"code":
"builtin:router_video"` in its target.json, and its `router` block saying how a
shot becomes that model's own arguments. Every Router model is called the same
way (comfy-sdk models.submit, by "provider/model" id); what differs is the
shape of its input, and that is what `router.inputs` maps. Each input names
where it goes -- a field (a dotted path: "prompt", "parameters.seed",
"instances.0.prompt") or a list it is appended to, with an item template
("$prompt" and "$url" are filled in):

    "router": {
      "model": "provider/model-id",
      "arguments": {...},                         # sent as they are
      "inputs": {
        "prompt": "prompt",                       # a field, or
                  # {"list": "content", "item": {"type": "text", "text": "$prompt"}}
        "negative": "negative_prompt",
        "duration": {"name": "duration", "min": 4, "max": 30},   # whole seconds,
                    # or "values": [5, 10] (the nearest), "as": "str" for "5"
        "resolution": {"name": "resolution", "values": ["480p", "720p", "1080p"]},
                    # names ("768P", "2K") or sizes ("1280x720", "1280*720"),
                    # or {"480": "480p", ...} by height
        "ratio": {"name": "aspect_ratio", "values": ["16:9", "9:16"], "with_frames": "omit"},
        "seed": {"name": "seed", "max": 2147483647},
        "audio": {"name": "generate_audio"},      # or "on": "on", "off": "off"
        "references": {"list": "image_urls", "max": 4},           # item default "$url";
                    # "mention": "<<<image_{n}>>>" names each in the prompt (Kling)
        "first": {"field": "image_url"},          # or a list and an item, e.g.
                  # {"list": "content", "item": {"type": "image_url",
                  #   "image_url": {"url": "$url"}, "role": "first_frame"}}
        "last": {"field": "last_frame_url"},
        "voices": {"list": "content", "item": {"type": "audio_url",
                   "audio_url": {"url": "$url"}, "role": "reference_audio"},
                   "max": 3, "min_seconds": 2, "max_seconds": 15,
                   "mention": "@Audio {n}", "needs_picture": true},
                    # a clone shot's voice samples, a dub shot's window of the
                    # recording (sounds); the recipe's policies say which it renders
        "via": "seedance",                        # how pictures go in (File.via)
        "mode": {"name": "mode", "frames": "i2v", "text": "t2v"}
                    # a field that says which: frames sent, else words alone (FLUX 3)
      },
      "draft": {"proxy": true, "resolution": "480p", "final_resolution": "1080p"},
      "provider": "fal",                            # another provider of the model
      "fallback": false                             # Router may not try another
    }

What a shot sends: its prose prompt (the shared prose compile, video_prose);
with a first keyframe on disk and an input for it, its frames (first, and
last when there is one), else its references -- the subjects' pictures, then
the plate, a character's 4-panel sheet cut to the one panel the shot wants
(no provider takes a 4:1 strip) -- its length, size and ratio snapped to what
the model takes, its seed folded into the model's range, and whether it
makes sound. `draft` (Seedance 2.5): a proxy take is a Draft, and a final
made from one (job.from_draft) sends that draft's task id alone. `provider`:
another provider serves the model (Router translates the model's own
arguments to its input), `fallback: false` stops Router trying another when
that one is down; both ride in the arguments under backends.router.ROUTING.

Stdlib only (a panel is cut by helpers/refsheet.py, run as a subprocess).
"""
from __future__ import annotations

import copy
import os
import re

from seriesmith.targets import moderate as MOD
from seriesmith.targets.generic import video_prose as G

compile_episode = G.compile_episode
compile_shot = G.compile_shot
required_refs = G.required_refs
ref_slots = G.ref_slots


def panel_file(sheet: str, panels: int, index: int) -> str:
    """Panel `index` of the `panels`-panel strip `sheet`, as its own picture:
    `_panels/<name>_p<index>_<sha1>.png` beside the sheet, cut once (a new
    sheet has a new sha1, so a new file). One whose size can't be read is
    sent as it is."""
    from seriesmith import refs as R
    from seriesmith import takes as T
    from seriesmith.targets.video.ltx2_ingredients import sheet as S
    d = os.path.join(os.path.dirname(sheet), "_panels")
    name = os.path.splitext(os.path.basename(sheet))[0]
    out = os.path.join(d, f"{name}_p{index}_{T.file_sha1(sheet)[:10]}.png")
    if os.path.isfile(out):
        return out
    w, h = R.image_size(sheet) or (0, 0)
    if not w or not h or w < panels:
        return sheet
    os.makedirs(d, exist_ok=True)
    S.compose({"width": w // panels, "height": h, "background": "white", "gap": 0,
               "panels": [{"path": sheet, "fit": "cover",
                           "crop": {"panels": panels, "index": index}}]}, out)
    return out


# -- snapping to what the model takes ------------------------------------------

def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio (e.g. "16:9") nearest the picture's shape ("adaptive" and
    the like are not shapes: left out)."""
    want = width / height
    shapes = [r for r in ratios if ":" in r]

    def off(r: str) -> float:
        a, b = (int(x) for x in r.split(":"))
        return abs(a / b - want)
    return min(shapes, key=off)


# named sizes, by their height
NAMED = {"2k": 1440, "4k": 2160, "8k": 4320, "uhd": 2160, "fhd": 1080, "hd": 720, "sd": 480}


def size_of(name: str) -> tuple[int | None, int]:
    """A size's (width or None, height): "1280x720" / "1280*720" -> (1280, 720),
    "720p" / "768P" -> (None, 720), "2K" -> (None, 1440)."""
    s = str(name).strip().lower()
    m = re.fullmatch(r"(\d+)\s*[x*]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"(\d+)p", s)
    if m:
        return None, int(m.group(1))
    return None, NAMED.get(s, 0)


def nearest_resolution(width: int, height: int, values) -> str:
    """The model's name for the size nearest (width, height): `values` is
    {"480": "480p", ...} by height, or a list of names or WxH sizes (one of
    the same shape preferred)."""
    if isinstance(values, dict):
        best = min(values, key=lambda h: abs(int(h) - height))
        return values[best]
    landscape = width >= height

    def off(v):
        w, h = size_of(v)
        if w is None:
            return (0, abs(h - min(width, height) if not landscape else h - height))
        same = (w >= h) == landscape
        return (0 if same else 1, abs(w * h - width * height))
    return min(values, key=off)


def seconds_for(frames: int, fps: float, spec: dict):
    """A length in whole seconds the model takes: the nearest of `values`,
    else clamped to [min, max]; as a string when `as` says "str"."""
    s = max(1, round(frames / (fps or 24)))
    if spec.get("values"):
        s = min(spec["values"], key=lambda v: abs(float(v) - s))
        s = int(float(s))
    else:
        s = max(int(spec.get("min", s)), min(int(spec.get("max", s)), s))
    return str(s) if spec.get("as") == "str" else s


# -- where values go -------------------------------------------------------------

def _name(spec) -> str | None:
    """The field an input names: "x", {"name": "x"} or {"field": "x"}."""
    if isinstance(spec, str):
        return spec
    return (spec or {}).get("name") or (spec or {}).get("field")


def put(args: dict, path: str, value) -> None:
    """Set `value` at the dotted `path` ("instances.0.image"), making the
    dicts and lists on the way."""
    keys = path.split(".")
    cur = args
    for i, k in enumerate(keys):
        last = i == len(keys) - 1
        nxt = None if last else ([] if keys[i + 1].isdigit() else {})
        if isinstance(cur, list):
            n = int(k)
            while len(cur) <= n:
                cur.append({} if nxt is None or isinstance(nxt, dict) else [])
            if last:
                cur[n] = value
            else:
                if not isinstance(cur[n], type(nxt)):
                    cur[n] = nxt
                cur = cur[n]
        else:
            if last:
                cur[k] = value
            else:
                if not isinstance(cur.get(k), type(nxt)):
                    cur[k] = nxt
                cur = cur[k]


def append(args: dict, path: str, item) -> None:
    """Append `item` to the list at `path`, made when it isn't there."""
    keys = path.split(".")
    cur = args
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, [] if k.isdigit() else {})
    lst = cur.setdefault(keys[-1], []) if isinstance(cur, dict) else cur[int(keys[-1])]
    lst.append(item)


def fill(template, **values):
    """The item `template` with "$prompt", "$url"... filled in."""
    if isinstance(template, str) and template.startswith("$") and template[1:] in values:
        return values[template[1:]]
    if isinstance(template, dict):
        return {k: fill(v, **values) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, **values) for v in template]
    return template


def place(args: dict, spec, **values) -> None:
    """One input set where `spec` says: a field (the value itself, or its
    `item` filled in) or a list it is appended to (its `item` filled in)."""
    if isinstance(spec, str):
        put(args, spec, next(iter(values.values())))
        return
    item = fill(spec["item"], **values) if "item" in spec else next(iter(values.values()))
    if spec.get("list"):
        append(args, spec["list"], item)
    else:
        put(args, _name(spec), item)


# -- the shot's pictures -----------------------------------------------------------

def pictures(target, job, shot: dict, inp: dict, frames_ok: bool = True):
    """("frames" | "references", [(role, path, what)]): the frames when the
    model has an input for a first frame and the shot has one on disk (and
    `frames_ok`), else the shot's references (subjects, up to max_subjects,
    then the rest), a sheet as the panel its `view` asks for; `what` is the
    subject or the location."""
    from seriesmith import jobs as J

    def on_disk(rel: str) -> str | None:
        p = os.path.normpath(J._abs(job.root, rel)) if rel else ""
        return p if p and os.path.isfile(p) else None

    frames = {end: on_disk(p) for end, p in (shot.get("keyframes") or {}).items()}
    if frames_ok and inp.get("first") and frames.get("first"):
        return "frames", [(end, frames[end], end) for end in ("first", "last")
                          if frames.get(end) and inp.get(end)]
    if not inp.get("references"):
        return "references", []
    ref = target.recipe.get("reference_image") or {}
    panels = shot.get("panels") or []
    most = inp["references"].get("max") or target.capabilities().get("max_subjects") or 99
    subjects = [p for p in panels if p.get("subject")]
    out = []
    for p in subjects[:most] + [p for p in panels if not p.get("subject")]:
        path = on_disk(p.get("path", ""))
        if path and p.get("view") and p["view"] in (ref.get("views") or {}):
            path = panel_file(path, int(ref.get("sheet_panels") or 4), int(ref["views"][p["view"]]))
        if path:
            out.append(("references", path, p.get("subject") or p.get("location") or ""))
    total = inp["references"].get("max_total")
    return "references", out[:total] if total else out


def fit(text: str, most: int) -> str:
    """`text` in at most `most` characters, by whole sentences: the style line
    goes first, then sentences from the start (the place, then the people's
    looks, which the pictures carry), so what happens -- the action, the
    dialogue, the sound, at the end -- stays; cut mid-sentence only when the
    last one alone is longer than that."""
    if len(text) <= most:
        return text
    sents = [s.strip() for s in re.findall(r"[^.!?]*[.!?]+[\"”')]*|[^.!?]+$", text) if s.strip()]
    sents = [s for s in sents if not s.startswith("Style:")] or sents
    while len(sents) > 1 and len(" ".join(sents)) > most:
        sents.pop(0)
    out = " ".join(sents)
    return out if len(out) <= most else out[:most].rstrip()


def mentions(template: str, pics: list, shot: dict) -> str:
    """The line naming each reference picture in the prompt, for a model that
    takes them by name, e.g. <<<image_1>>> is Earl Booker. <<<image_2>>> is
    the place, Pond Side."""
    out = []
    for n, (_, _, what) in enumerate(pics, 1):
        name = str(what).replace("_", " ").title()
        place_ = what and any(p.get("location") == what for p in shot.get("panels") or [])
        out.append(f"{template.replace('{n}', str(n))} is {'the place, ' + name if place_ else name}.")
    return " ".join(out)


DEFINE_WORDS = 20                     # a subject's features: its design's opening words
# words a cut phrase mustn't end on (a definition then reads "... into in @Image 1")
DANGLING = {"a", "an", "the", "and", "or", "of", "with", "into", "in", "on", "under", "over",
            "to", "for", "from", "at", "by", "her", "his", "their", "its"}


def features(text: str, most: int = DEFINE_WORDS, body: bool = True) -> str:
    """A design or a place's description cut to its opening clause(s): whole
    comma-separated clauses up to `most` words, else the first `most` words.
    Seedance's guide asks for 2-3 stable features that tell the subject apart;
    without `body`, what describes a body is left out (targets.moderate)."""
    head = re.split(r"[:;]", str(text or "").strip(), maxsplit=1)[0]     # a list after a colon is detail
    words = 0
    out = []
    clauses = [c.strip() for c in head.rstrip(".").split(",") if c.strip()]
    if not body:
        clauses = [c for c in (MOD.unbodied(c) for c in clauses) if c]
    for clause in clauses:
        n = len(clause.split())
        if out and words + n > most:
            break
        out.append(clause)
        words += n
    cut = ", ".join(out).split()[:most]
    while cut and cut[-1].lower() in DANGLING:                         # "...swept up into" -> "...swept up"
        cut.pop()
    return " ".join(cut)


def definitions(pics: list, shot: dict, series_cfg: dict) -> str:
    """The line that opens a Seedance prompt (BytePlus's prompt guide: "Define
    [core features] in <Image N> as <Subject N>", the subjects defined first
    and then called by the same label throughout, as the prose already calls
    them by name): each picture by its place among the request's images,
    `@Image N`; a character or a thing as its name, from the opening of its
    design; the plate as the scene."""
    subjects = series_cfg.get("subjects") or {}
    places = series_cfg.get("locations") or {}
    plate = {p.get("location") for p in shot.get("panels") or [] if p.get("location")}
    defs, scenes = [], []
    for n, (_, _, what) in enumerate(pics, 1):
        if what in plate:
            loc = places.get(what) or {}
            look = features(loc.get("description") or "") or str(what).replace("_", " ")
            # a multishot group with several plates: whose scene each is
            # (docs/MULTISHOT.md), else the one scene
            parts = shot.get("multishot") or []
            shots = [f"Shot {i}" for i, p in enumerate(parts, 1) if p.get("plate") == what]
            whose = (" of " + (" and ".join(shots) if len(shots) < 3 else
                               ", ".join(shots[:-1]) + " and " + shots[-1])
                     if len(plate) > 1 and shots else "")
            scenes.append(f"Define {look} in @Image {n} as the scene{whose}.")
            continue
        sub = subjects.get(what) or {}
        base = subjects.get(sub.get("of")) or {} if sub.get("of") else {}
        name = sub.get("name") or base.get("name") or str(what).replace("_", " ").title()
        look = features(sub.get("design") or base.get("design") or "", body=False)
        defs.append(f"{look} in @Image {n} as {name}" if look else f"the subject in @Image {n} as {name}")
    line = ("Define " + ", and define ".join(defs) + ".") if defs else ""
    return " ".join([x for x in [line, *scenes] if x])


def board_prompt(part: dict, pics: list, series_cfg: dict, mention: str | None, most: int) -> str:
    """One storyboard part's prompt (video_prose.board_parts) in at most
    `most` characters: its framing and lines always, then its action, camera
    and sound while there is room, in the order a shot reads; then the
    pictures of who is in it and the place, named by `mention`
    ("<<<image_{n}>>>") as the request numbers them."""
    subjects = series_cfg.get("subjects") or {}
    names = []
    for n, (_, _, what) in enumerate(pics, 1):
        if what in part.get("subjects", []):
            e = subjects.get(what) or {}
            name = e.get("name") or (subjects.get(e.get("of")) or {}).get("name") or what
            names.append(f"{mention.replace('{n}', str(n))} is {name}." if mention else "")
        elif what not in subjects and mention:
            names.append(f"{mention.replace('{n}', str(n))} is the place.")
    tail = " ".join(x for x in names if x)
    room = most - (len(tail) + 1 if tail else 0)
    keep = {"frame", "lines"}
    order = ["frame", "camera", "action", "lines", "sound"]

    def text() -> str:
        return " ".join(part[k] for k in order if k in keep and part.get(k))

    for k in ("action", "camera", "sound"):
        keep.add(k)
        if len(text()) > room:
            keep.discard(k)
    out = fit(text(), room)
    return f"{out} {tail}" if tail else out


def sounds_wanted(inp: dict, shot: dict) -> bool:
    """Whether this shot sends audio references: a clone or a dub, on a model
    with the input."""
    return bool(inp.get("voices")) and shot.get("audio_policy") in (
        "clone", "dub", "dub_keep_foley")


def sounds(target, job, shot: dict, inp: dict, pics: list) -> tuple[list, str]:
    """([(path, what)], the prompt's line naming them) a shot sends as audio
    references (router.inputs.voices): a clone shot's voice samples, one per
    speaker, or a dub shot's window of the recording; ([], "") for any other
    shot, a model without the input, or a file not on disk (rendering anyway
    without it). A sample past the model's longest is cut between words
    (audiocut.voice_clip); one shorter than its shortest, or a window outside
    the range, is a ValueError before anything is sent; a window shorter
    than the shortest is padded with silence. `mention` names each
    as the request numbers them, as the pictures are named ("@Audio {n}")."""
    from seriesmith import audiocut as AC
    from seriesmith import jobs as J
    from seriesmith.targets import held_audio as HA
    spec = inp.get("voices")
    policy = shot.get("audio_policy")
    if not spec or policy not in ("clone", *HA.DUB):
        return [], ""
    lo, hi = float(spec.get("min_seconds") or 0), float(spec.get("max_seconds") or 0)
    name = target.short or target.id

    def on_disk(rel: str) -> str | None:
        p = os.path.normpath(J._abs(job.root, rel)) if rel else ""
        return p if p and os.path.isfile(p) else None

    def check(path: str, what: str, secs: float | None) -> None:
        if secs is not None and lo and secs < lo:
            raise ValueError(f"{what} is {secs:.1f}s and {name} hears {lo:g}s at the least: "
                             f"use a longer one. Nothing was sent")
        if secs is not None and hi and secs > hi:
            raise ValueError(f"{what} is {secs:.1f}s and {name} hears {hi:g}s at the most. "
                             f"Nothing was sent")

    cfg = J.series_config(job.root) or {}
    book = cfg.get("subjects") or {}
    out, said = [], []
    mention = spec.get("mention") or "@Audio {n}"
    if policy == "clone":
        for r in shot.get("voice_refs") or []:
            path = on_disk(r.get("sample", ""))
            if not path:
                continue
            e = book.get(r["subject"]) or {}
            who = e.get("name") or (book.get(e.get("of")) or {}).get("name") or r["subject"]
            secs = AC.duration(path)
            if hi and secs and secs > hi:
                path, secs = AC.voice_clip(path, max(lo, hi - 3.0), hi)
            check(path, f"{who}'s voice sample", secs)
            out.append((path, r["subject"]))
            said.append(f"Use {mention.replace('{n}', str(len(out)))} as the voice of {who}.")
    else:
        (slot,) = HA.recording_slot(job.doc, shot)
        track = on_disk(slot["path"])
        if track:
            if "audio_in" in shot and not shot.get("audio_file"):
                a_in, a_out = float(shot["audio_in"]), float(shot["audio_out"])
                # a line shorter than the model hears is padded with silence
                check(track, f"{shot.get('id', 'the shot')}'s window of the recording "
                             f"({a_in:.2f}-{a_out:.2f}s)", max(a_out - a_in, lo))
                track = AC.window(track, a_in, a_out, at_least=lo)
            else:
                check(track, os.path.basename(track), AC.duration(track))
            out.append((track, "recording"))
            said.append(f"Use {mention.replace('{n}', '1')} as the exact dialogue and soundtrack "
                        f"of the shot: the lips are synced to it.")
            if spec.get("rereads"):
                job.notes.append(f"{policy} on {name}: it re-reads the recording in its voice, at "
                                 f"its own pace, so the lips follow the take's own sound: keep it "
                                 f"rather than laying the recording over the cut")
    if out and spec.get("needs_picture") and not pics:
        raise ValueError(f"{name} can't be sent audio without a picture, and "
                         f"{shot.get('id', 'this shot')} has none on disk. Nothing was sent")
    return out, " ".join(said)


def check_ratios(target, pics: list) -> None:
    """ValueError, before anything is sent, for a picture whose shape the model
    refuses (its target's `router.picture_ratio`, [narrowest, widest] as width
    over height: Seedance's library answers 400 AspectRatioTooLarge past 2.5).
    It says which picture and leaves it as it is: a paid call never crops or
    pads a picture by itself, so the cut (the sides, or another plate) is the
    user's to choose."""
    lo, hi = (target.spec.get("router") or {}).get("picture_ratio") or (None, None)
    if lo is None:
        return
    from seriesmith.refs import image_size
    for _, path, what in pics:
        size = image_size(path)
        if not size or not size[1]:
            continue
        r = size[0] / size[1]
        if not lo <= r <= hi:
            cut = (f"{round(size[1] * hi)}x{size[1]}, its sides trimmed" if r > hi else
                   f"{size[0]}x{round(size[0] / lo)}, its top and bottom trimmed")
            raise ValueError(
                f"{os.path.basename(path)} ({what or 'a picture'}) is {size[0]}x{size[1]}, "
                f"{r:.2f} wide to 1 high, and {target.short or target.id} takes pictures from "
                f"{lo:g} to {hi:g}: crop it ({cut}) or use another picture. Nothing was sent")


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one take of `job` (a seriesmith.jobs.Job), its
    pictures as backends.File, which the Router backend uploads."""
    from seriesmith import jobs as J
    from seriesmith.backends import File

    spec = target.spec["router"]
    inp = spec.get("inputs") or {}
    draft = spec.get("draft") or {}
    res_name = _name(inp.get("resolution")) or "resolution"
    if getattr(job, "from_draft", None):
        # the final of a draft: its task id alone; the provider reuses the
        # draft's prompt, pictures, length, ratio, seed and sound
        return spec["model"], with_routing({"content": [{"type": "draft_task",
                                                         "draft_task": {"id": job.from_draft["task"]}}],
                                            res_name: draft.get("final_resolution", "1080p")}, spec)
    shot = J.frozen_shotlist(job)["shots"][0]
    text = J._prompt_text(shot.get("prompt") or job.prompt)
    via = inp.get("via", "")
    # audio and frames don't mix on Seedance ("first/last frame content cannot
    # be mixed with reference media content"): a shot it hears goes by its
    # references, its keyframes left out
    hears = (inp.get("voices") or {}).get("with_frames") is False and bool(
        sounds_wanted(inp, shot))
    mode, pics = pictures(target, job, shot, inp, frames_ok=not hears)
    if hears and any(p for p in (shot.get("keyframes") or {}).values()
                     if os.path.isfile(J._abs(job.root, p))):
        job.notes.append(f"{target.short or target.id} can't take a first or last frame "
                         f"with audio: the shot's keyframes weren't sent, its references were")
    if target.capabilities().get("requires_first") and mode != "frames":
        # an image-to-video model (Runway): nothing to start from, nothing to send
        raise ValueError(f"{target.short or target.id} starts every shot from its first keyframe, and "
                         f"{shot.get('id', 'this shot')} has none yet: make it first (the shot's "
                         f"menu, or first: generate in the script)")
    check_ratios(target, pics)
    heard, voice_line = sounds(target, job, shot, inp, pics)
    args = copy.deepcopy(spec.get("arguments") or {})

    # the pictures named at the end (Kling), the prose cut to the longest
    # prompt the model takes (Runway: 1000) to leave room for them
    pspec = inp.get("prompt") or "prompt"
    mention = (inp.get("references") or {}).get("mention")
    tail = mentions(mention, pics, shot) if mention and mode == "references" and pics else ""
    # the pictures defined first (Seedance: its prompt guide's "Define ... in @Image N as ...")
    head = (definitions(pics, shot, J.series_config(job.root) or {})
            if (inp.get("references") or {}).get("define") and mode == "references" and pics else "")
    # the audio named after the pictures ("Use @Audio 1 as the voice of Ada.")
    head = "\n\n".join(x for x in (head, voice_line) if x)
    limit = pspec.get("max_chars") if isinstance(pspec, dict) else None
    if limit:
        text = fit(text, limit - sum(len(x) + 2 for x in (head, tail) if x))
    if head:
        text = f"{head}\n\n{text}"
    if tail:
        text = f"{text}\n\n{tail}"

    # the prompt, then the pictures, in that order (a content list keeps it); a
    # multishot group on a model that takes a storyboard sends each shot's own
    # prose and seconds there instead (docs/MULTISHOT.md: Kling's multi_prompt)
    board = inp.get("storyboard")
    # an override's prompt is sent as written, as one prompt (as ltx2's is)
    built = (getattr(job, "recompiled", None) or getattr(job, "shot", None) or {}).get("prompt")
    overridden = getattr(job, "prompt", None) not in (None, built)
    if board and shot.get("storyboard") and not overridden:
        most = int(board.get("max_chars") or 512)
        put(args, board["switch"], True)
        if board.get("type"):
            put(args, board["type"]["name"], board["type"]["value"])
        cfg = J.series_config(job.root) or {}
        for n, part in enumerate(shot["storyboard"], 1):
            secs = str(part["seconds"]) if board.get("seconds_as") == "str" else part["seconds"]
            append(args, board["list"], fill(board["item"], index=n,
                                            prompt=board_prompt(part, pics, cfg, mention, most),
                                            seconds=secs))
    else:
        place(args, pspec, prompt=text)
    for role, path, _ in pics:
        place(args, inp[role], url=File(path, via=via),
              mime="image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png")
    for path, _ in heard:
        # a sound's own way in (Seedance's library registers pictures only:
        # "get image info ... not supported", 2026-10-28), else the pictures'
        place(args, inp["voices"], url=File(path, via=inp["voices"].get("via", via)),
              mime="audio/wav")
    neg = inp.get("negative")
    if neg and getattr(job, "negative", None):
        place(args, neg, negative=job.negative)

    # length, size, ratio, seed, sound
    fps = job.fps or target.template.fps
    w, h = int(job.width or 1280), int(job.height or 720)
    if inp.get("duration"):
        put(args, _name(inp["duration"]), seconds_for(job.frames, fps, inp["duration"]))
    if inp.get("resolution"):
        put(args, res_name, nearest_resolution(w, h, inp["resolution"]["values"]))
    ratio = inp.get("ratio")
    if ratio:
        frames_mode = ratio.get("with_frames", "omit")
        if mode == "frames" and frames_mode != "keep":
            if frames_mode != "omit":
                put(args, _name(ratio), frames_mode)                 # e.g. "adaptive"
        else:
            put(args, _name(ratio), nearest_ratio(w, h, ratio["values"]))
    if inp.get("seed"):
        put(args, _name(inp["seed"]), int(job.seed) % (int(inp["seed"].get("max", 4294967295)) + 1))
    if inp.get("audio"):
        a = inp["audio"]
        on = shot.get("audio_policy") != "silent"
        put(args, _name(a), a.get("on", True) if on else a.get("off", False))
    if inp.get("mode"):
        m = inp["mode"]
        put(args, _name(m), m["frames"] if mode == "frames" and pics else
            m.get("references" if pics else "text", m.get("text")))

    # a proxy is a draft (Seedance 2.5): its final can be made from it
    if job.pass_ == "proxy" and draft.get("proxy"):
        args["draft"] = True
        if draft.get("resolution"):
            put(args, res_name, draft["resolution"])
    return spec["model"], with_routing(args, spec)


def with_routing(args: dict, spec: dict) -> dict:
    """`args` with how Router is to serve the call (the model's provider, and
    whether it may fall back), when the target says."""
    from seriesmith.backends.router import ROUTING
    how = {k: spec[k] for k in ("provider", "fallback") if spec.get(k) is not None}
    if how:
        args[ROUTING] = how
    return args
