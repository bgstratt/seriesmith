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
from seriesmith import router_inspect as RI  # noqa: E402
from seriesmith import targets as TG  # noqa: E402

SCHEMAS = os.path.join(ROOT, "tests", "fixtures", "router_schemas")
OUT = os.path.join(ROOT, "seriesmith", "targets", "video")


# -- corrections -------------------------------------------------------------------

def duration(p: dict, **spec) -> None:
    """The lengths the model takes (whole seconds), and the frame grid to match."""
    d = p["router"]["inputs"]["duration"]
    keep = {k: d[k] for k in ("name", "as") if k in d}
    p["router"]["inputs"]["duration"] = {**keep, **spec}
    vals = spec.get("values")
    lo = min(vals) if vals else spec.get("min", 1)
    hi = max(vals) if vals else spec.get("max", lo)
    p["template"]["frames"] = {"step": 24, "base": lo * 24, "max": hi * 24}


def resolutions(p: dict, values: list) -> None:
    """The sizes the model takes, and the final/proxy presets from them."""
    p["router"]["inputs"]["resolution"]["values"] = values
    sizes = RI._sizes(values)
    for k in ("final", "proxy"):
        p["presets"][k].update(width=sizes[k][0], height=sizes[k][1])


def references(p: dict, most: int) -> None:
    p["router"]["inputs"]["references"]["max"] = most
    p["capabilities"]["max_subjects"] = most


def no(p: dict, *inputs: str) -> None:
    """Inputs the schema shares with sibling models but this one doesn't take."""
    for k in inputs:
        p["router"]["inputs"].pop(k, None)
    p["recipe"]["keyframes"] = [e for e in ("first", "last") if e in p["router"]["inputs"]]
    if "references" not in p["router"]["inputs"]:
        p["recipe"].pop("reference_image", None)


def needs_first(p: dict) -> None:
    """Image to video: a shot needs its first keyframe (capabilities.requires_first)."""
    p["recipe"]["keyframe_required"] = {"first": f"{p['router']['model']} starts every shot from its "
                                                 f"first frame: generate one, import one, or give "
                                                 f"the shot `continuous: first`"}


def seedance_2_0(p):
    # "Seedance 2.0, 2.0 fast & 2.0 mini: [4,15]"; "do not support 1080p"
    duration(p, min=4, max=15)
    resolutions(p, ["480p", "720p"])
    p["router"]["inputs"]["ratio"]["with_frames"] = "keep"


def veo(p):
    # "Veo 3/3.1: 4, 6, or 8"; "up to 3 asset images"
    duration(p, values=[4, 6, 8])
    references(p, 3)


def wan_3_0(p):
    # "wan3.0-video: integer in [2, 30]"; reference_image max 10
    duration(p, min=2, max=30)
    references(p, 10)


def wan_2_7_r2v(p):
    # "[2, 10]"; "720P, 1080P"; first_frame optional, reference images up to 5, no last frame
    duration(p, min=2, max=10)
    resolutions(p, ["720P", "1080P"])
    references(p, 5)
    no(p, "last")


def wan_2_7_i2v(p):
    # "[2, 15]"; "720P, 1080P"; first_frame, last_frame -- no reference image
    duration(p, min=2, max=15)
    resolutions(p, ["720P", "1080P"])
    no(p, "references")
    needs_first(p)


def runway(p):
    p["_note"] = ("Image to video: every shot starts from its first keyframe (promptImage); no "
                  "reference pictures, no sound (the silent prose: Runway failed every prompt "
                  "carrying quoted lines, 2026-10-12).")


# (Router model, id, label, short, correction, draft) -- live ones were rendered
# on Porchlights ep03 (2026-10-12); drafts match a live sibling's schema
MODELS = [
    ("minimax/minimax-h3", "minimax_h3", "MiniMax H3", "MiniMax", None, False),
    ("byteplus/dreamina-seedance-2-0-260128", "seedance_2_0", "Seedance 2.0", "Seedance", seedance_2_0, False),
    ("byteplus/dreamina-seedance-2-0-fast-260128", "seedance_2_0_fast", "Seedance 2.0 Fast", "Seedance", seedance_2_0, True),
    ("byteplus/dreamina-seedance-2-0-mini", "seedance_2_0_mini", "Seedance 2.0 Mini", "Seedance", seedance_2_0, True),
    ("kling/kling-v3-omni", "kling_v3_omni", "Kling v3 Omni", "Kling", None, False),
    ("kling/kling-video-o1", "kling_video_o1", "Kling Video O1", "Kling O1", None, False),
    ("wan/wan3.0-video", "wan_3_0", "Wan 3.0", "Wan", wan_3_0, False),
    ("wan/wan3.0-video-prime", "wan_3_0_prime", "Wan 3.0 Prime", "Wan", wan_3_0, True),
    ("wan/wan2.7-r2v", "wan_2_7_r2v", "Wan 2.7 (references)", "Wan", wan_2_7_r2v, True),
    ("wan/wan2.7-i2v", "wan_2_7_i2v", "Wan 2.7 (first frame)", "Wan", wan_2_7_i2v, True),
    ("veo/veo-3.1-fast-generate-001", "veo_3_1_fast", "Veo 3.1 Fast", "Veo", veo, False),
    ("veo/veo-3.1-generate-001", "veo_3_1", "Veo 3.1", "Veo", veo, True),
    ("veo/veo-3.1-lite-generate-001", "veo_3_1_lite", "Veo 3.1 Lite", "Veo", veo, True),
    ("runway/gen4_turbo", "runway_gen4_turbo", "Runway Gen-4 Turbo", "Runway", runway, False),
]


def build() -> dict[str, dict]:
    base = TG.load_target("seedance_2_5", "video").spec
    out = {}
    for model, tid, label, short, fix, draft in MODELS:
        with open(os.path.join(SCHEMAS, model.replace("/", "__") + ".json"), encoding="utf-8") as fh:
            p = RI.propose(model, json.load(fh), base=base)["proposal"]
        p.update(id=tid, label=f"{label} (hosted, Comfy Router)", short=short)
        p.pop("draft", None)
        if fix:
            fix(p)
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
