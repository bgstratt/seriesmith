"""
H3 Singularity: AIGC-Singularity's fine-tune of MiniMax H3 Ref2VA (target.json
beside this file), compiled exactly as Ref2VA is: the same node
(MiniMaxH3ReferenceToVideo), the same six-section prompt and the same three
subject pictures and plate. Only the weights differ.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.video.minimax_h3_ref2va.compile import (  # noqa: F401
    DUB_BY_FILE, compile_episode, compile_shot, compile_without, ref_slots,
    required_refs,
)
