"""
ltx2_voice: LTX-2.5 audio-only, one speaking voice (target.json beside this
file). The brief is every audio target's (targets/audio/common.py); the graph
needs one piece of surgery the binding's widgets can't express, the voice
clone: the sample is held at the head of the clip and LTX continues it
(targets/held_audio.py).

Stdlib only.
"""
from __future__ import annotations

import math

from seriesmith.targets import held_audio as HA
from seriesmith.targets.audio.common import NEGATIVE, NEUTRAL_LINE, voice_line, voice_prompt  # noqa: F401,E402

WHAT = "voice sample"


def patch_graph(target, graph: dict, job, inputs: dict) -> None:
    """Hold the voice sample at the head of the clip when this job copies
    one: `inputs["reference_audio"]` is the name ComfyUI's LoadAudio reads (the
    sample's head, cut between words and uploaded by
    refs.stage_voice_reference), `inputs["reference_seconds"]` its length.

    The sample is held (held_audio.hold: the sampler leaves it as it is, and
    the zero padding after it is what LTX makes), so LTX generates the line
    as a continuation of the voice it has just heard. The clip is lengthened
    by the sample, on the target's frame grid and up to its longest, and the
    sample is trimmed off the decoded sound, so the take is the line alone, as
    long as was asked. Measured live 2026-10-28 (docs/PLAN.md, "Voice clone
    by continuation"). With no sample (or with `capabilities.reference_audio`
    false) nothing changes."""
    name = (inputs or {}).get("reference_audio")
    if not name:
        return
    head = float(inputs.get("reference_seconds") or 0.0)
    if head <= 0:
        raise ValueError(f"{target.id}: a held voice sample needs its length "
                         f"(inputs['reference_seconds'])")
    sel = ((target.spec.get("binding") or {}).get("reference_audio") or {}).get("empty") or {}
    if not sel.get("class_type"):
        raise ValueError(f"{target.id}: binding.reference_audio.empty must name the empty "
                         f"audio latent the sample lengthens")
    from seriesmith import jobs as J

    empty = J.select_nodes(graph, sel)[0]
    fps = float(job.fps or graph[empty]["inputs"].get("frame_rate") or 24.0)
    grid = (target.spec.get("template") or {}).get("frames") or {}
    step, base = int(grid.get("step") or 8), int(grid.get("base") or 1)
    most = int(grid.get("max") or 0)
    want = int(job.frames or graph[empty]["inputs"]["frames_number"])
    frames = base + step * math.ceil(max(want + head * fps - base, 0) / step)
    if most and frames > most:
        frames = most
    graph[empty]["inputs"]["frames_number"] = frames
    HA.hold(graph, name, WHAT)
    HA.trim_head(graph, head, max((frames - base) / fps - head, 0.5), WHAT)
