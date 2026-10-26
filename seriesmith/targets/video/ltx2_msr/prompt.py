"""
LTX-2.5 + MSR: the two prompts PromptRelay takes (docs/MULTISHOT.md, "LTX MSR
revisited"), as Licon's sample workflow writes them.

    references(shots, sq, series_cfg, slots) -> the pictures, in the guide's order
    global_prompt(refs, series_cfg)          -> "Image 1: the Stepmother, ..." per picture, the look
    shot_paragraph(shot, sq, series_cfg, refs) -> the shot: PromptRelay's local prompt

The guide numbers its pictures consecutively, pic1..pic4 then the background,
skipping any it isn't given, and the prompt calls each by that number: `Image
N` in place of the person's name wherever the prose says it. Up to four
people or things are pictures; anyone past that is left in words.

One shot a generation: a run of shots as one prompt cut on its own but drew
people into shots they weren't in (docs/MULTISHOT.md, "LTX MSR revisited").
`references` and the labels take a list of shots all the same.

Stdlib only.
"""
from __future__ import annotations

import re

from seriesmith.core import framing, ir

def _book(series_cfg: dict) -> dict:
    return series_cfg.get("subjects") or {}


def display_name(series_cfg: dict, sid: str) -> str:
    """A subject's name as the prose says it (a variant's is its person's)."""
    book = _book(series_cfg)
    e = book.get(sid) or {}
    return e.get("name") or (book.get(e.get("of")) or {}).get("name") or sid


def is_face(sid: str) -> bool:
    """A variant named for its person's face (`charming_face`)."""
    return "face" in sid.lower().replace("-", "_").split("_")


def references(shots: list[ir.Shot], sq: ir.Sequence, series_cfg: dict, slots: int = 4) -> list[dict]:
    """The pictures the guide is given, in its order: the first `slots` people
    and things on screen across `shots` (each person once, the first picture
    named of them), then the first shot's plate as the background. Each is
    {"subject": id, "path", "face"?} or {"location": key, "path"}: `face` a
    face picture beside the person's own (a `<id>_face` variant, or the one
    the shot names, whose person's picture is then the body). One the series
    config names no picture for is left out (it stays in words)."""
    from seriesmith.core.series_config import variant_of
    variants = variant_of(series_cfg)
    book = _book(series_cfg)
    out, seen = [], set()
    for s in shots:
        for sid in list(s.cast) + [p for p in s.props if p not in s.cast]:
            who = variants.get(sid, sid)
            if who in seen or len(out) >= slots:
                continue
            seen.add(who)
            e = book.get(sid) or {}
            base = book.get(e.get("of")) or {}
            if is_face(sid) and base.get("sheet") and e.get("sheet"):
                # a face picture (`charming_face`): its person's own picture is the body
                out.append({"subject": sid, "path": base["sheet"], "face": e["sheet"]})
                continue
            if not e.get("sheet"):
                continue
            face = next((v["sheet"] for vid, v in book.items()
                         if v.get("of") == sid and is_face(vid) and v.get("sheet")), None)
            out.append({"subject": sid, "path": e["sheet"], **({"face": face} if face else {})})
    key = shots[0].plate or sq.location
    plate = ((series_cfg.get("locations") or {}).get(key) or {}).get("plate")
    if plate:
        out.append({"location": key, "path": plate})
    return out


def labels(refs: list[dict], series_cfg: dict) -> dict[str, str]:
    """{person's name: "Image N"}, by the guide's numbering."""
    return {display_name(series_cfg, r["subject"]): f"Image {i}"
            for i, r in enumerate(refs, 1) if r.get("subject")}


