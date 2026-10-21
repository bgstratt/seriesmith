"""The repo as a ComfyUI node pack, as the Comfy Registry and ComfyUI-Manager
install it (the whole repo in custom_nodes): the nodes and the editor of
comfy_nodes/, with seriesmith/ found beside it. Linking comfy_nodes/ alone into
custom_nodes (INSTALL.md) loads the same pack."""

from .comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# ComfyUI reads it relative to this folder, not comfy_nodes/
WEB_DIRECTORY = "./comfy_nodes/web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
