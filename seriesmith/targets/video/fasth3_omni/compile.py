"""
FastH3 Omni: FastVideo's 8-step distilled MiniMax H3 reference-to-video model
(target.json beside this file), compiled exactly as Ref2VA is.

It is the same node (MiniMaxH3ReferenceToVideo) and the same six-section
prompt, so the compile is Ref2VA's (minimax_h3_ref2va/compile.py), which reads
its slots from the target it is given: here eight subject pictures and the
plate as <Picture 9> (recipe), against Ref2VA's three and <Picture 4>. The
shotlist's `defaults.subject_slots` tells the Shot Loader (comfy_nodes/
shotplan.py) how many sockets to fill.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_ref2va.compile import (  # noqa: F401
    DUB_BY_FILE, compile_episode, compile_shot, compile_without, ref_slots,
    required_refs,
)
