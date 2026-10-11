"""seriesmith's ComfyUI nodes: render a shot through any Comfy API surface
(local through comfy-api-proxy, Comfy Cloud, a deployment) without touching
the episode folder. Install by linking this folder into ComfyUI's
custom_nodes (docs/SETUP.md)."""

from .finish import NODE_CLASS_MAPPINGS as _FIN, NODE_DISPLAY_NAME_MAPPINGS as _FIN_NAMES
from .chain import NODE_CLASS_MAPPINGS as _CHAIN, NODE_DISPLAY_NAME_MAPPINGS as _CHAIN_NAMES
from .shot import NODE_CLASS_MAPPINGS as _SHOT, NODE_DISPLAY_NAME_MAPPINGS as _SHOT_NAMES
from .upscale import NODE_CLASS_MAPPINGS as _UP, NODE_DISPLAY_NAME_MAPPINGS as _UP_NAMES

NODE_CLASS_MAPPINGS = {**_SHOT, **_CHAIN, **_UP, **_FIN}
NODE_DISPLAY_NAME_MAPPINGS = {**_SHOT_NAMES, **_CHAIN_NAMES, **_UP_NAMES, **_FIN_NAMES}

# the editor, inside ComfyUI: its page (web/seriesmith-editor.js, `npm run
# build` in web/) and its API on ComfyUI's own server (seriesmith.server.
# comfyui). It needs the seriesmith package in ComfyUI's Python (`pip install
# -e <this repo>` with that Python, docs/SETUP.md); without it the nodes still
# load and the editor stays off.
WEB_DIRECTORY = "./web"
try:
    from seriesmith.server import comfyui as _host
    _host.register_on_prompt_server()
except Exception as _e:                                   # noqa: BLE001  never stop the nodes loading
    import logging
    logging.getLogger("seriesmith").warning(
        "seriesmith: the editor is off in this ComfyUI (%s): pip install -e the seriesmith "
        "repo with ComfyUI's Python", _e)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
