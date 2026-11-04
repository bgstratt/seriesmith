"""
mrt2: Magenta RealTime 2 (target.json beside this file), through seriesmith's own node
(comfy_nodes/mrt2.py). It plays a stream whose style can change at any frame, so a cue's arc
is a style a bar: the cue's head and the section's words with the bar's energy in words, a
section that rises or falls blended from its first bar's words to its last's. It followed an
arc so given better than any model followed one told in words, and a single prompt not at
all (docs/SOUND.md "Measured: MiniMax Music 3, HeartMuLa and Magenta RealTime 2").

Its quietest words are "soft, sparse", not "very quiet": a bar asked for very quiet came out
all but silent. A quiet bar has drums off; louder ones leave them to the model. A cue's theme
(cue_graph) is its recording, blended into every bar's style by MusicCoCa.

Stdlib only.
"""
from __future__ import annotations

import json

from seriesmith.targets.music import common as C

FPS = 25                                        # its frames: 40 ms
LEVELS = {1: "soft, sparse", 2: "gentle, quiet", 3: "moderate", 4: "strong, full",
          5: "fortissimo, full orchestra"}


def _text(base: str, words: str, level: int) -> str:
    return ", ".join(x for x in (base, words, LEVELS[level]) if x)


def schedule(cue: dict) -> list[dict]:
    """One segment a bar, its frames on the bar grid (the cue's length at FPS); the last
    bar takes what's left."""
    base = ", ".join(x for x in (C.head(cue, bpm_in_text=True).rstrip("."), C.notes(cue)) if x)
    secs = cue.get("sections") or [{"name": "cue", "bars": 1}]
    bars = sum(max(1, int(s.get("bars") or 1)) for s in secs)
    total = round(float(cue["seconds"]) * FPS)
    per = total / bars
    out, k = [], 0
    for s in secs:
        n = max(1, int(s.get("bars") or 1))
        words = " ".join((s.get("words") or "").split()).strip(" ,.")
        a, b = C.level(s.get("from", 3)), C.level(s.get("to", s.get("from", 3)))
        for j in range(n):
            frames = round((k + 1) * per) - round(k * per)
            w = j / (n - 1) if n > 1 else 0.0
            here = C.level(a + (b - a) * w)
            style = (_text(base, words, a) if a == b
                     else [[_text(base, words, a), round(1 - w, 3)], [_text(base, words, b), round(w, 3)]])
            out.append({"frames": frames, "style": style, **({"drums": 0} if here <= 2 else {})})
            k += 1
    out[-1]["frames"] += total - sum(x["frames"] for x in out)
    return out


def cue_prompt(target, cue: dict) -> dict:
    text = " ".join(x for x in (C.head(cue, bpm_in_text=True), C.story(cue)) if x)
    return {"prompt": text, "negative": None,
            "values": {"schedule": json.dumps({"segments": schedule(cue)})}}


def cue_graph(target, g: dict, plan: dict, values: dict, audio) -> None:
    """A theme as part of its style (plan["theme"]["use"] "timbre"; `audio` its sound, as the
    backend uploads it): LoadAudio into SeriesmithMRT2's theme, which MusicCoCa embeds and
    blends into every bar's style at the node's theme_weight."""
    if (plan.get("theme") or {}).get("use") != "timbre" or audio is None:
        return
    node = next((k for k, v in g.items() if v["class_type"] == "SeriesmithMRT2"), None)
    if node is None:
        return
    g["r1"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}, "_meta": {"title": "Theme"}}
    g[node]["inputs"]["theme"] = ["r1", 0]
