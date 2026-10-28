"""
features — what can be added to a seriesmith install, and whether it's there
(the Features window; docs/FULL_SETUP.md is the same list in prose).

A feature is a few items, each of one kind:

    model   a model file: its name, its ComfyUI models folder, its download
            (only ever a URL recorded in the code: a target's `downloads`, or
            the constants upscale / post / refs keep beside the files they use)
    pack    a ComfyUI node pack: its folder in custom_nodes, its git repo, and
            the node classes that say it's loaded
    link    seriesmith's own node pack (comfy_nodes/), linked into custom_nodes
            from this repo (a junction on Windows, a symlink elsewhere)
    pip     a Python package, in ComfyUI's Python or in seriesmith's own
    ffmpeg  a full ffmpeg build, downloaded into seriesmith's folder (seriesmith.ff)

A pack or a pip package is put in by you, not by seriesmith (`Item.manual`):
the Comfy Registry's rules let a node pack neither install Python packages at
runtime nor install other packs. status() says how for each one missing
(`how`): ComfyUI-Manager for a pack, the pip command for the right Python.

A target's feature takes its files from the target itself (the required and
accelerator files its passes load), and its status from readiness, which knows
a renamed or re-quantized copy of the same model counts.

`catalog()` lists them; `status(features, env)` says what's installed, given
an Env of what's known about this ComfyUI; `resolve(...)` turns ids (or the
What's missing window's files and node classes) into the items to install.

Stdlib only (the targets, upscale, post and refs constants are read lazily).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# node packs
# ---------------------------------------------------------------------------

# folder in custom_nodes -> its repo and the classes that say it is loaded
PACKS: dict[str, dict] = {
    "ComfyUI-PlagueKind-Nodes": {
        "repo": "https://github.com/PlagueKind/ComfyUI-PlagueKind-Nodes",
        "classes": ["H3SLAAttention"]},
    "ComfyUI-LTXVideo": {
        "repo": "https://github.com/Lightricks/ComfyUI-LTXVideo",
        "classes": ["LTXVAudioOnlyModel", "LTXVAudioOnlyEmptyVideoLatent",
                    "LTXICLoRALoaderModelOnly", "LTXAddVideoICLoRAGuide"]},
    "Comfyui_Minimax_h3_latent_Upscaler": {
        "repo": "https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler",
        "classes": ["MinimaxH3LatentUpscaler3D"]},
    "comfyui-obvpm-timeline": {
        "repo": "https://github.com/chanon/comfyui-obvpm-timeline",
        "classes": ["H3ContextWindows"]},
    "Nvidia_RTX_Nodes_ComfyUI": {
        "repo": "https://github.com/Comfy-Org/Nvidia_RTX_Nodes_ComfyUI",
        "classes": ["RTXVideoSuperResolution"]},
    "ComfyUI-VideoHelperSuite": {
        "repo": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
        "classes": ["VHS_VideoCombine"]},
    "ComfyUI-LTX2.5-MSR": {
        "repo": "https://github.com/liconstudio/ComfyUI-LTX2.5-MSR",
        "classes": ["ComfyUILTX25MSRICLoRALoader", "ComfyUILTX25MSRMultiReferenceGuide"]},
    "ComfyUI-PromptRelay": {
        "repo": "https://github.com/kijai/ComfyUI-PromptRelay",
        "classes": ["PromptRelayEncode"]},
}

# ---------------------------------------------------------------------------
# items and features
# ---------------------------------------------------------------------------


@dataclass
class Item:
    kind: str                      # model | pack | link | pip | ffmpeg
    name: str                      # the file, the pack's folder, the pip spec, "ffmpeg"
    folder: str = ""               # model: its models folder
    url: str = ""                  # model: its download; pack: its repo
    target: str = ""               # model: the target that names it (status from readiness)
    where: str = "comfyui"         # pip: which Python: "comfyui", "seriesmith", or "align"
                                   # (the one align runs on: track.align_python)
    module: str = ""               # pip: the module that says it's installed
    pip_args: tuple = ()           # pip: extra arguments (an index URL)
    classes: tuple = ()            # pack: the node classes it loads

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.folder + '/' if self.folder else ''}{self.name}"

    @property
    def manual(self) -> bool:
        """Put in by you (ComfyUI-Manager, pip), not by the installer."""
        return self.kind in ("pack", "pip")

    @property
    def gated(self) -> bool:
        """A Hugging Face file whose repo asks you to accept a licence (FLUX,
        LTX-2.5): it needs a token (settings hf_token)."""
        return self.kind == "model" and any(r in self.url for r in GATED_REPOS)

    def to_json(self) -> dict:
        d = {"key": self.key, "kind": self.kind, "name": self.name}
        if self.manual:
            d["manual"] = True
        for k in ("folder", "url", "target", "module"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.kind == "pip":
            d["where"] = self.where
        if self.gated:
            d["gated"] = True
            d["licence"] = self.url.split("/resolve/")[0]
        return d


# Hugging Face repos that ask for a licence first (checked 2026-10-18: their
# files answer 401 without a token)
GATED_REPOS = ("huggingface.co/black-forest-labs/", "huggingface.co/Lightricks/LTX-2.5")


@dataclass
class Feature:
    id: str
    group: str
    label: str
    about: str
    items: list[Item] = field(default_factory=list)
    restart: bool = False          # ComfyUI must restart to load it (a node pack)

    def to_json(self) -> dict:
        return {"id": self.id, "group": self.group, "label": self.label, "about": self.about,
                "items": [i.to_json() for i in self.items], "restart": self.restart}


GROUPS = [
    ("video", "Video models", "What shots render on. seriesmith uses the first one installed."),
    ("pictures", "Picture models", "What draws characters, places, props and keyframes."),
    ("h3", "MiniMax H3 extras", "For H3 at full quality and for the location tours."),
    ("sound", "Sound", "Generated voices and recorded dialogue."),
    ("upscale", "Upscaling", "Upscale takes (Upscale, Export 2x, master). Pick the methods you want."),
    ("post", "Post-processing", "Enhancement and motion blur after the upscale."),
    ("refs", "360s and turned views", "The Refs tab's Make 360 and a character's Turn."),
    ("tools", "Tools", "seriesmith's node pack, and a full ffmpeg."),
]


def _target_items(tid: str) -> list[Item]:
    """The files a target's passes load (targets.wanted_files: each param's
    file and the LoRAs; not a pass's `base`, the slower stand-in for a missing
    accelerator, nor an optional file), as model items."""
    from seriesmith import targets as TG
    try:
        t = TG.load_target(tid)
    except Exception:                                     # noqa: BLE001  not here (tests, a trimmed install)
        return []
    names: list[tuple[str, str]] = []
    for pass_ in t.presets:
        for param, want in TG.wanted_files(t, pass_, None).items():
            if param == "loras":
                names += [(lo["name"], "loras") for lo in want or [] if lo.get("name")]
            elif isinstance(want, str) and want:
                names.append((want, param))
    out, seen = [], set()
    for name, param in names:
        if (t.models.get(param) or {}).get("tier") == "optional":
            continue                      # a feature of its own (the duration head, a profile)
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        d = TG.download_for(t, name, (t.models.get(param) or {}).get("folder"))
        if base in seen or not d.get("folder"):
            continue
        seen.add(base)
        out.append(Item("model", base, folder=d["folder"], url=d.get("url") or "", target=tid))
    return out


def _lora_of(tid: str, name: str) -> Item:
    """A LoRA the refs code adds to a target's graph, with that target's
    download record of it."""
    from seriesmith import targets as TG
    d = TG.download_for(TG.load_target(tid), name, "loras")
    return Item("model", name, folder=d.get("folder") or "loras", url=d.get("url") or "")


# seriesmith's own node pack: its folder name in custom_nodes, and the classes
# that say ComfyUI loaded it (the portable shot loader and saver)
OWN_PACK = Item("link", "seriesmith", classes=("SeriesmithSaveTake", "SeriesmithShotLoader"))


def _pack(folder: str) -> Item:
    p = PACKS[folder]
    return Item("pack", folder, url=p["repo"], classes=tuple(p["classes"]))


def catalog() -> list[Feature]:
    """Every feature, in the window's order."""
    from seriesmith import post as P
    from seriesmith import refs as R
    from seriesmith import upscale as U
    from seriesmith import targets as TG

    def target_feature(fid, group, tid, label, about, extra=()):
        items = _target_items(tid)
        return Feature(fid, group, label, about, items + list(extra))

    def seedvr(size):
        return [Item("model", n, folder=f, url=u) for n, (f, u) in U.SEEDVR2_DOWNLOADS.items()
                if n == U.SEEDVR2_VAE or size in n]

    h3_up = TG.load_target("minimax_h3_ref2va").downloads.get("minimax_h3_latent_upscaler_3d_fp16.safetensors") or {}
    feats = [
        target_feature("video.h3", "video", "minimax_h3_ref2va", "MiniMax H3 Ref2VA",
                       "The default: characters and places like their pictures, lip-synced dialogue. "
                       "Wants a recent NVIDIA card (developed on 32 GB)."),
        target_feature("video.h3_fl2va", "video", "minimax_h3_fl2va", "MiniMax H3 FL2VA",
                       "Shots that carry on from the one before (continuous: first), and the location tours."),
        Feature("video.fasth3_omni", "video", "FastH3 Omni",
                "FastVideo's 8-step H3: up to eight characters and things per shot, no turbo LoRA. "
                "Also a picture model (Omni still). Shares H3's text encoder and VAEs.",
                _merge(_target_items("fasth3_omni"), _target_items("fasth3_omni_still"))),
        target_feature("video.ltx2", "video", "ltx2", "LTX-2.5",
                       "Quick, and makes its own sound. Gated: accept the licence on Hugging Face."),
        target_feature("video.ltx2_ingredients", "video", "ltx2_ingredients", "LTX-2.3 ingredients",
                       "LTX working from your character sheets and plates."),
        target_feature("video.ltx2_msr", "video", "ltx2_msr", "LTX-2.5 + MSR",
                       "LTX working from pictures of up to four people and the place (Licon's MSR "
                       "LoRA), two stages. Gated, as LTX-2.5.",
                       [_pack("ComfyUI-LTX2.5-MSR"), _pack("ComfyUI-PromptRelay")]),
        target_feature("video.wan22_vace", "video", "wan22_vace", "Wan 2.2 VACE 14B",
                       "Wan with reference pictures and keyframes. No sound."),
        target_feature("video.wan22_i2v", "video", "wan22_i2v", "Wan 2.2 I2V 14B",
                       "One picture brought to life, very good motion. No sound."),
        target_feature("video.wan22_ti2v", "video", "wan22_ti2v", "Wan 2.2 5B",
                       "Small and quick, from words or a first picture. No sound."),
        target_feature("pictures.krea2", "pictures", "krea2", "Krea 2",
                       "The default picture model: character sheets, props and plates."),
        Feature("pictures.flux2_klein", "pictures", "FLUX.2 Klein 9B",
                "Text to image, and keyframes drawn from the characters' and places' pictures. Gated.",
                _merge(_target_items("flux2_klein"), _target_items("flux2_klein_edit"))),
        target_feature("pictures.z_image", "pictures", "z_image_turbo", "Z-Image Turbo",
                       "Fast text to image."),
        target_feature("pictures.qwen_image_21", "pictures", "qwen_image_21", "Qwen-Image 2.1",
                       "Text to image and edits; also what Make 360 and Turn run on."),
        Feature("pictures.flux3_klein", "pictures", "FLUX.3 Klein",
                "Text to image and edits, with a step-distilled turbo. Gated.",
                _merge(_target_items("flux3_klein"), _target_items("flux3_klein_turbo"))),
        Feature("pictures.fibo2", "pictures", "Fibo 2.0",
                "Bria's Fibo 2.0: text to image and edits (relights too), with a 4-step edit turbo. "
                "Non-commercial licence (CC BY-NC 4.0).",
                _merge(_target_items("fibo2_dev"), _target_items("fibo2_edit_turbo"))),
        target_feature("pictures.moss_image_sft", "pictures", "moss_image_sft", "MOSS-Image SFT",
                       "Text to image, strong on lettering and layout (Apache 2.0). 50 steps."),
        target_feature("pictures.moss_image_base", "pictures", "moss_image_base", "MOSS-Image Base",
                       "The base MOSS-Image the SFT is tuned from: for LoRAs trained on it, and comparing."),
        Feature("h3.sparse_attention", "h3", "H3 sparse attention",
                "ComfyUI-PlagueKind-Nodes: the attention H3's turbo LoRAs were trained with. "
                "Without it H3 renders without it (degraded). The location tours need it.",
                [_pack("ComfyUI-PlagueKind-Nodes")], restart=True),
        Feature("sound.voice", "sound", "Generated voice samples",
                "A voice per character, that `clone` shots speak in: ComfyUI-LTXVideo and three LTX-2.5 "
                "files (gated). It also lets LTX-2.5 read reference sheets.",
                [_pack("ComfyUI-LTXVideo")] + _target_items("ltx2_voice"), restart=True),
        Feature("sound.align", "sound", "Recorded dialogue",
                "faster-whisper, for align and the Recording window, in the Python align runs on.",
                [Item("pip", "faster-whisper", where="align", module="faster_whisper"),
                 Item("pip", "numpy", where="align", module="numpy")]),
        Feature("sound.demucs", "sound", "Keep H3's foley under your vocal",
                "demucs in ComfyUI's Python, for the dub_keep_foley audio policy.",
                [Item("pip", "demucs", where="comfyui", module="demucs")]),
        Feature("upscale.h3_latent", "upscale", "H3 latent re-sample (2x)",
                "The best upscale for H3 takes: the LBH-123-AI pack and its model. Clone the pack: "
                "ComfyUI-Manager lists only its Plus fork, which invents detail.",
                [_pack("Comfyui_Minimax_h3_latent_Upscaler"),
                 Item("model", "minimax_h3_latent_upscaler_3d_fp16.safetensors",
                      folder=h3_up.get("folder") or "latent_upscale_models", url=h3_up.get("url") or "")],
                restart=True),
        Feature("upscale.h3_long", "upscale", "Long H3 takes (over 5.5 s)",
                "comfyui-obvpm-timeline's context windows, so a long take at 2x fits a 32 GB card.",
                [_pack("comfyui-obvpm-timeline")], restart=True),
        Feature("upscale.esrgan", "upscale", "Real-ESRGAN (pixel)",
                "Any take, through an upscale model: x2 (the default, gentle on grain) and x4.",
                [Item("model", n, folder="upscale_models", url=u) for n, u in U.PIXEL_DOWNLOADS.items()]),
        Feature("upscale.rtx_vsr", "upscale", "RTX Video Super Resolution (pixel)",
                "NVIDIA RTX cards: fast, no model file. Comfy-Org's RTX nodes and nvidia-vfx "
                "(needs CUDA PyTorch cu130 or newer).",
                [_pack("Nvidia_RTX_Nodes_ComfyUI"),
                 Item("pip", "nvidia-vfx", where="comfyui", module="nvvfx",
                      pip_args=("--extra-index-url", "https://pypi.nvidia.com"))], restart=True),
        Feature("upscale.seedvr2_7b", "upscale", "SeedVR2 7B",
                "Adds real detail; slow. Also post-processing's Production tier.", seedvr("7b")),
        Feature("upscale.seedvr2_3b", "upscale", "SeedVR2 3B", "Smaller and a little faster.", seedvr("3b")),
        Feature("post.supir", "post", "SUPIR (Cinematic tier)",
                "SUPIR on the SDXL base checkpoint.",
                [Item("model", P.SUPIR_MODEL, folder="model_patches", url=P.SUPIR_URL),
                 Item("model", P.SUPIR_CHECKPOINT, folder="checkpoints", url=P.SUPIR_CHECKPOINT_URL)]),
        Feature("post.motion_blur", "post", "Motion blur",
                "RAFT optical flow (torchvision's weights).",
                [Item("model", P.RAFT_FILE, folder="optical_flow", url=P.RAFT_URL)]),
        target_feature("refs.pano_klein", "refs", "klein_erp_360", "Make 360 on FLUX.2 Klein",
                       "The default 360 engine: FLUX.2 Klein 9B base and the ERP outpaint LoRA. Gated.",
                       [_lora_of("klein_erp_360", R.KLEIN_PANO_LORA)]),
        Feature("refs.pano_qwen", "refs", "Make 360 on Qwen-Image 2.1",
                "The pano360 LoRA (and Qwen-Image 2.1 itself).",
                [Item("model", R.PANO_LORA, folder="loras", url=R.PANO_LORA_URL)] + _target_items("qwen_image_21")),
        Feature("refs.turn", "refs", "Turn a character",
                "Qwen-Image 2.1's multiple-angles LoRA (and Qwen-Image 2.1 itself).",
                [Item("model", R.TURN_LORA, folder="loras", url=R.TURN_LORA_URL)] + _target_items("qwen_image_21")),
        Feature("tools.seriesmith_nodes", "tools", "seriesmith's node pack",
                "Its shot loader and saver, the chain, upscale and post nodes: latent continuity, "
                "kept latents, upscales and posts. Installed with ComfyUI-Manager, or linked "
                "from this repo into ComfyUI's custom_nodes. Without it, shots render through "
                "ComfyUI's own nodes.", [OWN_PACK], restart=True),
        Feature("tools.ffmpeg", "tools", "ffmpeg and ffprobe",
                "A full ffmpeg build in seriesmith's own folder, used before the built-in fallbacks "
                "(or set your own folder in Settings).", [Item("ffmpeg", "ffmpeg")]),
    ]
    return feats


