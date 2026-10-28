"""
LTX-2.5 + MSR: the story IR compiled into shotlist entries for Licon's MSR
two-stage graph (workflow.json, an API graph; target.json beside this file).

    compile_episode(target, story, series_cfg, pass_, only=None) -> (doc, report)
    compile_shot(target, shot_ir, series_cfg, preset, ctx) -> one entry
    compile_without(target, story, series_cfg, pass_, entry, missing) -> entry
    required_refs(target, shot_ir, series_cfg, ctx) -> [RefRequest]
    ref_slots(target, doc, shot) -> one slot per picture (and a face picture)
    stage_inputs(target, job, comfy) -> {"pic1": name, ..., "background": name}
    patch_graph(target, graph, job, inputs) -> the pictures into both guides

An entry carries the neutral keys every target's entries do, LTX's
`negative`, and MSR's own: `global_prompt` (PromptRelay's global prompt: each
picture's `Image N:` line and the look; `prompt` is the local one, the scene)
and `references`, the pictures in the guide's order, each {"subject", "path",
"face"?} or {"location", "path"}. One shot a generation: the target has no
`multishot` form, so the build refuses a `continuous: multishot` group on it
(docs/MULTISHOT.md, "LTX MSR revisited").

The pictures themselves are made at queue time (stage_inputs): each person or
thing a 16:9 sheet on grey at the render size, composed by
seriesmith/helpers/refsheet.py (the full body, the face, the back of a
4-panel strip; a whole picture and its face), uploaded, and moved into the
take as <shot>_tNN_msrN.png; the plate is sent as it is.

Missing pictures: all are required (blocked, as H3's). Rendering anyway
recompiles the entry without them (compile_without), so the prompt's `Image
N` numbers are the guide's. A shot with no person or thing pictured renders
from words alone: patch_graph splices both guides out.

Stdlib only.
"""
from __future__ import annotations

import os
import uuid

from seriesmith import targets as TG
from seriesmith.core import ir
from seriesmith.targets import video_compile as VC
from seriesmith.targets import held_audio as HA
from seriesmith.targets.graph import abs_path as _abs, consumers as _consumers, of as _of
from seriesmith.targets.video.ltx2_ingredients.compile import plate_request, subject_request
from seriesmith.targets.video_compile import shot_duration as _duration, shotlist_extra

from . import prompt as P

ID = "ltx2_msr"
TARGET = TG.load_target(ID, "video")
RECIPE = TARGET.recipe
REF = dict(RECIPE.get("references") or {})
SLOTS = list(REF.get("slots") or ["pic1", "pic2", "pic3", "pic4"])
BACKGROUND = REF.get("background_slot", "background")
GUIDE = "ComfyUILTX25MSRMultiReferenceGuide"
PLATE = "plate"                  # `absent`: compile without the plate


class Ctx:
    """One pass of one episode: the preset, the legal size, the report, and
    the pictures to leave out (`absent`: subject ids and/or "plate")."""

    def __init__(self, target, series_cfg: dict, pass_: str, absent: set | None = None):
        self.target, self.series_cfg, self.pass_ = target, series_cfg, pass_
        self.preset = target.preset(pass_, series_cfg)
        self.fps = target.template.fps_for(series_cfg)
        self.warnings: list[str] = []
        self.width, self.height = VC.legal_size(target, self.preset, pass_, self.warnings)
        self.total_req = self.total_raw = 0
        self.fallbacks: dict[str, list[str]] = {}
        self.profiles = TG.series_profiles(series_cfg)
        self.recording = series_cfg.get("audio", {}).get("track", "")
        self.absent = set(absent or ())


def _references(ctx: Ctx, shots: list[ir.Shot], sq: ir.Sequence) -> list[dict]:
    refs = P.references(shots, sq, ctx.series_cfg, len(SLOTS))
    refs = [r for r in refs if r.get("subject") not in ctx.absent
            and not (r.get("location") and PLATE in ctx.absent)]
    return refs if any(r.get("subject") for r in refs) else []


