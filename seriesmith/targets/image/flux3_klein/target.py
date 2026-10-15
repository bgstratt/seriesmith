"""
flux3_klein: FLUX.3 Image Klein (the base checkpoint) as an image target
(target.json beside this file) — text to image and edit from reference images
in one graph. flux3_klein_turbo, the step-distilled checkpoint, uses this
file's graph code.

`ReferenceMultiLatent` takes the positive and negative conditioning and any
number of IMAGE inputs (its autogrow group, named image0, image1, ...),
VAE-encodes each and appends it to both conditionings. The sampler starts
from an `EmptyFlux2LatentImage` at the job's size either way, so which job
this target does is decided per generate, by whether there are references:

    references  -> one LoadImage per picture, wired into the node: an edit
    none        -> the node and its LoadImage cut out, the sampler reading
                   the prompts themselves: text to image

Series refs and keyframes are worded as every image target words them
(targets/image/common.py); BFL's model card has the references named by
their order ("the first image, the second image"), as `ref_word` "image"
numbers them.

Stdlib only.
"""
from __future__ import annotations

import copy

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401

REFS = "ReferenceMultiLatent"
LOAD_NODE = "LoadImage"
REF_INPUT = "images.image{}"       # the node's autogrow group, counting from zero


def _node_of(g: dict, class_type: str) -> str | None:
    return next((k for k, v in g.items() if v.get("class_type") == class_type), None)


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """Wire `inputs["references"]` (the names ComfyUI's LoadImage reads, in
    order, at most capabilities.max_refs) into the ReferenceMultiLatent.

    The workflow carries one LoadImage feeding `images.image0`; each further
    reference gets a copy of it and the next slot. With none, the node goes
    and whatever read its positive and negative reads what fed them."""
    refs, load = _node_of(g, REFS), _node_of(g, LOAD_NODE)
    if refs is None or load is None:
        raise ValueError(f"a FLUX.3 Klein workflow needs a {REFS} and a {LOAD_NODE}")
    names = list(inputs.get("references") or [])[:target.capabilities().get("max_refs", 0)]
    node = g[refs]["inputs"]
    for k in [k for k in node if k.startswith("images.")]:
        node.pop(k)
    if not names:
        feeds = {0: node.get("positive"), 1: node.get("negative") or node.get("positive")}
        for v in g.values():
            for name, val in (v.get("inputs") or {}).items():
                if isinstance(val, list) and len(val) == 2 and val[0] == refs:
                    v["inputs"][name] = copy.deepcopy(feeds[val[1]])
        g.pop(refs)
        g.pop(load)
        return
    g[load]["inputs"]["image"] = names[0]
    node[REF_INPUT.format(0)] = [load, 0]
    nid = max((int(k) for k in g if str(k).isdigit()), default=0)
    for i, name in enumerate(names[1:], start=1):
        nid += 1
        extra = str(nid)
        g[extra] = copy.deepcopy(g[load])
        g[extra]["inputs"]["image"] = name
        if "_meta" in g[extra]:
            g[extra]["_meta"] = dict(g[extra]["_meta"], title=f"Reference {i + 1}")
        node[REF_INPUT.format(i)] = [extra, 0]
