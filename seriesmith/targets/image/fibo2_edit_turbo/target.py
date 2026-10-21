"""
fibo2_edit_turbo: Fibo 2.0 Edit Turbo (target.json beside this file), Bria's
4-step distillation of Fibo 2.0 Dev for edits. The graph and its code are
fibo2_dev's; the one difference is that it edits only (Bria: "Turbo is for
editing only: for text-to-image, use Fibo 2.0 Dev"), so a job with nothing to
edit is refused here rather than drawn badly.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401
from seriesmith.targets.image.fibo2_dev import target as _dev


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    if not inputs.get("references"):
        raise ValueError(f"{target.short} only edits: it needs a picture to start from. "
                         f"Pick Fibo 2.0 Dev to draw this from words.")
    _dev.patch_graph(target, g, job, inputs)
