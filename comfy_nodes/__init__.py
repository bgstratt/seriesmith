"""seriesmith's ComfyUI nodes: render a shot through any Comfy API surface
(this ComfyUI, Comfy Cloud, a deployment) without touching the episode
folder. Install by linking this folder into ComfyUI's custom_nodes
(INSTALL.md); nothing needs installing into ComfyUI's Python."""

from .finish import NODE_CLASS_MAPPINGS as _FIN, NODE_DISPLAY_NAME_MAPPINGS as _FIN_NAMES
from .chain import NODE_CLASS_MAPPINGS as _CHAIN, NODE_DISPLAY_NAME_MAPPINGS as _CHAIN_NAMES
from .shot import NODE_CLASS_MAPPINGS as _SHOT, NODE_DISPLAY_NAME_MAPPINGS as _SHOT_NAMES
from .upscale import NODE_CLASS_MAPPINGS as _UP, NODE_DISPLAY_NAME_MAPPINGS as _UP_NAMES

NODE_CLASS_MAPPINGS = {**_SHOT, **_CHAIN, **_UP, **_FIN}
NODE_DISPLAY_NAME_MAPPINGS = {**_SHOT_NAMES, **_CHAIN_NAMES, **_UP_NAMES, **_FIN_NAMES}


def _find_seriesmith() -> None:
    """The seriesmith package importable: pip-installed, else the repo this
    folder is linked from (its parent, the link resolved), put on sys.path.
    Everything it needs at load (aiohttp, Pillow, numpy) ComfyUI has."""
    import importlib.util
    import os
    import sys
    if importlib.util.find_spec("seriesmith") is not None:
        return
    repo = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if os.path.isfile(os.path.join(repo, "seriesmith", "__init__.py")) and repo not in sys.path:
        sys.path.append(repo)


# the editor, inside ComfyUI: its page (web/seriesmith-editor.js, `npm run
# build` in web/) and its API on ComfyUI's own server (seriesmith.server.
# comfyui). Without the seriesmith package (this folder copied rather than
# linked from the repo) the nodes still load and the editor stays off.
WEB_DIRECTORY = "./web"
try:
    _find_seriesmith()
    from seriesmith.server import comfyui as _host
    _host.register_on_prompt_server()
except Exception as _e:                                   # noqa: BLE001  never stop the nodes loading
    import logging
    logging.getLogger("seriesmith").warning(
        "seriesmith: the editor is off in this ComfyUI (%s): link this folder from the "
        "seriesmith repo (INSTALL.md) rather than copying it", _e)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
