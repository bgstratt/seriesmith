"""
blocking.py -- a story structure and a duration as shots: how many each beat gets (docs/PLAN.md,
the storyboard; "From beats to shots" in docs/STORY_STRUCTURES.md is the rule).

    block(structure, duration, shot_seconds)  -> the acts, their beats, each beat's shots

Model-free and stdlib only. The episode's shots are all one length, so the beats' seconds add up
to the duration exactly; a beat's share of the shots is its share of the story. A beat with a span
(`at`) takes its share of what's left after the beats at a point (`point`: Midpoint, Low Point),
which get a shot or two each. A beat with neither (the Pixar Spine's optional moral) isn't blocked.
"""
from __future__ import annotations

from seriesmith.core import spotting as SP

TYPICAL_SHOT = 3.5          # seconds: the middle of "3 to 4 s"
LONG_ENOUGH_FOR_TWO = 300   # seconds of episode from which a beat at a point gets two shots
THIN_SHOTS = 1.5            # a beat whose share comes to fewer shots than this wants merging


class BlockError(ValueError):
    pass


def _point_shots(duration: float) -> int:
    return 2 if duration >= LONG_ENOUGH_FOR_TWO else 1


def _apportion(widths: list[float], total: int) -> list[int]:
    """`total` shots shared by `widths`: at least one each, the rest by largest remainder (the
    earlier beat first on a tie). `total` is at least len(widths)."""
    whole = sum(widths)
    ideal = [w / whole * total for w in widths]
    shots = [max(1, int(x)) for x in ideal]
    by_remainder = sorted(range(len(widths)), key=lambda i: (shots[i] - ideal[i], i))
    n = 0
    while sum(shots) < total:
        shots[by_remainder[n % len(shots)]] += 1
        n += 1
    # the minimum of one can overshoot: take back from the beats furthest over their share
    while sum(shots) > total:
        i = max((k for k in range(len(shots)) if shots[k] > 1), key=lambda k: (shots[k] - ideal[k], k))
        shots[i] -= 1
    return shots


def block(structure: str | dict, duration: float, shot_seconds: float = TYPICAL_SHOT) -> dict:
    """{"structure", "duration", "shot_seconds", "wanted_shots", "shots", "warnings", "acts":
    [{"act", "seconds", "shots", "beats": [{"beat", "act", "guidance", "at" | "point", "shots",
    "seconds", "first_shot", "thin"}]}]}: `shot_seconds` as asked, and the length each shot comes
    to in the beats' own `seconds`; `first_shot` counts from 0 across the episode. BlockError when
    the structure is unknown or a number isn't above zero."""
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        raise BlockError("the episode needs a duration above zero")
    if not isinstance(shot_seconds, (int, float)) or isinstance(shot_seconds, bool) or shot_seconds <= 0:
        raise BlockError("a typical shot needs a length above zero")
    try:
        st = SP.structure(structure) if isinstance(structure, str) else structure
    except SP.SpotError as exc:
        raise BlockError(str(exc)) from exc

    beats = [b for b in st["beats"] if b.get("at") or "point" in b]
    if not beats:
        raise BlockError(f"{st['name']} has no beats placed in the story")
    wanted = max(1, round(duration / shot_seconds))
    each_point = _point_shots(duration)
    spans = [b for b in beats if b.get("at")]
    points = len(beats) - len(spans)
    room = max(len(spans), wanted - points * each_point) if spans else 0
    widths = [float(b["at"][1] - b["at"][0]) for b in spans]
    shares = iter(_apportion(widths, room)) if spans else iter(())
    whole = sum(widths)

    total = room + points * each_point
    length = duration / total
    out_acts: list[dict] = []
    warnings: list[str] = []
    at_shot = 0
    for b in beats:
        spanned = bool(b.get("at"))
        shots = next(shares) if spanned else each_point
        thin = spanned and (b["at"][1] - b["at"][0]) / whole * room < THIN_SHOTS
        beat = {"beat": b["beat"], "act": b.get("act", ""), "guidance": b.get("guidance", ""),
                "shots": shots, "seconds": round(shots * length, 3), "first_shot": at_shot, "thin": thin}
        beat["at" if spanned else "point"] = b["at"] if spanned else b["point"]
        at_shot += shots
        if not out_acts or out_acts[-1]["act"] != beat["act"]:
            out_acts.append({"act": beat["act"], "seconds": 0.0, "shots": 0, "beats": []})
        act = out_acts[-1]
        act["beats"].append(beat)
        act["shots"] += shots
        act["seconds"] = round(act["seconds"] + beat["seconds"], 3)
        if thin:
            warnings.append(f"{beat['beat']} comes to under two shots: merge it with a beat beside it, "
                            "or pick a longer duration or a shorter structure")
    if total > wanted:
        warnings.insert(0, f"{st['name']} has more beats than this duration has shots: "
                           f"each shot comes to {length:.2f} s")
    return {"structure": st["name"], "duration": float(duration), "shot_seconds": round(length, 3),
            "wanted_shots": wanted, "shots": total, "warnings": warnings, "acts": out_acts}
