"""
What the pipeline needs to know about seriesmith's ComfyUI nodes
(comfy_nodes/shot.py), which can't be imported here: they need torch and run
inside ComfyUI. tests/test_render_take.py checks the two agree.
"""
from __future__ import annotations

# SeriesmithShotLoader's file inputs: file_00 .. file_23
MAX_FILES = 24


def file_input(i: int) -> str:
    return f"file_{i:02d}"


# the file SeriesmithSaveTake writes beside a take's other files: what it did
RECORD_SUFFIX = ".record.json"

# h3pipe's own node pack (its comfy_nodes/): nothing seriesmith sends a
# backend may use one (runner.py checks, uses_h3pipe), so that pack isn't
# needed. Other packs' H3-named nodes (MiniMax H3's, obvpm's) aren't these.
H3PIPE_NODES = frozenset({
    "H3ChainLatent", "H3ChainTrim", "H3ContinuityFrame", "H3FinishUpscale", "H3FramesToBatch",
    "H3HoldAudio", "H3LoadFaceTracks", "H3LoadTakeFrame", "H3LoadTakeLatent", "H3LoadTakeVideo",
    "H3LoadVideo", "H3MotionBlur", "H3PixelUpscale", "H3SaveFaceTracks", "H3SaveRefAudio",
    "H3SaveRefTake", "H3SaveRender", "H3SaveShot", "H3SaveUpscale", "H3ShotInfo",
    "H3ShotListLoader"})


def uses_h3pipe(graph: dict | None) -> list[str]:
    """The h3pipe-pack nodes in `graph` ([] when none): "<class> (<id>)"."""
    return [f"{v.get('class_type')} ({k})" for k, v in (graph or {}).items()
            if v.get("class_type") in H3PIPE_NODES]
