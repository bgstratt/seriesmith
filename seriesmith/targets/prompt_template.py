"""
prompt_template -- a prompt as a template over a shot's parts (docs/DESIGN.md, section 9), so
how a model's prompt reads can be changed without code.

    {style} {framing} {subjects} {action} {lines} [[The sound is {sound_words}.]]

`{name}` is a part. An empty part leaves no gap: the whitespace either side of it becomes one
(the larger). `[[...]]` is a section: if any part in it is empty the whole section goes,
words and all. There is nothing else: no code, no conditions, no filters, so a template is
safe to share, and it is read in one pass, so a shot's own words can't act as template
syntax.

Two templates make one prompt:

- **The shot's** (`recipe.prompt_template`): a writer's parts (`PARTS`), when the shot is
  compiled, so the shotlist shows the prompt. Only the prose writers give parts; a target
  with a writer of its own (H3's fields) keeps it.
- **The request's** (`recipe.prompt_request`): the shot's prompt and what only the request
  knows, which pictures went and how they're numbered (`REQUEST_PARTS`). A part is only
  filled when the model's `inputs` ask for it (`define`, `mention`), whatever the template
  says.

`recipe.prompt` names a **prompt profile**, a writer and its two templates, shared by every
model that takes prompts the same way, whoever serves it (presets/prompt.json). A template
in the recipe wins over its profile's.

Stdlib only: the build uses it.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import re

# what a prose writer gives a shot's template: words ready to read, then the raw values to
# write your own around (`[[Style: {look}.]]`). A silent writer's sound parts are empty and its
# `lines` are acting, so one template serves both.
PARTS = {
    "style": "The series' look, as a sentence: \"Style: <look>.\"",
    "framing": "The framing, the place and the camera, as a sentence",
    "subjects": "Who is in frame and what they look like",
    "extras": "The unnamed background figures",
    "action": "What happens",
    "text": "The on-screen text",
    "lines": "What is said, by whom and how (acted silently on a model with no sound)",
    "sound": "The soundscape, as a sentence (says the place's sound follows when none is given)",
    "music": "The music, as a sentence (says there is none when none is given)",
    "look": "The series' look alone",
    "size": "The framing alone (\"medium shot\")",
    "place": "The place's description alone",
    "camera_move": "The camera's move alone; empty when it's static",
    "names": "The names of who is in frame",
    "spoken": "The lines alone, each after its speaker's name",
    "sound_words": "The script's sound alone; empty when it gives none",
    "music_words": "The script's music alone; empty when it gives none",
}

REQUEST_PARTS = {
    "prompt": "The shot's prompt",
    "definitions": "Each picture defined, by its number in the request (Seedance's \"Define ... in @Image 1 as ...\")",
    "voices": "Each audio reference named (\"Use @Audio 1 as the voice of Ada.\")",
    "mentions": "Each picture named at the end (Kling's \"<<<image_1>>> is Ada.\")",
}

_PART = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_SECTION = re.compile(r"\[\[(.*?)\]\]", re.S)

_PROFILES: dict | None = None
_WATCH: contextvars.ContextVar[dict | None] = contextvars.ContextVar("prompt_watch", default=None)


def problems(template: str, known) -> list[str]:
    """What is wrong with a template, for parts `known` ([]: nothing)."""
    out = []
    bare = _SECTION.sub("", template)
    if "[[" in bare or "]]" in bare:
        out.append("a [[ has no ]] to match it")
    for sec in _SECTION.findall(template):
        if "[[" in sec:
            out.append("a [[...]] section can't hold another")
    unknown = sorted(set(_PART.findall(template)) - set(known))
    if unknown:
        out.append(f"no part called {', '.join(unknown)}: the parts are {', '.join(known)}")
    return out


def _weight(space: str) -> tuple[int, int]:
    return (space.count("\n"), len(space))


def render(template: str, values: dict) -> str:
    """`template` with `values` in it. ValueError for a template that's wrong."""
    wrong = problems(template, values)
    if wrong:
        raise ValueError("the prompt template: " + "; ".join(wrong))

    def said(name: str) -> str:
        return str(values[name] if values[name] is not None else "")

    # literal text ("lit") and what parts and sections came to ("val"; empty leaves a gap)
    tokens: list[tuple[str, str]] = []

    def plain(text: str) -> None:
        at = 0
        for m in _PART.finditer(text):
            tokens.append(("lit", text[at:m.start()]))
            tokens.append(("val", said(m.group(1))))
            at = m.end()
        tokens.append(("lit", text[at:]))

    at = 0
    for m in _SECTION.finditer(template):
        plain(template[at:m.start()])
        inner = m.group(1)
        whole = not any(not said(n).strip() for n in _PART.findall(inner))
        tokens.append(("val", _PART.sub(lambda p: said(p.group(1)), inner) if whole else ""))
        at = m.end()
    plain(template[at:])

    # `said` is as far as a value reaches: only the template's own space is ever closed up
    out, said_to, gap = "", 0, False

    def closed() -> str:
        return out[:said_to] + out[said_to:].rstrip()

    for kind, text in tokens:
        if kind == "val":
            if text.strip():
                out += text
                said_to, gap = len(out), False
            else:
                gap = True
        elif gap:
            if not text:
                continue
            body = text.lstrip()
            lead = text[:len(text) - len(body)]
            kept = closed()
            tail = out[len(kept):]
            out = kept + (max(tail, lead, key=_weight) if kept else "") + body
            gap = False
        else:
            out += text
    return closed() if gap else out