def _merge(*lists: list[Item]) -> list[Item]:
    out, seen = [], set()
    for items in lists:
        for i in items:
            if i.key not in seen:
                seen.add(i.key)
                out.append(i)
    return out


# ---------------------------------------------------------------------------
# what's installed
# ---------------------------------------------------------------------------

@dataclass
class Env:
    """What's known about this machine's ComfyUI, for status(). Each callable
    answers None when it can't tell."""
    model_exists: Callable[[str, str], bool | None] = lambda folder, name: None
    node_classes: set | None = None          # /object_info's keys
    pack_dirs: set | None = None             # the folders in custom_nodes
    readiness: dict = field(default_factory=dict)   # {target id: readiness}
    python_has: Callable[[str, str], bool | None] = lambda where, module: None
    python_for: Callable[[str], str | None] = lambda where: None   # a pip item's Python
    ffmpeg_installed: bool = False


def pip_command(item: Item, python: str | None) -> str:
    """The pip line that puts `item` in `python` ("python" when it isn't
    known), quoted for this system's shell."""
    import shlex
    import subprocess
    cmd = [python or "python", "-m", "pip", "install", item.name, *item.pip_args]
    return subprocess.list2cmdline(cmd) if os.name == "nt" else shlex.join(cmd)


def how(item: Item, env: Env) -> str:
    """How you put in a pack or a pip package seriesmith doesn't install."""
    if item.kind == "pack":
        # some packs aren't in Manager's list (2026-10-28: the LBH latent upscaler), so
        # the clone is always offered too
        return (f"Install {item.name} with ComfyUI-Manager (Custom Nodes Manager, search "
                f"\"{item.name}\"), or if it isn't listed there, clone {item.url} into "
                f"custom_nodes (git clone, or Manager's Install via Git URL); then restart ComfyUI.")
    if item.kind == "pip":
        return f"Run: {pip_command(item, env.python_for(item.where))}"
    return ""


