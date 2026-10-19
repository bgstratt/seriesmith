"""
seriesmith shot nodes: render one shot through any Comfy API surface.

Nothing here reads or writes the episode folder. seriesmith uploads what a
shot needs and gives it to the loader; the saver writes into ComfyUI's own
output folder and reports every file, so the backend (local ComfyUI through
comfy-api-proxy, Comfy Cloud, a deployment) hands them back and seriesmith
writes the take (docs/DESIGN.md, "seriesmith writes the takes").

Nodes
-----
SeriesmithShotLoader   the shot (its frozen one-shot shotlist, as JSON text)
                       and its reference files (uploaded inputs) -> everything
                       MiniMaxH3ReferenceToVideo needs
SeriesmithSaveTake     writes the take's mp4, sound, thumbnails, latent and a
                       record of what it did into
                       <output>/seriesmith/<run>/, and reports each file

Reference slots
---------------
    <Picture 1..3>  the shot's subjects, characters first then props/vehicles
    <Picture 4>     the location plate, always

There is no style reference image. Style is already carried by every sheet and
plate (all drawn in it) and stated in the prompt text, so slot 4 buys concrete
layout, palette, lighting direction and depth instead -- and keeps one location
looking like one place across every cut in a sequence.

Ported from h3pipe's comfy_nodes/h3_shotlist.py (H3ShotListLoader, H3SaveShot).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import tempfile
import time

import numpy as np
import torch

try:
    from . import _ff
    from . import shotplan as _plan
except ImportError:                       # this file loaded on its own (a test), not as the pack
    import importlib.util as _iu

    def _sibling(name: str, as_name: str):
        spec = _iu.spec_from_file_location(
            as_name, os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py"))
        mod = _iu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    _ff = _sibling("_ff", "seriesmith_nodes_ff")
    _plan = _sibling("shotplan", "seriesmith_nodes_shotplan")

# ---------------------------------------------------------------------------
# H3 constants (the frame grid, the policies and panel modes: shotplan.py)
# ---------------------------------------------------------------------------

GRID_STEP, GRID_BASE, GRID_MAX = _plan.GRID_STEP, _plan.GRID_BASE, _plan.GRID_MAX

# Take thumbnails. STRIP_FRAMES must match takes.STRIP_FRAMES: the editor
# reads the strip as that many equal-width cells.
STRIP_FRAMES = 8
THUMB_LONG_SIDE = 480
STRIP_CELL_WIDTH = 192
JPEG_QUALITY = 85
AUDIO_POLICIES = _plan.AUDIO_POLICIES
PANEL_MODES = _plan.PANEL_MODES
snap_up = _plan.snap_up


# RGB frames to HD video the way every player reads HD: the BT.709 matrix,
# limited range, and all four colour tags written. ffmpeg's own conversion is
# BT.601 and untagged, which YouTube, browsers and HD players decode as
# BT.709: reds go orange and skin shifts (measured 2026-10-05: pure red came
# out Y 81, BT.601's value, where BT.709's is 63). Takes, upscales and
# renders all encode through this; assemble converts the older BT.601 takes.
RGB_TO_BT709 = ("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
                "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709")


def encode_av(images, mp4: str, fps: float, audio_path: str | None = None) -> None:
    """The take's mp4 as the ffmpeg command writes it (H.264 CRF 16, yuv420p,
    BT.709 limited range with all four colour tags, AAC 192k from a PCM wav,
    exactly as many frames as given), through PyAV: ffmpeg's own libraries,
    which ComfyUI installs (`av` in its requirements), for a machine with no
    ffmpeg on PATH. ImportError without PyAV."""
    import av
    from fractions import Fraction

    n, h, w = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
    rate = Fraction(fps).limit_denominator(1001)
    arr = (images[..., :3].clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
    tmp = mp4 + ".part.mp4"
    out = av.open(tmp, "w")
    try:
        vs = out.add_stream("libx264", rate=rate)
        vs.width, vs.height = w - w % 2, h - h % 2     # yuv420p needs even sides
        vs.pix_fmt = "yuv420p"
        vs.options = {"crf": "16"}
        cc = vs.codec_context
        for k, v in (("color_range", 1), ("colorspace", 1), ("color_primaries", 1),
                     ("color_trc", 1)):                # 1: MPEG (tv) range / BT.709
            try:
                setattr(cc, k, v)
            except (AttributeError, TypeError, ValueError):
                pass
        ast = None
        if audio_path:
            pcm, sr = _read_pcm_wav(audio_path)
            ast = out.add_stream("aac", rate=sr)
            ast.bit_rate = 192_000
            ast.layout = "stereo" if pcm.shape[0] > 1 else "mono"
        for i in range(n):
            frame = av.VideoFrame.from_ndarray(arr[i, :vs.height, :vs.width], format="rgb24")
            frame = frame.reformat(format="yuv420p", dst_colorspace="ITU709",
                                   dst_color_range="MPEG")
            frame.pts = i
            for packet in vs.encode(frame):
                out.mux(packet)
        for packet in vs.encode():
            out.mux(packet)
        if ast is not None:
            data = pcm[:2].numpy().astype(np.float32)
            chunk = 1024
            for start in range(0, data.shape[1], chunk):
                af = av.AudioFrame.from_ndarray(np.ascontiguousarray(data[:, start:start + chunk]),
                                                format="fltp", layout=ast.layout.name)
                af.sample_rate = sr
                af.pts = start
                for packet in ast.encode(af):
                    out.mux(packet)
            for packet in ast.encode():
                out.mux(packet)
    finally:
        out.close()
    os.replace(tmp, mp4)


def _blank(h: int = 64, w: int = 64) -> torch.Tensor:
    return torch.zeros((1, h, w, 3), dtype=torch.float32)


# An unused subject socket's picture (H3's smallest canvas): it holds the
# socket's number so the plate stays <Picture 4> (shotplan.plan_shot).
PLACEHOLDER_SIZE = _plan.PLACEHOLDER_SIZE


def _neutral(h: int, w: int) -> torch.Tensor:
    """Flat mid-grey: the stand-in for a missing reference picture when the
    shot is rendered anyway (`missing_refs: blank`). It carries no layout,
    colour or identity, so the prompt does the work -- close to text-to-video."""
    return torch.full((1, h, w, 3), 0.5, dtype=torch.float32)


# ---------------------------------------------------------------------------
# Image / audio IO
#
# Audio deliberately avoids torchaudio. As of 2.13 it routes both load and save
# through torchcodec and raises ImportError when that is absent, which turns
# "write a wav" into an install problem. PCM wav needs no library, so the
# stdlib handles it, torchaudio is tried only as a middle option, and ffmpeg
# covers mp3/m4a/flac. Nothing here adds a dependency.
# ---------------------------------------------------------------------------

def load_image(path: str) -> torch.Tensor:
    """Load an image as a ComfyUI IMAGE tensor, [1, H, W, 3] float32 0..1."""
    from PIL import Image, ImageOps

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def crop_panels(sheet: torch.Tensor, panels: int, keep: list[int]) -> torch.Tensor:
    """Take a horizontal N-panel strip and keep a subset of panels.

    The strip's short side is the vertical one, which is what H3 scales to
    2048 in `max` mode — so dropping panels narrows the image without
    costing per-panel resolution. It is a pure reference-cost reduction.
    """
    _, h, w, _ = sheet.shape
    box = _plan.crop_box(w, panels, keep)
    if box == [(0, w)]:
        return sheet
    # contiguous runs stay contiguous so the result is still a clean strip
    return torch.cat([sheet[:, :, x0:x1, :] for x0, x1 in box], dim=2)


def _read_pcm_wav(path: str) -> tuple[torch.Tensor, int]:
    """Read an integer PCM wav with the stdlib. Raises for anything exotic."""
    import wave

    with wave.open(path, "rb") as w:
        ch, width, sr, frames = (w.getnchannels(), w.getsampwidth(),
                                 w.getframerate(), w.getnframes())
        raw = w.readframes(frames)
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    return torch.from_numpy(a.reshape(-1, ch).T.copy()), sr


def _ffmpeg_decode(path: str) -> tuple[torch.Tensor, int]:
    """Last resort: let ffmpeg turn anything into a PCM wav we can read."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "decoded.wav")
        try:
            subprocess.run(
                [*_ff.tool("ffmpeg"), "-y", "-v", "error", "-i", path,
                 "-acodec", "pcm_s16le", out],
                check=True, capture_output=True, timeout=300)
        except FileNotFoundError:
            raise RuntimeError(
                f"cannot decode {os.path.basename(path)}: it is not a plain PCM wav "
                f"and ffmpeg is not on PATH. Convert it to 16-bit wav, or install "
                f"ffmpeg.") from None
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"ffmpeg could not decode {os.path.basename(path)}: "
                f"{exc.stderr.decode('utf-8', 'replace')[-200:]}") from None
        return _read_pcm_wav(out)


