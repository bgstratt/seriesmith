"""seriesmith's ComfyUI nodes: render a shot through any Comfy API surface
(local through comfy-api-proxy, Comfy Cloud, a deployment) without touching
the episode folder. Install by linking this folder into ComfyUI's
custom_nodes (docs/SETUP.md)."""

from .chain import NODE_CLASS_MAPPINGS as _CHAIN, NODE_DISPLAY_NAME_MAPPINGS as _CHAIN_NAMES
from .shot import NODE_CLASS_MAPPINGS as _SHOT, NODE_DISPLAY_NAME_MAPPINGS as _SHOT_NAMES

NODE_CLASS_MAPPINGS = {**_SHOT, **_CHAIN}
NODE_DISPLAY_NAME_MAPPINGS = {**_SHOT_NAMES, **_CHAIN_NAMES}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