def item_status(item: Item, env: Env) -> str:
    """installed | missing | restart (a pack cloned but not loaded yet) | unknown"""
    if item.kind == "model":
        got = env.model_exists(item.folder, item.name)
        if got:
            return "installed"
        if item.target:
            # readiness knows a substitute of the same family counts
            rd = env.readiness.get(item.target) or {}
            if rd.get("status") in ("ready", "degraded") and not any(
                    m.get("want", "").replace("\\", "/").rsplit("/", 1)[-1] == item.name
                    for m in rd.get("missing") or []):
                return "installed"
        return "missing" if got is False or env.readiness else "unknown"
    if item.kind in ("pack", "link"):
        loaded = env.node_classes is not None and any(c in env.node_classes for c in item.classes)
        if loaded:
            return "installed"
        if env.pack_dirs is not None and item.name.lower() in {d.lower() for d in env.pack_dirs}:
            return "restart"
        return "missing" if env.node_classes is not None or env.pack_dirs is not None else "unknown"
    if item.kind == "pip":
        got = env.python_has(item.where, item.module or item.name)
        return "installed" if got else ("missing" if got is False else "unknown")
    if item.kind == "ffmpeg":
        return "installed" if env.ffmpeg_installed else "missing"
    return "unknown"


def status(features: list[Feature], env: Env) -> list[dict]:
    """Each feature as JSON with its items' status and its own: installed
    (every item), partial, missing, or restart (only a restart is wanting)."""
    out = []
    for f in features:
        d = f.to_json()
        states = []
        for i, item in zip(d["items"], f.items):
            i["status"] = item_status(item, env)
            if item.manual and i["status"] not in ("installed", "restart"):
                i["how"] = how(item, env)
            states.append(i["status"])
        if not states:
            d["status"] = "unavailable"
        elif all(s == "installed" for s in states):
            d["status"] = "installed"
        elif all(s in ("installed", "restart") for s in states):
            d["status"] = "restart"
        elif all(s == "unknown" for s in states):
            d["status"] = "unknown"
        elif any(s in ("installed", "restart") for s in states):
            d["status"] = "partial"
        else:
            d["status"] = "missing"
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# what to install
# ---------------------------------------------------------------------------

