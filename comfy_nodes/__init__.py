"""seriesmith's ComfyUI nodes: render a shot through any Comfy API surface
(local through comfy-api-proxy, Comfy Cloud, a deployment) without touching
the episode folder. Install by linking this folder into ComfyUI's
custom_nodes (docs/SETUP.md)."""

from .shot import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
