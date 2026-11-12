"""
counts.py — people and faces in each sampled frame of a take (countcheck.py's measure).

Run in a Python that has ultralytics, PyAV and torch (ComfyUI's, where the Impact Subpack
puts them), as one of the package's modules:

    python _run.py seriesmith.helpers.counts VIDEO --person P.pt --face F.pt [--fps 8]

prints one JSON object on stdout: {"fps", "frames": [[t, people, faces], ...]}, or
{"error"} (and exits 1). On the CPU: the GPU stays ComfyUI's.

The weights are PyTorch pickles, which can run code as they load. So a file is loaded only
when its sha256 is the one countcheck.WEIGHTS records (checked here, just before loading):
another file of the same name is refused, never loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trusted(path: str, kind: str) -> str:
    """`path`, once its sha256 is the recorded one for `kind`; ValueError otherwise."""
    from seriesmith.countcheck import WEIGHTS
    want = WEIGHTS[kind]["sha256"]
    got = sha256(path)
    if got != want:
        raise ValueError(f"{os.path.basename(path)} isn't the file seriesmith knows "
                         f"(sha256 {got[:12]}…, expected {want[:12]}…): not loaded")
    return path


def frames(video: str, fps: float):
    """(t, an RGB frame as a numpy array) at about `fps`, from the first frame on."""
    import av
    with av.open(video) as cont:
        stream = cont.streams.video[0]
        rate = float(stream.average_rate or stream.guessed_rate or 24)
        step = max(1, round(rate / fps))
        for i, f in enumerate(cont.decode(stream)):
            if i % step == 0:
                yield round(i / rate, 3), f.to_ndarray(format="rgb24")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--person", required=True)
    ap.add_argument("--face", required=True)
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--conf", type=float, default=0.5)
    a = ap.parse_args(argv)
    try:
        person_pt, face_pt = trusted(a.person, "person"), trusted(a.face, "face")
        from ultralytics import YOLO
        person, face = YOLO(person_pt), YOLO(face_pt)
        rows = []
        for t, rgb in frames(a.video, a.fps):
            bgr = rgb[:, :, ::-1]
            n = [int((m(bgr, verbose=False, conf=a.conf, device="cpu")[0].boxes.conf >= a.conf).sum())
                 for m in (person, face)]
            rows.append([t, n[0], n[1]])
    except Exception as e:                      # noqa: BLE001  said to the caller, as JSON
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:300]}"}))
        return 1
    print(json.dumps({"fps": a.fps, "frames": rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
