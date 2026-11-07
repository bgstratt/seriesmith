"""
drama3: Fish Audio Drama 3 on PedroMarinhoDev's ComfyUI-Drama3 (target.json
beside this file). Sent the words alone (targets/audio/common.py words_line /
words_prompt); a character's voice sample is cloned, not continued.

The workflow carries the clone's branch (the sample, Qwen3-ASR hearing it,
Drama 3 Encode Voice into voice slot 0). patch_graph points it at the staged
sample, or, with none, unhooks it so the prune drops it, and steers the
model's own voice with the character's `voice` line as a bracketed direction,
which Drama 3 reads as how to say the words rather than words to say.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.audio.common import NEGATIVE, NEUTRAL_LINE, _clean  # noqa: F401
from seriesmith.targets.audio.common import words_line as voice_line  # noqa: F401
from seriesmith.targets.audio.common import words_prompt as voice_prompt  # noqa: F401

WHAT = "voice sample"
GENERATE = "Drama3Generate"
VOICE = "voices.voice0"


def _node(graph: dict, class_type: str) -> str:
    for k, v in graph.items():
        if v.get("class_type") == class_type:
            return k
    raise ValueError(f"drama3: the graph has no {class_type}")


def direction(voice: str) -> str:
    """The series config's `voice` line as a direction ("[a gravelly baritone, slow]"),
    "" with none. Brackets inside it would end it early."""
    said = _clean(voice).replace("[", "(").replace("]", ")").rstrip(".")
    return f"[{said}]" if said else ""


def patch_graph(target, graph: dict, job, inputs: dict) -> None:
    """The staged voice sample (`inputs["reference_audio"]`, refs.stage_voice_reference)
    into the clone's LoadAudio; with none, the voice unhooked from Generate and the
    character's `voice` line put before the words."""
    gen = _node(graph, GENERATE)
    name = (inputs or {}).get("reference_audio")
    if name:
        src = graph[gen]["inputs"].get(VOICE)
        if not isinstance(src, list):
            raise ValueError(f"{target.id}: Drama 3 Generate's {VOICE} must come from Encode Voice")
        enc = graph[src[0]]
        load = enc["inputs"]["audio"][0]
        graph[load]["inputs"]["audio"] = name
        return
    graph[gen]["inputs"].pop(VOICE, None)
    entry = getattr(getattr(job, "ref", None), "entry", None) or {}
    lead = direction(entry.get("voice", ""))
    if lead:
        graph[gen]["inputs"]["text"] = f"{lead} {graph[gen]['inputs'].get('text') or ''}".strip()
