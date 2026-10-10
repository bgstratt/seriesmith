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
