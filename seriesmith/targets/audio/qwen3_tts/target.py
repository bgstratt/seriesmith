"""
qwen3_tts: Alibaba's Qwen3-TTS 1.7B on flybirdxx's ComfyUI-Qwen-TTS (target.json
beside this file). Sent the words alone (targets/audio/common.py words_line /
words_prompt).

Two models, one per case, as the pack splits them:

- **No voice sample yet:** VoiceDesign, the workflow as it is, told how the
  character sounds in its own `instruct` (common.voice_description: their
  design's first sentence and the series config's `voice` line).
- **A sample:** the Base model clones it. patch_graph puts Voice Clone in
  Voice Design's place, reading the staged clip through LoadAudio, with the
  clip's words when seriesmith knows them (refs.stage_voice_reference's
  `reference_text`), else from the voice alone (x_vector_only).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.audio.common import NEGATIVE, NEUTRAL_LINE, voice_description  # noqa: F401
from seriesmith.targets.audio.common import words_line as voice_line  # noqa: F401
from seriesmith.targets.audio.common import words_prompt as voice_prompt  # noqa: F401

WHAT = "voice sample"
DESIGN = "FB_Qwen3TTSVoiceDesign"
CLONE = "FB_Qwen3TTSVoiceClone"
# what Voice Clone takes over from Voice Design as it is (the rest are Design's own)
SHARED = ("model_choice", "device", "precision", "language", "seed", "max_new_tokens", "top_p",
          "top_k", "temperature", "repetition_penalty", "attention", "unload_model_after_generate")


def _node(graph: dict, class_type: str) -> str:
    for k, v in graph.items():
        if v.get("class_type") == class_type:
            return k
    raise ValueError(f"qwen3_tts: the graph has no {class_type}")


def _free_id(graph: dict) -> str:
    return str(max((int(k) for k in graph if str(k).isdigit()), default=0) + 1)


def patch_graph(target, graph: dict, job, inputs: dict) -> None:
    """Voice Design told the character's voice; or, with a staged sample
    (`inputs["reference_audio"]`), Voice Clone in its place, on the same id so
    what reads it still does."""
    design = _node(graph, DESIGN)
    d = graph[design]["inputs"]
    name = (inputs or {}).get("reference_audio")
    if not name:
        ref = getattr(job, "ref", None)
        entry = getattr(ref, "entry", None) or {}
        d["instruct"] = voice_description(entry.get("name") or getattr(ref, "subject", "") or "",
                                          entry.get("voice", ""), entry.get("design", "")) \
            or "A clear, natural speaking voice."
        return
    load = _free_id(graph)
    graph[load] = {"class_type": "LoadAudio", "inputs": {"audio": name}, "_meta": {"title": "Voice sample"}}
    said = " ".join(str((inputs or {}).get("reference_text") or "").split())
    graph[design] = {"class_type": CLONE, "_meta": {"title": "Qwen3-TTS Voice Clone"},
                     "inputs": {"target_text": d.get("text") or "", "ref_audio": [load, 0],
                                "ref_text": said, "x_vector_only": not said,
                                **{k: d[k] for k in SHARED if k in d}}}
