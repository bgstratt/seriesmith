"""
The LTX-2 prompt: one flowing paragraph of prose, no <Picture N>.

LTX-2 was trained on long audio-visual captions, and its prompt enhancer
(ComfyUI's TextGenerateLTX2Prompt, whose system prompts spell the style out)
asks for: the visual style first ("Style: ..."), then the shot type, camera
motion and viewpoint woven into the prose ("a medium shot frames ... as the
camera slowly pushes in"; if there is none, say the camera remains static,
never invent one), then the subjects with their visible appearance, the action
in chronological order, dialogue quoted exactly with who says it and how, and
the soundscape and music integrated rather than labelled. No headings, no
"The scene opens with", no smell or touch. This writer produces that
paragraph from the story IR and the series config, without calling the LLM:

    Style: <look>. A <size> of <location description>, <camera>. <Name> is
    <design>, and <Name> is <design>. <action> <Name>, in a voice that is
    <voice>, says, <delivery>: "<line>" ... <sound>. <music> plays underneath.

Subjects are described in words (the series config's `design`): LTX takes no
identity reference. A shot rendered from a first-frame keyframe still carries
the full description; the picture wins where they differ.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets import prompt_template as TP
from seriesmith.targets.prose import scene_parts as _scene_parts
from seriesmith.targets.prose import subject_sentence as _subject_sentence, sentence as _sentence, join_and as _and, article as _article  # noqa: F401


def shot_parts(shot, seq, series_cfg: dict) -> dict:
    """The parts of the prose prompt for one shot (targets.prompt_template.PARTS)."""
    book = series_cfg.get("subjects", {})
    lines, spoken = [], []
    introduced: set[str] = set()
    for d in shot.dialogue:
        e = book.get(d.speaker) or {}
        name = e.get("name", d.speaker)
        voice = (e.get("voice") or "").strip()
        who = name
        if d.speaker not in introduced and voice:
            who = f"{name}, in a voice that is {voice},"
        introduced.add(d.speaker)
        if d.mode == "vo":
            verb = "says in an off-screen voiceover"
            if d.speaker in shot.cast:
                verb += ", their lips staying closed"
        elif d.mode == "os":
            verb = "says from off-screen, outside the frame"
        else:
            verb = "says"
        delivery = (d.delivery or "").strip()
        # A V.O./O.S. note ("on the truck radio") next to the line gets read
        # aloud as part of it, so on those it goes with the speaker instead.
        if delivery and d.mode in ("vo", "os"):
            who, delivery = f"{who.rstrip(',')}, {delivery},", ""
        line = f'{who} {verb}{", " + delivery if delivery else ""}: "{d.line.strip()}"'
        lines.append(line[0].upper() + line[1:])
        spoken.append(f'{name}: "{d.line.strip()}"')

    # the soundscape and music, integrated
    sound = (shot.sound or "").strip().rstrip(".")
    music = (shot.music or "").strip().rstrip(".")
    return {
        **_scene_parts(shot, seq, series_cfg),
        "lines": " ".join(lines),
        "spoken": " ".join(spoken),
        "sound": (_sentence(f"the sound is {sound}") if sound else
                  "The ambient sound of the place follows the action."),
        "sound_words": sound,
        "music": _sentence(f"{music} plays underneath") if music else "There is no music.",
        "music_words": music,
    }


def build_prompt(shot, seq, series_cfg: dict) -> str:
    """The prose prompt for one shot (`shot` an core.ir.Shot, `seq` its
    ir.Sequence), as the prose profile words it."""
    return TP.render(TP.profile("prose")["template"], shot_parts(shot, seq, series_cfg))