def _decode_audio(path: str) -> tuple[torch.Tensor, int]:
    """Decode to [C, T] float32 in -1..1, without depending on torchaudio.

    torchaudio 2.13 delegates both load and save to torchcodec and raises
    ImportError when it is absent — which is a hard failure for something as
    ordinary as reading a wav. The stdlib handles PCM wav natively, so try that
    first, then torchaudio if it happens to work, then ffmpeg for mp3/m4a/flac.
    """
    if path.lower().endswith(".wav"):
        try:
            return _read_pcm_wav(path)
        except Exception:
            pass                      # float or compressed wav — fall through
    try:
        import torchaudio
        return torchaudio.load(path)
    except Exception:
        pass
    return _ffmpeg_decode(path)


def load_audio(path: str, start: float | None = None,
               end: float | None = None) -> dict:
    """Load audio as a ComfyUI AUDIO dict, optionally slicing [start, end)."""
    waveform, sr = _decode_audio(path)          # [C, T]
    if start is not None:
        a = max(0, int(start * sr))
        b = int(end * sr) if end is not None else waveform.shape[-1]
        b = min(b, waveform.shape[-1])
        if b <= a:
            raise ValueError(
                f"empty audio slice {start}..{end} from {os.path.basename(path)} "
                f"(the file is only {waveform.shape[-1] / sr:.2f}s long)")
        waveform = waveform[:, a:b]
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sr}


