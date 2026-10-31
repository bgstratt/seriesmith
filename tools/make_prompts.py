#!/usr/bin/env python3
"""
make_prompts.py — regenerate prompts/ and the script-writing skill from docs/AUTHORING.md.

The authoring guide is the single source. This wraps it in the packaging each
assistant expects, so the copies cannot drift from the document:

    prompts/SKILL.md                         the skill's text alone (Claude Code / Claude.ai)
    prompts/seriesmith-script.instructions.md
                                             Cursor, Copilot, generic system prompt
    build/skill/seriesmith-episode-script/   the whole skill, ready to install:
        SKILL.md                             the same text, plus what the folder bundles
        references/script_conversion.md      docs/SCRIPT_CONVERSION.md (a screenplay scene
                                             worked through to shots)
        references/story_structures.md       docs/STORY_STRUCTURES.md (story structures,
                                             for outlining an episode written fresh)
        scripts/check.py, scripts/seriesmith/ (build.py, core/, targets/)
                                             the build, to validate a script with --check
                                             where seriesmith isn't installed
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

Stdlib only.
"""
from __future__ import annotations

import argparse
import fnmatch
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

PREAMBLE = """You are writing for seriesmith. Follow this format exactly: the output is compiled
by `seriesmith build`, and anything that does not match is a build error, not a style
preference.

Before writing anything, ask for the series config (`series.json`) if the series has one.
Adding a character means adding to that file, not inventing a new one: if you write `riley`
when the series config already has `riley_freeman`, every reference path breaks. With no
series config yet you are starting a series: write both files.

Starting a series, settle what **Starting a series: what to settle first** lists before the
first shot: the look, the delivery (1080p, 1440p or 4K, which sets the render size, the
proxy and the master recipe), the voices, the finishing pass and the titles. Ask what the
brief doesn't already say, in one message, then write the whole config: `upscale.master`
and `post` as well as the cast and the places. If the person would rather you just start,
use that section's defaults and list what you assumed. An existing series config is the
show's: add what the episode needs and change nothing else unasked, but if it has no
`upscale.master` block, say once that it can't be mastered by recipe until it has one.

Converting an existing screenplay, keep its story and dialogue and break it into shots
(`references/script_conversion.md` works a scene through). Writing fresh, outline the story
before the shots: if the person hasn't given it a shape, offer the menu in
`references/story_structures.md` (with the questions above, in the same message), then mark
each beat in the script with a `//` comment. Either way, write the film, not the model. Leave `target:` lines out unless a shot
needs something only one model does (see **Choosing a video target**); advice that holds for
one target only is marked with that target's name. Validate with `seriesmith check
series.json <script>` and `--pace` before calling a script finished. Rendering, upscaling
and mastering are the person's to run, not part of writing: point to `docs/FINISHING.md`
and `docs/COMMANDS.md` for those."""

BUNDLE_NOTE = """## Files in this skill

- `references/script_conversion.md`: a spec-format screenplay scene worked through to shots, with
  where the cuts land and why. Read it when adapting existing script pages rather than
  writing shots directly.
- `references/story_structures.md`: the story structures (three-act, Story Circle, Fable,
  Kishōtenketsu, the Hero's Journey and its 27 beats, …), a menu to offer, each one's beats
  with their share of the runtime, and how beats become shots. Read it when outlining an
  episode written fresh.
- `scripts/check.py` (with `scripts/seriesmith/`: the build, its core and the targets): the
  build, bundled so a script can be validated anywhere:

  ```
  python <this skill>/scripts/check.py series.json ep01.md --check
  python <this skill>/scripts/check.py series.json ep01.md --pace
  ```

  It needs Python 3.10+ and nothing else, and writes nothing with `--check` / `--pace`. If
  the user has seriesmith installed, use its `seriesmith check` (or
  `seriesmith check <episode folder>`): it is the source of truth, and this copy is
  `{version}`."""

# the launcher scripts/ carries: the bundled package on the path, then the build
CHECK_PY = '''"""Check an episode script against its series config with the build bundled
beside this file (seriesmith/build.py): python check.py series.json ep01.md --check"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seriesmith import build  # noqa: E402

raise SystemExit(build.main(sys.argv[1:], prog="check.py"))
'''

