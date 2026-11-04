"""
Pika H3 Flex: Pika's six-step post-training of MiniMax H3 Ref2VA (target.json beside
this file), compiled exactly as Ref2VA is: the same node (MiniMaxH3ReferenceToVideo), the
same six-section prompt and the same three subject pictures and plate. Only its LoRA and
sampling differ (its workflow: the Flex LoRA, LCM on six manual sigmas, no sigma shift).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_ref2va.compile import (  # noqa: F401
    DUB_BY_FILE, compile_episode, compile_shot, compile_without, patch_graph, ref_slots,
    required_refs,
)