def silent_audio(seconds: float = 0.1, sr: int = 44100) -> dict:
    n = max(1, int(seconds * sr))
    return {"waveform": torch.zeros((1, 1, n), dtype=torch.float32), "sample_rate": sr}


def save_audio(audio: dict, path: str) -> None:
    """Write a 16-bit PCM wav with the stdlib.

    Deliberately not torchaudio.save: as of 2.13 it routes through torchcodec
    and raises ImportError without it. Writing the wav directly removes a
    dependency rather than adding one, and cannot break when torchaudio
    changes backends again.
    """
    import wave

    wav = audio["waveform"]
    if wav.dim() == 3:
        wav = wav[0]                                   # [B, C, T] -> [C, T]
    if wav.dim() == 1:
        wav = wav.unsqueeze(0)
    arr = wav.detach().cpu().float().clamp(-1.0, 1.0).numpy()
    pcm = np.round(arr.T * 32767.0).astype("<i2")      # [T, C], interleaved
    with wave.open(path, "wb") as w:
        w.setnchannels(int(pcm.shape[1]))
        w.setsampwidth(2)
        w.setframerate(int(audio["sample_rate"]))
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# SeriesmithShotLoader
# ---------------------------------------------------------------------------

# How many files one shot can bring: three subjects, a plate, three voice
# samples and a recording, with room to spare.
MAX_FILES = 24


def file_input(i: int) -> str:
    return f"file_{i:02d}"