# -- profiles ----------------------------------------------------------------------

def profiles() -> dict:
    """{name: {"writer", "template", "request"}}: presets/prompt.json."""
    global _PROFILES
    if _PROFILES is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "presets", "prompt.json")
        with open(path, encoding="utf-8") as fh:
            _PROFILES = json.load(fh)["profiles"]
    return _PROFILES


def profile(name) -> dict:
    """A profile by name; {} for none (`fields`: a target with a writer of its own)."""
    found = profiles().get(str(name or "").strip())
    return found if isinstance(found, dict) else {}


def _recipe(target) -> dict:
    return target.recipe or {}


def writer_of(target) -> str:
    """The writer the target's profile names ("prose_silent"), "" for none."""
    return profile(_recipe(target).get("prompt")).get("writer", "")


def shot_template(target) -> str:
    """The template a shot's parts go through: the recipe's, else its profile's."""
    recipe = _recipe(target)
    return recipe.get("prompt_template") or profile(recipe.get("prompt")).get("template", "")


def request_template(target, kind: str = "video") -> str:
    """The template a request's prompt goes through: the recipe's, else its profile's, else
    what this kind of model has always sent."""
    recipe = _recipe(target)
    return (recipe.get("prompt_request") or profile(recipe.get("prompt")).get("request")
            or profile("image" if kind == "image" else "prose")["request"])


def request_prompt(template: str, text: str, limit, fit, **values) -> str:
    """The prompt a request sends: `text` in the template with `values`, `text` first cut by
    `fit(text, most)` so that the whole is within `limit` characters (no limit: as it is)."""
    if limit:
        room = len(render(template, {**values, "prompt": "x"})) - 1
        text = fit(text, limit - room)
    sent = render(template, {**values, "prompt": text})
    seen = _WATCH.get()
    if seen is not None:
        seen.update(values=values, text=text, sent=sent, limit=limit)
    return sent


@contextlib.contextmanager
def watching():
    """A dict that, once a request's prompt is made inside this, says what it was made of:
    {"values", "text", "sent", "limit"}. How a preview shows the real thing without a second
    idea of how a model's request is put together."""
    seen: dict = {}
    token = _WATCH.set(seen)
    try:
        yield seen
    finally:
        _WATCH.reset(token)


def signature(target) -> str:
    """What says a target's prompt or request is made its own way ("" when it's the default): a
    take remembers it, so a change to it reads as the reason the take is stale."""
    recipe = _recipe(target)
    both = [recipe.get("prompt_template") or "", recipe.get("prompt_request") or ""]
    mapped = {k: v for k, v in (getattr(target, "show_fields", None) or {}).items()
              if k.startswith("router.")}
    if recipe.get("mapping_edited"):            # a show's own model, changed in its target.json
        from seriesmith.targets import hosted_block
        mapped["router"] = {k: hosted_block(target.spec).get(k) for k in ("inputs", "arguments")}
    if not any(both) and not mapped:
        return ""
    return hashlib.sha1(json.dumps([both, mapped], sort_keys=True).encode("utf-8")).hexdigest()[:16]
