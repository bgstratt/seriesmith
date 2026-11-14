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
`references/story_structures.md` (with the questions above, in the same message). Either
way, mark the structure and each beat in the script (`// structure:` near the top, `// beat:`
above each beat's first shot; the structure that fits a converted screenplay best), so the
score can be drafted from them (that file's **From beats to shots**). Write the film, not
the model. Leave `target:` lines out unless a shot
needs something only one model does (see **Choosing a video target**); advice that holds for
one target only is marked with that target's name. Validate with `seriesmith check
<episode folder>` before calling a script finished. Rendering, upscaling
and mastering are the person's to run, not part of writing: point to `docs/FINISHING.md`
and `docs/COMMANDS.md` for those."""

BUNDLE_NOTE = """## Files in this skill

- `references/script_conversion.md`: a spec-format screenplay scene worked through to shots, with
  where the cuts land and why. Read it when adapting existing script pages rather than
  writing shots directly.
- `references/story_structures.md`: the story structures (three-act, Sitcom, Episodic Drama,
  Story Circle, Fable, Kishōtenketsu, the Hero's Journey and its 27 beats, …), a menu to
  offer, each one's beats with their share of the runtime and how each is scored, and how
  beats become shots. Read it when outlining an
  episode written fresh.
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


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def outside_repo(text: str) -> str:
    """The skill is read away from the repo, where the docs' relative links point at
    nothing: name each document by its path in the repo instead (`docs/FINISHING.md`,
    `INSTALL.md`), and AUTHORING, which the skill is, as SKILL.md."""
    def path(name: str) -> str:
        return name if name == "INSTALL.md" else f"docs/{name}"
    text = re.sub(r"\[[^\]]+\]\((?:\.\./)?([A-Z_]+\.md)\)", lambda m: f"`{path(m.group(1))}`", text)
    text = re.sub(r"`([A-Z_]+\.md)`", lambda m: f"`{path(m.group(1))}`", text)
    return re.sub(r"\bAUTHORING(?:\.md)?", "SKILL.md", text)


def body() -> str:
    text = read(SOURCE)
    # drop the document's own title and lede; the wrappers supply their own
    parts = text.split("\n## ", 1)
    return outside_repo("## " + parts[1] if len(parts) == 2 else text)


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
            f"the cuts land and why.\n\n{outside_repo(rest)}")


def bundle_structures() -> str:
    """references/story_structures.md: the structures, their lede pointing at SKILL.md
    rather than into the repo."""
    title, _lede, rest = read(STRUCTURES).split("\n\n", 2)
    return (f"{title}\n\n"
            "A reference for SKILL.md: the major story structures, for outlining an episode\n"
            f"written from scratch.\n\n{outside_repo(rest)}")


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