class SeriesmithShotLoader:
    """Emit one shot's worth of Ref2VA conditioning from its frozen shotlist.

    `shotlist` is the take's one-shot shotlist as JSON text. `files` is a JSON
    list of the episode-relative paths that shotlist names (sheets, the plate,
    voice samples, the recording); `file_00`, `file_01`, ... are those files,
    uploaded, in the same order: each holds the name ComfyUI's input folder
    knows it by. A path the shotlist names that isn't in `files` counts as
    missing."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shotlist": ("STRING", {"multiline": True, "default": "{}"}),
                "files": ("STRING", {"multiline": True, "default": "[]"}),
                "index": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "panel_mode": (PANEL_MODES, {"default": "auto"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 1.0}),
            },
            "optional": {
                "resolution_override": ("STRING", {"default": ""}),
                **{file_input(i): ("STRING", {"default": ""}) for i in range(MAX_FILES)},
            },
        }

    RETURN_TYPES = (
        "STRING", "STRING",
        "IMAGE", "IMAGE", "IMAGE", "IMAGE",
        "AUDIO", "AUDIO", "AUDIO",
        "INT", "INT", "INT", "INT", "INT",
        "STRING", "STRING", "INT",
    )
    RETURN_NAMES = (
        "shot_id", "prompt",
        "ref_1", "ref_2", "ref_3", "ref_bg",
        "ref_audio_1", "ref_audio_2", "ref_audio_3",
        "width", "height", "length", "steps", "seed",
        "audio_policy", "info", "shot_count",
    )
    FUNCTION = "load"
    CATEGORY = "seriesmith"

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _resolver(files: str, uploaded: dict):
        """path -> the uploaded file's place in ComfyUI's input folder ("" when
        the shot's files don't include it)."""
        import folder_paths

        try:
            names = json.loads(files or "[]")
        except ValueError:
            raise ValueError(f"files must be a JSON list of paths, got {files[:80]!r}") from None
        if len(names) > MAX_FILES:
            raise ValueError(f"{len(names)} files, but the loader takes at most {MAX_FILES}")
        where = {}
        for i, rel in enumerate(names):
            name = (uploaded.get(file_input(i)) or "").strip()
            if name:
                where[str(rel).replace("\\", "/")] = folder_paths.get_annotated_filepath(name)

        def resolve(path: str) -> str:
            return where.get(str(path or "").replace("\\", "/"), "") if path else ""
        return resolve

    # -- main --------------------------------------------------------------

    def load(self, shotlist, files, index, panel_mode, fps, resolution_override="",
             **uploaded):
        resolve = self._resolver(files, uploaded)
        try:
            doc = json.loads(shotlist)
        except ValueError as exc:
            raise ValueError(f"shotlist is not JSON: {exc}") from None

        # what to send (shotplan.py: the same plan seriesmith makes for a
        # ComfyUI without this pack), then the pictures and sounds it names
        plan = _plan.plan_shot(doc, index, panel_mode, fps, resolution_override, resolve)

        def picture(spec: dict) -> torch.Tensor:
            if "neutral" in spec:
                return _neutral(*spec["neutral"])
            return crop_panels(load_image(spec["path"]), spec["panels"], spec["keep"])

        refs = [picture(r) for r in plan["refs"]]
        ref_bg = picture(plan["bg"])
        sizes = [None if "neutral" in r else (int(t.shape[2]), int(t.shape[1]))
                 for r, t in zip(plan["refs"], refs)]
        audio_refs = [None if a is None else
                      load_audio(a["path"]) if a["start"] is None else
                      load_audio(a["path"], a["start"], a["end"])
                      for a in plan["audio"]]
        info = _plan.info_text(plan, sizes)

        print(f"[seriesmith] shot {plan['pos'] + 1}/{plan['count']}  {plan['label']}  "
              f"{plan['width']}x{plan['height']}  {plan['length']}f "
              f"({plan['length'] / fps:.2f}s)  {plan['steps']} steps  "
              f"{plan['policy']}", flush=True)

        return (
            plan["id"], plan["prompt"],
            refs[0], refs[1], refs[2], ref_bg,
            audio_refs[0], audio_refs[1], audio_refs[2],
            plan["width"], plan["height"], plan["length"], plan["steps"], plan["seed"],
            plan["policy"], info, plan["count"],
        )


# ---------------------------------------------------------------------------
# SeriesmithSaveTake
# ---------------------------------------------------------------------------

def loaded_refs(info: str) -> list[str]:
    """The reference lines of SeriesmithShotLoader's `info` (under "refs:", and a
    RENDERED WITHOUT line), as a take records them; [] for none."""
    out, inside = [], False
    for line in (info or "").splitlines():
        if line.startswith("RENDERED WITHOUT"):
            out.append(line.strip())
        elif line.strip() == "refs:":
            inside = True
        elif inside and line.startswith("  "):
            out.append(line.strip())
        elif inside:
            inside = False
    return out


def chain_record(text: str) -> dict | None:
    """H3ChainLatent's `record` (JSON) as a dict, else None."""
    try:
        rec = json.loads(text) if text else None
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def _write_json_atomic(path: str, data) -> None:
    """Same bytes and atomicity as takes.write_json (not importable here):
    temp file in the same folder, then os.replace; LF, indent 2, trailing newline."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


LATENT_FORMAT = "h3pipe-latent/1"


def save_latent(latent: dict, path: str, **meta) -> str:
    """Write a sampler's LATENT to `path` (safetensors, atomically); return its
    name. A joint AV latent (H3: a NestedTensor of video and audio) is stored
    as `video` and `audio`; a plain one as `samples`. `meta` (width, height,
    frames, fps) goes into the header with the format and the stream names."""
    from safetensors.torch import save_file

    samples = latent["samples"]
    parts = list(samples.unbind()) if getattr(samples, "is_nested", False) else [samples]
    if len(parts) == 2:
        names = ["video", "audio"]
    elif len(parts) == 1:
        names = ["samples"]
    else:
        names = [f"stream_{i}" for i in range(len(parts))]
    tensors = {n: t.detach().to("cpu").contiguous() for n, t in zip(names, parts)}
    header = {"format": LATENT_FORMAT, "streams": ",".join(names)}
    header.update({k: str(v) for k, v in meta.items()})
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".safetensors",
                               dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    try:
        save_file(tensors, tmp, metadata=header)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return os.path.basename(path)


def load_latent(path: str) -> dict:
    """The LATENT save_latent wrote: `video` and `audio` back as one joint AV
    latent (a NestedTensor), `samples` as a plain one."""
    import comfy.nested_tensor
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as fh:
        header = fh.metadata() or {}
        names = (header.get("streams") or "").split(",") if header.get("streams") else list(fh.keys())
        parts = [fh.get_tensor(n) for n in names]
    if len(parts) == 1:
        return {"samples": parts[0]}
    return {"samples": comfy.nested_tensor.NestedTensor(parts)}


def _now() -> str:
    """ISO-8601 local time with offset, seconds precision (as takes.now)."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class SeriesmithSaveTake:
    """Write one take's files into <output>/seriesmith/<run>/ and report each,
    so whatever runs the job can hand them back.

        <shot_id>_t<take>.mp4          picture + the audio the policy selects
        <shot_id>_t<take>_h3.wav       H3's generated mix, always kept
        <shot_id>_t<take>_foley.wav    vocal-stripped bed (dub_keep_foley only)
        <shot_id>_t<take>.jpg          middle frame, longest side 480 px
        <shot_id>_t<take>_strip.jpg    STRIP_FRAMES frames side by side, 192 px
                                       wide each, for hover scrub
        <shot_id>_t<take>.latent.safetensors
                                       the sampled latent, when `latent` is
                                       linked: what an upscale starts from
        <shot_id>_t<take>.record.json  what the saver did: status, finished,
                                       frames, fps, mp4, thumb, strip, latent,
                                       save_notes, save_ms, loaded_refs,
                                       continued_from -- the fields seriesmith
                                       merges into the take's record
        frames/<shot_id>_t<take>_%06d.png   optional PNG sequence (not reported)

    `run` names the folder, one per job, so two jobs never share one. The mp4
    comes first: a failure writing thumbnails or the latent is reported in the
    record and never raised.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "shot_id": ("STRING", {"forceInput": True}),
                "audio_policy": ("STRING", {"forceInput": True}),
                "run": ("STRING", {"default": "take"}),
                "take": ("INT", {"default": 1, "min": 1, "max": 999}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 1.0}),
                "save_frames": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "audio": ("AUDIO",),
                # the sampler's latent, kept for an upscale (jobs links it
                # when the render asks for it)
                "latent": ("LATENT",),
                # the loader's `info`: its reference lines (each picture, how
                # it was cut, its size, its slot) go into the take's record
                "ref_info": ("STRING", {"forceInput": True}),
                # continuous: latent: what H3ChainLatent held (its `record`,
                # JSON), written into the take's record as `continued_from`
                "chain": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("shot_dir", "status")
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "seriesmith"

    # -- vocal stripping ---------------------------------------------------

    @staticmethod
    def _strip_vocals(wav_path: str, out_path: str) -> str:
        """Demucs the H3 mix and keep everything except the vocal stem."""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(
                    ["python", "-m", "demucs", "--two-stems", "vocals",
                     "-o", tmp, wav_path],
                    check=True, capture_output=True, timeout=600,
                )
                stem = os.path.splitext(os.path.basename(wav_path))[0]
                for dirpath, _, files in os.walk(tmp):
                    if os.path.basename(dirpath) == stem and "no_vocals.wav" in files:
                        import shutil
                        shutil.copy(os.path.join(dirpath, "no_vocals.wav"), out_path)
                        return "foley bed written"
            return "demucs ran but produced no no_vocals.wav"
        except FileNotFoundError:
            return "demucs not installed - foley bed skipped (pip install demucs)"
        except subprocess.CalledProcessError as exc:
            return f"demucs failed: {exc.stderr.decode('utf-8', 'replace')[:160]}"
        except subprocess.TimeoutExpired:
            return "demucs timed out - foley bed skipped"

    # -- main --------------------------------------------------------------

    def save(self, images, shot_id, audio_policy, run, take, fps, save_frames, audio=None,
             latent=None, ref_info="", chain=""):
        import folder_paths
        from PIL import Image

        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", shot_id) or "shot"
        run_safe = re.sub(r"[^A-Za-z0-9_.-]", "_", run) or "take"
        subfolder = f"seriesmith/{run_safe}"
        shot_dir = os.path.join(folder_paths.get_output_directory(), "seriesmith", run_safe)
        os.makedirs(shot_dir, exist_ok=True)
        stem = f"{safe}_t{take:02d}"
        notes: list[str] = []
        # What this node spends, per step, in milliseconds (the record's
        # `save_ms`). ComfyUI's "Prompt executed in" covers the whole graph, so
        # without this there is no way to tell an ffmpeg encode from eight
        # LANCZOS resizes when a render feels slow. perf_counter is ~100 ns a
        # call, so the measuring costs nothing worth counting.
        ms: dict = {}
        clock = time.perf_counter

        # ---- frames ------------------------------------------------------
        frame_dir = os.path.join(shot_dir, "frames")
        if save_frames:
            t0 = clock()
            os.makedirs(frame_dir, exist_ok=True)
            arr = (images.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
            for i, frame in enumerate(arr):
                Image.fromarray(frame).save(
                    os.path.join(frame_dir, f"{stem}_{i:06d}.png"), compress_level=4
                )
            notes.append(f"{len(arr)} frames -> frames/")
            ms["frames"] = round((clock() - t0) * 1000)

        # ---- audio -------------------------------------------------------
        h3_wav = os.path.join(shot_dir, f"{stem}_h3.wav")
        mux_audio = None
        if audio is not None:
            t0 = clock()
            save_audio(audio, h3_wav)
            notes.append("H3 mix -> _h3.wav")
            # 'clone' speaks the written lines in the sampled voice: H3's mix is
            # the shot's real sound, as it is for 'generate'
            if audio_policy in ("generate", "clone"):
                mux_audio = h3_wav
            elif audio_policy == "dub_keep_foley":
                foley = os.path.join(shot_dir, f"{stem}_foley.wav")
                notes.append(self._strip_vocals(h3_wav, foley))
                mux_audio = foley if os.path.isfile(foley) else None
            # 'dub' leaves the mp4 mute: the real vocal is laid in at conform,
            # and muxing H3's competing vocal only gets in the way.
            ms["audio"] = round((clock() - t0) * 1000)

        # ---- mp4 ---------------------------------------------------------
        mp4 = os.path.join(shot_dir, f"{stem}.mp4")
        t0 = clock()
        status = self._encode(images, mp4, fps, mux_audio, frame_dir if save_frames else None)
        ms["mp4"] = round((clock() - t0) * 1000)
        notes.append(status)
        mp4_ok = status.startswith("mp4 written") and os.path.isfile(mp4)

        # ---- latent ------------------------------------------------------
        # After the mp4, and never fatal: without it the take can still be
        # upscaled, through the VAE.
        latent_file = None
        if latent is not None and mp4_ok:
            try:
                t0 = clock()
                latent_file = save_latent(latent, os.path.join(shot_dir, f"{stem}.latent.safetensors"),
                                          width=int(images.shape[2]), height=int(images.shape[1]),
                                          frames=int(images.shape[0]), fps=float(fps))
                ms["latent"] = round((clock() - t0) * 1000)
                mb = os.path.getsize(os.path.join(shot_dir, latent_file)) / 1e6
                notes.append(f"latent -> .latent.safetensors ({mb:.1f} MB)")
            except Exception as exc:
                notes.append(f"latent failed: {exc}")

        # ---- thumbnails --------------------------------------------------
        # After the mp4, and never fatal: the render is the valuable thing.
        thumb = strip = None
        try:
            t0 = clock()
            thumb = self._write_thumb(images, os.path.join(shot_dir, f"{stem}.jpg"))
            ms["thumb"] = round((clock() - t0) * 1000)
        except Exception as exc:
            notes.append(f"thumbnail failed: {exc}")
        try:
            t0 = clock()
            strip = self._write_strip(images, os.path.join(shot_dir, f"{stem}_strip.jpg"))
            ms["strip"] = round((clock() - t0) * 1000)
        except Exception as exc:
            notes.append(f"strip failed: {exc}")

        # ---- record ------------------------------------------------------
        ms["total"] = round(sum(v for k, v in ms.items() if k != "total"))
        record = self.record(shot_id, take, notes, stem=stem,
                             status="ok" if mp4_ok else "failed",
                             frames=int(images.shape[0]), fps=float(fps),
                             mp4=os.path.basename(mp4) if mp4_ok else None,
                             thumb=thumb, strip=strip, save_ms=ms, latent=latent_file,
                             loaded_refs=loaded_refs(ref_info),
                             continued_from=chain_record(chain))
        record_file = f"{stem}.record.json"
        _write_json_atomic(os.path.join(shot_dir, record_file), record)

        # ---- report every file, so the backend hands each back -----------
        def item(name):
            return {"filename": name, "subfolder": subfolder, "type": "output"}
        ui = {"files": [item(record_file)]}
        if mp4_ok:
            ui["gifs"] = [dict(item(os.path.basename(mp4)), format="video/h264-mp4")]
        wavs = [n for n in (f"{stem}_h3.wav", f"{stem}_foley.wav")
                if os.path.isfile(os.path.join(shot_dir, n))]
        if wavs:
            ui["audio"] = [item(n) for n in wavs]
        jpgs = [n for n in (thumb, strip) if n]
        if jpgs:
            ui["images"] = [item(n) for n in jpgs]
        if latent_file:
            ui["latents"] = [item(latent_file)]
        if save_frames and os.path.isdir(frame_dir):
            # the PNG sequence, reported too: seriesmith puts it in the take's frames/
            ui["files"] += [{"filename": n, "subfolder": f"{subfolder}/frames", "type": "output"}
                            for n in sorted(os.listdir(frame_dir))
                            if n.startswith(stem + "_") and n.endswith(".png")]
        return {"ui": ui, "result": (shot_dir, f"{stem}: " + "; ".join(notes))}

    # -- record ------------------------------------------------------------

    @staticmethod
    def record(shot_id: str, take: int, notes: list[str], *, stem: str, status: str,
               frames: int, mp4, thumb, strip, fps: float | None = None,
               save_ms: dict | None = None, latent: str | None = None,
               loaded_refs: list | None = None, continued_from: dict | None = None) -> dict:
        """What the saver did, as the fields of the take's record it fills in
        (h3pipe's H3SaveShot wrote these into the sidecar itself)."""
        data = {"shot": shot_id, "take": take, "status": status, "finished": _now(),
                "frames": frames, "mp4": mp4, "thumb": thumb, "strip": strip,
                "save_notes": f"{stem}: " + "; ".join(notes)}
        if fps:
            # the mp4's frame rate (the target's)
            data["fps"] = float(fps)
        if latent:
            # the take's latent file, beside it (an upscale starts from it)
            data["latent"] = latent
        if loaded_refs:
            # what the loader fed the model: each picture, how it was cut, its size
            data["loaded_refs"] = loaded_refs
        if continued_from:
            # continuous: latent: the take whose tail the render held
            data["continued_from"] = continued_from
        if save_ms:
            # what this node spent, in milliseconds, per step
            data["save_ms"] = dict(save_ms)
        return data

    # -- thumbnails --------------------------------------------------------

    @staticmethod
    def _frame(images, i: int):
        """Frame i as an RGB PIL image, converting only that frame."""
        from PIL import Image

        arr = (images[i].detach().float().clamp(0, 1).cpu().numpy() * 255.0 + 0.5)
        arr = arr.astype(np.uint8)
        if arr.ndim == 3 and arr.shape[2] == 1:
            arr = arr[:, :, 0]
        return Image.fromarray(arr).convert("RGB")

    @staticmethod
    def _save_jpeg(img, path: str) -> str:
        """Write a JPEG atomically (temp file, then os.replace); return its name."""
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".jpg",
                                   dir=os.path.dirname(os.path.abspath(path)))
        try:
            with os.fdopen(fd, "wb") as fh:
                img.save(fh, format="JPEG", quality=JPEG_QUALITY)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return os.path.basename(path)

    @classmethod
    def _write_thumb(cls, images, path: str) -> str:
        """The middle frame, scaled so its longest side is THUMB_LONG_SIDE."""
        from PIL import Image

        img = cls._frame(images, int(images.shape[0]) // 2)
        w, h = img.size
        k = THUMB_LONG_SIDE / max(w, h)
        img = img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        return cls._save_jpeg(img, path)

    @staticmethod
    def strip_indices(n: int) -> list[int]:
        """The frame at the centre of each of STRIP_FRAMES equal segments of an
        n-frame clip; every frame when there are fewer than STRIP_FRAMES."""
        k = min(STRIP_FRAMES, n)
        return [min(n - 1, int((i + 0.5) * n / k)) for i in range(k)]

    @classmethod
    def _write_strip(cls, images, path: str) -> str:
        """The strip_indices frames, STRIP_CELL_WIDTH wide each, left to right."""
        from PIL import Image

        cells = []
        for i in cls.strip_indices(int(images.shape[0])):
            img = cls._frame(images, i)
            w, h = img.size
            cells.append(img.resize(
                (STRIP_CELL_WIDTH, max(1, round(h * STRIP_CELL_WIDTH / w))), Image.LANCZOS))
        out = Image.new("RGB", (STRIP_CELL_WIDTH * len(cells), cells[0].size[1]))
        for j, cell in enumerate(cells):
            out.paste(cell, (j * STRIP_CELL_WIDTH, 0))
        return cls._save_jpeg(out, path)

    @staticmethod
    def _encode(images, mp4, fps, audio_path, existing_frames):
        """Write the take's mp4 with ffmpeg.

        With a PNG sequence already on disk (`save_frames`) ffmpeg reads that.
        Otherwise the frames are **piped in as raw RGB** rather than written out
        as PNGs first: measured 2026-09-22 on 73 frames at 864x480, writing the
        PNGs was 2.9 s of a 3.9 s encode, and the piped encode produces the same
        file in 1.1 s. A clip that isn't plain 3-channel RGB, or whose size is
        odd (yuv420p needs even sides), still goes the PNG way.
        """
        n_frames = int(images.shape[0])
        h, w = int(images.shape[1]), int(images.shape[2])
        channels = int(images.shape[3]) if images.ndim == 4 else 0
        pipe = existing_frames is None and channels == 3 and w % 2 == 0 and h % 2 == 0

        tmpdir = existing_frames
        cleanup = False
        raw = pattern = None
        if pipe:
            raw = (images.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8).tobytes()
        elif tmpdir is None:
            from PIL import Image

            tmpdir = tempfile.mkdtemp(prefix="seriesmith_take_")
            cleanup = True
            arr = (images.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
            for i, frame in enumerate(arr):
                Image.fromarray(frame).save(os.path.join(tmpdir, f"f_{i:06d}.png"))
            pattern = os.path.join(tmpdir, "f_%06d.png")
        else:
            first = sorted(os.listdir(tmpdir))[0]
            pattern = os.path.join(tmpdir, re.sub(r"\d{6}", "%06d", first))

        cmd = [*_ff.tool("ffmpeg"), "-y"]
        if pipe:
            cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                    "-framerate", str(fps), "-i", "-"]
        else:
            cmd += ["-framerate", str(fps), "-i", pattern]
        if audio_path:
            cmd += ["-i", audio_path, "-c:a", "aac", "-b:a", "192k"]
        # -frames:v pins the exact count. Never use -shortest here: H3's audio
        # is often a few milliseconds shorter than length/fps, and -shortest
        # would silently drop the final frame -- which breaks conform, because
        # the edit assumes every shot is exactly `length` frames long.
        cmd += ["-frames:v", str(n_frames), "-vf", RGB_TO_BT709,
                "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", mp4]

        proc = None
        try:
            if pipe:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                _, err = proc.communicate(input=raw, timeout=900)
                if proc.returncode:
                    raise subprocess.CalledProcessError(proc.returncode, cmd, b"", err)
            else:
                subprocess.run(cmd, check=True, capture_output=True, timeout=900)
            result = f"mp4 written ({'with audio' if audio_path else 'mute'})"
        except FileNotFoundError:
            # no ffmpeg on PATH: PyAV, which every ComfyUI has (its requirements)
            try:
                encode_av(images, mp4, fps, audio_path)
                result = f"mp4 written ({'with audio' if audio_path else 'mute'}; PyAV, no ffmpeg on PATH)"
            except ImportError:
                result = "ffmpeg not found - mp4 skipped"
            except Exception as exc:                      # noqa: BLE001  said in the record
                result = f"ffmpeg not found, and PyAV failed: {exc}"
        except subprocess.CalledProcessError as exc:
            result = f"ffmpeg failed: {(exc.stderr or b'').decode('utf-8', 'replace')[-160:]}"
        except subprocess.TimeoutExpired:
            if proc is not None:
                proc.kill()
                proc.communicate()
            result = "ffmpeg timed out - mp4 skipped"
        finally:
            if cleanup:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
        return result


# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "SeriesmithShotLoader": SeriesmithShotLoader,
    "SeriesmithSaveTake": SeriesmithSaveTake,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeriesmithShotLoader": "seriesmith Shot Loader",
    "SeriesmithSaveTake": "seriesmith Save Take",
}
