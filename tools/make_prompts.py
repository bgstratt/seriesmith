#!/usr/bin/env python3
"""
make_prompts.py — regenerate prompts/ and the script-writing skill from docs/AUTHORING.md.

The authoring guide is the single source. This wraps it in the packaging each
assistant expects, so the copies cannot drift from the document:

    prompts/SKILL.md                         the skill's core (Claude Code / Claude.ai; what
                                             `seriesmith mcp` serves as the script format)
    prompts/references/*.md                  the parts of the guide read only when needed
                                             (REFS), and the two bundled docs: `seriesmith
                                             mcp` serves each as a resource
    prompts/seriesmith-script.instructions.md
                                             Cursor, Copilot, generic system prompt: the
                                             whole guide in one file, for a client with no
                                             references
    build/skill/seriesmith-episode-script/   the whole skill, ready to install:
        SKILL.md                             the same text, plus what the folder bundles
        references/                          the same references
        scripts/check.py                     the build (build.py, core/, targets/) carried
                                             inside one file, to validate a script with
                                             --check where seriesmith isn't installed
    build/skill/seriesmith-episode-script.zip
                                             the folder zipped, to upload on claude.ai
                                             (Settings > Skills > Upload a skill)
    prompts/seriesmith-episode-script.zip    the same zip, committed: what a user installs
                                             (it ships in the node pack, so a Manager
                                             install has it too)

prompts/ is committed; build/ is not. The zip is stamped with the release in
pyproject.toml, not the commit, so the same sources give the same zip. Run it after
editing docs/AUTHORING.md, docs/SCRIPT_CONVERSION.md or docs/STORY_STRUCTURES.md, and before a release (the
zip also bundles the build: the core and the targets):

    python tools/make_prompts.py
    python tools/make_prompts.py --no-bundle     # prompts/ only, not the skill

For Claude Code, unzip prompts/seriesmith-episode-script.zip into .claude/skills/.

The split is written into AUTHORING.md as comments, each on a line of its own:

    <!-- skill:ref models -->      this part goes to references/models.md; where a
    ...                            reference's first part was, SKILL.md says when to read it
    <!-- /skill:ref -->
    <!-- skill:omit -->            this part is for a person reading the docs: it is in
    ...                            none of the skill's files
    <!-- /skill:omit -->

Stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "docs", "AUTHORING.md")
BREAKDOWN = os.path.join(ROOT, "docs", "SCRIPT_CONVERSION.md")
STRUCTURES = os.path.join(ROOT, "docs", "STORY_STRUCTURES.md")

NAME = "seriesmith-episode-script"
MAX_DESCRIPTION = 1024           # claude.ai's limit on a skill's description
INSTRUCTIONS = "seriesmith-script.instructions.md"

DESCRIPTION = (
    "Write episode scripts and series configs for seriesmith, the script-to-episode AI video "
    "pipeline, fresh or converted from an existing screenplay. Covers the epNN.md script "
    "format (sequences, shots, ALL-CAPS dialogue, who/with/size/dur/plate/camera/sound "
    "fields, continuity and keyframe lines) and the series config (series.json) with what's "
    "required, what each optional block defaults to, the cast, locations, look, voices, "
    "profiles, render size and master recipe. Shots render on a video model per shot or "
    "episode (MiniMax H3, LTX-2, Wan 2.2, Seedance and others). Use it whenever the user "
    "wants to write, outline or extend an episode, pick a story structure, start a series, break a screenplay or "
    "scene into shots, add characters, props or locations to a series config, choose which "
    "model renders a shot, re-time shots whose dialogue doesn't fit, or fix a script "
    "seriesmith check rejected, even if they never name seriesmith or the file formats."
)

# What both preambles open with.
OPENING = """You are writing for seriesmith. Follow this format exactly: the output is compiled
by `seriesmith build`, and anything that does not match is a build error, not a style
preference.

