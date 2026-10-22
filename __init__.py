"""The repo as a ComfyUI node pack, as the Comfy Registry and ComfyUI-Manager
install it (the whole repo in custom_nodes): the nodes and the editor of
comfy_nodes/, with seriesmith/ found beside it. Linking comfy_nodes/ alone into
custom_nodes (INSTALL.md) loads the same pack."""

import sys

# The nodes only when ComfyUI is loading the pack (it has folder_paths loaded
# before any custom node). pytest imports this file too, in a clone whose
# folder isn't named seriesmith: as a module with no package to be relative
# to, or as a package whose nodes want ComfyUI's torch. Either way it gets
# nothing, rather than an error that stops every test being collected.
if __package__ and "folder_paths" in sys.modules:
    from .comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
else:
    NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = {}, {}

# ComfyUI reads it relative to this folder, not comfy_nodes/
WEB_DIRECTORY = "./comfy_nodes/web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
