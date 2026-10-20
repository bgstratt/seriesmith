"""
Comfy Cloud: the nodes and model files it has, and a shot's portable graph
made into one it runs.

Cloud runs ComfyUI's own nodes and the packs it has installed, not
seriesmith's (comfy_nodes/), so a render sent there is made of Cloud's nodes
alone (`lower`):

- The loader's work is done here. comfy_nodes/shotplan.py plans the shot as the
  node does; its pictures (each sheet cut to its panels, the plate, the grey
  placeholders) and sounds (voice samples, the recording's slice) go up as
  files that LoadImage and LoadAudio read, and its numbers and text are
  written into the nodes that read them.
- The saver becomes CreateVideo + SaveVideo (H.264 at CRF 16, BT.709) and, for
  the model's own sound, SaveAudio. The thumbnail, the strip and the take's
  record are made here when the run comes back (`collect`), as for a hosted
  model's take.
- A node a target can do without (binding `bypass_if_missing`: H3's sparse
  attention) is spliced out when Cloud hasn't it, and the take says so.

What can't go: a `continuous: latent` shot (it holds the take before it through
the chain nodes); and a take rendered there keeps no latent, no PNG frames and
no foley bed (its record says so).
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave

from seriesmith.backends import BackendError, File, tls
from seriesmith.core import paths as P

# how long Cloud's node list is trusted before it is asked again
TTL = 600.0
_INFO: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()

# the loader's outputs (comfy_nodes/shot.py, SeriesmithShotLoader.RETURN_NAMES)
OUT_ID, OUT_PROMPT = 0, 1
OUT_PICTURES = (2, 3, 4, 5)                  # ref_1..ref_3, ref_bg
OUT_SOUNDS = (6, 7, 8)                       # ref_audio_1..3
OUT_NUMBERS = {9: "width", 10: "height", 11: "length", 12: "steps", 13: "seed"}
OUT_POLICY, OUT_INFO, OUT_COUNT = 14, 15, 16

CHAIN_NODES = ("SeriesmithChainLatent", "SeriesmithChainTrim")
CRF = 16                                     # the saver's (comfy_nodes/shot.py _encode)
VIDEO, AUDIO = "seriesmith_video", "seriesmith_audio"


def object_info(base_url: str, api_key: str | None, timeout: float = 120.0) -> dict:
    """Every node class a Comfy Cloud has, with its inputs (/api/object_info):
    asked once every TTL seconds."""
    base = base_url.rstrip("/")
    with _LOCK:
        hit = _INFO.get(base)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    req = urllib.request.Request(base + "/api/object_info",
                                 headers={"X-API-Key": api_key} if api_key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=tls()) as r:
            info = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise BackendError(f"{base} didn't list its nodes ({e.code})") from None
    except (OSError, ValueError) as e:
        raise BackendError(f"{base} didn't list its nodes: {e}") from None
    if not isinstance(info, dict):
        raise BackendError(f"{base} answered /api/object_info with no node list")
    with _LOCK:
        _INFO[base] = (time.monotonic(), info)
    return info


def forget() -> None:
    """Ask again next time (tests; a refresh)."""
    with _LOCK:
        _INFO.clear()


# ---------------------------------------------------------------------------
# lower: a portable graph as Cloud's nodes alone
# ---------------------------------------------------------------------------

_safe = P.safe_id


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _relink(g: dict, nid: str, out: dict) -> None:
    """Every input reading output k of node `nid` reads out[k] instead: a link,
    a value, or (None) nothing -- the input is left out."""
    for v in g.values():
        ins = v.get("inputs") or {}
        for k, x in list(ins.items()):
            if _is_link(x) and x[0] == nid:
                new = out.get(int(x[1]))
                if new is None:
                    del ins[k]
                else:
                    ins[k] = new


def lower(g: dict, job, take, info: dict) -> tuple[dict, dict]:
    """(the graph Comfy Cloud runs, what `collect` needs to make the take).
    `g` is the portable graph (jobs.graph_for(portable=True)); `info` Cloud's
    object_info. NotPortable when it needs what Cloud hasn't."""
    from seriesmith import jobs as J
    from seriesmith.targets import bypassable

    g = copy.deepcopy(g)
    notes: list[str] = []
    if any(v.get("class_type") in CHAIN_NODES for v in g.values()):
        raise J.NotPortable("a continuous: latent shot holds the take before it through "
                            "seriesmith's chain nodes, which Comfy Cloud hasn't: render it on local")
    # a continuity shot's first frame, cut when its job started: the picture itself
    for v in g.values():
        if v.get("class_type") == "H3ContinuityFrame":
            v["class_type"], v["inputs"] = "LoadImage", {"image": v["inputs"]["image"]}
    present = {v.get("class_type") for v in g.values()}
    gone = {c: via for c, via in bypassable().items() if c in present and c not in info}
    notes += [f"{c} isn't on Comfy Cloud: rendered without it" for c in J.bypass_nodes(g, gone)]

    staging = tempfile.mkdtemp(prefix="seriesmith_cloud_")
    try:
        loader = next((k for k, v in g.items() if v["class_type"] == J.PORTABLE_LOADER), None)
        shot = _lower_loader(g, loader, staging) if loader else None
        plan = _lower_saver(g, J.node_of(g, J.PORTABLE_SAVER), job, shot, notes)
        missing = sorted({v["class_type"] for v in g.values()} - set(info))
        if missing:
            raise J.NotPortable(f"Comfy Cloud hasn't {', '.join(missing)}: render it on local")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    plan.update(staging=staging, notes=notes)
    return g, plan


