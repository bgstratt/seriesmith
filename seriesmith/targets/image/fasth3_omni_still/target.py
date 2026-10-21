"""
fasth3_omni_still: FastH3 Omni used as an image target (target.json beside
this file), as minimax_h3_still uses Ref2VA: the shortest clip the node
allows, frame 0 kept, up to nine reference images. The graph surgery and the
wording are minimax_h3_still's; only the model chain differs (the workflow).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401
from seriesmith.targets.image.minimax_h3_still.target import patch_graph  # noqa: F401
