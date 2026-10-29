"""
H3 Singularity FL2VA: MiniMax H3 FL2VA's graph (its first / last frames, its prompt, its
voices) with H3 Singularity's weights (a fine-tune of H3 Ref2VA) in it (target.json beside this file): what a
`continuous: first` shot on h3_singularity renders on, so it keeps that model's look.
Compiled exactly as FL2VA is (minimax_h3_fl2va/compile.py).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_fl2va.compile import (  # noqa: F401
    DUB_BY_FILE, compile_episode, compile_shot, compile_without, patch_graph, ref_slots,
    required_refs, stage_inputs,
)