def _lower_loader(g: dict, nid: str, staging: str) -> dict:
    """SeriesmithShotLoader's outputs made here (shotplan) and put where it
    was read: pictures and sounds as LoadImage / LoadAudio of files in
    `staging`, the rest as values. Returns what the take's record wants of it."""
    from seriesmith import shotnodes as SN

    sp = SN.shotplan()
    li = g[nid]["inputs"]
    names = json.loads(li.get("files") or "[]")
    where = {}
    for i, rel in enumerate(names):
        f = li.get(SN.file_input(i))
        if isinstance(f, File):
            where[str(rel).replace("\\", "/")] = f.path

    def resolve(path: str) -> str:
        return where.get(str(path or "").replace("\\", "/"), "") if path else ""

    plan = sp.plan_shot(json.loads(li["shotlist"]), int(li.get("index") or 0),
                        li.get("panel_mode") or "auto", float(li.get("fps") or 24.0),
                        li.get("resolution_override") or "", resolve)
    out: dict = {OUT_ID: plan["id"], OUT_PROMPT: plan["prompt"], OUT_POLICY: plan["policy"],
                 OUT_COUNT: plan["count"]}
    out.update({k: plan[name] for k, name in OUT_NUMBERS.items()})
    sizes = []
    for i, (k, spec) in enumerate(zip(OUT_PICTURES, [*plan["refs"], plan["bg"]])):
        path, wh = picture(sp, spec, os.path.join(staging, f"picture_{i + 1}.png"))
        sizes.append(None if "neutral" in spec else wh)
        node = f"{nid}_picture_{i + 1}"
        g[node] = {"class_type": "LoadImage", "inputs": {"image": File(path)},
                   "_meta": {"title": f"<Picture {i + 1}>"}}
        out[k] = [node, 0]
    for i, (k, spec) in enumerate(zip(OUT_SOUNDS, plan["audio"])):
        if spec is None:
            out[k] = None
            continue
        node = f"{nid}_audio_{i + 1}"
        g[node] = {"class_type": "LoadAudio",
                   "inputs": {"audio": File(sound(spec, os.path.join(staging, f"audio_{i + 1}.wav")))},
                   "_meta": {"title": f"<Audio {i + 1}>"}}
        out[k] = [node, 0]
    out[OUT_INFO] = sp.info_text(plan, sizes[:3])
    _relink(g, nid, out)
    del g[nid]
    return {"id": plan["id"], "policy": plan["policy"], "fps": plan["fps"],
            "loaded_refs": ([f"RENDERED WITHOUT: {', '.join(plan['blanked'])} (missing refs)"]
                            if plan["blanked"] else []) + sp.ref_notes(plan, sizes[:3])}


