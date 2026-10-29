"""
A first frame on an H3 reference model (Ref2VA's node: H3 Ref2VA, FastH3 Omni,
H3 Singularity), for a target whose recipe says `keyframes: ["first"]` and
`keyframes_when_asked: true`: a shot that asks for one (`continuous: first`,
a `first:` line) opens on that picture and keeps its reference pictures. The
picture is anchored at frame 0 by MiniMaxH3AddGuide between the reference
node's conditioning and the guider (as FL2VA anchors a dub's audio), so the
shot needn't leave its model for FL2VA. A shot that asks for none renders as
the reference model always has.

    with_keyframes(target, story, doc)   each asking entry gets `keyframes`
    keyframe_entry(target, shot_ir, seq_ir, entry)
    keyframe_slots(target, shot)          its ref slot, role "first" (optional)
    patch_first(g, inputs)                the anchor in the graph

Stdlib only.
"""
from __future__ import annotations

from seriesmith import targets as TG
from seriesmith.core import paths as P
from seriesmith.targets.graph import consumers, new_id, of

TITLE = "first frame anchor at frame 0 (seriesmith)"


def asks(target, shot_ir, seq_ir=None) -> bool:
    """Whether the script asks this shot for a first frame (its `first:` line,
    or `continuous: first`, which the parser reads as one)."""
    v = shot_ir.keyframe("first", seq_ir)
    return bool(v) and v != "none" and "first" in (target.recipe.get("keyframes") or ())


def keyframe_entry(target, shot_ir, seq_ir, entry: dict) -> dict:
    if asks(target, shot_ir, seq_ir):
        path = target.recipe["keyframe_path"].format(shot=P.safe_id(shot_ir.id), end="first")
        entry["keyframes"] = {"first": path}
    return entry


def with_keyframes(target, story, doc: dict) -> dict:
    """Every entry of `doc` whose shot asks for a first frame, with it."""
    where = {s.id: (s, sq) for sq in story.sequences for s in sq.shots}
    for e in doc.get("shots") or []:
        if e.get("id") in where:
            shot_ir, sq = where[e["id"]]
            keyframe_entry(target, shot_ir, sq, e)
    return doc


def keyframe_slots(shot: dict) -> list[dict]:
    p = (shot.get("keyframes") or {}).get("first")
    return [{"slot": "first frame", "kind": "image", "path": p, "role": "first",
             "optional": True}] if p else []


def patch_first(g: dict, inputs: dict) -> None:
    """`inputs["first"]` (the name LoadImage reads) anchored at frame 0 of
    the reference node's latent; nothing without one."""
    if not inputs.get("first"):
        return
    (ref,) = of(g, "MiniMaxH3ReferenceToVideo")
    ri = g[ref]["inputs"]
    load = new_id(g, "h3_first_")
    g[load] = {"class_type": "LoadImage", "inputs": {"image": inputs["first"]},
               "_meta": {"title": "first frame (seriesmith)"}}
    guide = new_id(g, "h3_first_guide_")
    taken = consumers(g, ref, 0)
    g[guide] = {"class_type": "MiniMaxH3AddGuide",
                "inputs": {"positive": [ref, 0], "latent": [ref, 1], "frame_idx": 0,
                           "image": [load, 0], **({"vae": list(ri["vae"])} if ri.get("vae") else {})},
                "_meta": {"title": TITLE}}
    for k, name in taken:
        g[k]["inputs"][name] = [guide, 0]
