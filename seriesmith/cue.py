"""
cue.py — a music cue: what it is asked, its takes, and the one in the mix (docs/SOUND.md
"Music: a cue is written to its hits").

A cue lives in `<ep>/sound/<cue id>/`:

    spec.json   what it is asked (check_spec):
                {"id": "m01", "kind": "score" | "song", "label": "1M3 The Proposal",
                 "model": null (the kind's: model_for) | "stable_audio3",
                 "in": {"shot", "frame"}, "out": {"shot", "frame"},
                 "style": "romantic, solo horn for Edmund", "bpm": 92, "fixed_tempo": false,
                 "meter": "4/4" (beats/unit: "7/8", "12/8"...; a bare 3 is 3/4),
                 "key": "D minor", "tail": 2.0,
                 "sections": [{"name": "intro", "bars": 4, "words": "solo french horn",
                               "from": 1, "to": 1, "lyrics": ""}, ...],
                 "arc": [{"at": {"shot", "frame"}, "level": 1-5}, ...],
                 "hits": null (every hit of the mix in its span) | ["h1", ...],
                 "theme": null | {"cue": "m01"} (the take of m01 in the mix) |
                          {"cue": "m01", "take": 2} | {"file": "audio/theme.wav"},
                 "takes": null (the model's preset) | 8, "seed": null (from the ids)}
    tNN.wav     a take, stretched to the cue's exact tempo (tNN_raw.<ext> as it came)
    tNN.abc     a song's plan as it was sung (YuE2: its sections and bars, the cue's tempo)
    tNN.json    its sidecar: what it was asked (prompt, values, seed, model, the plan's
                tempo, the theme), its status, what was measured (measure), and a song's
                plan read (`song`: its sections against the cue)

Planning (`plan`): the cut is laid out as assemble lays it (cut_layout) so the cue's anchors
become seconds; the hits in its span are fitted (core/score.fit_tempo: the tempo within 8 %
of the asked one, and the pre-roll, that put the must-hits on bar lines); the cue runs from
the bar line before its in point through its out point and `tail`, in whole bars; its
sections fill those bars (given, else from the hits: a section ends where the music arrives,
drops or turns); the script's `music:` notes of the shots it plays over go to the prompt; its arc is one energy per bar (the spec's points, else its sections');
the model's prompt is its target's (cue_prompt). A model takes a whole bpm, so a take is
asked for `ask_bpm` and `seconds x stretch`, then stretched to the exact tempo.

A take, when it comes back (`measure`): converted to a wav, stretched by what its measured
tempo says (within 8 %; the plan's stretch when it can't be measured, as in soft music
without onsets), its downbeat found (beats.grid), so its first bar line is where the
cue's pre-roll starts (the fit has put each hit on a bar line of that grid); at each hit,
the strongest onset within half a beat and its distance in frames (whether the music does
something there); its level per bar against the arc (shape error); and a score that ranks
the takes (the worst must-hit error, then the shape).

A take is stale (`stale`) when the cut has moved under it since it was rendered: its span,
a hit, the tempo, the theme; each said in words.

A theme (the leitmotif: `theme`, docs/SOUND.md phase 2) is another cue's take or a file, and
each model hears it its own way. Another cue's take is a given one (`take`) or, without one,
whichever that cue has in the pass's mix (else its best finished take: theme_take), resolved
when a take is planned and named in its sidecar, so a new pick there makes this cue's takes
stale (`theme_for`): YuE2 sings its melody (the take's own plan when
it is a YuE2 take, else SheetSage2's transcription of its sound, in the same job), ACE-Step
takes its sound as its timbre reference, Stable Audio 3 renders from its sound (stage_theme
reshapes it to the cue's tempo and bars; the sampler starts from it at the theme's strength,
0.86 by default). A theme can also be the series config's (`sound.themes`: a picked take of
any episode's cue, or a file), named by the cue (`{"theme": "porch"}`: series_theme). With
SheetSage2 installed, a take rendered from a theme gets a melody score (core/abc.melody_match:
the take's transcription against the theme's, in the same job); under THEME_FLOOR it lost the
theme, and ranks after those that kept it.

Picking (`place`): the take becomes the cue's item on the music track of the pass's mix
(mix.py): anchored at the cue's in point, played from where its pre-roll ends, to its out
point with a one-bar fade, and (`fit_gain`) breakpoints at each bar that pull its level
toward the arc, ±6 dB at most.

Deleting (`delete`): the cue's folder moved whole to `<ep>/_history/cue-<id>.<stamp>/` (to put
back by hand) and its items taken out of every pass's mix. Muting it instead (its item's
`mute`, mix.py) keeps it where it is, silent.
"""

from __future__ import annotations

import math
import os
import re
import subprocess

from seriesmith import beats as B
from seriesmith import edit as E
from seriesmith import ff as FF
from seriesmith import jobs as J
from seriesmith import mix as MX
from seriesmith import peaks as PK
from seriesmith import takes as T
from seriesmith import targets as TG
from seriesmith.core import abc as ABC
from seriesmith.core import fileio as F
from seriesmith.core import score as SC
from seriesmith.core.ir import stable_seed

SOUND_DIR = "sound"
SPEC = "spec.json"
SPEC_FIELDS = ("id", "kind", "label", "model", "in", "out", "style", "bpm", "fixed_tempo", "meter", "key",
               "orchestra",
               "tail", "sections", "arc", "hits", "theme", "takes", "seed")
SECTION_FIELDS = ("name", "bars", "words", "from", "to", "lyrics")
# the orchestration grid's levels: who plays in a bar, and how much
ORCHESTRA_LEVELS = ("", "under", "present", "lead")
COMP_XFADE = 0.02                      # seconds of equal-power crossfade at each splice
DEFAULT_BPM = 100.0
# what a cue is: score (underscore composed to the picture; the default) or a song (sung, its
# sections' lyrics); each kind's default model, unless the series config's `sound` names one
KINDS = ("score", "song")
KIND_MODEL = {"score": ("music_model", None), "song": ("song_model", "yue2")}
# what a theme may be: a file of these (a recording, a gallery item, a take's video)
THEME_EXTS = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac", ".opus", ".mp4", ".mov", ".webm", ".mkv")
THEME_STRENGTH = (0.5, 0.99)           # where a theme's sound starts the schedule (t0), either end
THEME_ROLES = ("show", "story", "runner")
# a theme's melody kept by a take (core/abc.melody_match): under this it is lost (a take with no
# theme in it keeps about 0.2: docs/SOUND.md "Measured: leitmotifs")
THEME_FLOOR = 0.3
# a theme stretched further than this to a cue's tempo holds it less ("A theme take under
# another length and tempo": 0.8x lost some, 1.25x lost it): said, not refused
THEME_STRETCH_WARN = 0.08
THEME_XFADE = 0.03                     # seconds of equal-power crossfade where a theme loops
TAKES_MAX = 16
STRETCH_MAX = 0.08                     # how far a take is stretched to its tempo, either way
FIT_SPREAD = 0.08                      # how far the fit moves the asked tempo, either way
ALTERNATIVES = 4                       # the tempos a plan offers (score.alternatives)
# a tempo heard this close to the asked one is the model's drift, and believed; further off
# it is most likely the beat tracker lost in soft music (measured 81-108 on a 93 bpm cue),
# and the plan's stretch is used
TEMPO_TRUST = 0.03
GAIN_FIT_DB = 6.0                      # how far fit_gain moves a bar, either way
ONSET_MIN = 0.15                       # an onset this strong (of the take's strongest) marks a hit
_TAKE = re.compile(r"^t(\d{2,3})\.json$")
_ID_RX = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class CueError(ValueError):
    pass


# ---------------------------------------------------------------------------
# the spec
# ---------------------------------------------------------------------------

def _level(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= 5:
        raise CueError(f"{what} is an energy from 1 to 5, not {v!r}")
    return float(v)


def check_spec(raw) -> dict:
    """A cue's spec in its stored form. CueError says what's wrong."""
    if not isinstance(raw, dict):
        raise CueError("a cue must be an object")
    unknown = set(raw) - set(SPEC_FIELDS)
    if unknown:
        raise CueError(f"unknown cue field(s) {', '.join(sorted(unknown))}")
    cid = raw.get("id")
    if not isinstance(cid, str) or not MX._ID.match(cid):
        raise CueError(f"a cue's id is 1-40 letters, digits, _ or -, not {cid!r}")
    out: dict = {"id": cid}
    kind = raw.get("kind") or "score"
    if kind not in KINDS:
        raise CueError(f"cue {cid}'s kind is score or song, not {kind!r}")
    if kind != "score":
        out["kind"] = kind
    try:
        out["in"] = MX.check_anchor(raw.get("in"), f"cue {cid}'s in")
        out["out"] = MX.check_anchor(raw.get("out"), f"cue {cid}'s out")
    except ValueError as e:
        raise CueError(str(e)) from None
    for k in ("label", "style", "key"):
        if raw.get(k) is not None:
            if not isinstance(raw[k], str):
                raise CueError(f"cue {cid}'s {k} is text")
            if raw[k].strip():
                out[k] = " ".join(raw[k].split())[:500]
    if raw.get("model") is not None:
        try:
            t = TG.load_target(raw["model"])
        except Exception:
            raise CueError(f"cue {cid}'s model {raw['model']!r} isn't a target") from None
        if t.kind != "music":
            raise CueError(f"cue {cid}'s model {raw['model']!r} is a {t.kind} target, not music")
        if kind == "song" and not t.capabilities().get("lyrics"):
            raise CueError(f"cue {cid} is a song, and {t.label} sings no lyrics (instrumental only): "
                           f"pick a model that does, or make it score")
        out["model"] = t.id
    if raw.get("bpm") is not None:
        b = raw["bpm"]
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 30 <= b <= 240:
            raise CueError(f"cue {cid}'s bpm is 30 to 240, not {b!r}")
        out["bpm"] = round(float(b), 3)
    if raw.get("fixed_tempo"):
        out["fixed_tempo"] = True
    try:
        beats, unit = parse_meter(raw.get("meter", 4))
    except ValueError as e:
        raise CueError(f"cue {cid}'s {e}") from None
    if (beats, unit) != (4, 4):
        out["meter"] = f"{beats}/{unit}"
    tail = raw.get("tail", 2.0)
    if isinstance(tail, bool) or not isinstance(tail, (int, float)) or not 0 <= tail <= 30:
        raise CueError(f"cue {cid}'s tail is 0 to 30 seconds, not {tail!r}")
    if tail != 2.0:
        out["tail"] = float(tail)
    secs = []
    for i, s in enumerate(raw.get("sections") or []):
        if not isinstance(s, dict) or set(s) - set(SECTION_FIELDS):
            raise CueError(f"cue {cid}'s section {i + 1} takes {', '.join(SECTION_FIELDS)}")
        sec: dict = {"name": " ".join(str(s.get("name") or f"section {i + 1}").split())[:40]}
        if s.get("bars") is not None:
            if isinstance(s["bars"], bool) or not isinstance(s["bars"], int) or not 1 <= s["bars"] <= 256:
                raise CueError(f"cue {cid}'s section {i + 1}'s bars is a whole number, 1 or more")
            sec["bars"] = s["bars"]
        for k in ("words", "lyrics"):
            if s.get(k):
                sec[k] = str(s[k]).strip()[:2000]
        for k in ("from", "to"):
            if s.get(k) is not None:
                sec[k] = _level(s[k], f"cue {cid}'s section {i + 1}'s {k}")
        secs.append(sec)
    if secs:
        out["sections"] = secs
    arc = []
    for i, p in enumerate(raw.get("arc") or []):
        if not isinstance(p, dict) or set(p) - {"at", "level"}:
            raise CueError(f"cue {cid}'s arc point {i + 1} is {{\"at\", \"level\"}}")
        try:
            at = MX.check_anchor(p.get("at"), f"cue {cid}'s arc point {i + 1}")
        except ValueError as e:
            raise CueError(str(e)) from None
        arc.append({"at": at, "level": _level(p.get("level"), f"cue {cid}'s arc point {i + 1}")})
    if arc:
        out["arc"] = arc
    if raw.get("orchestra"):
        orch = raw["orchestra"]
        if not isinstance(orch, dict):
            raise CueError(f"cue {cid}'s orchestra is {{family: [level per bar]}}")
        clean = {}
        for fam, levels in orch.items():
            name = " ".join(str(fam).split())[:40]
            if not name:
                raise CueError(f"cue {cid}'s orchestra has a family with no name")
            if not isinstance(levels, list) or len(levels) > 256 or not all(
                    isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 3 for x in levels):
                raise CueError(f"cue {cid}'s orchestra {name}: a level per bar, 0 (off) to 3 (lead)")
            while levels and levels[-1] == 0:
                levels = levels[:-1]
            if levels:
                clean[name] = levels
        if clean:
            out["orchestra"] = clean
    if raw.get("theme") is not None:
        out["theme"] = check_theme(raw["theme"], cid)
    if raw.get("hits") is not None:
        if not isinstance(raw["hits"], list) or not all(isinstance(h, str) for h in raw["hits"]):
            raise CueError(f"cue {cid}'s hits are the ids of the mix's hits it lands")
        out["hits"] = list(raw["hits"])
    for k, hi in (("takes", TAKES_MAX), ("seed", 2 ** 63 - 1)):
        v = raw.get(k)
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, int) or not (1 if k == "takes" else 0) <= v <= hi:
                raise CueError(f"cue {cid}'s {k} is a whole number up to {hi}")
            out[k] = v
    return out


