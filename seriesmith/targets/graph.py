"""
Small reads and edits of an API-format graph ({id: {"class_type", "inputs",
"_meta"}}) that the targets' compile code and jobs share (they were copies in
ltx2, H3 FL2VA, the prose targets, the image targets and jobs). Stdlib only.
"""
from __future__ import annotations

import os


def of(g: dict, ctype: str, title: str | None = None) -> list[str]:
    """The ids of the nodes of class `ctype` (titled `title`, when given)."""
    return [k for k, v in g.items() if v["class_type"] == ctype
            and (title is None or (v.get("_meta") or {}).get("title") == title)]


def consumers(g: dict, nid: str, slot: int = 0) -> list[tuple[str, str]]:
    """(node, input name) of everything output `slot` of `nid` feeds."""
    return [(k, name) for k, v in g.items() for name, val in v["inputs"].items()
            if val == [nid, slot]]


def new_id(g: dict, stem: str) -> str:
    """An id not in the graph yet: `stem` with the first free number."""
    i = 1
    while f"{stem}{i}" in g:
        i += 1
    return f"{stem}{i}"


def abs_path(root: str, p: str) -> str:
    """`p` as given when absolute, else under `root` (an episode's file)."""
    return p if os.path.isabs(p) else os.path.join(root, p)
