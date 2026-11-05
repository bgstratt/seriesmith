"""
A voice model behind an API (`"code": "builtin:router_audio"`, its `api` block as a video model's):
words in, a recording out. A sample for a voice ref goes through the queue as any hosted take does.

Two things differ from a voice model that takes a description (targets/audio/common.py):

- **The voice is a speaker the provider has**, picked for the character and kept on the subject in
  the series config (`voices.<provider>`, `refs.set_provider_voice`). No speaker, no call: nothing
  is paid for until the voice is picked.
- **The request is the words alone.** A description or a note would be read aloud, so the sample
  opens with no "this is Mia speaking" either: there's nothing being continued to skip it.

Target.json's `api`:

    {"service": "elevenlabs", "model": "eleven_v4",
     "inputs": {"prompt": {"field": "text", "max_chars": 10000}, "seed": {"name": "seed", "max": 4294967295}}}

Stdlib only.
"""
from __future__ import annotations

import copy

from seriesmith.targets import hosted_block
from seriesmith.targets.audio.common import NEGATIVE, NEUTRAL_LINE, _clean, lines_of, voice_line as _voice_line  # noqa: F401
from seriesmith.targets.generic.request_map import fit, max_chars, place, put_seed

WHAT = "voice sample"


def voice_line(story, subject: str, seconds: float | None = None, pace: str = "normal",
               name: str | None = None, held: bool = False) -> tuple[str, str]:
    """(the words a sample says, where they came from): the character's own lines with no opener."""
    return _voice_line(story, subject, seconds, pace, None, False)


def voice_prompt(name: str, voice: str = "", design: str = "", line: str = "",
                 seconds: float | None = None) -> str:
    """What's sent: the words and nothing else."""
    return _clean(line) or NEUTRAL_LINE


def speaker_of(entry: dict | None, service: str) -> dict | None:
    """The speaker a subject has on a provider ({"id", "name"?}), or None."""
    got = ((entry or {}).get("voices") or {}).get(service)
    if isinstance(got, str):
        got = {"id": got}
    return got if isinstance(got, dict) and got.get("id") else None


def refuses(target, job) -> str | None:
    """Why this take can't be asked for yet, in words for the person; None when it can."""
    service = hosted_block(target.spec).get("service") or ""
    if speaker_of(job.ref.entry, service):
        return None
    name = job.ref.entry.get("name", job.ref.subject)
    from seriesmith import providers as PR
    who = (PR.definitions().get(service) or {}).get("label") or service
    return f"{name} has no voice on {who} yet: pick one first, so nothing is paid for in the wrong voice"


def router_call(target, job) -> tuple[str, dict]:
    """(the model's id, its arguments) for one voice sample."""
    spec = hosted_block(target.spec)
    why = refuses(target, job)
    if why:
        raise ValueError(why)
    inp = spec.get("inputs") or {}
    args = copy.deepcopy(spec.get("arguments") or {})
    pspec = inp.get("prompt") or {"field": "text"}
    most = max_chars(pspec)
    place(args, pspec, prompt=fit(job.prompt, most) if most else job.prompt)
    if inp.get("seed"):
        put_seed(args, inp["seed"], job.seed, 4294967295)
    from seriesmith.backends.router import ROUTING
    speaker = speaker_of(job.ref.entry, spec.get("service") or "")
    args[ROUTING] = {"values": {**(spec.get("values") or {}), "voice": speaker["id"]}}
    return spec["model"], args