def global_prompt(refs: list[dict], series_cfg: dict) -> str:
    """One `Image N:` paragraph a picture (who or where, and how they look),
    then the look: what PromptRelay holds over the whole clip."""
    book = _book(series_cfg)
    out = []
    for i, r in enumerate(refs, 1):
        if r.get("subject"):
            e = book.get(r["subject"]) or {}
            base = book.get(e.get("of")) or {}
            # a face variant is described as its person (its own design is a close-up's)
            own = base.get("design") if is_face(r["subject"]) and base else e.get("design")
            design = (own or e.get("design") or base.get("design") or "").strip().rstrip(".")
            name = display_name(series_cfg, r["subject"])
            out.append(f"Image {i}: {name[:1].upper()}{name[1:]}" + (f", {design}." if design else "."))
        else:
            loc = (series_cfg.get("locations") or {}).get(r["location"]) or {}
            where = (loc.get("description") or r["location"]).strip().rstrip(".")
            out.append(f"Image {i}: Scene, {where}.")
    look = ((series_cfg.get("style") or {}).get("look") or "").strip().rstrip(".")
    if look:
        out.append(f"The whole video is {look}.")
    return "\n\n".join(out)


def _named(text: str, names: dict[str, str]) -> str:
    """`text` with each pictured person's name as their `Image N` (longest
    names first, so "the Stepmother" goes before a shorter name inside it)."""
    for name in sorted(names, key=len, reverse=True):
        bare = re.sub(r"(?i)^the\s+", "", name)
        pat = r"(?i)\b(?:the\s+)?" + re.escape(bare) + r"\b" if bare != name else r"\b" + re.escape(name) + r"\b"
        text = re.sub(pat, names[name], text)
    return text


def shot_paragraph(shot: ir.Shot, sq: ir.Sequence, series_cfg: dict, refs: list[dict]) -> str:
    """One shot: its framing and who is in it (by picture), where (the
    background's picture), the action, the camera, each line spoken with
    visible lip movement while the others listen, the sound."""
    on = list(shot.cast) + [p for p in shot.props if p not in shot.cast]
    names = labels(refs, series_cfg)
    who =[names.get(display_name(series_cfg, s), display_name(series_cfg, s)) for s in on]
    listed = (", ".join(who[:-1]) + " and " + who[-1]) if len(who) > 1 else (who[0] if who else "")
    frame = framing.article(framing.term(shot.size))
    bg = next((i for i, r in enumerate(refs, 1) if r.get("location")), None)
    head = f"{frame} of {listed}" if listed else frame
    if len(who) == 1:
        head += " alone"
    if bg:
        head += f", in the place matching Image {bg}"
    parts = [head + "."]
    if len(who) > 1:
        parts.append("All faces clearly visible.")
    elif len(who) == 1:
        parts.append("No other characters are visible.")
    action = (shot.action or "").strip()
    if action:
        text = action if action.endswith((".", "!", "?")) else action + "."
        parts.append(_named(text, names))
    cam = framing.orbit((shot.camera or "").strip().rstrip("."), ", ".join(who))
    if cam:
        parts.append(_named(f"The camera {cam}.", names))
    spoke, said = [], []
    for d in shot.dialogue:
        speaker = names.get(display_name(series_cfg, d.speaker), display_name(series_cfg, d.speaker))
        speaker = speaker[:1].upper() + speaker[1:]
        how = f", {d.delivery.strip()}" if (d.delivery or "").strip() else ""
        if d.mode in ("vo", "os"):
            where = " in voiceover" if d.mode == "vo" else " from off screen"
            said.append([speaker, f"{speaker} speaks{where}{how}", [d.line.strip()]])
        elif said and said[-1][0] == speaker and said[-1][2]:
            said[-1][2].append(d.line.strip())          # one speaker's lines run on: said once
        else:
            said.append([speaker, f"{speaker} speaks with visible lip movement{how}", [d.line.strip()]])
            spoke.append(speaker)
    for _, lead, lines in said:
        parts.append(f'{lead}: "{" ".join(lines)}"')
    if spoke and len(who) > len(set(spoke)):
        parts.append("The others listen with their lips closed.")
    if (shot.sound or "").strip():
        parts.append(f"Sound: {shot.sound.strip().rstrip('.')}.")
    return " ".join(parts)
