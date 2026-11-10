"""A release's notes for the Comfy Registry's Updates section, from its entry in docs/PLAN.md.

The Registry shows a version's changelog as plain text in one paragraph (no Markdown, line
breaks folded, the version list showing its first two lines), so the entry is flattened: its
lines joined, backticks dropped, PR numbers and the closing "Published by ..." sentence left out.

    python tools/release_notes.py 0.1.23           # prints the notes
    python tools/release_notes.py 0.1.23 -o FILE   # writes them (the publish workflow)

Exits 1 when PLAN has no entry for the version: a release always has one.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "PLAN.md")


def entry(text: str, version: str) -> str | None:
    """The PLAN entry for a version (`- [x] **0.1.22** (date, branch): ...` and its
    continuation lines), as written; None when there is none."""
    head = re.compile(r"^- \[[ x]\] \*\*" + re.escape(version) + r"\*\*")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if head.match(line):
            out = [line]
            for more in lines[i + 1:]:
                if not more.startswith("  ") or not more.strip():
                    break
                out.append(more)
            return "\n".join(out)
    return None


def notes(raw: str) -> str:
    """An entry as the Registry's one paragraph."""
    text = " ".join(part.strip() for part in raw.splitlines())
    text = re.sub(r"^- \[[ x]\] \*\*[^*]+\*\*\s*(\([^)]*\))?:?\s*", "", text)
    text = re.sub(r"\s*Published by[^.]*\.", "", text)
    text = re.sub(r"\(#\d+(?:, #\d+)*\)\s*", "", text)
    text = re.sub(r"\(#\d+:\s*", "(", text)
    text = text.replace("`", "")
    text = re.sub(r"\s+([;:,.)])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:1].upper() + text[1:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("version")
    ap.add_argument("-o", "--out", help="write the notes to this file")
    a = ap.parse_args(argv)
    with open(PLAN, encoding="utf-8") as f:
        raw = entry(f.read(), a.version)
    if raw is None:
        print(f"docs/PLAN.md has no entry for {a.version}", file=sys.stderr)
        return 1
    text = notes(raw)
    if a.out:
        sys.path.insert(0, ROOT)
        from seriesmith.core.fileio import write_bytes
        write_bytes(a.out, (text + "\n").encode("utf-8"))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
