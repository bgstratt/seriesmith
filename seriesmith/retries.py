"""
retries.py — what happens after a take a render asked retries for has been checked
(docs/EDITOR.md, "Retries"): the retry ladder's decisions; api's retry step carries them out.

A render may ask, per shot, for `tries` more takes when a take fails its checks (takecheck: a
cut it wasn't asked for, its words, or a check registered there, a vision-language model's
look among them). Each one is a new seed on the same model. When they're spent and `fallback`
is on, the shot renders once more on its target's `retry.fallback` (H3 Ref2VA -> H3 FL2VA,
FastH3 Omni -> FastH3 FL2VA, ...), led by a first keyframe (`Next.frame`), the first of:
- "live": the shot's own first keyframe, when it has one (given, continuity, a frame picked):
  kept as it is;
- "take": the last failed take's first frame, when nothing its checks found is at its opening
  (a cut in its first OPENING seconds, or a registered check's flag, which may be anywhere);
- "make": one made on the keyframe image model, as Generate first frame does; when that can't
  be queued, the ladder stops there.

It stops, and says why, when:
- the take passed its checks, or has none (they're off, or couldn't read it);
- the shot has a take picked in the cut (a circled take: the choice is made);
- the take rendered on a paid backend and the render didn't say retries may cost (`paid`);
- there are no tries left and no fallback.

Stdlib only; nothing here renders.
"""
from __future__ import annotations

from dataclasses import dataclass

from seriesmith import takecheck as TC
from seriesmith import takes as T

MAX_TRIES = 5
OPENING = 0.5               # seconds: a cut this early spoils the take's first frame as a keyframe


@dataclass
class Plan:
    """What a render asked of its takes' checks (POST /render's `retry`)."""
    tries: int = 0              # new seeds after a failed take, at most MAX_TRIES
    fallback: bool = False      # then once on the target's retry.fallback, from the take's first frame
    paid: bool = False          # a hosted (paid) backend's takes are retried too

    def to_json(self) -> dict:
        return {"tries": self.tries, "fallback": self.fallback, "paid": self.paid}

    @classmethod
    def from_json(cls, d) -> "Plan":
        """A request's `retry`, checked (its `fallback` on unless it says not): ValueError says
        what's wrong. None: no retries."""
        if d is None:
            return cls()
        if not isinstance(d, dict):
            raise ValueError("retry must be {tries, fallback?, paid?}")
        tries = d.get("tries", 0)
        if not isinstance(tries, int) or isinstance(tries, bool) or not 0 <= tries <= MAX_TRIES:
            raise ValueError(f"retry's tries must be a whole number, 0 to {MAX_TRIES}")
        for k in ("fallback", "paid"):
            if k in d and not isinstance(d[k], bool):
                raise ValueError(f"retry's {k} must be true or false")
        return cls(tries, d.get("fallback", True), d.get("paid", False))

    @property
    def asks(self) -> bool:
        return self.tries > 0 or self.fallback


@dataclass
class Next:
    """The ladder's next rung: do "stop", "seed" (a new seed on `target`) or "fallback" (on
    `target`, from the take's first frame); `why` in words; `plan` the next take's own."""
    do: str
    why: str
    target: str | None = None
    plan: Plan | None = None
    note: str = ""
    frame: str | None = None    # a fallback's first keyframe: "live", "take" or "make"


def opening_clean(checks: dict | None) -> bool:
    """Whether a failed take's first frame can lead a fallback: no cut in its first OPENING
    seconds and no registered check's flag (it may be about the frame itself). Its words
    don't touch the picture."""
    if not checks:
        return False
    if any((c.get("t") if c.get("t") is not None else 0) < OPENING for c in checks.get("cuts") or []):
        return False
    return not any(isinstance(v, dict) and v.get("flag") for v in (checks.get("more") or {}).values())


def decide(take: T.Take | None, plan: Plan, picked: bool, attempt: int = 1,
           fallback_of=None, has_first: bool = False) -> Next:
    """The next rung after `take` (its checks recorded). `picked`: the shot's cut entry picks a
    take. `attempt`: which try this take was (1: the render's own). `fallback_of(target_id)`:
    that target's retry.fallback (targets.Target.retry_fallback), None for none. `has_first`:
    the shot has a live first keyframe of its own (the fallback's `frame` is "live" then)."""
    sc = (take.sidecar or {}) if take else {}
    if take is None or sc.get("status") != "ok":
        return Next("stop", f"the take is {sc.get('status') or 'gone'}")
    checks = TC.checks_of(sc, take.paths.mp4)
    if checks is None:
        return Next("stop", "the take wasn't checked")
    found = TC.reasons(checks)
    if not found:
        return Next("stop", "it passed its checks")
    if picked:
        return Next("stop", "a take is picked in the cut")
    backend = str(sc.get("backend") or "local")
    if backend.split(":", 1)[0] != "local" and not plan.paid:
        return Next("stop", f"it rendered on {backend}, which costs: retry it by hand")
    target = sc.get("target") or T.DEFAULT_TARGET
    tag = f"t{take.take:02d}: " + "; ".join(found)
    if plan.tries > 0:
        return Next("seed", f"a new seed ({tag})", target,
                    Plan(plan.tries - 1, plan.fallback, plan.paid),
                    note=f"retry {attempt} after {tag}")
    fb = fallback_of(target) if (plan.fallback and fallback_of) else None
    if fb and fb != target:
        frame = "live" if has_first else "take" if opening_clean(checks) else "make"
        led = {"live": "the shot's own first keyframe", "take": f"t{take.take:02d}'s first frame",
               "make": "a first frame made on the keyframe model"}[frame]
        return Next("fallback", f"on {fb} from {led} ({tag})", fb,
                    Plan(0, False, plan.paid), note=f"fallback to {fb} from {led}, after {tag}",
                    frame=frame)
    return Next("stop", f"out of retries ({tag})")


def fallback_now(take: T.Take | None, fallback_of, has_first: bool = False) -> Next:
    """The fallback asked for by hand (a take's "Render on FL2VA from its first frame"), whatever
    its checks found: the same first keyframe as the ladder's (`decide`), a take not checked yet
    taken as clean at its opening. Stops for a take that isn't finished or a target with none."""
    sc = (take.sidecar or {}) if take else {}
    if take is None or sc.get("status") != "ok":
        return Next("stop", f"the take is {sc.get('status') or 'gone'}")
    target = sc.get("target") or T.DEFAULT_TARGET
    fb = fallback_of(target)
    if not fb or fb == target:
        return Next("stop", f"{target} has no fallback")
    checks = TC.checks_of(sc, take.paths.mp4)
    frame = "live" if has_first else "take" if (checks is None or opening_clean(checks)) else "make"
    led = {"live": "the shot's own first keyframe", "take": f"t{take.take:02d}'s first frame",
           "make": "a first frame made on the keyframe model"}[frame]
    return Next("fallback", f"on {fb} from {led}", fb, Plan(0, False, False),
                note=f"on {fb} from {led}", frame=frame)
