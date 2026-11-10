"""A file a node is given by name: one uploaded to ComfyUI (its input folder), or one of
ComfyUI's own outputs or temp files, as `folder_paths.get_annotated_filepath` names them
("x.mp4", "x.mp4 [output]"). A name that reaches anywhere else (an absolute path, `..` out of
those folders, a link to a file elsewhere) is refused, as ComfyUI's own loaders refuse it."""
from __future__ import annotations

import os


def _real(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:                                    # another drive
        return False


def input_file(name: str) -> str:
    """`name`'s path, inside ComfyUI's input, output or temp folder ("" for no name).
    ValueError for one outside them."""
    name = (name or "").strip()
    if not name:
        return ""
    import folder_paths
    path = folder_paths.get_annotated_filepath(name)
    allowed = [folder_paths.get_input_directory(), folder_paths.get_output_directory(),
               folder_paths.get_temp_directory()]
    real = _real(path)
    if not any(_inside(real, _real(d)) for d in allowed if d):
        raise ValueError(f"{name!r} isn't a file in ComfyUI's input, output or temp folder")
    return path
