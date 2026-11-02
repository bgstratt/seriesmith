"""
yue2: YuE2, songs (target.json beside this file). Its style is the cue's head with the tempo
in words and "vocal" (the style words barely move the tempo; the plan's Q: line does: docs/
SOUND.md "Measured: YuE2"), and the script's music: notes; its lyrics are the sections that
have lyrics, each under its tag ([Verse], [Chorus]...), a blank line between; `tempo` is
what the graph's second RegexReplace puts before the plan's K: line (the cue's whole bpm, of
the cue's beat). A song with no lyrics is refused before it renders (cue.plan's `blocked`):
YuE2 sings words.

`cue_graph` is the graph surgery a theme needs (cue.graph calls it): a theme's plan given as
text replaces the planner; a theme to transcribe replaces it with SheetSage2 (LoadAudio ->
AudioEncoderLoader -> SheetSage2AudioToABC, as ComfyUI's audio_yue2_music_cover template);
either way both stages sing in `melody` mode.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C

# the editor's section names (web/src/lib/cue.ts SONG_SECTIONS) as YuE2's tags; any other
# name sings as a verse
TAGS = {"intro": "Intro", "verse": "Verse", "pre-chorus": "Pre-Chorus", "prechorus": "Pre-Chorus",
        "chorus": "Chorus", "bridge": "Bridge", "outro": "Outro", "hook": "Chorus", "refrain": "Chorus"}


def tag(name: str) -> str:
    """A section's name as YuE2's tag: "chorus 2" -> "Chorus"; one it doesn't know -> "Verse"."""
    words = (name or "").lower().split()
    while words and words[-1].isdigit():
        words = words[:-1]
    return TAGS.get(" ".join(words).replace(" ", "-"), "Verse")


def lyrics(cue: dict) -> str:
    """The sections with lyrics, each under its tag, a blank line between; "" when none has."""
    out = []
    for s in cue.get("sections") or []:
        lines = [ln.strip() for ln in (s.get("lyrics") or "").splitlines() if ln.strip()]
        if lines:
            out.append("\n".join([f"[{tag(s.get('name') or '')}]"] + lines))
    return "\n\n".join(out)


def tempo_line(cue: dict) -> str:
    """The plan's tempo as the graph sets it: `Q:1/<the meter's note>=<bpm>`, then K: (the
    RegexReplace that puts it before the plan's K: line)."""
    unit = str(cue.get("meter") or "4/4").split("/")[-1].strip() or "4"
    return f"Q:1/{unit}={int(round(float(cue.get('bpm') or 120)))}\nK:"


def cue_prompt(target, cue: dict) -> dict:
    head = C.head(cue, bpm_in_text=True).rstrip(".")
    style = ", ".join(x for x in (head, "vocal", C.notes(cue)) if x)
    values = {"lyrics": lyrics(cue), "mode": "melody" if cue.get("theme") else "full",
              "tempo": tempo_line(cue)}
    return {"prompt": style, "negative": None, "values": values}


def _one(g: dict, ctype: str) -> str | None:
    ids = [k for k, v in g.items() if v.get("class_type") == ctype]
    return ids[0] if len(ids) == 1 else None


def cue_graph(target, g: dict, plan: dict, values: dict, audio) -> None:
    """A theme in the graph (plan["theme"], cue.theme_for): `use` "plan" puts its plan text
    (the melody, no tempo) where the planner's output went; "transcribe" puts SheetSage2's
    transcription of `audio` (the theme's sound, as the backend uploads it) there. The
    planner goes; the song sings in `melody` mode. Nothing to do without a theme."""
    th = plan.get("theme") or {}
    use = th.get("use")
    if use not in ("plan", "transcribe"):
        return
    planner = _one(g, "YuE2GenerateABC")
    if planner is None:
        return
    feeds = [(nid, k) for nid, node in g.items() for k, v in node["inputs"].items()
             if isinstance(v, list) and len(v) == 2 and v[0] == planner]
    if use == "plan":
        src = th.get("abc") or ""
        for nid, k in feeds:
            if g[nid]["class_type"] == "SaveText":
                del g[nid]                       # the plan as written is the theme's own
            else:
                g[nid]["inputs"][k] = src
    else:
        g["t1"] = {"class_type": "AudioEncoderLoader",
                   "inputs": {"audio_encoder_name": values.get("sheetsage") or "sheetsage2_bf16.safetensors"},
                   "_meta": {"title": "Transcriber"}}
        g["t2"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}, "_meta": {"title": "Theme"}}
        g["t3"] = {"class_type": "SheetSage2AudioToABC",
                   "inputs": {"audio_encoder": ["t1", 0], "audio": ["t2", 0], "mode": "melody"},
                   "_meta": {"title": "Theme as ABC"}}
        for nid, k in feeds:
            g[nid]["inputs"][k] = ["t3", 0]
    del g[planner]
    for node in g.values():
        if node["class_type"] == "YuE2GenerateMusic":
            node["inputs"]["mode"] = "melody"
