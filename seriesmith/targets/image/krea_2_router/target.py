"""
krea_2_router: Krea 2, hosted (Comfy Router), text to image (target.json
beside this file). Series refs and keyframes are worded as every image target
words them (targets/image/common.py); a take is one Router call.

    router_call(target, job) -> (model, arguments)
        the provider's request for one ref take (a refs.GenJob)

Not yet tried against the live service (docs/PLAN.md, step 8).
Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401


def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio ("16:9", "2.35:1") nearest the picture's shape."""
    want = width / height

    def off(r: str) -> float:
        a, b = (float(x) for x in r.split(":"))
        return abs(a / b - want)
    return min(ratios, key=off)


def router_call(target, job) -> tuple[str, dict]:
    spec = target.spec["router"]
    args = {"prompt": job.prompt,
            "aspect_ratio": nearest_ratio(int(job.width or 1024), int(job.height or 1024),
                                          spec["ratios"]),
            "resolution": spec.get("resolution", "1K"),
            "seed": int(job.seed) % (int(spec.get("seed_max", 4294967295)) + 1)}
    if spec.get("creativity"):
        args["creativity"] = spec["creativity"]
    return spec["model"], args
