"""
FastH3 Omni: FastVideo's 8-step distilled MiniMax H3 reference-to-video model
(target.json beside this file), compiled exactly as Ref2VA is.

It is the same node (MiniMaxH3ReferenceToVideo), the same six-section prompt and
the same pictures (eight subjects round the plate, <Picture 4>), so the compile
is Ref2VA's (minimax_h3_ref2va/compile.py). A shotlist built before 2026-11-05
has its plate as <Picture 9> and says so, `defaults.subject_slots`: the Shot
Loader (comfy_nodes/shotplan.py) and the graph (compile.wire_pictures) follow it.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_ref2va.compile import (  # noqa: F401
    DUB_BY_FILE, compile_episode, compile_shot, compile_without, patch_graph, ref_slots,
    required_refs,
)
