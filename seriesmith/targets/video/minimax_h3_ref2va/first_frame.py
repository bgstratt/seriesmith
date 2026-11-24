"""
Keyframes on an H3 reference model (Ref2VA's node: H3 Ref2VA, H3 Hybrid,
H3 Singularity), for a target whose recipe says `keyframes: ["first", "last"]`
and `keyframes_when_asked: true`: a shot that asks for one (`continuous: first`
or a `first:` line; a `last:` line) opens on that picture, or ends on it, and
keeps its reference pictures. Each picture is anchored by MiniMaxH3AddGuide
between the reference node's conditioning and the guider (as FL2VA anchors a
dub's audio): the first at frame 0, the last at frame -1 (counted from the
end), chained when there are both. So a shot needn't leave its model for
FL2VA, and a `continuous: latent` shot, whose held frames are in the latent
(jobs.chain_latent), can still end on a picture. A shot that asks for none
renders as the reference model always has.

    with_keyframes(target, story, doc)   each asking entry gets `keyframes`
    keyframe_entry(target, shot_ir, seq_ir, entry)
    keyframe_slots(shot)                  its ref slots, roles "first" / "last" (optional)
    patch_first(g, inputs)                the anchors in the graph

Stdlib only.
"""
from __future__ import annotations

from seriesmith.core import paths as P
from seriesmith.targets.graph import consumers, new_id, of

TITLE = "first frame anchor at frame 0 (seriesmith)"
LAST_TITLE = "last frame anchor at the last frame (seriesmith)"
# each end: the frame it's anchored at (MiniMaxH3AddGuide: negative counts from the end),
# its slot's name, the anchor's title, and the ids' prefix
ENDS = {"first": (0, "first frame", TITLE, "h3_first_"),
        "last": (-1, "last frame", LAST_TITLE, "h3_last_")}


def asks(target, shot_ir, seq_ir=None, end: str = "first") -> bool:
    """Whether the script asks this shot for that keyframe (its `first:` /
    `last:` line, or `continuous: first`, which the parser reads as a first),
    on a target that reads it."""
    v = shot_ir.keyframe(end, seq_ir)
    return bool(v) and v != "none" and end in (target.recipe.get("keyframes") or ())


def keyframe_entry(target, shot_ir, seq_ir, entry: dict) -> dict:
    keys = {end: target.recipe["keyframe_path"].format(shot=P.safe_id(shot_ir.id), end=end)
            for end in ENDS if asks(target, shot_ir, seq_ir, end)}
    if keys:
        entry["keyframes"] = keys
    return entry


def with_keyframes(target, story, doc: dict) -> dict:
    """Every entry of `doc` whose shot asks for a keyframe, with it."""
    where = {s.id: (s, sq) for sq in story.sequences for s in sq.shots}
    for e in doc.get("shots") or []:
        if e.get("id") in where:
            shot_ir, sq = where[e["id"]]
            keyframe_entry(target, shot_ir, sq, e)
    return doc


def keyframe_slots(shot: dict) -> list[dict]:
    keys = shot.get("keyframes") or {}
    return [{"slot": ENDS[end][1], "kind": "image", "path": keys[end], "role": end,
             "optional": True} for end in ENDS if keys.get(end)]


def patch_first(g: dict, inputs: dict) -> None:
    """`inputs["first"]` / `inputs["last"]` (the names LoadImage reads) anchored
    at frame 0 / the last frame of the reference node's latent, the second
    chained after the first; nothing without either."""
    ends = [end for end in ENDS if inputs.get(end)]
    if not ends:
        return
    (ref,) = of(g, "MiniMaxH3ReferenceToVideo")
    ri = g[ref]["inputs"]
    feed = [ref, 0]
    for end in ends:
        frame, name, title, prefix = ENDS[end]
        load = new_id(g, prefix)
        g[load] = {"class_type": "LoadImage", "inputs": {"image": inputs[end]},
                   "_meta": {"title": f"{name} (seriesmith)"}}
        guide = new_id(g, prefix + "guide_")
        taken = consumers(g, feed[0], feed[1])
        g[guide] = {"class_type": "MiniMaxH3AddGuide",
                    "inputs": {"positive": list(feed), "latent": [ref, 1], "frame_idx": frame,
                               "image": [load, 0], **({"vae": list(ri["vae"])} if ri.get("vae") else {})},
                    "_meta": {"title": title}}
        for k, inp in taken:
            g[k]["inputs"][inp] = [guide, 0]
        feed = [guide, 0]
