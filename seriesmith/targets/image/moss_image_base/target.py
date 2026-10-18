"""
moss_image_base: MOSS-Image Base, text to image (target.json beside this file).
Series refs are worded as every image target words them, keyframes by
targets/image/common.py; no reference images, so no graph code.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401
