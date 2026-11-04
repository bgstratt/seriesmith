"""
minimax_music3_cloud: MiniMax Music 3 on Comfy Cloud (target.json beside this file), a Comfy
partner node: the local target's caption and a song's lyrics under its section tags
(minimax_music3/prompt.py). A score cue's lyrics are empty: the hosted model has an
instrumental switch, which the node sets for empty lyrics.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music.minimax_music3 import prompt as LOCAL


def cue_prompt(target, cue: dict) -> dict:
    brief = LOCAL.cue_prompt(target, cue)
    if cue.get("kind") != "song":
        brief["values"]["lyrics"] = ""
    return brief