def known_files(features: list[Feature] | None = None) -> dict[str, Item]:
    """Every model file with a recorded download, by name: what the What's
    missing window may ask for by name (the server never takes a URL from
    the page)."""
    from seriesmith import targets as TG
    out: dict[str, Item] = {}
    for f in features or catalog():
        for i in f.items:
            if i.kind == "model" and i.url:
                out.setdefault(i.name, i)
    for t in TG.list_targets():
        for name, d in t.downloads.items():
            if d.get("url") and d.get("folder"):
                base = name.replace("\\", "/").rsplit("/", 1)[-1]
                out.setdefault(base, Item("model", base, folder=d["folder"], url=d["url"], target=t.id))
    return out


def pack_for_class(cls: str) -> Item | None:
    if cls in OWN_PACK.classes:
        return OWN_PACK
    for folder, p in PACKS.items():
        if cls in p["classes"]:
            return _pack(folder)
    return None


def resolve(feature_ids=(), files=(), classes=(), features: list[Feature] | None = None,
            env: Env | None = None) -> tuple[list[Item], list[str]]:
    """The items to install for these feature ids, file names and node
    classes, each once, those already installed left out (with `env`).
    Returns (items, what couldn't be: unknown ids, files with no recorded
    download, classes no known pack provides, and each pack or pip package
    you put in yourself, with how)."""
    feats = features or catalog()
    by_id = {f.id: f for f in feats}
    items: list[Item] = []
    skipped: list[str] = []
    for fid in feature_ids:
        if fid not in by_id:
            skipped.append(f"no feature {fid}")
            continue
        items += by_id[fid].items
    if files:
        known = known_files(feats)
        for name in files:
            base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
            if base in known:
                items.append(known[base])
            else:
                skipped.append(f"{base}: no recorded download")
    for cls in classes:
        p = pack_for_class(cls)
        if p:
            items.append(p)
        else:
            skipped.append(f"{cls}: no known node pack")
    out, seen = [], set()
    for i in items:
        if i.key in seen:
            continue
        seen.add(i.key)
        if env is not None and item_status(i, env) in ("installed", "restart"):
            continue
        if i.manual:
            skipped.append(f"{i.name}: {how(i, env or Env())}")
            continue
        out.append(i)
    return out, skipped


def managed_ffmpeg_dir() -> str:
    """Where tools.ffmpeg puts the build: beside the settings file."""
    from seriesmith.settings import settings_path
    return os.path.join(os.path.dirname(settings_path()), "ffmpeg")


__all__ = ["Env", "Feature", "GROUPS", "Item", "PACKS", "catalog", "how", "item_status",
           "known_files", "managed_ffmpeg_dir", "pack_for_class", "pip_command", "resolve",
           "status"]