Before writing anything, ask for the series config (`series.json`) if the series has one.
Adding a character means adding to that file, not inventing a new one: if you write `riley`
when the series config already has `riley_freeman`, every reference path breaks. An existing
series config is the show's: add what the episode needs and change nothing else unasked (if
it has no `upscale.master` block, say once that it can't be mastered by recipe until it has
one)."""

# SKILL.md's: it has the references and, in the bundle, the check.
PREAMBLE = OPENING + """ With no series config yet you are starting a series: write both files,
and read `references/series_config.md` first. It says what to settle before the first shot
(ask what the brief doesn't say, in one message) and the defaults to use, and to list, when
the person would rather you just start.

Converting an existing screenplay, keep its story and dialogue and break it into shots
(`references/script_conversion.md` works a scene through). Writing fresh, outline the story
before the shots: if the person hasn't given it a shape, offer the menu in
`references/story_structures.md` (with the questions about the series, in the same message;
if they'd rather you just start, pick one from it and say which and why in a line).
Either way, mark the structure and each beat in the script (`// structure:` near the top,
`// beat:` above each beat's first shot; the structure that fits a converted screenplay
best), so the score can be drafted from them (that file's **From beats to shots**).

Write the film, not the model. Leave `target:` lines out unless a shot needs something only
one model does (`references/models.md`); advice that holds for one target only is marked
with that target's name.

Validate before calling a script finished, with the first of these you have: seriesmith's MCP
tools (`check_pair` for a series config and a script not on disk yet, `check_source` for an
episode's, `preview_shot` for what one shot would render); the command `seriesmith check
<episode folder>`; this skill's `scripts/check.py`. Fix what it reports and check again until
it is clean. Rendering, upscaling and mastering are the person's to run, not part of
writing."""

# The one-file instructions': the whole guide follows, with no references and no check.
PREAMBLE_ONE_FILE = OPENING + """ With no series config yet you are starting a series: write both
files, and settle what **Starting a series: what to settle first** lists before the first
shot. Ask what the brief doesn't say, in one message; if the person would rather you just
start, use that section's defaults and list what you assumed.

Converting an existing screenplay, keep its story and dialogue and break it into shots.
Writing fresh, outline the story before the shots, and offer a story structure if the
person hasn't given it a shape. Either way, mark the structure and each beat in the script
(`// structure:` near the top, `// beat:` above each beat's first shot), so the score can be
drafted from them.

Write the film, not the model. Leave `target:` lines out unless a shot needs something only
one model does (see **Choosing a video target**); advice that holds for one target only is
marked with that target's name.

Validate before calling a script finished: seriesmith's MCP tools when you have them
(`check_pair`, `check_source`, `preview_shot`), else ask the person to run `seriesmith check
<episode folder>` and send what it prints. Fix what it reports and check again until it is
clean. Rendering, upscaling and mastering are the person's to run, not part of writing."""

BUNDLE_NOTE = """## Files in this skill

{references}
- `scripts/check.py`: the build itself (its core and the targets), carried inside one
  file so a script can be validated anywhere. Run it; don't open it (it is the build's
  files as text, about 2 MB, and reading it tells you nothing):

  ```
  python <this skill>/scripts/check.py series.json ep01.md --check
  python <this skill>/scripts/check.py series.json ep01.md --pace
  ```

  It needs Python 3.10+ and nothing else. The first run writes the build's files to a
  folder under the system's temporary folder and uses them from there; `--check` and
  `--pace` write nothing else. If the user has seriesmith installed, use its
  `seriesmith check` (or `seriesmith check <episode folder>`): it is the source of truth,
  and this copy is `{version}`."""

# scripts/check.py: the build's files carried inside it as text (claude.ai takes a skill of
# 200 files at most and refuses an archive in one, so not a folder of them and not a zip),
# written to a temporary folder when it runs, then the build itself. `{files}` is the table.
CHECK_PY = '''"""Check an episode script against its series config:

    python check.py series.json ep01.md --check
    python check.py series.json ep01.md --pace

This file carries seriesmith's build inside it (build.py, core/, targets/: the table
below, each file's bytes as base64). Run it; there is nothing to read here. The first run
writes those files to a folder under the system's temporary folder and uses them there.
"""
import base64
import os
import sys
import tempfile

STAMP = "{stamp}"


def unpack() -> str:
    """The folder holding the build's package, written on the first run."""
    root = os.path.join(tempfile.gettempdir(), "seriesmith-check-" + STAMP)
    done = os.path.join(root, ".unpacked")
    if os.path.isfile(done):
        return root
    for name, data in FILES.items():
        path = os.path.join(root, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data))
    with open(done, "w") as fh:
        fh.write(STAMP)
    return root


FILES = {
{files}}

if __name__ == "__main__":
    try:
        where = unpack()
    except OSError as e:
        sys.exit(f"check.py needs a folder it can write the build to, and the temporary "
                 f"folder isn't one ({e}). With seriesmith installed, run "
                 f"`seriesmith check <episode folder>` instead.")
    if sys.argv[1:] == ["--where"]:      # for a test: where the build was written
        print(where)
        raise SystemExit(0)
    sys.path.insert(0, where)
    from seriesmith import build
    raise SystemExit(build.main(sys.argv[1:], prog="check.py"))
'''

# What scripts/seriesmith/ carries: the build and what a check imports (all stdlib):
# settings, because the targets look beside it for this machine's own models. The
# upscale and post stages stay out (they need the rest of seriesmith): the build
# passes their recipes over with a note. Workflows are only read when rendering.
BUNDLE_FILES = ["__init__.py", "build.py", "settings.py"]
BUNDLE_DIRS = ["core", "targets"]
BUNDLE_SKIP = ["__pycache__", "*.pyc", "workflow.json"]
# claude.ai takes a skill of 200 files at most, and refuses a zip inside it: the build is
# carried inside scripts/check.py (CHECK_PY), so the skill is a handful of files whatever
# the models number. A model's folder (targets/<kind>/<id>/) goes without its __init__.py
# when that holds only a docstring: its code is imported by module path, which Python 3
# finds without one (a namespace package).
MAX_FILES = 200
# SKILL.md is read whole every time the skill loads: its core (AUTHORING.md less what the
# markers send to references or leave out) stays under this, so a section added to the
# guide is marked for a reference or the generator fails (docs/SKILL_SPLIT.md, section 8).
MAX_CORE_WORDS = 9500


# The references cut out of AUTHORING.md by its `skill:ref` markers, in the order SKILL.md
# lists them: (name, title, what it covers, when to read it). The last two are also what
# `seriesmith mcp` says of each resource.
REFS = [
    ("series_config", "The series config, block by block",
     "starting a series and what to settle first, render size and delivery, the master recipe, "
     "post, the intro and outro and a cold open before them, the `look` line, render profiles, "
     "the `refs`, `sound` and `ambience` blocks, relit plates",
     "writing a new `series.json` or any block of one besides `subjects` and `locations`, "
     "relighting a plate, or marking a cold open"),
    ("models", "Which model renders a shot",
     "the targets and what each takes, a section per model, the hosted models and their table "
     "of pictures, keyframes, `dur: model`, `target: hold`",
     "the series config or a shot names a `target:`, or the person asks which model to use"),
    ("continuity", "Shots that carry on from one another",
     "`continuous: first`, `latent` and `multishot`: what each does, where it renders, how to "
     "write it",
     "you are about to write a `continuous:` line"),
    ("people", "Wardrobe, groups and vehicles",
     "a wardrobe change as a variant and how to cut round it, the same background people in "
     "several shots as a group, a blurred plate for a close-up, vehicles in motion",
     "a character changes clothes, the same background people are seen twice, a vehicle moves, "
     "or a close-up needs nothing but blur behind the face"),
]
# the two whole documents bundled as references: (name, what it covers, when to read it)
DOC_REFS = [
    ("script_conversion", "a spec-format screenplay scene worked through to shots, with where "
     "the cuts land and why",
     "adapting existing script pages rather than writing shots directly"),
    ("story_structures", "the story structures (three-act, Sitcom, Episodic Drama, Story Circle, "
     "Fable, Kishōtenketsu, the Hero's Journey and its 27 beats, …), a menu to offer, each one's "
     "beats with their share of the runtime and how each is scored, and how beats become shots",
     "outlining an episode written fresh"),
]
MARK = re.compile(r"^<!-- (/?)skill:(ref|omit)(?: ([a-z_]+))? -->$")
GENERATED = re.compile(r"^<!-- (BEGIN|END) [A-Z ]+")      # a generated block's own markers


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# the two documents the skill bundles whole
BUNDLED_DOCS = {"SCRIPT_CONVERSION.md": "references/script_conversion.md",
                "STORY_STRUCTURES.md": "references/story_structures.md"}


def outside_repo(text: str, bundled: bool = True) -> str:
    """The skill is read away from the repo, where the docs' links point at nothing. A
    document the skill bundles is named as its reference (`references/story_structures.md`;
    with `bundled` off, for the one-file instructions, it is words like the rest); any other
    becomes plain words ("seriesmith's finishing guide"), since its reader can't open it;
    and AUTHORING, which the skill is, is SKILL.md."""
    def said(name: str) -> str:
        if bundled and name in BUNDLED_DOCS:
            return f"`{BUNDLED_DOCS[name]}`"
        return f"seriesmith's {name[:-3].lower().replace('_', ' ')} guide"
    doc = r"(?!AUTHORING\.md)([A-Z_]+\.md)"
    text = re.sub(r"\[[^\]]+\]\((?:\.\./)?(?:docs/)?" + doc + r"(?:#[^)]*)?\)", lambda m: said(m.group(1)), text)
    text = re.sub(r"`(?:docs/)?" + doc + "`", lambda m: said(m.group(1)), text)
    text = re.sub(r"\bdocs/" + doc, lambda m: said(m.group(1)), text)
    text = re.sub(r"(?<![\w/`.])(?!SKILL\.md)" + doc + r"\b", lambda m: said(m.group(1)), text)
    return re.sub(r"\bAUTHORING(?:\.md)?", "SKILL.md", text)


def source(bundled: bool = True) -> str:
    """AUTHORING.md less its own title and lede (the wrappers supply their own), its links
    turned for a reader away from the repo (`bundled`: one who has the references)."""
    text = read(SOURCE)
    parts = text.split("\n## ", 1)
    return outside_repo("## " + parts[1] if len(parts) == 2 else text, bundled)


def headings(block: str) -> list[str]:
    """A block's `##` and `###` headings, less their backticked field names' punctuation
    (a line inside a code fence is a script's shot, not a heading)."""
    out, fenced = [], False
    for ln in block.split("\n"):
        if ln.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{2,3} ", ln):
            out.append(ln.lstrip("#").strip())
    return out


def trigger(name: str, when: str, block: str) -> str:
    """What SKILL.md says where a reference's first part was: when to read it, and the
    headings it holds (the core names a section by its heading)."""
    heads = headings(block)
    holds = f" It holds {', '.join(f'**{h}**' for h in heads)}." if heads else ""
    return f"> **Read `references/{name}.md`** when {when}.{holds}"


def split(text: str) -> tuple[str, dict[str, list[str]], str]:
    """(the core, {reference: its blocks in the document's order}, the whole): `text` with
    its `skill:` markers read. The core has a reference's trigger where its first block was
    and nothing where the others were; the whole has every `skill:ref` block in place and no
    marker. `skill:omit` blocks are in neither. A marker that doesn't pair, nests, names no
    reference of REFS, or sits inside a generated block, is an error."""
    names = [r[0] for r in REFS]
    when = {r[0]: r[3] for r in REFS}
    core: list[str] = []
    whole: list[str] = []
    refs: dict[str, list[str]] = {n: [] for n in names}
    inside: tuple[str, str | None] | None = None      # (kind, name) of the open block
    at = 0
    buf: list[str] = []
    generated = False
    slots: list[tuple[int, str]] = []                 # where in the core each reference's trigger goes
    for i, ln in enumerate(text.split("\n"), 1):
        g = GENERATED.match(ln)
        if g:
            generated = g.group(1) == "BEGIN"
        m = MARK.match(ln.strip()) if ln.strip().startswith("<!--") else None
        if not m:
            if "skill:" in ln and ln.strip().startswith("<!--"):
                raise SystemExit(f"  !! AUTHORING.md line {i}: not a marker the generator reads: {ln.strip()}")
            if inside:
                buf.append(ln)
            else:
                core.append(ln)
                whole.append(ln)
            continue
        closing, kind, name = m.group(1) == "/", m.group(2), m.group(3)
        if generated:
            raise SystemExit(f"  !! AUTHORING.md line {i}: a skill marker inside a generated block")
        if not closing:
            if inside:
                raise SystemExit(f"  !! AUTHORING.md line {i}: a skill marker inside the block opened at line {at}")
            if kind == "ref" and name not in names:
                raise SystemExit(f"  !! AUTHORING.md line {i}: skill:ref names {name!r}; the references are {', '.join(names)}")
            if kind == "omit" and name:
                raise SystemExit(f"  !! AUTHORING.md line {i}: skill:omit takes no name")
            inside, at, buf = (kind, name), i, []
            continue
        if not inside or inside[0] != kind:
            raise SystemExit(f"  !! AUTHORING.md line {i}: a closing skill:{kind} with none open")
        block = "\n".join(buf).strip("\n")
        if kind == "ref":
            n = inside[1]
            if not refs[n]:
                slots.append((len(core), n))
                core.append("")                       # the trigger, written once every block is read
            refs[n].append(block)
            whole.extend(buf)
        inside = None
    if inside:
        raise SystemExit(f"  !! AUTHORING.md line {at}: skill:{inside[0]} is never closed")
    for pos, n in slots:
        core[pos] = trigger(n, when[n], "\n\n".join(refs[n]))
    tidy = lambda lines: re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return tidy(core), refs, tidy(whole)


def body() -> str:
    """The core: what SKILL.md says under its preamble."""
    return split(source())[0]


def whole() -> str:
    """The whole guide in the document's order: the one-file instructions' text, which
    has no references to point at."""
    return split(source(bundled=False))[2]


def references() -> dict[str, str]:
    """{file name: text} of every reference: those cut from AUTHORING.md (a reference with
    no block in the document isn't written) and the two bundled documents."""
    blocks = split(source())[1]
    out = {}
    for name, title, covers, when in REFS:
        if blocks[name]:
            out[f"{name}.md"] = (f"# {title}\n\n"
                                 f"A reference for SKILL.md: {covers}. Read it when {when}.\n\n"
                                 + "\n\n".join(blocks[name]) + "\n")
    out["script_conversion.md"] = bundle_breakdown()
    out["story_structures.md"] = bundle_structures()
    return out


def words(text: str) -> int:
    return len(text.split())


def write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    print(f"  -> {os.path.relpath(path, ROOT)}")


def skill_text(text: str, extra: str = "") -> str:
    # the frontmatter is YAML: an unquoted value can't hold ": "
    assert ": " not in DESCRIPTION and "#" not in DESCRIPTION, DESCRIPTION
    # claude.ai refuses a skill whose description is longer
    assert len(DESCRIPTION) <= MAX_DESCRIPTION, f"description is {len(DESCRIPTION)} characters, over {MAX_DESCRIPTION}"
    return ("---\n"
            f"name: {NAME}\n"
            f"description: {DESCRIPTION}\n"
            "---\n\n"
            "# Writing an episode for seriesmith\n\n"
            f"{PREAMBLE}\n\n{text}" + (f"\n{extra}\n" if extra else ""))


def instructions_text() -> str:
    """The one-file instructions: the whole guide, for a client with no references."""
    return ("# seriesmith episode script — assistant instructions\n\n"
            "Paste this into Cursor rules, Copilot instructions, a custom GPT, or any\n"
            "system prompt. Generated from docs/AUTHORING.md by tools/make_prompts.py.\n\n"
            f"{PREAMBLE_ONE_FILE}\n\n{whole()}")


def version() -> str:
    """The release the skill is from (pyproject.toml's version): a commit's hash would
    make the committed zip differ on every commit."""
    m = re.search(r'^version\s*=\s*"([^"]+)"', read(os.path.join(ROOT, "pyproject.toml")), re.M)
    return f"seriesmith {m.group(1)}" if m else "a snapshot of seriesmith"


def skipped(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in BUNDLE_SKIP)


def docstring_only(path: str) -> bool:
    """Whether a Python file holds nothing but a docstring (or nothing)."""
    import ast
    tree = ast.parse(read(path))
    return all(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) for n in tree.body)


def left_out(folder: str, names: list[str]) -> list[str]:
    """What copying `folder` into the bundle leaves out: BUNDLE_SKIP, and a model
    folder's __init__.py that holds only a docstring (see MAX_FILES)."""
    out = [n for n in names if skipped(n)]
    model = os.path.basename(os.path.dirname(os.path.dirname(folder))) == "targets"
    if model and "__init__.py" in names and docstring_only(os.path.join(folder, "__init__.py")):
        out.append("__init__.py")
    return out


def carried() -> list[tuple[str, bytes]]:
    """The build's files a check runs, as (path inside the package's parent, bytes), sorted:
    BUNDLE_FILES and BUNDLE_DIRS of seriesmith/, less what `left_out` leaves out."""
    src = os.path.join(ROOT, "seriesmith")
    out = []
    for f in BUNDLE_FILES:
        out.append(f"seriesmith/{f}")
    for d in BUNDLE_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(src, d)):
            drop = set(left_out(dirpath, dirnames + filenames))
            dirnames[:] = [n for n in dirnames if n not in drop]
            for n in filenames:
                if n not in drop:
                    rel = os.path.relpath(os.path.join(dirpath, n), src).replace(os.sep, "/")
                    out.append(f"seriesmith/{rel}")
    files = []
    for name in sorted(out):
        with open(os.path.join(ROOT, *name.split("/")), "rb") as fh:
            # as git has them: a checkout with CRLF gives the same file
            files.append((name, fh.read().replace(b"\r\n", b"\n")))
    return files


def check_py() -> str:
    """scripts/check.py: CHECK_PY with the build's files written in."""
    files = carried()
    stamp = hashlib.sha256(b"\0".join(n.encode() + b"\0" + d for n, d in files)).hexdigest()[:16]
    rows = []
    for name, data in files:
        b64 = base64.b64encode(data).decode("ascii")
        lines = [b64[i:i + 100] for i in range(0, len(b64), 100)] or [""]
        rows.append(f'    "{name}": (\n' + "".join(f'        "{ln}"\n' for ln in lines) + "    ),\n")
    return CHECK_PY.replace("{stamp}", stamp).replace("{files}", "".join(rows))


def reference_list() -> str:
    """The skill's references as its "Files in this skill" lists them, each once."""
    have = references()
    rows = [(n, covers, when) for n, _title, covers, when in REFS if f"{n}.md" in have] + DOC_REFS
    return "\n".join(f"- `references/{n}.md`: {covers}. Read it when {when}." for n, covers, when in rows)


def bundle_skill(text: str) -> str:
    """The bundled skill's SKILL.md: the skill's text and what the folder holds."""
    return skill_text(text, BUNDLE_NOTE.replace("{version}", version()).replace("{references}", reference_list()))


def homed(text: str) -> str:
    """A bundled document's pointers into the guide ("SKILL.md's **A cold open**"), said for
    where that heading is now: a reference's, when the markers moved it there."""
    home = {h: name for name, blocks in split(source())[1].items() for b in blocks for h in headings(b)}

    def point(m):
        said = m.group(1)
        at = next((ref for h, ref in home.items() if h.startswith(" ".join(said.split()))), None)
        return f"`references/{at}.md`, **{said}**" if at else f"SKILL.md, **{said}**"
    return re.sub(r"SKILL\.md(?:'s|,) (?:\*\*|\")([^*\"]+)(?:\*\*|\")", point, text)


def bundle_breakdown() -> str:
    """references/script_conversion.md: the breakdown, its lede pointing at SKILL.md
    rather than into the repo."""
    title, _lede, rest = read(BREAKDOWN).split("\n\n", 2)
    return (f"{title}\n\n"
            "A worked example for SKILL.md. The input is ordinary spec-format script pages;\n"
            "the output is the shot list. The interesting part is not the syntax, it's where\n"
            f"the cuts land and why. Read it when {DOC_REFS[0][2]}.\n\n{homed(outside_repo(rest))}")


def bundle_structures() -> str:
    """references/story_structures.md: the structures, their lede pointing at SKILL.md
    rather than into the repo."""
    title, _lede, rest = read(STRUCTURES).split("\n\n", 2)
    return (f"{title}\n\n"
            "A reference for SKILL.md: the major story structures, for outlining an episode\n"
            f"written from scratch. Read it when {DOC_REFS[1][2]}.\n\n{homed(outside_repo(rest))}")


def bundle(text: str, out: str | None = None) -> str:
    """The skill's folder and zip, in `out` (build/skill/ by default)."""
    out = out or os.path.join(ROOT, "build", "skill")
    folder = os.path.join(out, NAME)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    write(os.path.join(folder, "SKILL.md"), bundle_skill(text))
    for name, ref in references().items():
        write(os.path.join(folder, "references", name), ref)

    scripts = os.path.join(folder, "scripts")
    os.makedirs(scripts)
    check = os.path.join(scripts, "check.py")
    with open(check, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(check_py())
    print(f"  -> {os.path.relpath(check, ROOT)} ({len(carried())} files of the build inside it: "
          f"{', '.join(BUNDLE_FILES + [d + '/' for d in BUNDLE_DIRS])}; {os.path.getsize(check) // 1024} KB)")

    # The zip holds the folder itself, as claude.ai's skill upload expects.
    # Fixed timestamps and sorted entries: the same sources give the same zip.
    zpath = os.path.join(out, f"{NAME}.zip")
    entries = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for n in sorted(filenames):
            full = os.path.join(dirpath, n)
            entries.append((full, os.path.relpath(full, out).replace(os.sep, "/")))
    assert len(entries) <= MAX_FILES, f"the skill is {len(entries)} files, over claude.ai's {MAX_FILES}"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, arc in entries:
            info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as fh:
                zf.writestr(info, fh.read())
    print(f"  -> {os.path.relpath(zpath, ROOT)} ({len(entries)} files, "
          f"{os.path.getsize(zpath) // 1024} KB)")
    return zpath


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-bundle", action="store_true",
                    help="write prompts/ only, not build/skill/")
    args = ap.parse_args()
    for p in (SOURCE, BREAKDOWN, STRUCTURES):
        if not os.path.isfile(p):
            sys.exit(f"  !! {p} not found")
    text = body()
    if words(text) > MAX_CORE_WORDS:
        sys.exit(f"  !! the skill's core is {words(text)} words, over {MAX_CORE_WORDS}: mark the new part of "
                 f"docs/AUTHORING.md for a reference (<!-- skill:ref NAME -->) or for the docs only "
                 f"(<!-- skill:omit -->)")
    out = os.path.join(ROOT, "prompts")

    write(os.path.join(out, "SKILL.md"), skill_text(text))
    refs = references()
    folder = os.path.join(out, "references")
    for stale in (os.listdir(folder) if os.path.isdir(folder) else []):
        if stale not in refs:
            os.remove(os.path.join(folder, stale))
    for name, ref in refs.items():
        write(os.path.join(folder, name), ref)
    write(os.path.join(out, INSTRUCTIONS), instructions_text())
    print(f"  the core is {words(text)} words, the whole guide {words(whole())}")
    if not args.no_bundle:
        zpath = bundle(text)
        shutil.copyfile(zpath, os.path.join(out, f"{NAME}.zip"))
        print(f"  -> {os.path.relpath(os.path.join(out, NAME + '.zip'), ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
