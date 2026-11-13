"""
minimax_h3_image: MiniMax-H3-Image as an image target (target.json beside
this file) — text to image and edit from reference images in one graph.

`MiniMaxH3ImageConditioning` takes the prompt and any number of IMAGE inputs
(its autogrow group, named image_0, image_1, ...; sorted by that number, the
first is the picture to edit) and gives both the conditioning and the latent.
So which job this target does is decided per generate, by whether there are
references:

    references  -> one LoadImage per picture, wired into the node: an edit
    none        -> the LoadImage cut out; the node makes a blank latent at the
                   job's size: text to image

The node scales each reference itself (a 1024 px short edge for the text
encoder, up to 2048 for the VAE), so the graph has no resize nodes. The model
reads the references as "Picture 1", "Picture 2", ... (the node labels them
so for the text encoder), which `ref_word` "picture" matches.

Stdlib only.
"""
from __future__ import annotations

import copy

from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401

COND = "MiniMaxH3ImageConditioning"
LOAD_NODE = "LoadImage"
REF_INPUT = "images.image_{}"      # the node's autogrow group, counting from zero


def _node_of(g: dict, class_type: str) -> str | None:
    return next((k for k, v in g.items() if v.get("class_type") == class_type), None)


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """Wire `inputs["references"]` (the names ComfyUI's LoadImage reads, in
    order, at most capabilities.max_refs) into the conditioning node.

    The workflow carries one LoadImage feeding `images.image_0`; each further
    reference gets a copy of it and the next slot. With none, the LoadImage
    and the slot go, and the node works from the prompt alone."""
    cond, load = _node_of(g, COND), _node_of(g, LOAD_NODE)
    if cond is None or load is None:
        raise ValueError(f"a MiniMax-H3-Image workflow needs a {COND} and a {LOAD_NODE}")
    names = list(inputs.get("references") or [])[:target.capabilities().get("max_refs", 0)]
    node = g[cond]["inputs"]
    for k in [k for k in node if k.startswith("images.")]:
        node.pop(k)
    if not names:
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
