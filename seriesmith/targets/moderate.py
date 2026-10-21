"""
What a hosted model's moderation refuses, left out of what we tell it
(docs/AUTHORING.md, "Writing the design sentence").

A hosted model (Comfy Router's: Seedance, Kling, Veo, Seedream, ...) runs
behind its provider's content filter. BytePlus refused a Seedance prompt that
opened with a character's design as written ("a young woman large round
breasts ...", content_policy_violation, 2026-10-21) where the same prose had
passed further down; such words identify no one, and the reference pictures
carry the look. So for a moderated target (targets.Target.moderated) a
subject's design keeps its category, hair, wardrobe and accessories, and loses
what describes a body: each "with ..." part that does, the first kept as far
as its category ("a young woman large round breasts ... with blonde hair" ->
"a young woman with blonde hair"), and words like "curvy" alone. A local
model keeps the design as written. Places are not touched. Stdlib only.
"""
from __future__ import annotations

import copy
import re

BODY = re.compile(r"\b(breasts?|bust|cleavage|chest|nipples?|curves|hips?|thighs?|"
                  r"buttocks?|butt|waist|belly|navel|crotch|groin|legs)\b", re.I)
# a body word that only describes ("a curvy woman"): the word itself goes
BODY_ADJ = re.compile(r"\b(curvy|busty|buxom|voluptuous|shapely|leggy|big-breasted|"
                      r"large-breasted|full-figured)\s+", re.I)
PERSON = re.compile(r"\b(woman|man|girl|boy|lady|gentleman|child|teenager|teen|person|"
                    r"women|men|girls|boys)\b", re.I)


def unbodied(clause: str) -> str:
    """One comma-separated clause of a design without what describes a body."""
    parts = re.split(r"\s+with\s+", BODY_ADJ.sub("", clause))
    kept = []
    for i, part in enumerate(parts):
        hit = BODY.search(part)
        if not hit:
            kept.append(part)
        elif i == 0:
            who = list(PERSON.finditer(part[:hit.start()]))
            if who:
                kept.append(part[:who[-1].end()])
    return " with ".join(p.strip() for p in kept if p.strip())


def moderate(design: str) -> str:
    """A whole design sentence without what describes a body (unbodied, clause
    by clause); as written when nothing does."""
    text = str(design or "").strip()
    end = "." if text.endswith(".") else ""
    clauses = [c.strip() for c in text.rstrip(".").split(",") if c.strip()]
    kept = [c for c in (unbodied(c) for c in clauses) if c]
    if kept == clauses:
        return text
    return ", ".join(kept) + end


def moderated_config(series_cfg: dict) -> dict:
    """The series config as a moderated target is told it: each subject's
    design moderated (the rest, places included, as written)."""
    subjects = series_cfg.get("subjects")
    if not isinstance(subjects, dict):
        return series_cfg
    out = copy.copy(series_cfg)
    out["subjects"] = {k: (dict(v, design=moderate(v["design"]))
                           if isinstance(v, dict) and isinstance(v.get("design"), str) else v)
                       for k, v in subjects.items()}
    return out
