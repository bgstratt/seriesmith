"""
minimax_music3: MiniMax Music 3 (target.json beside this file). Its caption is three parts,
as ComfyUI's audio_minimax_music_3 template writes them: Global Metadata (the cue's head with
the tempo in words, and the script's music: notes as its mood), Vocal Details, and
Arrangement (the sections told as a story). Its lyrics are the sections as its own tags (the
only thing it follows as structure, its template says), a song's sections with their lines.
A score cue's lyrics are the tags alone: empty lyrics end a take early and leak a voice, the
tags alone reach the length asked (docs/SOUND.md "Measured: MiniMax Music 3 and
Magenta RealTime 2").

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C

NO_VOICE = ("None. Purely instrumental throughout: no vocals, no singing, no humming, no choir, "
            "no spoken words.")
VOICE = "A clear lead vocal, every word sung clearly, in the style above."


def lyrics(cue: dict) -> str:
    out = []
    for s in cue.get("sections") or []:
        out.append("[" + " ".join((s.get("name") or "section").split()).lower() + "]")
        if cue.get("kind") == "song":
            out += [ln.strip() for ln in (s.get("lyrics") or "").splitlines() if ln.strip()]
    return "\n".join(out) or "[intro]\n[outro]"


def cue_prompt(target, cue: dict) -> dict:
    mood = C.notes(cue)
    meta = " ".join(x for x in (C.head(cue, bpm_in_text=True), f"Mood: {mood}." if mood else "") if x)
    story = C.story(cue) or "One steady section."
    voice = VOICE if cue.get("kind") == "song" else NO_VOICE
    caption = f"Global Metadata: {meta}\n\nVocal Details: {voice}\n\nArrangement: {story}"
    return {"prompt": caption, "negative": None,
            "values": {"lyrics": lyrics(cue), "seconds": round(float(cue["seconds"]), 3)}}