def _compile(ctx: Ctx, sq: ir.Sequence, shot: ir.Shot, ep_id: str) -> dict:
    series_cfg = ctx.series_cfg
    loc_key, pace = VC.check_shot(series_cfg, sq, shot)
    dur, windowed = _duration(ctx, shot, pace)
    req, raw = VC.snap_frames(ctx, shot, dur)
    VC.crammed(ctx, shot, pace, raw)
    VC.count_frames(ctx, req, raw)
    intent, policy, note = VC.shot_audio(ctx, shot)
    VC.check_dub_window(ctx, shot, policy)
    layers = VC.shot_layers(series_cfg, sq, shot, ctx.profiles)
    entry = VC.entry_head(ctx, sq, shot, ep_id, loc_key, raw, layers, policy)
    refs = _references(ctx, [shot], sq)
    entry["prompt"] = P.shot_paragraph(shot, sq, series_cfg, refs)
    entry["global_prompt"] = P.global_prompt(refs, series_cfg)
    entry["negative"] = ctx.preset.extra.get("negative", "")
    entry["references"] = refs
    if policy == "clone":
        entry.update(HA.clone_entry(shot, series_cfg["subjects"]))
    return VC.entry_tail(ctx, sq, shot, entry, layers, intent, note, dur, windowed, pace)


def compile_episode(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    only: set[str] | None = None, absent=None) -> tuple[dict, dict]:
    ctx = Ctx(target, series_cfg, pass_, absent)
    shots_out, seqs = [], 0
    for sq in story.sequences:
        mine = [s for s in sq.shots if only is None or s.id in only]
        if mine:
            seqs += 1
        for s in mine:
            shots_out.append(_compile(ctx, sq, s, story.id))
    p = ctx.preset
    doc = {
        "episode": story.id,
        "title": story.title,
        "target": target.id,
        "defaults": {"width": ctx.width, "height": ctx.height, "fps": ctx.fps,
                     "steps": p.steps, "model": p.model, "lora": p.lora,
                     "audio_policy": "generate", "master_track": ctx.recording,
                     **shotlist_extra(p)},
        "subjects": {s: {"kind": e.get("kind", "character"), "sheet": e.get("sheet", "")}
                     for s, e in series_cfg["subjects"].items()},
        "shots": shots_out,
    }
    VC.fallback_warnings(ctx, target)
    for sh in shots_out:
        VC.override_warnings(ctx, sh)
    return doc, VC.episode_report(ctx, story, target, shots_out, seqs, {}, {},
                                  RECIPE.get("size_hints"))


def compile_shot(target, shot_ir: ir.Shot, series_cfg: dict, preset, ctx=None) -> dict:
    """One shot's entry, as compile_episode builds it. `ctx` needs {"episode": ir.Episode}; {"absent": ...} leaves
    pictures out."""
    ctx = dict(ctx or {})
    story = ctx.get("episode")
    if story is None:
        raise ValueError("compile_shot needs ctx['episode'], the shot's ir.Episode")
    pass_ = preset if isinstance(preset, str) else preset.name
    doc, _ = compile_episode(target, story, series_cfg, pass_, only={shot_ir.id},
                             absent=ctx.get("absent"))
    if not doc["shots"]:
        raise ValueError(f"{shot_ir.id} is not in episode {story.id}")
    return doc["shots"][0]


def compile_without(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    entry: dict, missing: list[dict]) -> dict:
    """`entry` compiled again as if the `missing` pictures (ref_slots dicts)
    didn't exist, so the prompt's `Image N` are the guide's numbers.
    ValueError when the build is out of date."""
    shot_ir = next((s for s in story.shots() if s.id == entry["id"]), None)
    if shot_ir is None:
        raise ValueError(f"{entry['id']} is not in shots.json")
    if compile_shot(target, shot_ir, series_cfg, pass_, {"episode": story}) != entry:
        raise ValueError(f"{entry['id']}: the build is out of date (rebuild the episode)")
    absent = {r["subject"] for r in missing if r.get("subject") and not r.get("optional")}
    if any(r.get("location") for r in missing):
        absent.add(PLATE)
    return compile_shot(target, shot_ir, series_cfg, pass_, {"episode": story, "absent": absent})


