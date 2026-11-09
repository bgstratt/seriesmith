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
LOADER = "Drama3Loader"
VOICE = "voices.voice0"

# Each file's size in bytes (PedroMarinhoDev/Drama-3-ComfyUI, 2026-11-07), by the words in its
# name: what the experts take in VRAM when they all live there.
SIZES = {"w4a8experts": 24603565376, "w6a8experts": 32656613840,
         "int8experts": 38696401232, "fp8experts": 38578417928}
# Beside the whole file in VRAM: the activations, the codec and a little of ComfyUI's own (W4A8 in
# VRAM ran on a 32 GB card, 2026-11-07; its peak wasn't measured, so this errs towards RAM).
VRAM_HEADROOM = 4 * 1024 ** 3


def experts_where(model_name: str, gpu_memory: int | None) -> str:
    """Where the experts live when the preset says "auto": "in VRAM" when the whole file and
    VRAM_HEADROOM fit the GPU, else "in RAM" (the pack's default: any card from 8 GB, but it holds
    the file in RAM, about its size plus 8 GB free). Unknown file or GPU: "in RAM".

    Why it matters: with the experts in RAM on a machine whose free RAM is near the file's size,
    ComfyUI's RAM-pressure cache (its default since 0.40) frees the loaded model to make room, and
    every job reads the file again: 23-30 s of a 37-50 s take, and free RAM at 0 GB (live
    2026-11-07, 64 GB of RAM, W4A8). In VRAM the next take was 8 s."""
    size = next((v for k, v in SIZES.items() if k in (model_name or "").lower()), None)
    if size and gpu_memory and size + VRAM_HEADROOM <= gpu_memory:
        return "in VRAM"
    return "in RAM"


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
    character's `voice` line put before the words. Experts "auto" (the preset) made
    "in VRAM" or "in RAM" for the file and the GPU (`inputs["gpu_memory"]`,
    refs.stage_gpu_memory): experts_where."""
    load = graph[_node(graph, LOADER)]["inputs"]
    if load.get("experts") not in ("in RAM", "in VRAM"):
        load["experts"] = experts_where(load.get("model_name") or "", (inputs or {}).get("gpu_memory"))
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
