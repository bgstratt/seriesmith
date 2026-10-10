"""
A round trip through a ComfyUI backend with core nodes only: a small picture
goes up, is inverted, and comes back. What `seriesmith backends --try` runs
to show a backend works end to end (upload, submit, progress, download).
"""
from __future__ import annotations

import os
import struct
import tempfile
import zlib

from seriesmith.backends import Backend, BackendError, File


def png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A solid-colour PNG, stdlib only."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def png_first_pixel(data: bytes) -> tuple[int, ...]:
    """The top-left pixel of an 8-bit RGB or RGBA PNG (the first row is
    unfiltered or Sub-filtered, which leaves its first pixel as stored)."""
    pos, idat = 8, b""
    channels = 3
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            channels = {2: 3, 6: 4}.get(body[9], 3)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    return tuple(raw[1:1 + channels])[:3]


SMOKE_IN = (200, 40, 10)
SMOKE_OUT = tuple(255 - c for c in SMOKE_IN)


def graph(picture: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": File(picture)}},
        "2": {"class_type": "ImageInvert", "inputs": {"image": ["1", 0]}},
        "3": {"class_type": "SaveImage",
              "inputs": {"images": ["2", 0], "filename_prefix": "seriesmith_smoke"}},
    }


def round_trip(backend: Backend, folder: str | None = None, on_progress=None,
               on_status=None) -> str:
    """Run the round trip on `backend`; returns the downloaded picture's path.
    BackendError says what went wrong."""
    folder = folder or tempfile.mkdtemp(prefix="seriesmith_smoke_")
    src = os.path.join(folder, "smoke_in.png")
    with open(src, "wb") as fh:
        fh.write(png(48, 32, SMOKE_IN))
    run = backend.submit(graph(src))
    status = run.watch(on_progress=on_progress, on_status=on_status)
    if status != "succeeded":
        raise BackendError(f"{backend.name}: the round trip ended {status}: {run.error}")
    saved = [o for o in run.outputs() if o.node == "3"]
    if not saved:
        raise BackendError(f"{backend.name}: the job succeeded but returned no picture "
                           f"(outputs: {[(o.node, o.name) for o in run.outputs()]})")
    out = saved[0].save(os.path.join(folder, "smoke_out.png"))
    with open(out, "rb") as fh:
        data = fh.read()
    size = png_size(data)
    if size != (48, 32):
        raise BackendError(f"{backend.name}: the picture came back {size[0]}x{size[1]}, "
                           f"not 48x32")
    pixel = png_first_pixel(data)
    # ComfyUI works in floats and truncates on save, so a level can come back
    # one lower (200 inverted reads 54, not 55)
    if any(abs(a - b) > 1 for a, b in zip(pixel, SMOKE_OUT)):
        raise BackendError(f"{backend.name}: the picture came back {pixel}, not inverted "
                           f"{SMOKE_OUT}")
    return out