def check_theme(th, cid: str) -> dict:
    """A cue's theme in its stored form: {"cue": id} (whichever take of another cue in the
    episode is in the pass's mix: theme_take), {"cue": id, "take": n} (that take), {"file":
    a path relative to the episode} or {"theme": name} (one of the series config's
    `sound.themes`: series_theme); any of them with a "strength" (where a model that renders
    from the theme's sound starts, 0.5 to 0.99; the model's own when none). Whether it is
    there is the plan's to say (save_spec checks the cue)."""
    if isinstance(th, dict) and "strength" in th:
        s = th["strength"]
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not THEME_STRENGTH[0] <= s <= THEME_STRENGTH[1]:
            raise CueError(f"cue {cid}'s theme strength is {THEME_STRENGTH[0]} to {THEME_STRENGTH[1]}, not {s!r}")
        rest = check_theme({k: v for k, v in th.items() if k != "strength"}, cid)
        return {**rest, "strength": round(float(s), 3)}
    if isinstance(th, dict) and set(th) == {"theme"}:
        if not isinstance(th["theme"], str) or not MX._ID.match(th["theme"]):
            raise CueError(f"cue {cid}'s theme names a series theme by its name, not {th['theme']!r}")
        return {"theme": th["theme"]}
    if isinstance(th, dict) and set(th) in ({"cue"}, {"cue", "take"}):
        if not isinstance(th["cue"], str) or not MX._ID.match(th["cue"]):
            raise CueError(f"cue {cid}'s theme names a cue by its id, not {th['cue']!r}")
        if th["cue"] == cid:
            raise CueError(f"cue {cid}'s theme can't be one of its own takes")
        if "take" not in th:
            return {"cue": th["cue"]}
        n = th["take"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999:
            raise CueError(f"cue {cid}'s theme take is a take number, not {n!r}")
        return {"cue": th["cue"], "take": n}
    if isinstance(th, dict) and set(th) == {"file"}:
        f = th["file"]
        if not isinstance(f, str) or not f.strip():
            raise CueError(f"cue {cid}'s theme file is a path relative to the episode")
        f = f.strip().replace("\\", "/")
        if re.match(r"^([A-Za-z]:|/)", f) or len(f) > 500:
            raise CueError(f"cue {cid}'s theme file is a path relative to the episode, not {f!r}")
        if os.path.splitext(f)[1].lower() not in THEME_EXTS:
            raise CueError(f"cue {cid}'s theme is a sound file ({', '.join(THEME_EXTS)}), not {f!r}")
        return {"file": f}
    raise CueError("cue " + cid + "'s theme is {\"cue\"} (another cue's take in the mix), {\"cue\", "
                   "\"take\"} (another cue's take), {\"file\"} or {\"theme\"} (a series theme)")


def check_series_theme(name: str, raw) -> dict:
    """One of the series config's `sound.themes` in its stored form: {"ep", "cue", "take"} (a
    take of a cue in an episode of the series: its folder beside this one's, pinned, so a
    pick there never makes another episode's cues stale) or {"file"} (relative to the series
    config's folder; its "bpm", and "beats" to the bar, when it has a steady tempo: it's played
    at the cue's, its first beat the bar line), with "words" (what it is, in words), "for" (the cast ids it belongs to)
    and "role" ("show", "story", "runner") as notes the draft reads. CueError says what's
    wrong."""
    if not isinstance(name, str) or not MX._ID.match(name):
        raise CueError(f"a series theme's name is 1-40 letters, digits, _ or -, not {name!r}")
    if not isinstance(raw, dict):
        raise CueError(f"series theme {name} is an object")
    out: dict = {}
    src = set(raw) & {"ep", "cue", "take", "file"}
    if src == {"ep", "cue", "take"}:
        if not isinstance(raw["ep"], str) or not _ID_RX.match(raw["ep"]):
            raise CueError(f"series theme {name}'s ep is an episode's folder name, not {raw['ep']!r}")
        if not isinstance(raw["cue"], str) or not MX._ID.match(raw["cue"]):
            raise CueError(f"series theme {name}'s cue is a cue's id, not {raw['cue']!r}")
        n = raw["take"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999:
            raise CueError(f"series theme {name}'s take is a take number, not {n!r}")
        out.update(ep=raw["ep"], cue=raw["cue"], take=n)
    elif src == {"file"}:
        out["file"] = check_theme({"file": raw["file"]}, name)["file"]
        for k, lo, hi in (("bpm", 30, 240), ("beats", 1, 16)):
            v = raw.get(k)
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                    raise CueError(f"series theme {name}'s {k} is {lo} to {hi}, not {v!r}")
                out[k] = float(v) if k == "bpm" else int(v)
    else:
        raise CueError(f"series theme {name} is {{\"ep\", \"cue\", \"take\"}} (a picked take) or {{\"file\"}}")
    if raw.get("words") is not None:
        if not isinstance(raw["words"], str):
            raise CueError(f"series theme {name}'s words are text")
        out["words"] = " ".join(raw["words"].split())[:500]
    if raw.get("for") is not None:
        if not isinstance(raw["for"], list) or not all(isinstance(x, str) for x in raw["for"]):
            raise CueError(f"series theme {name}'s for is a list of cast ids")
        out["for"] = list(raw["for"])
    if raw.get("role") is not None:
        if raw["role"] not in THEME_ROLES:
            raise CueError(f"series theme {name}'s role is {', '.join(THEME_ROLES)}, not {raw['role']!r}")
        out["role"] = raw["role"]
    unknown = set(raw) - {"ep", "cue", "take", "file", "bpm", "beats", "words", "for", "role"}
    if unknown:
        raise CueError(f"series theme {name}: unknown field(s) {', '.join(sorted(unknown))}")
    return out


def series_themes(series: dict | None) -> dict:
    """The series config's `sound.themes`, each checked (check_series_theme); one that doesn't
    read is left out, its error under "_errors" ({name: why})."""
    raw = ((series or {}).get("sound") or {}).get("themes") or {}
    out, errors = {}, {}
    for name, v in raw.items() if isinstance(raw, dict) else ():
        try:
            out[name] = check_series_theme(name, v)
        except CueError as e:
            errors[name] = str(e)
    if errors:
        out["_errors"] = errors
    return out


def theme_text(th: dict | None) -> str | None:
    """A theme in words, for a take's fingerprint and the window: "m01 t02", "audio/x.wav",
    "porch" (a series theme); a theme that follows the mix's pick is its cue alone ("m01")
    until it is resolved."""
    if not th:
        return None
    if th.get("theme"):
        return th["theme"]
    if th.get("cue"):
        return f"{th['cue']} t{th['take']:02d}" if th.get("take") else th["cue"]
    return th.get("file")


def parse_meter(m) -> tuple[int, int]:
    """(beats to the bar, the note a beat is) from a meter: "7/8", "6/8", "5/4", or a bare
    number of beats in 4 (the stored form before meters were text). The tempo counts the
    beats, so a bar is `beats` x 60 / bpm whatever the unit; the unit only tells the model the
    feel. ValueError for one that isn't a meter (1 to 16 beats of a 2, 4, 8 or 16)."""
    if isinstance(m, int) and not isinstance(m, bool):
        beats, unit = m, 4
    elif isinstance(m, str) and re.fullmatch(r"\s*\d{1,2}\s*/\s*\d{1,2}\s*", m):
        beats, unit = (int(x) for x in m.split("/"))
    else:
        raise ValueError(f"meter is beats/unit, e.g. 4/4, 6/8 or 7/8, not {m!r}")
    if not 1 <= beats <= 16 or unit not in (2, 4, 8, 16):
        raise ValueError(f"meter is 1 to 16 beats of a 2, 4, 8 or 16, not {m!r}")
    return beats, unit


def meter_beats(spec: dict) -> int:
    return parse_meter(spec.get("meter", 4))[0]


def cue_dir(root: str, cid: str) -> str:
    return os.path.join(root, SOUND_DIR, cid)


def load_spec(root: str, cid: str) -> dict:
    raw = F.read_json_or(os.path.join(cue_dir(root, cid), SPEC), None)
    if raw is None:
        raise FileNotFoundError(f"no cue {cid} in {root}")
    return check_spec(raw)


def save_spec(root: str, raw) -> dict:
    spec = check_spec(raw)
    th = spec.get("theme") or {}
    if th.get("cue") and not os.path.isfile(os.path.join(cue_dir(root, th["cue"]), SPEC)):
        raise CueError(f"cue {spec['id']}'s theme: there is no cue {th['cue']} in the episode")
    F.write_json(os.path.join(cue_dir(root, spec["id"]), SPEC), spec)
    return spec


def _of_cue(item: dict, cid: str) -> bool:
    """Whether a mix item is cue `cid`'s: its id, or one of its takes' files."""
    return item.get("id") == cid or (item.get("path") or "").startswith(f"{SOUND_DIR}/{cid}/")


def delete(root: str, cid: str) -> dict:
    """Cue `cid` taken out of the episode: its folder (spec, takes, their sidecars) moved
    whole to <ep>/_history/cue-<id>.<YYYYmmdd-HHMMSS>/ (put back by hand: move it to
    sound/<id>/ again), and its items taken out of every pass's mix (each a normal mix
    write: the old mix.json to _history too). Returns {"cue", "moved_to" (relative to the
    episode, "/"), "takes", "mixes" (the passes whose mix had it)}. FileNotFoundError when
    there's no such cue; CueError when another cue takes it as its theme, or a pass's mix
    doesn't read (nothing is changed then)."""
    from seriesmith import source as SRC                # it imports edit: not at the top
    d = cue_dir(root, cid)
    if not _ID_RX.match(cid or "") or not os.path.isfile(os.path.join(d, SPEC)):
        raise FileNotFoundError(f"no cue {cid} in {root}")
    users = [c["id"] for c in list_cues(root)
             if c["id"] != cid and ((c.get("theme") or {}).get("cue") == cid)]
    if users:
        raise CueError(f"{cid} is the theme of {', '.join(users)}: give "
                       f"{'it' if len(users) == 1 else 'them'} another theme first")
    ep = os.path.basename(os.path.normpath(root))
    named = [n for n, t in series_themes(J.series_config(root)).items()
             if n != "_errors" and t.get("ep") == ep and t.get("cue") == cid]
    if named:
        raise CueError(f"{cid} is the series theme {', '.join(named)} (the series config's sound.themes): "
                       f"pick {'it' if len(named) == 1 else 'them'} from another cue first")
    mixes = {}
    for pass_, raw in MX.load(root).items():
        try:
            mix = MX.check(raw)
        except ValueError as e:
            raise CueError(f"the {pass_} pass's {MX.MIX_FILE} doesn't read: {e}") from None
        kept = [i for i in mix.get("items") or [] if not _of_cue(i, cid)]
        if len(kept) != len(mix.get("items") or []):
            out = dict(mix)
            if kept:
                out["items"] = kept
            else:
                out.pop("items", None)
            mixes[pass_] = out
    takes = len(list_takes(root, cid))
    dst = SRC.move_to_history(root, d, f"cue-{cid}")
    for pass_, mix in mixes.items():
        MX.write(root, pass_, mix)
    return {"cue": cid, "moved_to": os.path.relpath(dst, root).replace(os.sep, "/"),
            "takes": takes, "mixes": sorted(mixes)}


def list_cues(root: str) -> list[dict]:
    """Every cue's spec in the episode, by id (one that doesn't read is left out)."""
    base = os.path.join(root, SOUND_DIR)
    out = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            out.append(load_spec(root, name))
        except (FileNotFoundError, CueError):
            continue
    return out


# ---------------------------------------------------------------------------
# the cut, laid out
# ---------------------------------------------------------------------------

def cut_layout(root: str, pass_: str) -> tuple[list[dict], float]:
    """The pass's cut as assemble lays it, without probing a file: [{"id", "trim_in",
    "used", "dissolve_in", "sound", "sound_start"}] in cut order (`sound`: the file its
    sound plays from, the take's or its cut entry's audio source, None for silence;
    `sound_start`: seconds into it where the clip starts) (orphans, shots left out and shots with no
    usable take skipped), and the cut's frame rate. A take's length is its sidecar's;
    a shot with a dialogue window keeps the window; a dissolve that doesn't fit beside
    its neighbours is left out, as assemble leaves it."""
    fps = E.pass_fps(root, pass_)
    try:
        shots = {s["id"]: s for d, i in J.episode_shots(root, pass_) for s in [d["shots"][i]]}
    except FileNotFoundError:
        shots = {}
    windows = E.dialogue_windows(root, pass_, fps)
    out = []
    for e in E.cut_entries(root, pass_):
        if e.orphan or e.out:
            continue
        chosen, _, ok = E.cut_take(root, e)
        if not ok:
            continue
        span = windows.get(e.shot) or E.take_span(root, e, fps) \
            or int((shots.get(e.shot) or {}).get("length") or 0)
        used = span - max(0, e.trim_in) - max(0, e.trim_out)
        if used < 1:
            continue
        d = e.dissolve if out and e.dissolve * 2 <= min(used, out[-1]["used"]) else 0
        if e.audio:
            sound = T.audio_source_file(root, e.audio, pass_)
            start = float(e.audio.get("start") or 0.0) - float(e.audio.get("offset") or 0.0)
        else:
            sound = PK.clip_audio(chosen.paths.mp4, chosen.paths.h3_wav if
                                  os.path.isfile(chosen.paths.h3_wav) else None)
            start = max(0, e.trim_in) / fps
        out.append({"id": e.shot, "trim_in": max(0, e.trim_in), "used": used, "dissolve_in": d,
                    "sound": sound, "sound_start": round(start, 4)})
    return out, fps


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def _arc_per_bar(points: list[tuple[float, float]], bars: int, bar: float, start: float) -> list[float]:
    """One energy per bar from (cue seconds, level) points: linear between them, held
    beyond; each bar's value at its middle."""
    pts = sorted(points)
    out = []
    for b in range(bars):
        t = start + (b + 0.5) * bar
        if t <= pts[0][0]:
            out.append(pts[0][1])
        elif t >= pts[-1][0]:
            out.append(pts[-1][1])
        else:
            for (t0, a), (t1, c) in zip(pts, pts[1:]):
                if t0 <= t <= t1:
                    out.append(a + (c - a) * (t - t0) / (t1 - t0) if t1 > t0 else c)
                    break
    return [round(x, 2) for x in out]


def _sections_from_hits(bars: int, hits: list[dict], preroll: float, bar: float) -> list[dict]:
    """Sections when the spec gives none: a boundary at each hit that arrives, drops or
    turns (on its bar), a build into an arrival and quiet after a drop."""
    cuts = []
    for h in hits:
        if h["kind"] in ("arrive", "drop", "turn"):
            b = int(round((h["t"] + preroll) / bar))
            if 0 < b < bars and b not in [c[0] for c in cuts]:
                cuts.append((b, h["kind"]))
    cuts.sort()
    edges = [0] + [c[0] for c in cuts] + [bars]
    kinds = [None] + [c[1] for c in cuts]
    out = []
    for i in range(len(edges) - 1):
        start_kind, end_kind = kinds[i], (kinds[i + 1] if i + 1 < len(kinds) else None)
        a, b = 2.0, 3.0
        if end_kind == "arrive":
            a, b = 2.0, 5.0
        if start_kind == "arrive":
            a, b = 5.0, 4.0
        if start_kind == "drop":
            a, b = 1.0, 1.5
        name = {"arrive": "climax", "drop": "drop", "turn": "turn"}.get(start_kind or "", "") \
            or ("build" if end_kind == "arrive" else "intro" if i == 0 else "section")
        out.append({"name": name, "bars": edges[i + 1] - edges[i], "from": a, "to": b})
    return out


def _fill_bars(sections: list[dict], bars: int) -> list[dict]:
    """The spec's sections fitted to the cue's bars: those without a count share what the
    others leave, the last one takes up any difference."""
    secs = [dict(s) for s in sections]
    fixed = sum(s["bars"] for s in secs if s.get("bars"))
    loose = [s for s in secs if not s.get("bars")]
    left = max(len(loose), bars - fixed)
    for i, s in enumerate(loose):
        s["bars"] = left // len(loose) + (1 if i < left % len(loose) else 0)
    diff = bars - sum(s["bars"] for s in secs)
    if secs and diff:
        secs[-1]["bars"] = max(1, secs[-1]["bars"] + diff)
    for s in secs:
        s.setdefault("from", 3.0)
        s.setdefault("to", s["from"])
    return secs


def script_notes(root: str, shots: list[str]) -> list[dict]:
    """The script's `music:` notes of these shots, in their order: [{"shot", "music"}]
    (none when the episode's story IR, shotlist/shots.json, can't be read)."""
    from seriesmith.core import ir
    try:
        with open(os.path.join(root, "shotlist", "shots.json"), encoding="utf-8") as fh:
            story = ir.Episode.loads(fh.read())
    except (OSError, ValueError, KeyError):
        return []
    by = {s.id: s.music for s in story.shots() if s.music}
    return [{"shot": sid, "music": " ".join(by[sid].split())} for sid in shots if sid in by]


def model_for(spec: dict, series: dict) -> str:
    """The cue's music target: its own, else its kind's in the series config's `sound`
    (`music_model` for score, `song_model` for a song), else the kind's default (Stable Audio
    3 for score; YuE2 for a song, the model here that sings lyrics)."""
    if spec.get("model"):
        return spec["model"]
    key, default = KIND_MODEL[spec.get("kind", "score")]
    return ((series.get("sound") or {}).get(key)) or default or TG.DEFAULT_MUSIC_TARGET


def item_take(item: dict | None, cid: str) -> int | None:
    """The take of cue `cid` a mix item plays (`sound/<cid>/tNN.wav`), None for anything else."""
    m = _TAKE_WAV.match((item or {}).get("path") or "")
    return int(m.group(2)) if m and m.group(1) == cid else None


def mix_take(root: str, pass_: str, cid: str) -> int | None:
    """The take cue `cid`'s item in the pass's mix plays (muted or not), None when it has none
    there (or the mix doesn't read)."""
    try:
        items = MX.check(MX.load(root).get(pass_)).get("items") or []
    except ValueError:
        return None
    return item_take(next((i for i in items if i.get("id") == cid), None), cid)


def theme_take(root: str, pass_: str | None, cid: str) -> tuple[int | None, str | None]:
    """The take of cue `cid` a theme that follows it is: (n, "mix") the take its item in the
    pass's mix plays; else (n, "best") its best finished take (ranked: the best measured,
    else the first finished); (None, None) when it has none finished."""
    n = mix_take(root, pass_, cid) if pass_ else None
    if n is not None:
        return n, "mix"
    done = [t for t in ranked(list_takes(root, cid)) if t.get("status") == "ok"]
    return (done[0]["take"], "best") if done else (None, None)


def series_theme(root: str, series: dict | None, name: str) -> tuple[dict | None, str | None]:
    """A series theme as a cue's theme resolves it: ({"root" (the episode it's in, or None for
    a file), "cue", "take" | "file" (an absolute path), "label"}, None), or (None, why not)."""
    themes = series_themes(series)
    if name in (themes.get("_errors") or {}):
        return None, themes["_errors"][name]
    t = themes.get(name)
    if t is None:
        return None, f"there's no theme {name} in the series config's sound.themes"
    if t.get("ep"):
        ep_root = os.path.join(os.path.dirname(os.path.normpath(root)), t["ep"])
        if os.path.normcase(os.path.normpath(ep_root)) == os.path.normcase(os.path.normpath(root)):
            ep_root = root
        if not os.path.isdir(ep_root):
            return None, f"the theme {name} is in {t['ep']}, which isn't beside this episode"
        return {"root": ep_root, "cue": t["cue"], "take": t["take"],
                "label": f"{name} ({t['ep']} {t['cue']} t{t['take']:02d})"}, None
    from seriesmith.core import paths as P
    home = P.series_home(root) or root
    return {"root": None, "file": os.path.normpath(os.path.join(home, *t["file"].split("/"))),
            "label": f"{name} ({t['file']})", "bpm": t.get("bpm"), "beats": t.get("beats")}, None


def theme_list(root: str, series: dict | None = None) -> list[dict]:
    """The series config's themes for the window to offer: [{"name", "label", "role", "words",
    "for", "error"}], by name (`error`: why one doesn't read, or isn't there to render from)."""
    series = series if series is not None else J.series_config(root)
    themes = series_themes(series)
    out = []
    for name in sorted(set(themes) - {"_errors"} | set(themes.get("_errors") or {})):
        t = themes.get(name) or {}
        found, why = series_theme(root, series, name)
        out.append({"name": name, "label": found["label"] if found else name, "role": t.get("role"),
                    "words": t.get("words"), "for": t.get("for"), "error": why})
    return out


def pin_series_theme(root: str, cid: str, n: int, name: str, role: str | None = None,
                     words: str | None = None, everywhere: bool = True, for_: list[str] | None = None) -> dict:
    """A finished take of cue `cid` made a series theme: `sound.themes.<name>` = {"ep" (this
    episode's folder), "cue", "take"} (and `role`, `words`, `for`: the cast ids it belongs to,
    a character's theme) written into the series config,
    this episode's and, with `everywhere`, every episode's beside it (each episode has its
    own: source.episodes_under), each saved as the editor saves it (a history copy, the
    file's format). Returns {"theme" (the entry), "written" (the episodes whose config was
    written, by folder name), "same" (those that had it already)}. CueError for a take that
    isn't finished or a name or role that isn't one."""
    import json
    from seriesmith import source as SRC                 # it imports edit: not at the top
    sc = next((t for t in list_takes(root, cid) if t["take"] == n), None)
    if sc is None or sc.get("status") != "ok":
        raise CueError(f"cue {cid} has no finished take {n} to make a theme of")
    entry = {"ep": os.path.basename(os.path.normpath(root)), "cue": cid, "take": n}
    if role:
        entry["role"] = role
    if words:
        entry["words"] = words
    if for_:
        entry["for"] = list(for_)
    entry = check_series_theme(name, entry)
    eps = [root]
    if everywhere:
        eps += [e for e in SRC.episodes_under(os.path.dirname(os.path.normpath(root)))
                if os.path.normcase(os.path.normpath(e)) != os.path.normcase(os.path.normpath(root))]
    written, same, seen = [], [], set()
    for ep in eps:
        try:
            src = SRC.read_source(ep, "series")
        except SRC.SourceError:
            continue
        if os.path.normcase(src.path) in seen:
            continue                                     # a shared series config: once
        seen.add(os.path.normcase(src.path))
        try:
            raw = json.loads(src.text)
        except ValueError:
            continue
        sound = raw.setdefault("sound", {})
        themes = sound.setdefault("themes", {})
        if themes.get(name) == entry:
            same.append(os.path.basename(ep))
            continue
        themes[name] = entry
        SRC.write_source(src, SRC.dump_series(raw, src.text))
        written.append(os.path.basename(ep))
    return {"theme": {"name": name, **entry}, "written": written, "same": same}


def theme_for(root: str, spec: dict, target, pass_: str | None = None,
              pin: tuple[int, str] | None = None, series: dict | None = None) -> dict | None:
    """How the cue's theme reaches its model (None without one): {"spec", "label", "use",
    "audio", "abc", "warning", "from", "strength", "grid"}. `use`: "plan" (YuE2 sings the
    theme take's own plan, `abc`: its melody), "transcribe" (YuE2 sings SheetSage2's
    transcription of `audio`), "timbre" (ACE-Step's timbre reference, `audio`), "audio" (Stable
    Audio 3 renders from `audio`, reshaped to the cue first: stage_theme, at `strength`), or
    None with `warning` saying why it is left out (the take or file isn't there, or the model
    takes no theme). A theme that follows another cue's pick ({"cue"} alone) is resolved here
    (theme_take, in `pass_`'s mix; `pin` (take, from) to use instead: a repaint's, the take its
    source was made with), `label` naming the take ("m01 t03") and `from` how it was found
    ("mix", "best"; None for a theme that names its take or file). A series theme ({"theme"})
    is found in the series config (`series`, else the episode's: series_theme), its take in its
    own episode. `grid` is a theme take's tempo ({"bpm", "downbeat", "beats"}: its cue's, as it
    was measured), None for a file."""
    th = spec.get("theme")
    if not th:
        return None
    out = {"spec": th, "label": theme_text(th), "use": None, "audio": None, "abc": None, "warning": None,
           "from": None, "strength": None, "grid": None}
    plan_file = None
    src_root = root
    if th.get("theme"):
        found, why = series_theme(root, series if series is not None else J.series_config(root), th["theme"])
        if found is None:
            out["warning"] = f"{why}: rendered without it"
            return out
        out["label"] = found["label"]
        if found["root"] is None:
            th = {"file": found["file"]}
            if found.get("bpm"):
                out["grid"] = {"bpm": float(found["bpm"]), "downbeat": 0.0, "beats": found.get("beats") or 4}
        else:
            src_root, th = found["root"], {"cue": found["cue"], "take": found["take"]}
    if th.get("cue") and not th.get("take"):
        n, how = pin if pin is not None else theme_take(root, pass_, th["cue"])
        if n is None:
            out["warning"] = f"the theme {th['cue']} has no finished take: rendered without it"
            return out
        th = {"cue": th["cue"], "take": n}
        out["label"], out["from"] = theme_text(th), how
    if th.get("cue"):
        sc = next((t for t in list_takes(src_root, th["cue"]) if t["take"] == th["take"]), None)
        wav = take_paths(src_root, th["cue"], th["take"])["wav"]
        if sc is None:
            out["warning"] = f"the theme {out['label']} isn't there (no such take): rendered without it"
        elif sc.get("status") != "ok" or not os.path.isfile(wav):
            out["warning"] = f"the theme {out['label']} isn't finished: rendered without it"
        else:
            out["audio"] = wav
            f = os.path.join(cue_dir(src_root, th["cue"]), f"t{th['take']:02d}.abc")
            plan_file = f if os.path.isfile(f) else None
            m, fit = sc.get("measured") or {}, (sc.get("plan") or {}).get("fit") or {}
            bpm = (sc.get("rendered_for") or {}).get("bpm") or fit.get("bpm")
            if bpm and m.get("downbeat") is not None:
                try:
                    beats = meter_beats(load_spec(src_root, th["cue"]))
                except (OSError, ValueError):
                    beats = 4
                out["grid"] = {"bpm": float(bpm), "downbeat": float(m["downbeat"]), "beats": beats}
    else:
        f = th["file"] if os.path.isabs(th["file"]) else os.path.normpath(os.path.join(root, *th["file"].split("/")))
        if os.path.isfile(f):
            out["audio"] = f
        else:
            out["warning"] = f"the theme file {th.get('file')} isn't there: rendered without it"
    if out["warning"]:
        return out
    how = target.capabilities().get("theme")
    if how == "melody" and plan_file:
        with open(plan_file, encoding="utf-8") as fh:
            out.update(use="plan", abc=ABC.melody(fh.read()))
    elif how == "melody":
        out["use"] = "transcribe"
    elif how == "timbre":
        out["use"] = "timbre"
    elif how == "audio":
        out.update(use="audio", strength=float((spec.get("theme") or {}).get("strength")
                                               or target.capabilities().get("theme_strength") or 0.86))
    else:
        out["warning"] = (f"{target.label} takes no theme: rendered without it (Stable Audio 3 renders "
                          f"from a theme's sound, ACE-Step hears it as its timbre, YuE2 sings its melody)")
    return out


def stage_theme(root: str, cid: str, p: dict) -> dict:
    """A plan's theme sound reshaped to the cue (Stable Audio 3 renders from it: the take
    keeps its timing): stretched from the theme's tempo to the tempo the cue is asked at, cut
    at its first bar line, its whole bars looped (an equal-power crossfade at each join) to
    the length asked, the last second faded. A file with no grid is looped as it is, its tempo
    heard when it can be. Written once per sound and shape as `sound/<cue>/theme_<hash>.wav`;
    the plan's theme gets `audio` (that file), `staged` ({"stretch", "bars", "seconds"}), and a
    warning when it was stretched more than THEME_STRETCH_WARN. Returns the plan."""
    import hashlib
    th = p.get("theme") or {}
    if th.get("use") != "audio" or not th.get("audio"):
        return p
    np = MX._np()
    src = th["audio"]
    ask_bpm, seconds = float(p["fit"]["ask_bpm"]), float(p["ask_seconds"])
    grid = th.get("grid")
    st = os.stat(src)
    key = f"{os.path.abspath(src)}|{st.st_mtime_ns}|{st.st_size}|{grid}|{ask_bpm}|{seconds}"
    dst = os.path.join(cue_dir(root, cid), f"theme_{hashlib.sha1(key.encode()).hexdigest()[:10]}.wav")
    buf = MX.decode(src)
    if grid is None and len(buf):
        # a file that doesn't say its tempo: what's heard (its octaves folded toward the cue's)
        # is trusted only near the cue's own; else it plays at its own tempo, looped whole
        env = B.onsets(buf)
        heard = B.tempo(env, asked=ask_bpm)
        if heard and abs(heard - ask_bpm) / ask_bpm <= STRETCH_MAX:
            _, down = B.grid(env, heard, buf, 4)
            grid = {"bpm": heard, "downbeat": down, "beats": 4}
        else:
            p.setdefault("warnings", []).append(
                "the theme file's tempo couldn't be told" + (f" (heard {heard:.0f} bpm)" if heard else "")
                + ": it plays at its own, looped whole; give it a bpm in the series config to fit it to the cue")
    factor = ask_bpm / grid["bpm"] if grid else 1.0
    if abs(factor - 1.0) > 1e-4:
        tmp = F.temp_beside(dst, ".wav")
        try:
            stretch_file(src, tmp, factor)
            buf = MX.decode(tmp)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    n_out = int(round(seconds * MX.RATE))
    if grid:
        bar = grid["beats"] * 60.0 / ask_bpm
        start = int(round(grid["downbeat"] / factor * MX.RATE))
        bars = max(1, int((len(buf) - start) / (bar * MX.RATE) + 1e-6))
        body = buf[start:start + int(round(bars * bar * MX.RATE))]
    else:
        bars, body = 0, buf
    if not len(body):
        th["warning"] = "the theme's sound is empty: rendered without it"
        th["use"] = None
        return p
    xf = int(THEME_XFADE * MX.RATE)
    out = body.copy()
    while len(out) < n_out + xf:
        if xf and len(out) > xf and len(body) > xf:
            a = np.cos(np.linspace(0, np.pi / 2, xf, dtype=np.float32))[:, None]
            b = np.sin(np.linspace(0, np.pi / 2, xf, dtype=np.float32))[:, None]
            out = np.concatenate([out[:-xf], out[-xf:] * a + body[:xf] * b, body[xf:]])
        else:
            out = np.concatenate([out, body])
    out = out[:n_out]
    fade = min(len(out), MX.RATE)
    out[len(out) - fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
    if not os.path.isfile(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        MX.write_wav(dst, out)
    th["audio"] = dst
    th["staged"] = {"stretch": round(factor, 4), "bars": bars, "seconds": round(len(out) / MX.RATE, 3)}
    if abs(factor - 1.0) > THEME_STRETCH_WARN:
        msg = (f"the theme is played {abs(factor - 1) * 100:.0f} % {'faster' if factor > 1 else 'slower'} "
               f"than it was made ({grid['bpm']:.0f} to {ask_bpm:.0f} bpm): it holds less the further it goes")
        p.setdefault("warnings", []).append(msg)
    return p


def theme_record(th: dict) -> dict:
    """A plan's theme as a take's sidecar keeps it: {"label" (the take or file it was: "m01
    t03"), "use"}, "from" ("mix", "best") when it followed another cue's pick, "strength" when
    the model rendered from its sound, and "staged" (stage_theme: how it was reshaped)."""
    return {"label": th["label"], "use": th["use"], **({"from": th["from"]} if th.get("from") else {}),
            **({"strength": th["strength"]} if th.get("strength") is not None else {}),
            **({"staged": th["staged"]} if th.get("staged") else {})}


def song_sections(info: dict, bpm: float, offset: float, bar: float) -> list[dict]:
    """A song plan's sections (core/abc.read) where a take at `bpm` puts them: {"name",
    "start" and "seconds" (in the take), "at" (seconds from the cue's in point: `offset` is
    where the in point falls in the take), "bars" and "beats" (the plan's), "cue_bars" (its
    length in the cue's bars)}."""
    return [{**t, "at": round(t["start"] - offset, 3), "cue_bars": round(t["seconds"] / bar, 2)}
            for t in ABC.times(info, bpm)]


def orchestrate(sections: list[dict], orchestra: dict) -> list[dict]:
    """Sections with the orchestration grid in their words: each family's strongest level
    over the section's bars, strongest first ("strings lead, solo horn present, timpani
    under"), after the section's own words. A family off throughout a section isn't named;
    a change inside a section can't be followed (a section is the finest the models follow),
    so the strongest wins."""
    out, b0 = [], 0
    for s in sections:
        n = s["bars"]
        who = []
        for fam, levels in orchestra.items():
            lv = max(levels[b0:b0 + n] or [0])
            if lv:
                who.append((lv, fam))
        who.sort(key=lambda x: -x[0])
        words = ", ".join(f"{fam} {ORCHESTRA_LEVELS[lv]}" for lv, fam in who)
        own = (s.get("words") or "").strip(" ,.")
        out.append({**s, "words": ", ".join(x for x in (own, words) if x)} if words else dict(s))
        b0 += n
    return out


def plan(root: str, pass_: str, spec: dict, series: dict | None = None) -> dict:
    """What a cue is asked, from its spec, the pass's cut and mix: {"spec", "target",
    "fps", "start_frame", "end_frame", "span", "hits": [{"id", "name", "kind", "must",
    "t", "at"}], "fit": {...}, "alternatives" (the best few tempos within FIT_SPREAD of
    the asked one, the fit's first unless the tempo is fixed: score.alternatives),
    "direction" (the series config's score direction, `sound.score`; "" when none), "bars", "bar", "preroll", "seconds", "ask_seconds", "sections",
    "arc", "cue" (what the prompt writer gets), "prompt"}. CueError when its anchors
    aren't in the cut."""
    series = series if series is not None else (J.series_config(root) or {})
    layout, fps = cut_layout(root, pass_)
    origins = MX.shot_origins(layout)
    a, b = MX.place(spec["in"], origins), MX.place(spec["out"], origins)
    if a is None or b is None:
        raise CueError(f"cue {spec['id']}: {spec['in']['shot'] if a is None else spec['out']['shot']} "
                       f"isn't in the {pass_} cut")
    if b <= a:
        raise CueError(f"cue {spec['id']}: its out is at or before its in")
    span = (b - a) / fps
    mix = MX.check(MX.load(root).get(pass_))
    want = set(spec["hits"]) if spec.get("hits") is not None else None
    hits = []
    for h in mix.get("hits") or []:
        f = MX.place(h["at"], origins)
        if f is None or (want is not None and h["id"] not in want):
            continue
        if want is None and not a <= f <= b:
            continue
        hit = {"id": h["id"], "name": h.get("name") or h["id"], "kind": h.get("kind", "accent"),
               "must": h.get("must", True), "t": round((f - a) / fps, 4), "at": h["at"]}
        # a drop on the cue's out point is its end: the music is cut there, whatever the bar,
        # so it isn't fitted to a bar line and there is nothing in the music to measure
        if hit["kind"] == "drop" and f >= b - 2:
            hit["ends"] = True
        hits.append(hit)
    meter = meter_beats(spec)
    target = TG.load_target(model_for(spec, series))
    theme = theme_for(root, spec, target, pass_, series=series)
    # a cue with a theme and no tempo of its own takes the theme's: a theme stretched to
    # another tempo holds it less ("A theme take under another length and tempo")
    asked = spec.get("bpm") or ((theme or {}).get("grid") or {}).get("bpm") or DEFAULT_BPM
    fitted = [h for h in hits if not h.get("ends")]
    to_fit = [(h["t"], h["must"], h["kind"] == "accent") for h in fitted]
    fit = SC.fit_tempo(to_fit, asked, fps, meter, spread=0.0 if spec.get("fixed_tempo") else FIT_SPREAD)
    # the best few tempos near the asked one, a fixed tempo's too (the spotting sheet offers them)
    alts = [{"bpm": x.bpm, "preroll": x.preroll, "worst_must": x.worst_must, "total": x.total}
            for x in SC.alternatives(to_fit, asked, fps, meter, spread=FIT_SPREAD, count=ALTERNATIVES)]
    # the fit's errors for every hit, in order: an end has none (None)
    errs = iter(fit.errors)
    fit_errors = [None if h.get("ends") else next(errs) for h in hits]
    bar = fit.bar
    preroll = fit.preroll
    tail = spec.get("tail", 2.0)
    bars = max(1, math.ceil((preroll + span + tail) / bar - 1e-6))
    seconds = round(bars * bar, 3)
    if spec.get("sections"):
        sections = _fill_bars(spec["sections"], bars)
    else:
        sections = _sections_from_hits(bars, hits, preroll, bar)
    if spec.get("orchestra"):
        sections = orchestrate(sections, spec["orchestra"])
    if spec.get("arc"):
        pts = [((MX.place(p["at"], origins) - a) / fps, p["level"]) for p in spec["arc"]
               if MX.place(p["at"], origins) is not None]
    else:
        pts, t = [], -preroll
        for s in sections:
            pts += [(t + 0.01, s["from"]), (t + s["bars"] * bar - 0.01, s["to"])]
            t += s["bars"] * bar
    arc = _arc_per_bar(pts, bars, bar, -preroll) if pts else [3.0] * bars
    if spec.get("arc"):
        # a drawn arc is the intent: each section's energies (and so its words) are the arc's
        # at its first and last bar, whatever the section says
        b0 = 0
        for sec in sections:
            sec["from"], sec["to"] = round(arc[b0] * 2) / 2, round(arc[b0 + sec["bars"] - 1] * 2) / 2
            b0 += sec["bars"]
    direction = ((series.get("sound") or {}).get("score") or "").strip()
    style = ", ".join(x for x in (direction.rstrip("."), spec.get("style", "")) if x)
    # the script's music: notes of the shots the cue plays over (each shot whose clip
    # overlaps its span), in cut order
    over = [x["id"] for x in layout
            if origins[x["id"]]["origin"] + x["trim_in"] < b
            and origins[x["id"]]["origin"] + x["trim_in"] + x["used"] > a]
    notes = script_notes(root, over)
    kind = spec.get("kind", "score")
    cue = {"kind": kind, "style": style or ("cinematic orchestral film score" if kind == "score" else "song"),
           "bpm": fit.ask_bpm,
           "meter": "{}/{}".format(*parse_meter(spec.get("meter", 4))), "key": spec.get("key", ""),
           "seconds": round(seconds * fit.stretch, 3),
           "sections": sections, "notes": [n["music"] for n in notes]}
    if theme and theme["use"]:
        cue["theme"] = theme["use"]
    brief = target.cue_prompt(cue)
    caps = target.capabilities()
    warnings = [theme["warning"]] if theme and theme["warning"] else []
    blocked = None
    if kind == "song" and caps.get("needs_lyrics") and not (brief.get("values") or {}).get("lyrics"):
        blocked = (f"{target.short or target.label} sings words: give the song's sections their lyrics "
                   f"(a section's Lyrics in the cue window)")
    song = None
    if theme and theme["use"] == "plan":
        unit = parse_meter(spec.get("meter", 4))[1]
        info = ABC.read(ABC.set_tempo(theme["abc"], fit.ask_bpm, f"1/{unit}"))
        song = {"source": "theme plan", "bars": info["bars"], "meter": info["meter"],
                "sections": song_sections(info, fit.bpm, preroll, bar)}
    out = {"spec": spec, "target": target.id, "fps": fps, "start_frame": a, "end_frame": b,
            "span": round(span, 3), "hits": hits, "notes": notes,
            "fit": {"bpm": fit.bpm, "ask_bpm": fit.ask_bpm, "stretch": fit.stretch,
                    "errors": fit_errors, "worst_must": fit.worst_must},
            "alternatives": alts,
            "direction": direction,
            "bars": bars, "bar": round(bar, 5), "preroll": preroll, "seconds": seconds,
            "ask_seconds": cue["seconds"], "sections": sections, "arc": arc, "cue": cue,
            "prompt": brief}
    if theme:
        out["theme"] = theme
    if warnings:
        out["warnings"] = warnings
    if blocked:
        out["blocked"] = blocked
    if song:
        out["song"] = song
    return out


# ---------------------------------------------------------------------------
# takes
# ---------------------------------------------------------------------------

def fingerprint(p: dict) -> dict:
    """What a take was rendered for, kept in its sidecar so a later cut can be told apart:
    the span in frames, each hit's place, the tempo and the bars, and the theme when it has
    one."""
    out = {"span_frames": p["end_frame"] - p["start_frame"], "fps": p["fps"],
           "hits": {h["id"]: h["t"] for h in p["hits"]}, "bpm": p["fit"]["bpm"],
           "bars": p["bars"]}
    if p.get("theme"):
        out["theme"] = p["theme"]["label"]
        if p["theme"].get("strength") is not None:
            out["theme_strength"] = p["theme"]["strength"]
    return out


def stale(sc: dict, p: dict) -> list[str]:
    """What has changed since a take was rendered (its sidecar's `rendered_for` against
    the plan now), in words; [] when nothing has, or when the take doesn't say. A shorter
    span is said too, though the take still ends on the out point with its fade."""
    was = sc.get("rendered_for")
    if not isinstance(was, dict):
        return []
    now = fingerprint(p)
    fps = now["fps"] or 24
    out = []
    d = now["span_frames"] - int(was.get("span_frames") or 0)
    if d > 1:
        out.append(f"the cue is {d / fps:.1f} s longer: the take runs out before its out point")
    elif d < -1:
        out.append(f"the cue is {-d / fps:.1f} s shorter: the take ends on its out point, faded")
    hits = was.get("hits") or {}
    for h in p["hits"]:
        if h["id"] not in hits:
            out.append(f"{h['name']} is a new hit")
        elif abs(h["t"] - hits[h["id"]]) * fps > 1:
            out.append(f"{h['name']} moved {(h['t'] - hits[h['id']]) * fps:+.0f} frames")
    for hid in hits:
        if hid not in now["hits"]:
            out.append(f"hit {hid} is gone")
    if abs(float(was.get("bpm") or 0) - now["bpm"]) > 0.05:
        out.append(f"the tempo is {now['bpm']:g}, not {float(was.get('bpm') or 0):g}")
    if (was.get("theme") == now.get("theme") and now.get("theme")
            and was.get("theme_strength") != now.get("theme_strength")):
        out.append(f"the theme's strength is {now.get('theme_strength')}, not {was.get('theme_strength')}")
    if was.get("theme") != now.get("theme"):
        if now.get("theme"):
            out.append(f"the theme is {now['theme']}" + (f", not {was['theme']}" if was.get("theme") else ""))
        else:
            out.append(f"the theme {was['theme']} is gone")
    return out


def take_paths(root: str, cid: str, n: int) -> dict:
    d = cue_dir(root, cid)
    return {"sidecar": os.path.join(d, f"t{n:02d}.json"), "wav": os.path.join(d, f"t{n:02d}.wav"),
            "rel": f"{SOUND_DIR}/{cid}/t{n:02d}.wav"}


def list_takes(root: str, cid: str) -> list[dict]:
    """Every take's sidecar (with its `take` number), by number."""
    d = cue_dir(root, cid)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = _TAKE.match(name)
        if m:
            sc = F.read_json_or(os.path.join(d, name), None)
            if isinstance(sc, dict):
                out.append({**sc, "take": int(m.group(1))})
    return out


def ranked(takes: list[dict]) -> list[dict]:
    """The finished takes best first (their measured score), then the rest. A take whose
    melody score says it lost its theme (`on_theme` false) goes after those that kept it:
    the score filters, the hits rank (docs/SOUND.md phase 8)."""
    done = [t for t in takes if t.get("status") == "ok" and (t.get("measured") or {}).get("score") is not None]
    rest = [t for t in takes if t not in done]
    return sorted(done, key=lambda t: ((t["measured"].get("on_theme") is False), t["measured"]["score"])) + rest


def reserve(root: str, cid: str, record: dict) -> int:
    """The next take number, its sidecar written `queued` with `record`."""
    os.makedirs(cue_dir(root, cid), exist_ok=True)
    n = max([t["take"] for t in list_takes(root, cid)] + [0]) + 1
    F.write_json(take_paths(root, cid, n)["sidecar"], {**record, "status": "queued", "created": T.now()})
    return n


def update(root: str, cid: str, n: int, **fields) -> dict:
    path = take_paths(root, cid, n)["sidecar"]
    sc = F.read_json_or(path, {}) or {}
    sc.update(fields)
    F.write_json(path, sc)
    return sc


def graph(target, p: dict, seed: int, pass_: str) -> dict:
    """The API graph for one take: the target's workflow, its preset's model files,
    steps, cfg, sampler and negative, the brief and the seed, pruned to the saver."""
    import copy
    base, _ = J.target_workflow(target, None, None, required=True, prefer_repo=True)
    g = copy.deepcopy(base)
    b = target.binding
    preset = target.presets.get(pass_) or target.presets.get("final")
    vals = {}
    if preset is not None:
        if preset.model:
            vals["model"] = preset.model
        if preset.steps:
            vals["steps"] = preset.steps
        vals.update({k: v for k, v in preset.extra.items() if not k.startswith("_")})
    brief = p["prompt"]
    vals["prompt"] = brief["prompt"]
    if brief.get("negative") is not None:
        vals["negative"] = brief["negative"]
    vals.update(brief.get("values") or {})
    vals["seed"] = seed
    for name, v in vals.items():
        if v is not None and b.specs(name):
            J.patch_param(g, b, name, v)
    if target.supports("cue_graph"):
        # a theme's graph surgery (YuE2: the planner replaced; ACE-Step: the timbre reference)
        th = p.get("theme") or {}
        audio = None
        if th.get("audio") and th.get("use") in ("transcribe", "timbre", "audio"):
            from seriesmith.backends import File
            audio = File(th["audio"])
        target.module.cue_graph(target, g, p, vals, audio)
    saver = J.node_of(g, b.saver_class or "SaveAudio")
    if b.prune:
        # the saver and what it needs, and a song's plan saved beside it (SaveText)
        need: set = set()
        for k in [saver] + [k for k, v in g.items() if v["class_type"] == "SaveText"]:
            part = dict(g)
            J.prune(part, k)
            need |= set(part)
        for k in [k for k in g if k not in need]:
            del g[k]
    return g


def plan_outputs(g: dict) -> dict:
    """{node id: "written" | "sung" | "melody" | "theme_melody"} for the graph's SaveText
    nodes: a song's plan as its model wrote it, and as it was sung (its tempo set); the take's
    melody and its theme's, as SheetSage2 transcribed them (the melody score). The queue's
    job reads them when the take comes back."""
    out = {}
    for k, v in g.items():
        if v["class_type"] == "SaveText":
            prefix = str(v["inputs"].get("filename_prefix", ""))
            out[k] = next((role for end, role in (("cue_plan", "sung"), ("theme_melody", "theme_melody"),
                                                  ("cue_melody", "melody")) if prefix.endswith(end)), "written")
    return out


def seeds(root: str, spec: dict, count: int, already: int) -> list[int]:
    """`count` seeds for new takes: from the spec's seed, else the episode and cue ids,
    each the next after the takes already made (a re-render gets new ones)."""
    base = spec.get("seed")
    ep = os.path.basename(os.path.normpath(root))
    return [(base + already + k) if base is not None else stable_seed(ep, "cue", spec["id"], str(already + k))
            for k in range(count)]


def takes_wanted(target, pass_: str, spec: dict) -> int:
    preset = target.presets.get(pass_) or target.presets.get("final")
    n = spec.get("takes") or (preset.extra.get("takes") if preset is not None else None) or 8
    return max(1, min(TAKES_MAX, int(n)))


# ---------------------------------------------------------------------------
# a take measured
# ---------------------------------------------------------------------------

def stretch_file(src: str, dst: str, factor: float) -> None:
    """`src` played `factor` times faster (atempo: the pitch kept) as a 24-bit wav."""
    af = [] if abs(factor - 1.0) < 1e-4 else ["-af", f"atempo={factor:.6f}"]
    tmp = F.temp_beside(dst, ".wav")
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, *af, "-ar", str(MX.RATE),
                        "-ac", "2", "-c:a", "pcm_s24le", tmp], capture_output=True, timeout=600)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("stretching the take: " + r.stderr.decode("utf-8", "replace")[-300:])
    F.replace(tmp, dst)


def measure(raw_file: str, wav: str, p: dict) -> dict:
    """A take that came back (`raw_file`) stretched to the cue's tempo into `wav`, and
    measured: {"bpm_heard", "stretch", "downbeat", "offset", "hit_errors", "worst_must",
    "levels", "shape_error", "score", "tempo_heard"}. `offset` is where in the wav the cue's
    in point falls (its first bar line, plus the pre-roll)."""
    fit, bar_s, fps = p["fit"], p["bar"], p["fps"]
    buf = MX.decode(raw_file)
    env = B.onsets(buf)
    heard = B.tempo(env, asked=fit["ask_bpm"])
    # a tempo it can't tell (soft music) or far off: the plan's stretch
    believed = heard is not None and abs(heard - fit["ask_bpm"]) / fit["ask_bpm"] <= TEMPO_TRUST
    factor = (fit["bpm"] / heard) if believed else fit["stretch"]
    factor = max(1 - STRETCH_MAX, min(1 + STRETCH_MAX, factor))
    if p.get("at_tempo"):
        factor = 1.0                     # already at the cue's tempo (a comp of two takes)
    elif p.get("factor"):
        factor = p["factor"]             # a repaint: stretched as the take it was made from
    stretch_file(raw_file, wav, factor)
    buf = MX.decode(wav)
    env = B.onsets(buf)
    meter = meter_beats(p["spec"])
    first, down = B.grid(env, fit["bpm"], buf, meter)
    if p.get("downbeat") is not None:
        down = p["downbeat"]             # a repaint: the take's own grid (its bars kept)
    # the first bar line the music has: a downbeat a bar or more in is the same grid earlier
    down = down - bar_s * math.floor(down / bar_s + 1e-9) if down >= bar_s else down
    offset = down + p["preroll"]
    # the grid puts every hit on its bar line (the fit's doing); what a take adds is whether
    # the music does something there: the strongest onset within half a beat of the hit,
    # its distance in frames (None: nothing there, counted as half a beat off)
    beat_s = bar_s / meter
    errs = []
    for h in p["hits"]:
        if h.get("ends"):
            errs.append(None)                  # the cue's end: cut there, nothing to hear
            continue
        f = offset + h["t"]
        at, strength = B.onset_near(env, f, beat_s / 2)
        errs.append(round((at - f) * fps, 2) if at is not None and strength >= ONSET_MIN else None)
    musts = [abs(e) if e is not None else beat_s / 2 * fps
             for e, h in zip(errs, p["hits"]) if h["must"] and not h.get("ends")]
    worst = max(musts) if musts else 0.0
    levels = B.bar_levels(buf, fit["bpm"], down, meter, p["bars"])
    shape = B.shape_error(levels, p["arc"])
    score = round(worst / max(1.0, fps / 8) + (shape if shape is not None else 0.5), 4)
    return {"bpm_heard": round(heard, 2) if heard else None, "tempo_heard": believed,
            "stretch": round(factor, 5), "downbeat": round(down, 4), "offset": round(offset, 4),
            "hit_errors": errs, "worst_must": round(worst, 2), "levels": levels,
            "shape_error": shape, "score": score}


def remeasure(root: str, cid: str, n: int, p: dict) -> dict:
    """A finished take measured again against the plan `p` (the cut or the cue changed, or
    the measuring did): stretched again from its raw file to the plan's tempo, its sidecar's
    `measured` and `rendered_for` replaced, without rendering it again. A take the plan's
    tempo is more than STRETCH_MAX from (another bpm asked) can't be: it stays as it was."""
    sc = next((t for t in list_takes(root, cid) if t["take"] == n), None)
    if sc is None or sc.get("status") != "ok" or not sc.get("raw"):
        raise CueError(f"cue {cid} has no finished take {n} to measure again")
    asked = ((sc.get("plan") or {}).get("fit") or {}).get("ask_bpm") or p["fit"]["ask_bpm"]
    if abs(asked - p["fit"]["bpm"]) / p["fit"]["bpm"] > STRETCH_MAX:
        raise CueError(f"cue {cid} t{n:02d} was played at {asked} bpm, too far from {p['fit']['bpm']}")
    raw = os.path.join(root, *sc["raw"].split("/"))
    q = dict(p, fit=dict(p["fit"], ask_bpm=asked, stretch=round(p["fit"]["bpm"] / asked, 5)))
    m = measure(raw, take_paths(root, cid, n)["wav"], q)
    return update(root, cid, n, measured=m, rendered_for=fingerprint(p), remeasured=T.now())


def splice(buf, other, s1: int, e1: int, shift: int = 0, xfade: float = COMP_XFADE):
    """`buf` with its samples [s1, e1) from `other` (whose sample i + shift is buf's i), an
    equal-power crossfade of `xfade` seconds centred on each splice. A crossfade that would
    run off either buffer is left out (the splice is cut there)."""
    np = MX._np()
    x = int(xfade * MX.RATE)
    out = buf.copy()
    out[s1:e1] = other[s1 + shift:e1 + shift]
    up = np.sin(np.linspace(0, np.pi / 2, x, dtype=np.float32))[:, None]

    def blend(at: int, into_other: bool) -> None:
        """x samples centred on `at`: one take fading out as the other fades in."""
        lo = at - x // 2
        mine, theirs = buf[lo:lo + x], other[lo + shift:lo + shift + x]
        if lo >= 0 and lo + shift >= 0 and len(mine) == x and len(theirs) == x:
            out[lo:lo + x] = mine * up[::-1] + theirs * up if into_other else theirs * up[::-1] + mine * up
    blend(s1, True)
    blend(e1, False)
    return out


def comp(root: str, pass_: str, cid: str, base: int, src: int, bars: tuple[int, int]) -> dict:
    """A new take: take `base` with bars [a, b) (the cue's bars, 0 the pre-roll's first)
    from take `src`, spliced on bar lines where each take's measured downbeat puts them (both
    are at the cue's tempo), with COMP_XFADE equal-power crossfades; kept, measured and ranked
    like any take, its sidecar saying what it was made of. CueError when either take isn't
    finished, or the bars aren't inside the cue."""
    spec = load_spec(root, cid)
    p = plan(root, pass_, spec)
    takes = {t["take"]: t for t in list_takes(root, cid)}
    for n in (base, src):
        if (takes.get(n) or {}).get("status") != "ok":
            raise CueError(f"cue {cid} has no finished take {n}")
    a, b = bars
    if not 0 <= a < b <= p["bars"]:
        raise CueError(f"bars {a}-{b} aren't inside cue {cid}'s {p['bars']}")
    bar = p["bar"]

    def load(n):
        t = takes[n]
        return MX.decode(take_paths(root, cid, n)["wav"]), t["measured"]["downbeat"]
    buf, d1 = load(base)
    other, d2 = load(src)
    # where `other` lines up with `buf`: its sample i + shift is buf's sample i
    shift = int(round((d2 - d1) * MX.RATE))
    s1, e1 = int((d1 + a * bar) * MX.RATE), int((d1 + b * bar) * MX.RATE)
    e1 = min(e1, len(buf), len(other) - shift)
    x = int(COMP_XFADE * MX.RATE)
    if s1 - x < 0 or s1 + shift - x < 0 or e1 - s1 < 2 * x:
        raise CueError(f"take {src} doesn't reach bars {a}-{b} of take {base}")
    out = splice(buf, other, s1, e1, shift)
    n = reserve(root, cid, {"pass": pass_, "target": takes[base].get("target"), "seed": None,
                            "comp": {"base": base, "from": src, "bars": [a, b]},
                            "prompt": takes[base].get("prompt"), "rendered_for": fingerprint(p),
                            "plan": {"fit": dict(p["fit"], ask_bpm=p["fit"]["bpm"], stretch=1.0)}})
    raw = os.path.join(cue_dir(root, cid), f"t{n:02d}_raw.wav")
    MX.write_wav(raw, out)
    q = dict(p, at_tempo=True, fit=dict(p["fit"], ask_bpm=p["fit"]["bpm"], stretch=1.0))
    m = measure(raw, take_paths(root, cid, n)["wav"], q)
    return update(root, cid, n, status="ok", finished=T.now(), file=take_paths(root, cid, n)["rel"],
                  raw=os.path.relpath(raw, root).replace(os.sep, "/"), measured=m)



# ---------------------------------------------------------------------------
# bars of a take made again (docs/SOUND.md "Measured: repaint")
# ---------------------------------------------------------------------------

REPAINT_NODE = "SeriesmithAudioSpanMask"     # comfy_nodes/audio.py: the span's noise mask


def can_repaint(target) -> bool:
    """Whether the model makes bars of a take again (target.json capabilities.repaint)."""
    return bool(target.capabilities().get("repaint"))


def codes_seed(takes: dict, n: int) -> int | None:
    """The seed take `n`'s music was written from: its own, a repaint's codes, or (a comp)
    its base's. ACE-Step's language model writes the same codes from the same seed, so a
    repaint at that seed plays the same music again on the take's grid."""
    seen = set()
    while n in takes and n not in seen:
        seen.add(n)
        t = takes[n]
        if t.get("repaint"):
            return t["repaint"].get("codes")
        if t.get("seed") is not None:
            return t["seed"]
        n = (t.get("comp") or {}).get("base")
    return None


def repaint_span(sc: dict, bar: float, bars: tuple[int, int], cue_bars: int,
                 raw_seconds: float) -> tuple[float, float]:
    """The cue's bars [a, b) of take `sc` in seconds of its raw file (as the model played
    it, before the stretch): its measured downbeat and the cue's bar, times its stretch.
    The cue's last bar runs to the end of the file (its ending made again too)."""
    m = sc["measured"]
    f = m.get("stretch") or 1.0
    a, b = bars
    start = (m["downbeat"] + a * bar) * f
    end = raw_seconds if b >= cue_bars else min(raw_seconds, (m["downbeat"] + b * bar) * f)
    return round(start, 4), round(end, 4)


def repaint_graph(g: dict, raw: str, seconds: float, span: tuple[float, float], seed: int) -> dict:
    """A take's graph `g` made to repaint `span` (seconds) of `raw`, its own audio: the
    sampler's empty latent replaced by `raw` encoded (VAEEncodeAudio, the decode's VAE)
    under a noise mask over the span (SeriesmithAudioSpanMask), sampled from `seed`."""
    from seriesmith.backends import File
    ks = [k for k, v in g.items() if v["class_type"] == "KSampler"]
    dec = [k for k, v in g.items() if v["class_type"] == "VAEDecodeAudio"]
    if len(ks) != 1 or len(dec) != 1:
        raise CueError("a repaint needs a graph with one KSampler and one VAEDecodeAudio")
    k = g[ks[0]]["inputs"]
    empty = k["latent_image"][0] if isinstance(k.get("latent_image"), list) else None
    g["rp_load"] = {"class_type": "LoadAudio", "inputs": {"audio": File(raw)}, "_meta": {"title": "The take"}}
    g["rp_encode"] = {"class_type": "VAEEncodeAudio",
                      "inputs": {"audio": ["rp_load", 0], "vae": list(g[dec[0]]["inputs"]["vae"])},
                      "_meta": {"title": "The take encoded"}}
    g["rp_mask"] = {"class_type": REPAINT_NODE,
                    "inputs": {"samples": ["rp_encode", 0], "seconds": round(seconds, 4),
                               "start": span[0], "end": span[1], "feather": 0.0},
                    "_meta": {"title": "The bars made again"}}
    k["latent_image"] = ["rp_mask", 0]
    k["seed"] = seed
    k["denoise"] = 1.0
    if empty and not any(isinstance(v, list) and len(v) == 2 and v[0] == empty
                         for node in g.values() for v in node["inputs"].values()):
        del g[empty]
    return g


def repaint(root: str, pass_: str, cid: str, n: int, bars: tuple[int, int],
            seed: int | None = None, fresh: bool = False) -> tuple[dict, dict, int]:
    """Bars [a, b) of take `n` (the cue's bars, 0 the pre-roll's first) to be made again:
    the take's own graph (its model, pass, prompt and theme), its raw file encoded and
    masked over those bars, sampled from `seed` (else the next of the cue's seeds), the
    text encoder at the seed the take's music was written from (codes_seed: the same
    music played again on the take's grid) or, `fresh`, at `seed` too (new music there,
    the beat checked when it comes back). A new take is reserved, its sidecar saying
    `repaint`: {"from", "bars", "codes", "fresh", "span" (seconds of the raw file)}.
    Returns (the graph, the plan to finish it with, its number); the job's audio goes to
    finish_take, which splices the take's own audio back outside the span. CueError when
    the take isn't finished, its model can't repaint, or the bars aren't inside the cue.
    `pass_` is used only when the take records none."""
    spec = load_spec(root, cid)
    takes = {t["take"]: t for t in list_takes(root, cid)}
    sc = takes.get(n)
    if (sc or {}).get("status") != "ok" or not sc.get("raw") or not sc.get("measured"):
        raise CueError(f"cue {cid} has no finished take {n}")
    try:
        target = TG.load_target(sc.get("target") or "")
    except Exception:                                    # noqa: BLE001  a model gone
        raise CueError(f"t{n:02d}'s model {sc.get('target')!r} isn't here")
    if not can_repaint(target):
        raise CueError(f"{target.label} can't make bars of a take again (docs/SOUND.md "
                       f"'Measured: repaint'): comp them from another take instead")
    take_pass = sc.get("pass") or pass_
    p = plan(root, take_pass, spec)
    a, b = bars
    if not 0 <= a < b <= p["bars"]:
        raise CueError(f"bars {a}-{b} aren't inside cue {cid}'s {p['bars']}")
    raw = os.path.join(root, *sc["raw"].split("/"))
    if not os.path.isfile(raw):
        raise CueError(f"cue {cid} t{n:02d}'s file as it came ({sc['raw']}) isn't there")
    seconds = len(MX.decode(raw)) / MX.RATE
    span = repaint_span(sc, p["bar"], bars, p["bars"], seconds)
    if span[1] - span[0] < 0.25:
        raise CueError(f"bars {a}-{b} are past the end of t{n:02d}")
    codes = codes_seed(takes, n)
    if seed is None:
        seed = seeds(root, spec, 1, len(takes))[0]
    if fresh or codes is None:
        codes = seed
    # the take's theme, when the cue still has it (ACE-Step: its timbre reference); a theme
    # that follows another cue's pick is the take this one was made with, whatever is picked now
    theme = None
    if sc.get("theme"):
        own = spec.get("theme") or {}
        follows = own.get("cue") if not own.get("take") else None
        m = re.fullmatch(rf"{re.escape(follows)} t(\d{{2,3}})", sc["theme"].get("label") or "") if follows else None
        pin = (int(m.group(1)), sc["theme"].get("from") or "mix") if m else None
        th = theme_for(root, spec, target, take_pass, pin)
        if not th or th.get("label") != sc["theme"].get("label") or not th.get("audio"):
            raise CueError(f"t{n:02d} was made with the theme {sc['theme'].get('label')}, which the cue "
                           f"no longer has: render the cue again instead")
        theme = th
    g = repaint_graph(graph(target, {"prompt": sc["prompt"], "theme": theme}, codes, take_pass),
                      raw, seconds, span, seed)
    fit = (sc.get("plan") or {}).get("fit") or p["fit"]
    n2 = reserve(root, cid, {"pass": take_pass, "target": target.id, "seed": seed,
                             "repaint": {"from": n, "bars": [a, b], "codes": codes, "fresh": bool(fresh),
                                         "span": list(span)},
                             "prompt": sc["prompt"], "rendered_for": sc.get("rendered_for") or fingerprint(p),
                             "plan": {**(sc.get("plan") or {}), "fit": fit},
                             **({"theme": sc["theme"]} if sc.get("theme") else {})})
    # measured as the take was: stretched by its factor, on its grid, so the kept bars are
    # its own where they were
    stretch = sc["measured"].get("stretch") or 1.0
    finish = dict(p, fit=dict(p["fit"], ask_bpm=fit.get("ask_bpm", p["fit"]["ask_bpm"])), factor=stretch,
                  downbeat=sc["measured"]["downbeat"],
                  repaint={"raw": raw, "span": list(span), "downbeat": sc["measured"]["downbeat"],
                           "stretch": stretch})
    return g, finish, n2


def beats_held(orig, new, span, first: float, beat: float) -> dict:
    """How bars made again sit on the take's beat: at each of its beats inside `span`
    (seconds of the raw file; `first` a beat of its grid, `beat` its length there), the
    strongest onset within a quarter beat, in the take and in the new audio. {"beats",
    "on" (the new audio's onsets within 40 ms of a beat), "on_before" (the take's),
    "median_ms" (the new audio's median distance)}. A soft span (few onsets) reads low in
    both; it's the two against each other that tells."""
    np = MX._np()
    e_old, e_new = B.onsets(orig), B.onsets(new)
    k = math.ceil((span[0] - first) / beat - 1e-9)
    on = on_before = count = 0
    dist = []
    t = first + k * beat
    while t < span[1] - 0.05:
        count += 1
        at, strength = B.onset_near(e_old, t, beat / 4)
        if at is not None and strength >= 0.1 and abs(at - t) <= 0.04:
            on_before += 1
        at, strength = B.onset_near(e_new, t, beat / 4)
        if at is not None and strength >= 0.1:
            dist.append(abs(at - t) * 1000)
            if abs(at - t) <= 0.04:
                on += 1
        t += beat
    return {"beats": count, "on": on, "on_before": on_before,
            "median_ms": round(float(np.median(dist)), 1) if dist else None}


def finish_take(root: str, cid: str, n: int, raw_path: str, p: dict, plans: dict | None = None) -> dict:
    """A take's file is back: kept as tNN_raw, stretched and measured into tNN.wav, its
    sidecar closed. A song's plan (`plans`: {"written", "sung"}, the ABC the graph saved) is
    kept as tNN.abc (as sung) and read into the sidecar's `song` (song_record)."""
    paths = take_paths(root, cid, n)
    extra = {}
    rp = p.get("repaint")
    if rp:
        # bars made again: the take's own audio back outside them (the VAE's round trip
        # changes them a little), spliced at the bar lines as a comp is
        np = MX._np()
        orig, new = MX.decode(rp["raw"]), MX.decode(raw_path)
        if len(new) < len(orig):
            new = np.concatenate([new, orig[len(new):]])
        s1, e1 = int(rp["span"][0] * MX.RATE), min(len(orig), int(rp["span"][1] * MX.RATE))
        out = splice(orig, new[:len(orig)], s1, e1)
        keep = os.path.join(cue_dir(root, cid), f"t{n:02d}_raw.wav")
        MX.write_wav(keep, out)
        os.remove(raw_path)
        f = rp["stretch"]
        extra["repaint_check"] = beats_held(orig, out, rp["span"], rp["downbeat"] * f,
                                            60.0 / p["fit"]["bpm"] * f)
    else:
        keep = os.path.join(cue_dir(root, cid), f"t{n:02d}_raw{os.path.splitext(raw_path)[1] or '.flac'}")
        F.replace(raw_path, keep)
    m = measure(keep, paths["wav"], p)
    plans = plans or {}
    if plans.get("melody") and plans.get("theme_melody"):
        # the theme kept: SheetSage2's transcriptions of the take and of the theme as staged
        score = ABC.melody_match(plans["theme_melody"], plans["melody"])
        if score is not None:
            m["melody"] = score
            m["on_theme"] = score >= THEME_FLOOR
        F.write_text(os.path.join(cue_dir(root, cid), f"t{n:02d}.melody.abc"), plans["melody"])
    if plans.get("sung"):
        abc_path = os.path.join(cue_dir(root, cid), f"t{n:02d}.abc")
        F.write_text(abc_path, plans["sung"])
        th = p.get("theme") or {}
        written = plans.get("written") or (th.get("abc") if th.get("use") == "plan" else None)
        extra["song"] = song_record(plans["sung"], written, keep, m, p,
                                    os.path.relpath(abc_path, root).replace(os.sep, "/"))
    return update(root, cid, n, status="ok", finished=T.now(), file=paths["rel"],
                  raw=os.path.relpath(keep, root).replace(os.sep, "/"), measured=m, **extra)


def song_record(sung: str, written: str | None, raw: str, m: dict, p: dict, rel: str) -> dict:
    """What a song take's plan says against what came back: {"file" (tNN.abc), "source"
    ("planned", "theme plan", "theme transcribed"), "tempo_written" (the plan's own Q:,
    before it was set), "tempo" (as sung), "meter", "key", "bars", "plan_seconds" (its beats
    at the tempo asked), "raw_seconds" (the take as it came), "short" (how much shorter it
    came than its plan), "first_note" (the plan's first sung note, seconds into the take as
    stretched), "sections" (song_sections: at the cue's tempo, against its in point)}."""
    info = ABC.read(sung)
    before = ABC.read(written) if written else None
    use = (p.get("theme") or {}).get("use")
    try:
        raw_s = round(len(MX.decode(raw)) / MX.RATE, 3)
    except Exception:                                      # noqa: BLE001  recorded without it
        raw_s = None
    plan_s = round(info["beats"] * 60.0 / p["fit"]["ask_bpm"], 3)
    bpm = p["fit"]["bpm"]
    return {"file": rel,
            "source": {"plan": "theme plan", "transcribe": "theme transcribed"}.get(use, "planned"),
            "tempo_written": before["tempo"] if before else None, "tempo": info["tempo"],
            "meter": info["meter"], "key": info["key"], "bars": info["bars"],
            "plan_seconds": plan_s, "raw_seconds": raw_s,
            "short": round(plan_s - raw_s, 3) if raw_s is not None else None,
            "first_note": round(info["first_note"] * 60.0 / bpm, 3) if info["first_note"] is not None else None,
            "sections": song_sections(info, bpm, m["offset"], p["bar"])}


# ---------------------------------------------------------------------------
# beats to cut to (docs/SOUND.md phase 5)
# ---------------------------------------------------------------------------

_TAKE_WAV = re.compile(rf"^{SOUND_DIR}/([A-Za-z0-9_-]{{1,40}})/t(\d{{2,3}})\.wav$")


def take_grid(root: str, rel: str) -> dict | None:
    """The beat grid of a cue's take from its sidecar, when `rel` (relative to the episode)
    is one (`sound/<cue>/tNN.wav`, finished and measured): the take is stretched to the
    cue's tempo, so its beats are every 60 / bpm seconds through its measured downbeat
    (the first bar line). {"bpm", "first", "downbeat", "beats_per_bar", "seconds" (None:
    not read), "steady": True, "source": "cue"}; None for anything else."""
    m = _TAKE_WAV.match(rel or "")
    if not m:
        return None
    sc = F.read_json_or(os.path.join(cue_dir(root, m.group(1)), f"t{int(m.group(2)):02d}.json"), None, dict)
    meas = (sc or {}).get("measured") or {}
    bpm = (((sc or {}).get("plan") or {}).get("fit") or {}).get("bpm")
    if sc is None or sc.get("status") != "ok" or meas.get("downbeat") is None or not bpm:
        return None
    try:
        per = meter_beats(load_spec(root, m.group(1)))
    except (OSError, CueError, ValueError):
        per = 4
    beat = 60.0 / float(bpm)
    down = float(meas["downbeat"])
    first = down - beat * math.floor(down / beat + 1e-9)
    return {"bpm": round(float(bpm), 4), "first": round(first, 4), "downbeat": round(down, 4),
            "beats_per_bar": per, "seconds": None, "steady": True, "source": "cue"}


def beat_grid(root: str, full: str, rel: str | None = None) -> dict | None:
    """A sound file's beat grid to cut to: a cue take's from its sidecar (take_grid), any
    other file's measured once and kept beside it (beats.file_grid, `"source": "measured"`).
    None when it has none."""
    g = take_grid(root, rel) if rel else None
    if g is not None:
        return g
    g = B.file_grid(full)
    return {**g, "source": "measured"} if g else None


# ---------------------------------------------------------------------------
# into the mix
# ---------------------------------------------------------------------------

def fit_gain(levels: list[float], arc: list[float], bound: float = GAIN_FIT_DB) -> list[float]:
    """dB per bar that move a take's level toward the arc: the arc mapped onto the take's
    own loudness range (its mean and spread), each bar's difference, at most `bound` either
    way, half a dB steps. A silent bar (or a flat arc) gets 0."""
    heard = [x for x in levels if x > -60]
    if len(heard) < 2 or max(arc) - min(arc) < 1e-6:
        return [0.0] * len(levels)
    mean = sum(heard) / len(heard)
    spread = max(max(heard) - min(heard), 6.0)
    amean = sum(arc) / len(arc)
    k = spread / (max(arc) - min(arc))
    out = []
    for lv, a in zip(levels, arc):
        if lv <= -60:
            out.append(0.0)
            continue
        want = mean + (a - amean) * k
        out.append(round(max(-bound, min(bound, want - lv)) * 2) / 2)
    return out


def place(root: str, pass_: str, cid: str, n: int, gain: bool = True) -> dict:
    """Take `n` as the cue's item on the music track of the pass's mix: anchored at the
    cue's in point, from its offset, to the out point with a one-bar fade out, and (`gain`)
    a breakpoint at each bar fitting its level to the arc. Returns the mix as written."""
    spec = load_spec(root, cid)
    sc = next((t for t in list_takes(root, cid) if t["take"] == n), None)
    if sc is None or sc.get("status") != "ok":
        raise CueError(f"cue {cid} has no finished take {n}")
    p = plan(root, pass_, spec)
    m = sc["measured"]
    layout, fps = cut_layout(root, pass_)
    origins = MX.shot_origins(layout)
    mix = MX.check(MX.load(root).get(pass_))
    # the track its item is on (moved to a music track of the mix's own), else the music one
    was = next((i for i in mix.get("items") or [] if i["id"] == cid), None)
    track = was["track"] if was else MX.first_of(mix, "music")
    if track is None:
        raise CueError("the mix has no music track to put the cue on: add one")
    item = {"id": cid, "track": track, "path": take_paths(root, cid, n)["rel"],
            "in": spec["in"], "out": spec["out"], "offset": max(0.0, round(m["offset"], 3)),
            "fade_out": max(1, round(p["bar"] * fps)), "label": spec.get("label") or cid}
    if gain:
        pts = []
        for b, db in enumerate(fit_gain(m["levels"], p["arc"])):
            # the bar's start, from the cue's in point (the pre-roll is before it)
            t = -p["preroll"] + b * p["bar"]
            if t < 0:
                continue
            at = MX.anchor_at(p["start_frame"] + round(t * fps), origins)
            if at is not None:
                pts.append({"at": at, "db": db})
        if any(x["db"] for x in pts):
            item["points"] = pts
    items = [i for i in mix.get("items") or [] if i["id"] != cid] + [item]
    mix["items"] = items
    out = MX.write(root, pass_, mix)
    update(root, cid, n, placed=pass_)
    return out
