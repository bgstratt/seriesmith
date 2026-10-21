"""
fibo2_dev: Bria's Fibo 2.0 Dev as an image target (target.json beside this
file) -- text to image and edit from reference images in one graph.
fibo2_edit_turbo, the step-distilled edit checkpoint, uses this file's graph
code.

`TextEncodeFibo2` (ComfyUI's native Fibo 2.0 node) takes the prompt and any
number of IMAGE inputs (its autogrow group, named image_1, image_2, ...) and
returns the positive and negative conditioning, each with the images as
reference latents, and the empty latent of the result's size. So which job
this target does is decided per generate, by whether there are references:

    references  -> one LoadImage per picture, wired into the encoder: an edit
    none        -> the LoadImage cut out: text to image at the job's size

Series refs and keyframes are worded as every image target words them
(targets/image/common.py).

Stdlib only.
"""
from __future__ import annotations

import copy

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401

ENCODER = "TextEncodeFibo2"
LOAD_NODE = "LoadImage"
REF_INPUT = "images.image_{}"      # the node's autogrow group, image_1..image_16
REF_BASE = 1                       # ...counting from one


def _node_of(g: dict, class_type: str) -> str | None:
    return next((k for k, v in g.items() if v.get("class_type") == class_type), None)


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """Wire `inputs["references"]` (the names ComfyUI's LoadImage reads, in
    order, at most capabilities.max_refs) into the encoder. The workflow
    carries one LoadImage feeding `images.image_1`; each further reference
    gets a copy of it and the next slot. With none, the LoadImage and the
    slots go and the graph is text to image."""
    enc, load = _node_of(g, ENCODER), _node_of(g, LOAD_NODE)
    if enc is None or load is None:
        raise ValueError(f"a Fibo 2.0 workflow needs a {ENCODER} and a {LOAD_NODE}")
    names = list(inputs.get("references") or [])[:target.capabilities().get("max_refs", 0)]
    for k in [k for k in g[enc]["inputs"] if k.startswith("images.")]:
        g[enc]["inputs"].pop(k)
    if not names:
        g.pop(load, None)
        return
    g[load]["inputs"]["image"] = names[0]
    g[enc]["inputs"][REF_INPUT.format(REF_BASE)] = [load, 0]
    nid = max((int(k) for k in g if str(k).isdigit()), default=0)
    for i, name in enumerate(names[1:], start=REF_BASE + 1):
        nid += 1
        extra = str(nid)
        g[extra] = copy.deepcopy(g[load])
        g[extra]["inputs"]["image"] = name
        if "_meta" in g[extra]:
            g[extra]["_meta"] = dict(g[extra]["_meta"], title=f"Reference {i}")
        g[enc]["inputs"][REF_INPUT.format(i)] = [extra, 0]
