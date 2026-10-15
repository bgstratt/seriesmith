"""
flux3_klein_turbo: FLUX.3 Image Klein, the step-distilled checkpoint
(target.json beside this file). The same graph as flux3_klein's, at 16 steps
and cfg 1 with the negative zeroed, so its graph code is flux3_klein's.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401
from seriesmith.targets.image.flux3_klein.target import patch_graph  # noqa: F401
