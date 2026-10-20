"""
The Comfy Router models seriesmith ships. Video: written from their published
schemas (tests/fixtures/router_schemas) by router_inspect.propose, with the
corrections a schema states only in prose (or a live test found), into
seriesmith/targets/video/<id>/target.json. Image: each request mapped by hand
from its schema (image models differ too much in shape to propose: a chat
message's parts, numbered input fields, a WxH string, a ratio and a 1K/2K
size), into seriesmith/targets/image/<id>/target.json, driven by
targets/generic/router_image.py. Every show sees them; a `draft` one stays
out of the pickers until it is switched on (the editor's Enable).

    python tools/make_router_targets.py           write them
    python tools/make_router_targets.py --check   fail when one differs

Router models that take no picture (text to video) are refused by propose:
seriesmith draws from refs and keyframes. Seedance 2.5 is hand-written
(targets/video/seedance_2_5) and not made here.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith import inspector as IN  # noqa: E402
from seriesmith import limits as L  # noqa: E402
from seriesmith import router_inspect as RI  # noqa: E402
from seriesmith import targets as TG  # noqa: E402

SCHEMAS = os.path.join(ROOT, "tests", "fixtures", "router_schemas")
OUT = os.path.join(ROOT, "seriesmith", "targets", "video")
OUT_IMAGE = os.path.join(ROOT, "seriesmith", "targets", "image")


# -- corrections: limits the schemas state only in prose (seriesmith.limits) -------

# "Seedance 2.0, 2.0 fast & 2.0 mini: [4,15]"; "do not support 1080p"
SEEDANCE_2_0 = {"length": {"seconds": {"min": 4, "max": 15}}, "size": {"resolutions": ["480p", "720p"]}}
# "Veo 3/3.1: 4, 6, or 8"; "up to 3 asset images"; a prompt past ~1000 characters
# fails (router_inspect.PROMPT_LIMITS)
VEO = {"length": {"seconds": {"values": [4, 6, 8]}}, "pictures": {"references": 3}}
# "wan3.0-video: integer in [2, 30]"; reference_image max 10
WAN_3_0 = {"length": {"seconds": {"min": 2, "max": 30}}, "pictures": {"references": 10}}
# "wan2.7-r2v: [2, 10]"; "720P, 1080P"; first_frame optional, up to 5 reference
# images, no last frame
WAN_2_7_R2V = {"length": {"seconds": {"min": 2, "max": 10}}, "size": {"resolutions": ["720P", "1080P"]},
               "pictures": {"references": 5, "last": False}}
# "wan2.7-i2v: [2, 15]"; "720P, 1080P"; first_frame and last_frame, no reference image
WAN_2_7_I2V = {"length": {"seconds": {"min": 2, "max": 15}}, "size": {"resolutions": ["720P", "1080P"]},
               "pictures": {"references": 0, "needs_first": True}}


def seedance_ratio(p: dict) -> None:
    """Seedance 2.0 takes a ratio alongside its frames (2.5 refuses one)."""
    p["router"]["inputs"]["ratio"]["with_frames"] = "keep"


def runway_note(p: dict) -> None:
    p["_note"] = ("Image to video: every shot starts from its first keyframe (promptImage); no "
                  "reference pictures, no sound (the silent prose: Runway failed every prompt "
                  "carrying quoted lines, 2026-10-12).")


# (Router model, id, label, short, limits, draft, extra) -- live ones were rendered
# on Porchlights ep03 (2026-10-12); drafts match a live sibling's schema
MODELS = [
    ("minimax/minimax-h3", "minimax_h3", "MiniMax H3", "MiniMax", None, False, None),
    ("byteplus/dreamina-seedance-2-0-260128", "seedance_2_0", "Seedance 2.0", "Seedance", SEEDANCE_2_0, False, seedance_ratio),
    ("byteplus/dreamina-seedance-2-0-fast-260128", "seedance_2_0_fast", "Seedance 2.0 Fast", "Seedance", SEEDANCE_2_0, True, seedance_ratio),
    ("byteplus/dreamina-seedance-2-0-mini", "seedance_2_0_mini", "Seedance 2.0 Mini", "Seedance", SEEDANCE_2_0, True, seedance_ratio),
    ("kling/kling-v3-omni", "kling_v3_omni", "Kling v3 Omni", "Kling", None, False, None),
    ("kling/kling-video-o1", "kling_video_o1", "Kling Video O1", "Kling O1", None, False, None),
    ("wan/wan3.0-video", "wan_3_0", "Wan 3.0", "Wan", WAN_3_0, False, None),
    ("wan/wan3.0-video-prime", "wan_3_0_prime", "Wan 3.0 Prime", "Wan", WAN_3_0, True, None),
    ("wan/wan2.7-r2v", "wan_2_7_r2v", "Wan 2.7 (references)", "Wan", WAN_2_7_R2V, True, None),
    ("wan/wan2.7-i2v", "wan_2_7_i2v", "Wan 2.7 (first frame)", "Wan", WAN_2_7_I2V, True, None),
    ("veo/veo-3.1-fast-generate-001", "veo_3_1_fast", "Veo 3.1 Fast", "Veo", VEO, False, None),
    ("veo/veo-3.1-generate-001", "veo_3_1", "Veo 3.1", "Veo", VEO, True, None),
    ("veo/veo-3.1-lite-generate-001", "veo_3_1_lite", "Veo 3.1 Lite", "Veo", VEO, True, None),
    ("runway/gen4_turbo", "runway_gen4_turbo", "Runway Gen-4 Turbo", "Runway", None, False, runway_note),
]


# -- image models: each request mapped from its schema ----------------------------

SEED = {"max": 2147483647}
# Gemini's image models: a chat message (contents[0].parts), the pictures
# inline before the text (fileData takes Google Cloud Storage only); the
# ratios and 1K/2K/4K its docs list (the schema leaves aspectRatio a string)
GEMINI_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


def gemini(most: int) -> tuple[dict, dict]:
    return ({"contents": [{"role": "user"}],
             "generationConfig": {"responseModalities": ["IMAGE"]}},
            {"prompt": {"list": "contents.0.parts", "item": {"text": "$prompt"}},
             "images": {"list": "contents.0.parts", "first": True, "max": most,
                        "item": {"inlineData": {"mimeType": "$mime", "data": "$url"}}},
             "via": "base64",
             "ratio": {"name": "generationConfig.imageConfig.aspectRatio", "values": GEMINI_RATIOS},
             "resolution": {"name": "generationConfig.imageConfig.imageSize", "values": ["1K", "2K", "4K"]},
             "seed": {"name": "generationConfig.seed", **SEED}})


# (Router model, id, label, short, arguments, inputs, draft, note)
IMAGE_MODELS = [
    ("vertexai/gemini-3-pro-image", "nano_banana_pro", "Nano Banana Pro (Gemini 3 Pro Image)", "Nano Banana Pro",
     *gemini(6), False, "Google's own, on Vertex. Up to 6 reference pictures sent inline."),
    ("vertexai/gemini-nano-banana-2.1", "nano_banana_2_1", "Nano Banana 2.1", "Nano Banana",
     *gemini(6), False, "Google's own, on Vertex. Up to 6 reference pictures sent inline."),
    ("vertexai/gemini-3.1-flash-image", "gemini_3_1_flash_image", "Gemini 3.1 Flash Image", "Gemini Flash",
     *gemini(3), False, "Google's own, on Vertex: the faster, cheaper sibling."),
    ("byteplus/seedream-5-0-260128", "seedream_5_0", "Seedream 5.0", "Seedream",
     {"response_format": "url", "watermark": False, "sequential_image_generation": "disabled",
      "output_format": "png"},
     {"prompt": "prompt", "images": {"field": "image", "max": 10},
      # "total pixels: [2560x1440, ~3072x3072]": a ref is asked for at least 3.7 MP
      "size": {"name": "size", "format": "{w}x{h}", "multiple": 16,
               "min_pixels": 3686400, "max_pixels": 9437184},
      "seed": {"name": "seed", **SEED}}, False,
     "BytePlus. A picture of a photoreal person may be refused as a plain link (as Seedance's "
     "were): if so, send pictures through the Seedance library (Limits: sent as)."),
    ("openai/gpt-image-2", "gpt_image_2", "GPT Image 2", "GPT Image",
     {"n": 1, "quality": "medium", "output_format": "png", "moderation": "low"},
     {"prompt": "prompt", "images": {"field": "image", "max": 8},
      "size": {"name": "size", "values": ["1024x1024", "1536x1024", "1024x1536"]}}, False,
     "OpenAI. With pictures it edits (the `image` field selects the edit operation)."),
    ("bfl/flux-kontext-pro", "flux_kontext_pro", "Flux Kontext Pro", "Kontext Pro",
     {"output_format": "png", "prompt_upsampling": False},
     {"prompt": "prompt",
      "images": {"fields": ["input_image", "input_image_2", "input_image_3", "input_image_4"], "max": 4},
      "ratio": {"name": "aspect_ratio",
                "values": ["21:9", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16", "9:21"]},
      "seed": {"name": "seed", **SEED}}, False,
     "Black Forest Labs. The first picture is the one edited; the others are references."),
    ("bfl/flux-2-pro", "flux_2_pro", "Flux 2 Pro", "Flux 2 Pro",
     {"output_format": "png", "prompt_upsampling": False},
     {"prompt": "prompt",
      "images": {"fields": ["input_image"] + [f"input_image_{i}" for i in range(2, 9)], "max": 8},
      "width": {"name": "width", "min": 256, "max": 2048, "multiple": 16},
      "height": {"name": "height", "min": 256, "max": 2048, "multiple": 16},
      "seed": {"name": "seed", **SEED}}, False, "Black Forest Labs."),
    ("qwen/qwen-image-3.0", "qwen_image_3", "Qwen Image 3.0", "Qwen Image",
     {"input": {"messages": [{"role": "user"}]},
      "parameters": {"n": 1, "prompt_extend": False, "watermark": False}},
     {"prompt": {"list": "input.messages.0.content", "item": {"text": "$prompt"}},
      "images": {"list": "input.messages.0.content", "item": {"image": "$url"}, "first": True, "max": 3},
      "negative": "parameters.negative_prompt",
      # "a pixel area between 262144 (512*512) and 6553600 (2560*2560)"
      "size": {"name": "parameters.size", "format": "{w}*{h}", "multiple": 16,
               "min_pixels": 262144, "max_pixels": 6553600},
      "seed": {"name": "parameters.seed", **SEED}}, False, "Alibaba. 1 to 3 pictures to edit."),
    ("kling/kling-image-o1", "kling_image_o1", "Kling Image O1", "Kling Image",
     {"n": 1, "result_type": "single"},
     {"prompt": {"field": "prompt", "max_chars": 2500},
      "images": {"list": "image_list", "item": {"image": "$url"}, "max": 10, "mention": "<<<image_{n}>>>"},
      "ratio": {"name": "aspect_ratio", "values": ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"]},
      "resolution": {"name": "resolution", "values": ["1k", "2k", "4k"]}}, False,
     "Kling. Its pictures are named in the prompt (<<<image_1>>>)."),
    ("krea/krea-2", "krea_2_router", "Krea 2", "Krea 2 (Router)",
     {"creativity": "medium"},
     {"prompt": "prompt",
      "ratio": {"name": "aspect_ratio", "values": ["1:1", "4:3", "3:2", "16:9", "2.35:1", "4:5", "2:3", "9:16"]},
      "resolution": {"name": "resolution", "values": ["1K"]},
      "seed": {"name": "seed", "max": 4294967295}}, False,
     "The same model family as the local krea2 target, so a series' refs look alike made either "
     "way. Text to image: Krea's image references are style references, not a subject to keep."),
]

IMAGE_VIEWS = ["01_threequarter", "02_side", "03_back", "04_face"]


def image_spec(model: str, tid: str, label: str, short: str, arguments: dict, inputs: dict,
               draft: bool, note: str) -> dict:
    imgs = inputs.get("images")
    spec = {
        "id": tid, "kind": "image", "label": f"{label} (hosted, Comfy Router)", "short": short,
        "code": "builtin:router_image",
        "_note": note,
        "capabilities": {"backends": ["router"], "seed": "provider",
                         "mode": "edit" if imgs else "t2i",
                         "max_refs": int(imgs.get("max") or 1) if imgs else 0},
        "template": {"view_size": [1024, 1024], "plate_size": [1344, 768], "object_size": [1024, 1024]},
        "recipe": {"views": IMAGE_VIEWS, "ref_word": "image"},
        "router": {"model": model, "arguments": arguments, "inputs": inputs},
        "presets": {"final": {"model": model, "lora": "", "steps": 0, "cfg": 1.0}},
    }
    if draft:
        spec["draft"] = True
    return spec


def build_images() -> dict[str, dict]:
    out = {}
    for row in IMAGE_MODELS:
        p = image_spec(*row)
        problems = [x for x in IN.validate_spec(dict(p)) if "built-in target's name" not in x]
        if problems:
            raise SystemExit(f"{p['id']}: {problems}")
        out[p["id"]] = p
    return out


def build() -> dict[str, dict]:
    base = TG.load_target("seedance_2_5", "video").spec
    out = {}
    for model, tid, label, short, limits, draft, extra in MODELS:
        with open(os.path.join(SCHEMAS, model.replace("/", "__") + ".json"), encoding="utf-8") as fh:
            p = RI.propose(model, json.load(fh), base=base)["proposal"]
        p.update(id=tid, label=f"{label} (hosted, Comfy Router)", short=short)
        p.pop("draft", None)
        # the recipe came from Seedance's: its audio fallback says the model's own name
        fb = (p.get("recipe") or {}).get("policy_fallback") or {}
        if fb.get("why", "").startswith(base["short"] + " makes its own sound"):
            fb["why"] = short + fb["why"][len(base["short"]):]
        if limits:
            p = L.apply(p, limits)
        if extra:
            extra(p)
        if draft:
            p["draft"] = True
        problems = [x for x in IN.validate_spec(dict(p)) if "built-in target's name" not in x]
        if problems:
            raise SystemExit(f"{tid}: {problems}")
        out[tid] = p
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    made = [(OUT, tid, p) for tid, p in build().items()]
    made += [(OUT_IMAGE, tid, p) for tid, p in build_images().items()]
    for out, tid, p in made:
        path = os.path.join(out, tid, "target.json")
        text = json.dumps(p, indent=2, ensure_ascii=False) + "\n"
        old = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
        if old == text:
            continue
        if check:
            stale.append(tid)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote", os.path.relpath(path, ROOT))
    if stale:
        print("out of date (python tools/make_router_targets.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