def picture(sp, spec: dict, path: str) -> tuple[str, tuple[int, int]]:
    """The file one picture slot sends, and its size: flat grey, the picture
    itself when it goes whole (LoadImage reads it as the loader does), else
    its kept panels side by side, as a PNG at `path`."""
    from PIL import Image, ImageOps

    if "neutral" in spec:
        h, w = spec["neutral"]
        Image.new("RGB", (w, h), (128, 128, 128)).save(path)
        return path, (w, h)
    with Image.open(spec["path"]) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    box = sp.crop_box(img.width, int(spec.get("panels") or 1), list(spec.get("keep") or []))
    if box == [(0, img.width)]:
        return spec["path"], img.size
    out = Image.new("RGB", (sum(x1 - x0 for x0, x1 in box), img.height))
    x = 0
    for x0, x1 in box:
        out.paste(img.crop((x0, 0, x1, img.height)), (x, 0))
        x += x1 - x0
    out.save(path)
    return path, out.size


def sound(spec: dict, path: str) -> str:
    """The file one audio slot sends: the file itself, or its slice [start,
    end) written at `path` (sample-exact on a PCM wav; anything else is made a
    16-bit wav first)."""
    from seriesmith import ff as FF

    src = spec["path"]
    if spec.get("start") is None:
        return src
    try:
        w = wave.open(src, "rb")
    except (wave.Error, EOFError):
        tmp = path + ".src.wav"
        import subprocess
        try:
            subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src,
                            "-acodec", "pcm_s16le", tmp], check=True, capture_output=True,
                           timeout=300)
        except (OSError, subprocess.CalledProcessError) as e:
            raise RuntimeError(f"can't decode {os.path.basename(src)}: {e}") from None
        w = wave.open(tmp, "rb")
    with w:
        params, sr, n = w.getparams(), w.getframerate(), w.getnframes()
        a = max(0, int(spec["start"] * sr))
        b = min(int(spec["end"] * sr) if spec.get("end") is not None else n, n)
        if b <= a:
            raise ValueError(f"empty audio slice {spec['start']}..{spec.get('end')} from "
                             f"{os.path.basename(src)} (the file is only {n / sr:.2f}s long)")
        w.setpos(a)
        frames = w.readframes(b - a)
    with wave.open(path, "wb") as o:
        o.setparams(params)
        o.writeframes(frames)
    return path


def _lower_saver(g: dict, nid: str, job, shot: dict | None, notes: list[str]) -> dict:
    """SeriesmithSaveTake as Cloud's own nodes: the picture (and, for a policy
    that keeps it, the model's sound) into an mp4 by CreateVideo + SaveVideo;
    the model's sound kept too by SaveAudio. Returns what collect needs."""
    si = g[nid]["inputs"]

    def value(name, default):
        v = si.get(name)
        return default if v is None or _is_link(v) else v
    policy = value("audio_policy", (shot or {}).get("policy") or "generate")
    shot_id = value("shot_id", (shot or {}).get("id") or job.id)
    fps = float(value("fps", (shot or {}).get("fps") or 24.0))
    stem = f"{_safe(shot_id, 'shot')}_t{int(si.get('take') or 1):02d}"
    prefix = f"seriesmith/{_safe(si.get('run') or 'take', 'take')}/{stem}"
    audio = si.get("audio")
    video = {"images": si["images"], "fps": fps}
    if audio is not None and policy in ("generate", "clone"):
        video["audio"] = audio
    g[f"{VIDEO}_create"] = {"class_type": "CreateVideo", "inputs": video}
    g[VIDEO] = {"class_type": "SaveVideo",
                "inputs": {"video": [f"{VIDEO}_create", 0], "filename_prefix": prefix,
                           "format": "mp4", "format.codec": "h264",
                           "format.codec.encoding": "re-encode",
                           "format.codec.encoding.crf": float(CRF)}}
    if audio is not None:
        g[AUDIO] = {"class_type": "SaveAudio",
                    "inputs": {"audio": audio, "filename_prefix": f"{prefix}_h3"}}
    if policy == "dub_keep_foley":
        notes.append("no foley bed on Comfy Cloud (seriesmith's saver strips the vocal): "
                     "the mp4 is mute, as for dub")
    if si.get("latent") is not None:
        notes.append("no latent kept on Comfy Cloud: an upscale of this take goes through the VAE")
    if si.get("save_frames"):
        notes.append("no PNG frames kept on Comfy Cloud")
    del g[nid]
    return {"video": VIDEO, "audio": AUDIO if audio is not None else None, "stem": stem,
            "policy": policy, "fps": fps, "loaded_refs": (shot or {}).get("loaded_refs") or []}


