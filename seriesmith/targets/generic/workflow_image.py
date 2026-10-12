"""
A user's image workflow as an image model for refs and keyframes: `"code":
"builtin:workflow_image"` in its target.json (inspector proposes it from the
graph). Refs and keyframes are worded as every image target words them
(targets/image/common.py); the graph is patched by refs.image_graph from
`binding.params` (prompt, seed, steps, cfg, size, model files, LoRAs) and its
saver put in place of the workflow's own (binding.saver), and this module
gives its LoadImage nodes the take's pictures:

    "binding": {"references": [{"class_type": "LoadImage", "title": "Face"},
                               {"class_type": "LoadImage", "index": 1}]}

in order -- an edit's source, a keyframe's characters then its plate, a
wardrobe variant's base view (refs.reference_images), as many as the graph
has slots (capabilities.max_refs). A slot past the last picture gets the last
one again, so the graph stays whole; a take with no picture at all is refused
(the workflow edits a picture: it's for keyframes and edits).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401


def slots(target, g: dict) -> list[str]:
    """The graph's LoadImage nodes the binding names, in its order."""
    specs = (target.spec.get("binding") or {}).get("references") or []
    loads = sorted((k for k, v in g.items() if v.get("class_type") == "LoadImage"),
                   key=lambda k: int(k) if str(k).isdigit() else 0)
    out = []
    for i, s in enumerate(specs):
        if s.get("title"):
            hit = [k for k in loads if ((g[k].get("_meta") or {}).get("title") or "").strip() == s["title"]]
        else:
            idx = int(s.get("index", i))
            hit = [loads[idx]] if idx < len(loads) else []
        if hit:
            out.append(hit[0])
    return out


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """The take's pictures into the workflow's LoadImage slots (`inputs`:
    {"references": [the names ComfyUI reads]})."""
    nodes = slots(target, g)
    if not nodes:
        return
    names = list((inputs or {}).get("references") or [])
    if not names:
        raise ValueError(f"{target.short or target.id} edits a picture: a take needs one to start "
                         f"from (use it for keyframes and edits; a character's first view is drawn "
                         f"by a text-to-image model)")
    for i, nid in enumerate(nodes):
        g[nid]["inputs"]["image"] = names[min(i, len(names) - 1)]
