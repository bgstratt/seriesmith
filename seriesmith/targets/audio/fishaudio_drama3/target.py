"""
fishaudio_drama3: Fish Audio's Drama 3 hosted, through ComfyUI's partner nodes
(target.json beside this file): paid per take on the Comfy API key. Sent the
words alone (targets/audio/common.py words_line / words_prompt), as the local
drama3 target is.

With a voice sample, patch_graph adds LoadAudio and Fish Audio Instant Voice
Clone into the speech node's first voice (`model.voices.voice0`, a dynamic
combo's input as ComfyUI's API names it); with none, Fish picks a voice, and the
character's `voice` line goes before the words as a direction (drama3.direction).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.audio.common import NEGATIVE, NEUTRAL_LINE  # noqa: F401
from seriesmith.targets.audio.common import words_line as voice_line  # noqa: F401
from seriesmith.targets.audio.common import words_prompt as voice_prompt  # noqa: F401
from seriesmith.targets.audio.drama3.target import direction

WHAT = "voice sample"
SPEECH = "FishAudioTextToSpeech"
VOICE = "model.voices.voice0"


def _node(graph: dict, class_type: str) -> str:
    for k, v in graph.items():
        if v.get("class_type") == class_type:
            return k
    raise ValueError(f"fishaudio_drama3: the graph has no {class_type}")


def _free_id(graph: dict) -> str:
    return str(max((int(k) for k in graph if str(k).isdigit()), default=0) + 1)


def patch_graph(target, graph: dict, job, inputs: dict) -> None:
    """The staged voice sample (`inputs["reference_audio"]`) cloned into the
    speech node's first voice; with none, the `voice` line before the words."""
    speech = _node(graph, SPEECH)
    # its seed only says when to run again (Fish's results aren't repeatable), in 0..2^31-1
    graph[speech]["inputs"]["seed"] = int(getattr(job, "seed", 0) or 0) % 2147483648
    name = (inputs or {}).get("reference_audio")
    if name:
        load = _free_id(graph)
        graph[load] = {"class_type": "LoadAudio", "inputs": {"audio": name}, "_meta": {"title": "Voice sample"}}
        clone = _free_id(graph)
        graph[clone] = {"class_type": "FishAudioInstantVoiceClone",
                        "inputs": {"files.audio0": [load, 0], "enhance_audio_quality": True},
                        "_meta": {"title": "Fish Audio Instant Voice Clone (Comfy partner node)", "partner": True}}
        graph[speech]["inputs"][VOICE] = [clone, 0]
        return
    entry = getattr(getattr(job, "ref", None), "entry", None) or {}
    lead = direction(entry.get("voice", ""))
    if lead:
        graph[speech]["inputs"]["text"] = f"{lead} {graph[speech]['inputs'].get('text') or ''}".strip()