# ---------------------------------------------------------------------------
# collect: the take made from what came back
# ---------------------------------------------------------------------------

def done_sending(plan: dict) -> None:
    """The run has its inputs: the files made for it go."""
    if plan.get("staging"):
        shutil.rmtree(plan["staging"], ignore_errors=True)


def collect(take, run, status: str, plan: dict) -> str:
    """After a lowered run has ended with `status`: SaveVideo's mp4 becomes the
    take's, SaveAudio's sound its _h3.wav, and seriesmith makes the frame count,
    thumbnail and strip and closes the take's record as the saver would have.
    Returns the take's status."""
    from seriesmith import finish as F
    from seriesmith import ff as FF
    from seriesmith import jobs as J
    from seriesmith import takes as T

    done_sending(plan)
    if status != "succeeded":
        J.mark_failed(take, run.error or f"the job ended {status}")
        return "failed"
    outs = list(run.outputs())
    videos = [o for o in outs if o.node == plan["video"]]
    if not videos:
        J.mark_failed(take, f"the job finished but sent no video back "
                            f"(got {', '.join(o.name for o in outs) or 'nothing'})")
        return "failed"
    notes = list(plan.get("notes") or [])
    try:
        videos[0].save(take.paths.mp4)
        info = F.probe(take.paths.mp4)
    except (OSError, F.FinishError) as e:
        J.mark_failed(take, f"the video didn't come back whole: {e}")
        return "failed"
    notes.insert(0, f"mp4 from Comfy Cloud ({'with audio' if info['audio'] else 'mute'}, "
                    f"{info['width']}x{info['height']})")
    sounds = [o for o in outs if plan.get("audio") and o.node == plan["audio"]]
    if sounds:
        tmp = os.path.join(take.paths.dir, f".{take.paths.stem}_h3{os.path.splitext(sounds[0].name)[1]}")
        try:
            sounds[0].save(tmp)
            F._run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", tmp, "-acodec", "pcm_s16le",
                    take.paths.h3_wav])
            notes.append("H3 mix -> _h3.wav")
        except (OSError, F.FinishError) as e:
            notes.append(f"the model's sound didn't come back: {e}")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    thumb = strip = None
    try:
        F.thumb(take.paths.mp4, take.paths.thumb, info["frames"])
        thumb = os.path.basename(take.paths.thumb)
        F.strip(take.paths.mp4, take.paths.strip, info["frames"])
        strip = os.path.basename(take.paths.strip)
    except F.FinishError as e:
        notes.append(f"thumbnails failed: {e}")
    take.sidecar = T.update_sidecar(
        take.paths.sidecar, status="ok", finished=T.now(), frames=info["frames"],
        fps=float(plan.get("fps") or info["fps"]), mp4=os.path.basename(take.paths.mp4),
        thumb=thumb, strip=strip, save_notes=f"{take.paths.stem}: " + "; ".join(notes),
        **({"loaded_refs": plan["loaded_refs"]} if plan.get("loaded_refs") else {}))
    return "ok"
