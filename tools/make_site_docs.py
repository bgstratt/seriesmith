"""Write the docs site's pages (docs/site/*.mdx, published by Mintlify at
docs.seriesmith.com) from the user docs: INSTALL.md and docs/*.md, the
internal ones (DESIGN, PLAN) left out. Run after changing any of them;
tests/test_docs.py fails while a page is out of date.

Each page is its document as MDX: the title (its first heading) and a
description (written here) in front matter, the links between the docs
pointing at the site's pages (anything else in the repo at GitHub), and what MDX
would read as JSX escaped outside code ({, } and <). The site's
own pages (index.mdx) and docs.json are written by hand.

    python tools/make_site_docs.py           # write them
    python tools/make_site_docs.py --check   # exit 1 if any is out of date
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs", "site")
GITHUB = "https://github.com/bgstratt/seriesmith/blob/main/"

# (source, page, description): the order is docs.json's
PAGES = [
    ("docs/QUICKSTART.md", "quickstart", "Clone, link the node pack, start ComfyUI: seriesmith running on the models you already have."),
    ("docs/FULL_SETUP.md", "full-setup", "The node packs, model files, LoRAs and software for every feature: H3 at full quality, voices, upscale, post, master."),
    ("INSTALL.md", "install", "Every part in detail: seriesmith, the node pack, the workflows, every model file with its folder and link, the first run."),
    ("docs/SETUP.md", "setup", "Where shots render: your ComfyUI, Comfy Cloud, a deployment or Comfy Router, and the settings that choose."),
    ("docs/EDITOR.md", "editor", "The editor page: shots, takes, refs, the cut and the queue, every button and key."),
    ("docs/COMMANDS.md", "commands", "Every stage as a command, the files each reads and writes, and an episode worked from a terminal."),
    ("docs/AUTHORING.md", "authoring", "The script and series config format: a first episode to copy, then every field."),
    ("docs/SCRIPT_CONVERSION.md", "script-conversion", "A spec-format screenplay scene worked all the way through to shots."),
    ("docs/CONTINUOUS.md", "continuous", "Shots that carry straight on from the one before: from its last frame, or its held latent."),
    ("docs/POST_PROCESSING.md", "post-processing", "The post pass: face restore, enhancement and motion blur, per take or across a master."),
    ("docs/RECORDED_DIALOGUE.md", "recorded-dialogue", "Lip-synced episodes from real recorded lines instead of generated voices."),
    ("docs/KREAGEN.md", "reference-images", "How the reference pictures are made: sheets, plates, props and keyframes on an image model."),
    ("docs/H3_TARGET.md", "h3-target", "The default video model, MiniMax H3 Ref2VA, in detail: its picture slots, sheets, voices and pacing."),
    ("docs/API.md", "api-reference", "The editor's HTTP API and the files behind it, for driving seriesmith from your own code."),
]
PAGE_OF = {src: page for src, page, _ in PAGES}
HEADER = "{/* Generated from %s by tools/make_site_docs.py: edit that file, not this one. */}\n"

FENCE = re.compile(r"^\s*(```|~~~)")
LINK = re.compile(r"(\]\()([^)\s]+)(\))")
AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")


def _target(href: str, src: str) -> str:
    """A link in `src` as the site has it: another doc's page, else the file on GitHub."""
    if re.match(r"^[a-z]+:|^#", href):
        return href
    path, _, anchor = href.partition("#")
    full = os.path.normpath(os.path.join(os.path.dirname(src), path)).replace(os.sep, "/")
    if full in PAGE_OF:
        return "/" + PAGE_OF[full] + (f"#{anchor}" if anchor else "")
    return GITHUB + full + (f"#{anchor}" if anchor else "")


def _escape(text: str) -> str:
    """Prose MDX would take for JSX or an expression, as text."""
    text = AUTOLINK.sub(r"[\1](\1)", text)
    text = text.replace("{", "\\{").replace("}", "\\}")
    return text.replace("<", "&lt;")


def _line(line: str, src: str) -> str:
    """A paragraph of prose: links retargeted, everything outside `code` escaped."""
    parts = re.split(r"(`+[^`]*`+)", line)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            # a code span wrapped onto the next line, joined (MDX reads a line's leading < as a tag)
            out.append(part.replace("\n", " "))
            continue
        out.append(LINK.sub(lambda m: m.group(1) + _target(m.group(2), src) + m.group(3), _escape(part)))
    return "".join(out)


def page(src: str, desc: str) -> str:
    with open(os.path.join(ROOT, src), encoding="utf-8") as f:
        lines = f.read().splitlines()
    title = src
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        lines = lines[1:]
    title = re.sub(r"`", "", title)
    # prose a paragraph at a time: a `code span` can wrap onto the next line
    body, para, fenced = [], [], False

    def flush():
        if para:
            body.extend(_line("\n".join(para), src).split("\n"))
            para.clear()

    for line in lines:
        if FENCE.match(line):
            flush()
            fenced = not fenced
            body.append(line)
        elif fenced:
            body.append(line)
        elif line.strip().startswith("<!--") and line.strip().endswith("-->"):
            flush()
        elif not line.strip():
            flush()
            body.append(line)
        else:
            para.append(line)
    flush()
    front = f"---\ntitle: {_yaml(title)}\ndescription: {_yaml(desc)}\n---\n\n"
    return front + HEADER % src + "\n" + "\n".join(body).strip("\n") + "\n"


def _yaml(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for src, name, desc in PAGES:
        text = page(src, desc)
        out = os.path.join(SITE, name + ".mdx")
        old = open(out, encoding="utf-8").read() if os.path.exists(out) else None
        if old == text:
            continue
        if check:
            stale.append(name)
        else:
            os.makedirs(SITE, exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"  wrote docs/site/{name}.mdx")
    if stale:
        print("out of date (python tools/make_site_docs.py): " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
