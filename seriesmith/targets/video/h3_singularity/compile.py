"""
H3 Singularity: AIGC-Singularity's fine-tune of MiniMax H3 Ref2VA (target.json
beside this file), compiled exactly as Ref2VA is: the same node
(MiniMaxH3ReferenceToVideo), the same six-section prompt and the same three
subject pictures and plate. Only the weights differ. A shot that asks for a
first frame (`continuous: first`, a `first:` line) opens on it, its pictures
kept (minimax_h3_ref2va/first_frame.py: anchored at frame 0).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_ref2va import compile as R
from seriesmith.targets.video.minimax_h3_ref2va import first_frame as FF
from seriesmith.targets.video.minimax_h3_ref2va.compile import (  # noqa: F401
    DUB_BY_FILE, required_refs,
)


def compile_episode(target, story, series_cfg: dict, pass_: str, only=None):
    doc, report = R.compile_episode(target, story, series_cfg, pass_, only)
    return FF.with_keyframes(target, story, doc), report


def compile_shot(target, shot_ir, series_cfg: dict, preset, ctx=None) -> dict:
    entry = R.compile_shot(target, shot_ir, series_cfg, preset, ctx)
    story = (ctx or {})["episode"]
    sq = next(q for q in story.sequences if any(s.id == shot_ir.id for s in q.shots))
    return FF.keyframe_entry(target, shot_ir, sq, entry)


def compile_without(target, story, series_cfg: dict, pass_: str, entry: dict,
                    missing: list[dict]) -> dict:
    got = R.compile_without(target, story, series_cfg, pass_, entry, missing)
    if entry.get("keyframes"):
        got["keyframes"] = dict(entry["keyframes"])
    return got


def ref_slots(target, doc: dict, shot: dict) -> list[dict]:
    return R.ref_slots(target, doc, shot) + FF.keyframe_slots(shot)


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    FF.patch_first(g, inputs)
