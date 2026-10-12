"""
The Comfy Router video models seriesmith ships, written from their published
schemas (tests/fixtures/router_schemas) by router_inspect.propose, with the
corrections a schema states only in prose (or a live test found), into
seriesmith/targets/video/<id>/target.json. Every show sees them; a `draft`
one stays out of the pickers until it is switched on here.

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


def build() -> dict[str, dict]:
    base = TG.load_target("seedance_2_5", "video").spec
    out = {}
    for model, tid, label, short, limits, draft, extra in MODELS:
        with open(os.path.join(SCHEMAS, model.replace("/", "__") + ".json"), encoding="utf-8") as fh:
            p = RI.propose(model, json.load(fh), base=base)["proposal"]
        p.update(id=tid, label=f"{label} (hosted, Comfy Router)", short=short)
        p.pop("draft", None)
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
    for tid, p in build().items():
        path = os.path.join(OUT, tid, "target.json")
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