# What scripts/seriesmith/ carries: the build and what a check imports (all stdlib):
# settings, because the targets look beside it for this machine's own models. The
# upscale and post stages stay out (they need the rest of seriesmith): the build
# passes their recipes over with a note. Workflows are only read when rendering.
BUNDLE_FILES = ["__init__.py", "build.py", "settings.py"]
BUNDLE_DIRS = ["core", "targets"]
BUNDLE_SKIP = ["__pycache__", "*.pyc", "workflow.json"]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def body() -> str:
    text = read(SOURCE)
    # drop the document's own title and lede; the wrappers supply their own
    parts = text.split("\n## ", 1)
    return "## " + parts[1] if len(parts) == 2 else text


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


def version() -> str:
    """The release the skill is from (pyproject.toml's version): a commit's hash would
    make the committed zip differ on every commit."""
    m = re.search(r'^version\s*=\s*"([^"]+)"', read(os.path.join(ROOT, "pyproject.toml")), re.M)
    return f"seriesmith {m.group(1)}" if m else "a snapshot of seriesmith"


def skipped(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in BUNDLE_SKIP)


def bundle_skill(text: str) -> str:
    """The bundled skill's SKILL.md: the skill's text and what the folder holds."""
    return skill_text(text, BUNDLE_NOTE.replace("{version}", version()))


def bundle_breakdown() -> str:
    """references/script_conversion.md: the breakdown, its lede pointing at SKILL.md
    rather than into the repo."""
    title, _lede, rest = read(BREAKDOWN).split("\n\n", 2)
    return (f"{title}\n\n"
            "A worked example for SKILL.md. The input is ordinary spec-format script pages;\n"
            "the output is the shot list. The interesting part is not the syntax, it's where\n"
            f"the cuts land and why.\n\n{rest}")


def bundle_structures() -> str:
    """references/story_structures.md: the structures, their lede pointing at SKILL.md
    rather than into the repo."""
    title, _lede, rest = read(STRUCTURES).split("\n\n", 2)
    return (f"{title}\n\n"
            "A reference for SKILL.md: the major story structures, for outlining an episode\n"
            f"written from scratch.\n\n{rest}")


def bundle(text: str, out: str | None = None) -> str:
    """The skill's folder and zip, in `out` (build/skill/ by default)."""
    out = out or os.path.join(ROOT, "build", "skill")
    folder = os.path.join(out, NAME)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    write(os.path.join(folder, "SKILL.md"), bundle_skill(text))
    write(os.path.join(folder, "references", "script_conversion.md"), bundle_breakdown())
    write(os.path.join(folder, "references", "story_structures.md"), bundle_structures())

    scripts = os.path.join(folder, "scripts")
    pkg = os.path.join(scripts, "seriesmith")
    os.makedirs(pkg)
    with open(os.path.join(scripts, "check.py"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CHECK_PY)
    src = os.path.join(ROOT, "seriesmith")
    for f in BUNDLE_FILES:
        shutil.copy2(os.path.join(src, f), os.path.join(pkg, f))
    for d in BUNDLE_DIRS:
        shutil.copytree(os.path.join(src, d), os.path.join(pkg, d),
                        ignore=lambda _dir, names: [n for n in names if skipped(n)])
    print(f"  -> {os.path.relpath(scripts, ROOT)}{os.sep} (check.py, seriesmith/: "
          f"{', '.join(BUNDLE_FILES + [d + '/' for d in BUNDLE_DIRS])})")

    # The zip holds the folder itself, as claude.ai's skill upload expects.
    # Fixed timestamps and sorted entries: the same sources give the same zip.
    zpath = os.path.join(out, f"{NAME}.zip")
    entries = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for n in sorted(filenames):
            full = os.path.join(dirpath, n)
            entries.append((full, os.path.relpath(full, out).replace(os.sep, "/")))
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
    out = os.path.join(ROOT, "prompts")

    write(os.path.join(out, "SKILL.md"), skill_text(text))
    write(os.path.join(out, INSTRUCTIONS),
          "# seriesmith episode script — assistant instructions\n\n"
          "Paste this into Cursor rules, Copilot instructions, a custom GPT, or any\n"
          "system prompt. Generated from docs/AUTHORING.md by tools/make_prompts.py.\n\n"
          f"{PREAMBLE}\n\n{text}")
    if not args.no_bundle:
        zpath = bundle(text)
        shutil.copyfile(zpath, os.path.join(out, f"{NAME}.zip"))
        print(f"  -> {os.path.relpath(os.path.join(out, NAME + '.zip'), ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