def required_refs(target, shot_ir: ir.Shot, series_cfg: dict, ctx=None) -> list[TG.RefRequest]:
    """The pictures a shot is given: the first four people and things on
    screen, then the place's plate. `ctx` may give {"sequence": ir.Sequence}
    (the location when the shot names no plate)."""
    ctx = dict(ctx or {})
    book = series_cfg["subjects"]
    subjects = list(shot_ir.cast) + [p for p in shot_ir.props if p not in shot_ir.cast]
    out = [subject_request(s, book[s], f"MSR {slot}")
           for s, slot in zip(subjects, SLOTS)]
    key = shot_ir.plate or (ctx["sequence"].location if ctx.get("sequence") else "")
    loc = series_cfg["locations"].get(key)
    if out and loc and loc.get("plate"):
        out.append(plate_request(key, loc, f"MSR {BACKGROUND}"))
    return out


def _ref_slots(target, doc: dict, shot: dict) -> list[dict]:
    """One slot per picture, required; a person's face picture (a `_face`
    variant) is an optional slot beside it, so re-picking it makes the take
    stale."""
    out = []
    for i, r in enumerate(shot.get("references") or []):
        slot = BACKGROUND if r.get("location") else SLOTS[i]
        s = {"slot": f"MSR {slot}", "kind": "image", "path": r.get("path", "")}
        if r.get("subject"):
            s["subject"] = r["subject"]
        else:
            s["location"] = r.get("location")
        out.append(s)
        if r.get("face"):
            out.append({"slot": f"MSR {slot} face", "kind": "image", "path": r["face"],
                        "subject": r.get("subject"), "optional": True})
    return out


# ---------------------------------------------------------------------------
# queue time: the pictures
# ---------------------------------------------------------------------------

def sheet_spec(job, ref: dict, book: dict) -> dict:
    """What seriesmith/helpers/refsheet.py composes for one person or thing:
    the render size, grey, and its panels. A character's 4-panel strip (wider
    than `strip_ratio`) gives the views' panels; one whole picture gives
    itself and its face (the face picture, else `face_box` of it). A prop is
    its picture alone."""
    from seriesmith import refs as R
    body = os.path.abspath(_abs(job.root, ref["path"]))
    face = os.path.abspath(_abs(job.root, ref["face"])) if ref.get("face") else None
    kind = (book.get(ref["subject"]) or {}).get("kind", "character")
    size = R.image_size(body) or (1, 1)
    views = REF.get("views") or {}
    panels = []
    if kind != "character":
        panels.append({"path": body, "fit": "figure"})
    elif size[0] / max(size[1], 1) > float(REF.get("strip_ratio", 2.0)):
        n = int(REF.get("sheet_panels", 4))
        panels.append({"path": body, "fit": "figure", "crop": {"panels": n, "index": int(views["body"])}})
        panels.append({"path": face, "fit": "figure"} if face and os.path.isfile(face) else
                      {"path": body, "fit": "figure", "crop": {"panels": n, "index": int(views["face"])}})
        panels.append({"path": body, "fit": "figure", "crop": {"panels": n, "index": int(views["back"])}})
    else:
        panels.append({"path": body, "fit": "figure"})
        if face and os.path.isfile(face):
            panels.append({"path": face, "fit": "figure"})
        else:
            l, t, r, _ = REF.get("face_box") or [0.34, 0.02, 0.66, 0.26]
            # a square of the picture's width: the box's height follows its shape
            b = t + (r - l) * size[0] / max(size[1], 1)
            panels.append({"path": body, "fit": "figure", "crop": {"box": [l, t, r, b]}})
    return {"width": int(job.width), "height": int(job.height),
            "background": REF.get("background", "grey"), "gap": REF.get("gap", 0.02),
            "panels": panels}


