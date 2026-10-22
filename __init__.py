"""The repo as a ComfyUI node pack, as the Comfy Registry and ComfyUI-Manager
install it (the whole repo in custom_nodes): the nodes and the editor of
comfy_nodes/, with seriesmith/ found beside it. Linking comfy_nodes/ alone into
custom_nodes (INSTALL.md) loads the same pack."""

# ComfyUI loads this folder as a package. Anything else that imports the file
# on its own (pytest in a clone whose folder isn't named seriesmith) has no
# package to be relative to: it gets nothing, rather than an ImportError that
# stops every test being collected.
if __package__:
    from .comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
else:
    NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = {}, {}

# ComfyUI reads it relative to this folder, not comfy_nodes/
WEB_DIRECTORY = "./comfy_nodes/web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