def _stage_inputs(target, job, comfy=None) -> dict:
    """Compose each person's and thing's sheet and upload it, with the plate
    as it is: {"pic1": name, ..., "background": name}, the guide's slots.
    The sheets wait in the shot's folder until jobs.start_job moves them into
    the take. Without `comfy` (a dry run) nothing is composed or written."""
    from seriesmith import jobs as J
    from seriesmith import takes as T
    from seriesmith.targets.video.ltx2_ingredients import sheet as S
    entry = job.recompiled or job.shot
    refs = entry.get("references") or []
    book = ((J.series_config(job.root) or {}).get("subjects") or {}) if comfy is not None else {}
    out, made = {}, []
    try:
        for i, r in enumerate(refs):
            slot = BACKGROUND if r.get("location") else SLOTS[i]
            path = _abs(job.root, r["path"])
            if comfy is None:
                out[slot] = f"{J.INPUT_SUBFOLDER}/dry_run_{T.safe_id(job.id)}_{slot}.png"
                continue
            if r.get("location"):
                name = J.input_name(path)
                comfy.upload_input(path, name)
                out[slot] = name
                continue
            d = T.shot_dir(job.root, job.pass_, job.id, job.folder)
            os.makedirs(d, exist_ok=True)
            tmp = os.path.join(d, f".tmp_msr_{uuid.uuid4().hex}.png")
            made.append(tmp)
            S.compose(sheet_spec(job, r, book), tmp)
            name = J.input_name(tmp)
            comfy.upload_input(tmp, name)
            out[slot] = name
            job.staged.append({"tmp": tmp, "suffix": REF["take_suffix"].format(n=i + 1),
                               "slot": f"MSR {slot}", "kind": "image", "role": slot})
    except BaseException:
        for tmp in made:
            if os.path.isfile(tmp):
                os.remove(tmp)
        raise
    people = sum(1 for r in refs if r.get("subject"))
    if people:
        job.notes.append(f"MSR: {people} sheet{'s' if people > 1 else ''}"
                         + (" and the plate" if any(r.get("location") for r in refs) else "")
                         + " as reference pictures")
    else:
        job.notes.append("MSR: no one pictured, so this shot renders from words alone")
    return out


def _patch_graph(target, g: dict, job, inputs: dict) -> None:
    """The staged pictures into both guides' slots (LoadImage per slot; a
    slot with no picture is left empty, and the guide numbers what it has
    consecutively, as the prompt does). With no picture at all both guides
    are spliced out: their conditioning and latent pass straight through."""
    guides = _of(g, GUIDE)
    if not guides:
        raise ValueError(f"the ltx2_msr workflow must have the MSR guide ({GUIDE})")
    if not inputs.get(SLOTS[0]):
        for k in guides:
            gi = g[k]["inputs"]
            for out, keep in enumerate((gi["positive"], gi["negative"], gi["latent"])):
                for c, name in _consumers(g, k, out):
                    g[c]["inputs"][name] = list(keep)
            del g[k]
        return
    for slot in SLOTS + [BACKGROUND]:
        load = f"load_{slot}"
        if inputs.get(slot):
            g[load]["inputs"]["image"] = inputs[slot]
            continue
        for k in guides:
            g[k]["inputs"].pop(slot, None)
        g.pop(load, None)


# -- a dub shot's recording (targets/held_audio.py) ----------------------------------

def ref_slots(target, doc: dict, shot: dict) -> list[dict]:
    """_ref_slots, then a clone shot's voice samples or a dub shot's recording."""
    return _ref_slots(target, doc, shot) + HA.audio_slots(doc, shot)


def stage_inputs(target, job, comfy=None) -> dict:
    """_stage_inputs, then a dub shot's window of the recording, or a clone
    shot's voice samples."""
    out = dict(_stage_inputs(target, job, comfy) or {})
    out.update(HA.stage_dub(target, job, comfy))
    out.update(HA.stage_clone(target, job, comfy))
    return out


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """_patch_graph, then a dub shot's window held as the soundtrack through
    every stage, or a clone shot's lines made and held."""
    _patch_graph(target, g, job, inputs)
    HA.patch_dub(g, inputs)
    HA.patch_clone(target, g, job, inputs)
