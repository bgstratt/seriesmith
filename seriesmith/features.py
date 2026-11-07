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
    key     an account's key, not a file: the Comfy API key the hosted models
            (Comfy Router), Comfy Cloud and deployments run on, set in Settings
    hub     what a package would otherwise fetch by itself the first time a job
            runs (seriesmith.hubcache): a Hugging Face repo's files into its
            cache (faster-whisper's models, HunyuanVideo-Foley's SigLIP2 and
            CLAP) or into a models folder (ComfyUI-MMAudio's BigVGAN), or a file
            into torch's hub cache (demucs's htdemucs). Downloaded here, where
            that package looks; the job that needs one refuses until it's there,
            so nothing downloads behind its back. A target's are its target.json
            `fetches`; the rest are constants beside the code that reads them

A pack, a pip package or a key is put in by you, not by seriesmith
(`Item.manual`): the Comfy Registry's rules let a node pack neither install
Python packages at runtime nor install other packs. status() says how for each
one missing (`how`): ComfyUI-Manager for a pack, the pip command for the right
Python, Settings for a key.

Every node class a shipped graph uses is ComfyUI's own (CORE_CLASSES),
seriesmith's (OWN_PACK) or a pack's here (PACKS), and every file a shipped
target loads is in a feature: tests/test_features.py checks both.

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
                    "LTXICLoRALoaderModelOnly", "LTXAddVideoICLoRAGuide",
                    # ltx23_foley's guiders and mask
                    "GuiderParameters", "MultimodalGuider", "LTXVSetAudioVideoMaskByTime"]},
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
    "ComfyUI-MMAudio": {
        "repo": "https://github.com/kijai/ComfyUI-MMAudio",
        "classes": ["MMAudioModelLoader", "MMAudioFeatureUtilsLoader", "MMAudioSampler"]},
    "ComfyUI-HunyuanVideo-Foley": {
        "repo": "https://github.com/phazei/ComfyUI-HunyuanVideo-Foley",
        "classes": ["HunyuanModelLoader", "HunyuanDependenciesLoader", "HunyuanFoleySampler"]},
    "ComfyUI-PromptRelay": {
        "repo": "https://github.com/kijai/ComfyUI-PromptRelay",
        "classes": ["PromptRelayEncode"]},
    "ComfyUI-Drama3": {
        "repo": "https://github.com/PedroMarinhoDev/ComfyUI-Drama3",
        "classes": ["Drama3Loader", "Drama3CodecLoader", "Drama3EncodeVoice", "Drama3Generate",
                    "Drama3Decode", "Qwen3ASRLoader", "Qwen3ASRTranscribe"]},
    "ComfyUI-Qwen-TTS": {
        "repo": "https://github.com/flybirdxx/ComfyUI-Qwen-TTS",
        "classes": ["FB_Qwen3TTSVoiceDesign", "FB_Qwen3TTSVoiceClone"]},
}

# The node classes seriesmith's graphs use (the shipped targets' workflows and
# target.json, and the graphs built in Python: upscale, post, refs, chain) that
# are ComfyUI's own, each found in ComfyUI's source (nodes.py, comfy_extras/,
# comfy_api_nodes/; checked 2026-11-02; SamplerCustom and SaveText 2026-11-03; Fish Audio's 2026-11-07). Nothing to install but a newer ComfyUI:
# a missing one says so. tests/test_features.py fails on a class a graph adds
# that is neither one of these, seriesmith's own, nor a pack's above.
CORE_CLASSES = frozenset({
    "AudioEncoderLoader", "BasicGuider", "BasicScheduler", "BlockSparseAttention", "CFGGuider",
    "CLIPLoader", "CLIPTextEncode", "CheckpointLoaderSimple", "ComfySwitchNode",
    "ConditioningZeroOut", "CreateVideo", "DualCLIPLoader", "EmptyAceStep1.5LatentAudio",
    "EmptyFlux2LatentImage", "EmptyImage", "EmptyLTXVLatentVideo", "EmptyLatentAudio",
    "EmptyLatentImage", "EmptySD3LatentImage", "EmptyYuE2LatentAudio", "Flux2Scheduler",
    "FluxGuidance", "FluxKVCache", "FluxKontextImageScale", "GetICLoRAParameters",
    "GetVideoComponents", "ImageBatch", "ImageFromBatch", "ImageInvert", "ImageScale",
    "ImageScaleToTotalPixels", "ImageToMask", "KSampler", "KSamplerAdvanced", "KSamplerSelect",
    "LTXAVTextEncoderLoader", "LTXVAddGuide", "LTXVAudioVAEDecode", "LTXVAudioVAEEncode",
    "LTXVAudioVAELoader", "LTXVConcatAVLatent", "LTXVConditioning", "LTXVCropGuides",
    "LTXVDualCFGGuider", "LTXVDurationPredictor", "LTXVEmptyLatentAudio", "LTXVImgToVideoInplace",
    "LTXVLatentUpsampler", "LTXVPreprocess", "LTXVScheduler", "LTXVSeparateAVLatent",
    "LatentConcat", "LatentCut", "LatentUpscaleModelLoader", "LoadAudio", "LoadImage",
    "MiniMaxH3ContextWindows", "MiniMaxH3LatentUpscaleWithModel",
    "LoadVideo", "LoraLoader", "LoraLoaderModelOnly", "ManualSigmas", "MiniMaxH3AddGuide",
    "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo", "MiniMaxH3SigmaShift",
    "MiniMaxMusic3TextEncode", "EmptyMiniMaxMusic3LatentAudio",
    "ComfyCloudMiniMaxMusic3TextToAudioNode",
    "FishAudioTextToSpeech", "FishAudioInstantVoiceClone",
    "ModelPatchLoader", "ModelSamplingAuraFlow", "ModelSamplingSD3", "OpticalFlowLoader",
    "QwenImage21Cache", "RandomNoise", "RebatchImages", "ReferenceLatent", "ReferenceMultiLatent",
    "ReferenceTimbreAudio", "RegexReplace", "RepeatImageBatch", "ResizeAndPadImage",
    "ResizeImageMaskNode", "SUPIRApply", "SamplerCustom", "SamplerCustomAdvanced", "SaveAudio", "SaveImage", "SaveText",
    "SaveVideo", "SeedVR2Conditioning", "SeedVR2PostProcessing", "SeedVR2Preprocess",
    "SeedVR2TemporalChunk", "SeedVR2TemporalMerge", "SetLatentNoiseMask", "SheetSage2AudioToABC",
    "SolidMask", "SplitSigmas", "TextEncodeAceStepAudio1.5", "TextEncodeFibo2",
    "TextEncodeQwenImage21", "TextEncodeQwenImageEditPlus", "TrimAudioDuration", "TrimVideoLatent",
    "UNETLoader", "UpscaleModelLoader", "VAEDecode", "VAEDecodeAudio", "VAEDecodeAudioTiled",
    "VAEDecodeTiled",
    "VAEEncode", "VAEEncodeAudio", "VAEEncodeTiled", "VAELoader", "Wan22ImageToVideoLatent",
    "WanFirstLastFrameToVideo", "WanImageToVideo", "WanVaceToVideo", "YuE2GenerateABC",
    "YuE2GenerateMusic"})

# ---------------------------------------------------------------------------
# items and features
# ---------------------------------------------------------------------------


@dataclass
class Item:
    kind: str                      # model | pack | link | pip | ffmpeg | key | hub
    name: str                      # the file, the pack's folder, the pip spec, "ffmpeg",
                                   # the key's setting ("api_key"); hub: the Hugging Face
                                   # repo, or the file's path in torch's hub folder
    folder: str = ""               # model: its models folder; hub: "hf", "torch" or a
                                   # models folder (hubcache)
    url: str = ""                  # model: its download; pack: its repo; hub: the repo's
                                   # page or the file's download
    target: str = ""               # model: the target that names it (status from readiness)
    where: str = "comfyui"         # pip: which Python: "comfyui", "seriesmith", or "align"
                                   # (the one align runs on: track.align_python)
    module: str = ""               # pip: the module that says it's installed
    pip_args: tuple = ()           # pip: extra arguments (an index URL)
    classes: tuple = ()            # pack: the node classes it loads
    files: tuple = ()              # hub (a repo): the files it must have (patterns)
    extra: tuple = ()              # hub (a repo): more fetched with them, not required
    label: str = ""                # hub: what it is, in words
    alt: str = ""                  # model: the same file in torch's hub folder (its path
                                   # there), which counts as installed too
    dir: str = ""                  # hub (into a models folder): the folder the repo goes
                                   # in there, when its pack doesn't read it by the repo's
                                   # name (ComfyUI-Qwen-TTS: models/qwen-tts/<model>/)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.folder + '/' if self.folder else ''}{self.name}"

    @property
    def manual(self) -> bool:
        """Put in by you (ComfyUI-Manager, pip, Settings), not by the installer."""
        return self.kind in ("pack", "pip", "key")

    @property
    def gated(self) -> bool:
        """A Hugging Face file whose repo asks you to accept a licence (FLUX,
        LTX-2.5): it needs a token (settings hf_token)."""
        return self.kind == "model" and any(r in self.url for r in GATED_REPOS)

    def to_json(self) -> dict:
        d = {"key": self.key, "kind": self.kind, "name": self.name}
        if self.manual:
            d["manual"] = True
        for k in ("folder", "url", "target", "module", "label"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.kind == "hub":
            from seriesmith import hubcache as HC
            d["into"] = HC.where_text(self)
            d.pop("folder", None)              # not a models folder, or said in `into`
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
    ("sound", "Sound", "Generated voices, recorded dialogue, music, ambience beds and effects."),
    ("upscale", "Upscaling", "Upscale takes (Upscale, Export 2x, master). Pick the methods you want."),
    ("post", "Post-processing", "Enhancement and motion blur after the upscale."),
    ("refs", "360s, turned views and relights", "The Refs tab's Make 360, a character's Turn and a relight."),
    ("hosted", "Hosted models", "Comfy's cloud: no files, a Comfy API key."),
    ("tools", "Tools", "seriesmith's node pack, comfy-api-proxy and a full ffmpeg."),
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
    return out + fetch_items(t)


def fetch_items(target) -> list[Item]:
    """What a target's node pack would fetch by itself (target.json
    `fetches`), as hub items: downloaded in Features, and readiness holds the
    target back until they're there."""
    from seriesmith import hubcache as HC
    out = []
    for repo, f in getattr(target, "fetches", {}).items():
        out.append(Item("hub", repo, folder=f["into"], url=f"{HC.HF}/{repo}",
                        files=tuple(f.get("files") or ()), extra=tuple(f.get("extra") or ()),
                        label=f.get("label") or "", dir=f.get("dir") or ""))
    return out


def whisper_item(model: str) -> Item:
    """A faster-whisper model align transcribes with, in the Hugging Face
    cache where faster-whisper looks (track.WHISPER_REPOS)."""
    from seriesmith import hubcache as HC
    from seriesmith import track as K
    repo = K.WHISPER_REPOS[model]
    return Item("hub", repo, folder="hf", url=f"{HC.HF}/{repo}", files=K.WHISPER_FILES,
                extra=K.WHISPER_EXTRA, label=f"Whisper {model} (faster-whisper)")


def nodes_hub():
    """comfy_nodes/_hub.py (what the node pack reads from torch's hub cache),
    loaded by its path: the node pack isn't a package seriesmith imports."""
    import importlib.util
    import sys
    name = "seriesmith_nodes_hub"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "comfy_nodes", "_hub.py")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[name] = mod
    return sys.modules[name]


def _optional_items(tid: str, param: str) -> list[Item]:
    """An optional model setting's file (its `default`, else what a pass
    names), with the target's download record of it: the extras a target
    leaves out of its own feature (the LTX duration head, SheetSage2). Status
    from the file alone: readiness counts the target ready without it."""
    from seriesmith import targets as TG
    try:
        t = TG.load_target(tid)
    except Exception:                                     # noqa: BLE001  not here (a trimmed install)
        return []
    spec = t.models.get(param) or {}
    names = [spec.get("default")] + [TG.wanted_files(t, p, None).get(param) for p in t.presets]
    if not any(isinstance(n, str) and n for n in names):
        # named nowhere but its download (a file no pass loads by name)
        names = [n for n, d in t.downloads.items() if d.get("folder") == spec.get("folder")
                 and TG.download_for(t, n, spec.get("folder")).get("url")
                 and any(_match(n, p) for p in spec.get("patterns") or [])]
    out = []
    for n in names:
        if isinstance(n, str) and n:
            base = n.replace("\\", "/").rsplit("/", 1)[-1]
            d = TG.download_for(t, n, spec.get("folder"))
            if d.get("folder") and base not in {i.name for i in out}:
                out.append(Item("model", base, folder=d["folder"], url=d.get("url") or ""))
    return out


def _match(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(name.lower(), pattern.lower())


def _edit_models() -> str:
    """The local picture models that edit (an edit, a relight, a Turn told in
    words runs on any of them), by their short names."""
    from seriesmith import targets as TG
    return ", ".join(t.short for t in TG.list_targets("image")
                     if TG.can_edit(t) and not TG.is_hosted(t.spec) and not t.draft)


def _hosted_models(kind: str) -> list:
    from seriesmith import targets as TG
    return [t for t in TG.list_targets(kind) if TG.is_hosted(t.spec)]


def _names(targets: list) -> str:
    """Their short names, each once (Seedance's four sizes are one)."""
    return ", ".join(dict.fromkeys(t.short for t in targets))


def _download_of(tid: str, name: str) -> list[Item]:
    """One file a target records the download of but no pass wants by name (a larger
    quantisation it prefers once it's there: Drama 3's), as a model item. Status from the
    file alone."""
    from seriesmith import targets as TG
    try:
        d = TG.download_for(TG.load_target(tid), name, None)
    except Exception:                                     # noqa: BLE001  not here (a trimmed install)
        return []
    return [Item("model", name, folder=d["folder"], url=d.get("url") or "")] if d.get("folder") else []


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
    from seriesmith import sdk as SDK
    from seriesmith import upscale as U
    from seriesmith import targets as TG
    from seriesmith import track as K
    from seriesmith import vocals as V
    hub = nodes_hub()

    def target_feature(fid, group, tid, label, about, extra=()):
        items = _target_items(tid)
        return Feature(fid, group, label, about, items + list(extra))

    def seedvr(size):
        return [Item("model", n, folder=f, url=u) for n, (f, u) in U.SEEDVR2_DOWNLOADS.items()
                if n == U.SEEDVR2_VAE or size in n]

    h3_up = TG.load_target("minimax_h3_ref2va").downloads.get("minimax_h3_latent_upscaler_3d_fp16.safetensors") or {}
    hosted_video, hosted_image = _hosted_models("video"), _hosted_models("image")
    feats = [
        Feature("video.h3", "video", "MiniMax H3 Ref2VA",
                "The default: characters and places like their pictures, lip-synced dialogue. "
                "Wants a recent NVIDIA card (developed on 32 GB). Also a picture model (H3 still).",
                _merge(_target_items("minimax_h3_ref2va"), _target_items("minimax_h3_still"))),
        target_feature("video.h3_fl2va", "video", "minimax_h3_fl2va", "MiniMax H3 FL2VA",
                       "Shots that carry on from the one before (continuous: first), and the location tours."),
        Feature("video.fasth3_omni", "video", "FastH3 Omni",
                "FastVideo's 8-step H3: up to eight characters and things per shot, no turbo LoRA. "
                "Also a picture model (Omni still), and its shots that carry on from the one "
                "before (FastH3 FL2VA). Shares H3's text encoder and VAEs.",
                _merge(_target_items("fasth3_omni"), _target_items("fasth3_omni_still"),
                       _target_items("fasth3_fl2va"))),
        Feature("video.pika_h3_flex", "video", "Pika H3 Flex",
                "Pika's six-step post-training of H3 (two LoRAs, about 2 GB each, on H3's own files): "
                "Ref2VA shots, and the ones that carry on from the one before (FL2VA). MiniMax H3 "
                "Community License.",
                _merge(_target_items("pika_h3_flex"), _target_items("pika_h3_flex_fl2va"))),
        Feature("video.h3_singularity", "video", "H3 Singularity",
                "AIGC-Singularity's fine-tune of H3 Ref2VA (clearer HDR, distant faces, motion), and "
                "its shots that carry on from the one before. H3's text encoder, VAEs and turbo "
                "LoRAs. Apache 2.0 over H3's community licence.",
                _merge(_target_items("h3_singularity"), _target_items("h3_singularity_fl2va"))),
        target_feature("video.ltx2", "video", "ltx2", "LTX-2.5",
                       "Quick, and makes its own sound. Gated: accept the licence on Hugging Face."),
        Feature("video.ltx2_duration", "video", "LTX-2.5 duration head",
                "dur: model: LTX-2.5 chooses a shot's length as it renders. Without it the shot "
                "renders at seriesmith's estimate. Gated, as LTX-2.5.",
                _optional_items("ltx2", "duration_head")),
        Feature("video.ltx2_quality", "video", "LTX-2.5 quality profile",
                "The LTX-2.5 dev transformer, for LTX-2.5's quality profile (more steps, real "
                "guidance; slower than the distilled one). Gated, as LTX-2.5.",
                _optional_items("ltx2", "quality_model")),
        Feature("video.ltx2_sheets", "video", "LTX-2.5 reading reference sheets",
                "LTX-2.5 working from the characters' and places' sheets: the ingredients IC-LoRA "
                "and ComfyUI-LTXVideo's IC-LoRA nodes. Gated, as LTX-2.5.",
                [_pack("ComfyUI-LTXVideo")] + _optional_items("ltx2", "reference_lora"), restart=True),
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
                       "Text to image, edits and keyframes; also what Make 360 and Turn run on."),
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
        target_feature("pictures.flux_kontext", "pictures", "flux_kontext", "FLUX.1 Kontext dev",
                       "Edits from one reference picture (relights and turns too). Its VAE is FLUX.1's."),
        target_feature("pictures.qwen_rapid_aio", "pictures", "qwen_rapid_aio", "Qwen-Image-Edit Rapid AIO",
                       "A 4-step all-in-one edit checkpoint, up to three reference pictures (relights and "
                       "turns too)."),
        Feature("h3.sparse_attention", "h3", "H3 sparse attention",
                "ComfyUI-PlagueKind-Nodes: the attention H3's turbo LoRAs were trained with. "
                "Without it H3 renders without it (degraded). The location tours need it.",
                [_pack("ComfyUI-PlagueKind-Nodes")], restart=True),
        Feature("sound.voice", "sound", "Generated voice samples",
                "A voice per character, that `clone` shots speak in: ComfyUI-LTXVideo and three LTX-2.5 "
                "files (gated). H3 FL2VA's clone shots make their lines with it too.",
                [_pack("ComfyUI-LTXVideo")] + _target_items("ltx2_voice"), restart=True),
        Feature("sound.voice_drama3", "sound", "Voices (Fish Audio Drama 3)",
                "A character's voice cloned from their sample, line by line (the voice model "
                "Drama 3): PedroMarinhoDev's ComfyUI-Drama3, the W4A8 experts (24.6 GB; about 32 GB "
                "of RAM with the experts in RAM, the default), its codec and Qwen3-ASR, which hears "
                "the sample's words. Fish Audio Community License: free under USD 500k yearly "
                "revenue, credit \"Built with Fish Audio\", no real person's voice without consent.",
                [_pack("ComfyUI-Drama3")] + _target_items("drama3"), restart=True),
        Feature("sound.voice_drama3_w6a8", "sound", "Drama 3 W6A8 (larger, steadier)",
                "Drama 3's W6A8 experts, 32.7 GB: used in place of W4A8 once they're here, and "
                "they fall silent less often with real voice clips. About 40 GB of free RAM with "
                "the experts in RAM.", _download_of("drama3", "drama3_w6a8experts_bf16.safetensors")),
        Feature("sound.voice_drama3_int8", "sound", "Drama 3 int8 (largest offered)",
                "Drama 3's int8 experts, 38.7 GB: used in place of the others once they're here; "
                "the fastest on cards under 24 GB. About 48 GB of free RAM with the experts in RAM.",
                _download_of("drama3", "drama3_int8experts_bf16.safetensors")),
        Feature("sound.voice_qwen3", "sound", "Voices (Qwen3-TTS)",
                "A character's voice designed from their description, then cloned from their "
                "sample (the voice model Qwen3-TTS): flybirdxx's ComfyUI-Qwen-TTS and three "
                "models (about 9 GB) into models/qwen-tts. Apache 2.0. On transformers 5.21 or "
                "later its cloning needs the pack's fix for the Mimi encoder "
                "(flybirdxx/ComfyUI-Qwen-TTS#115).",
                [_pack("ComfyUI-Qwen-TTS")] + _target_items("qwen3_tts"), restart=True),
        Feature("sound.voice_fishaudio", "sound", "Voices (Fish Audio Drama 3 on Comfy; paid)",
                "Drama 3 hosted, through ComfyUI's Fish Audio partner nodes: a character's voice "
                "cloned from their sample, paid per take, nothing to download; a Comfy API key "
                "in Settings.", [Item("key", "api_key")]),
        target_feature("sound.score", "sound", "stable_audio3", "Music cues (Stable Audio 3 Medium)",
                       "Score's default: an instrumental cue from its words, on ComfyUI's own nodes."),
        Feature("sound.score_theme", "sound", "A theme's melody score (SheetSage2)",
                "Each take rendered from a theme scored by how much of its melody it kept, so the "
                "ones that lost it rank last. Non-commercial licence (CC BY-NC 4.0).",
                _optional_items("stable_audio3", "sheetsage")),
        target_feature("sound.score_mrt2", "sound", "mrt2", "Music cues (Magenta RealTime 2)",
                       "Score that follows a cue's arc bar by bar: Google's Magenta RealTime 2 on "
                       "seriesmith's own node (its node pack), the base model for the final pass and "
                       "the small one for the proxy, and its style encoder, about 11 GB. Weights CC BY "
                       "4.0: credit Magenta RealTime 2 by Google.", [OWN_PACK]),
        target_feature("sound.songs", "sound", "yue2", "Songs (YuE2)",
                       "A song sung from its style words and lyrics, on ComfyUI's own nodes. "
                       "Non-commercial licence (CC BY-NC 4.0)."),
        Feature("sound.songs_theme", "sound", "A song's theme from a recording (SheetSage2)",
                "YuE2 singing a melody transcribed from a recording you give it. Non-commercial "
                "licence (CC BY-NC 4.0).", _optional_items("yue2", "sheetsage")),
        target_feature("sound.music_ace", "sound", "ace_step15", "Music and songs (ACE-Step 1.5 XL)",
                       "Cues and songs from words and lyrics, on ComfyUI's own nodes (MIT)."),
        target_feature("sound.songs_minimax", "sound", "minimax_music3", "Songs (MiniMax Music 3)",
                       "Songs whose words come through clearest, on ComfyUI's own nodes; the tempo "
                       "follows the song, not the cut. MiniMax's community licence (free under $20M "
                       "yearly revenue)."),
        target_feature("sound.songs_minimax_cloud", "sound", "minimax_music3_cloud",
                       "Songs (MiniMax Music 3 on Comfy Cloud; paid)",
                       "The same model hosted on Comfy Cloud through ComfyUI's partner node: paid "
                       "per take, nothing to download; a Comfy API key in Settings.",
                       [Item("key", "api_key")]),
        Feature("sound.ambience", "sound", "Ambience beds (MMAudio)",
                "A place's room tone or air, made once from its `ambience` words and looped under "
                "its shots: kijai's ComfyUI-MMAudio and its four files (MIT). The default.",
                [_pack("ComfyUI-MMAudio")] + _target_items("mmaudio_ambience"), restart=True),
        target_feature("sound.ambience_sfx", "sound", "sa3_sfx_ambience",
                       "Ambience beds (Stable Audio 3 Small SFX)",
                       "Livelier beds, second choice to MMAudio: Stable Audio 3's small sound-effects "
                       "model (Stability AI Community License)."),
        target_feature("sound.effects", "sound", "h3_foley", "Effects (MiniMax H3)",
                       "A shot's sync sound made from its take's frames (a clip's Sound menu, "
                       "seriesmith fx): H3 FL2VA's files, which H3 FL2VA shots use too. The default."),
        Feature("sound.effects_ltx", "sound", "Effects (LTX-2.3 Foley)",
                "Effects from Lightricks' LTX-2.3 Foley LoRA on LTX-2.3 dev: as good as H3 by ear, "
                "slower (a minute or two a shot), about 36 GB of files and ComfyUI-LTXVideo.",
                [_pack("ComfyUI-LTXVideo")] + _target_items("ltx23_foley"), restart=True),
        Feature("sound.effects_hunyuan", "sound", "Effects (HunyuanVideo-Foley XL)",
                "Effects from Tencent's HunyuanVideo-Foley XL: phazei's node pack and three files "
                "(Tencent's community licence: it doesn't apply in some territories).",
                [_pack("ComfyUI-HunyuanVideo-Foley")] + _target_items("hunyuan_xl_foley"), restart=True),
        Feature("sound.align", "sound", "Recorded dialogue",
                "faster-whisper, for align and the Recording window, in the Python align runs on "
                "(the server's you start it from: seriesmith's own, or ComfyUI's in the editor "
                "inside ComfyUI); "
                "with an NVIDIA card, CUDA 12's cuBLAS too, or it transcribes on the CPU (its "
                "CTranslate2 is built on CUDA 12 and brings cuDNN, not cuBLAS; ComfyUI's PyTorch "
                "has CUDA 13's, which it can't use). And the Whisper model align uses "
                f"({K.DEFAULT_MODEL}), into the Hugging Face cache: align won't run without it.",
                [Item("pip", "faster-whisper", where="align", module="faster_whisper"),
                 Item("pip", "numpy", where="align", module="numpy"),
                 Item("pip", "nvidia-cublas-cu12", where="align", module="nvidia.cublas"),
                 whisper_item(K.DEFAULT_MODEL)]),
        *[Feature(f"sound.whisper.{m}", "sound", f"Whisper {m} (align)",
                  "Another Whisper model for align (the Recording window's Model): "
                  f"{K.WHISPER_ABOUT.get(m, '')}", [whisper_item(m)])
          for m in K.MODELS if m != K.DEFAULT_MODEL],
        Feature("sound.vocals", "sound", "Vocal stem (Hybrid Demucs)",
                "A song's singing split from the band, for align --vocals and an episode that "
                "dubs from the stem (optional; off by default): seriesmith's node pack and "
                "torchaudio's Hybrid Demucs weights (a copy torchaudio downloaded before, in "
                "torch's hub cache, counts). The split won't run without them.",
                [OWN_PACK, Item("model", V.WEIGHTS_FILE, folder=V.WEIGHTS_FOLDER,
                                url=V.WEIGHTS_URL, alt=hub.TORCHAUDIO_HDEMUCS)], restart=True),
        Feature("sound.demucs", "sound", "Keep H3's foley under your vocal",
                "demucs in ComfyUI's Python, for the dub_keep_foley audio policy, and its "
                "htdemucs model in torch's hub cache, where demucs looks: without it the take "
                "keeps no foley bed.",
                [Item("pip", "demucs", where="comfyui", module="demucs"),
                 Item("hub", hub.HTDEMUCS, folder="torch", url=hub.HTDEMUCS_URL,
                      label="demucs's htdemucs model")]),
        Feature("upscale.h3_latent", "upscale", "H3 latent re-sample (2x)",
                "H3's latent upscaler model. ComfyUI 0.44 or later has the nodes that use it, "
                "and samples a long take in windows so it fits a 32 GB card.",
                [Item("model", "minimax_h3_latent_upscaler_3d_fp16.safetensors",
                      folder=h3_up.get("folder") or "latent_upscale_models", url=h3_up.get("url") or "")]),
        Feature("upscale.h3_pack", "upscale", "H3 upscaler node pack (optional)",
                "For a ComfyUI before 0.44, or to choose it over ComfyUI's own: LBH-123-AI's pack. "
                "Its Plus version, which ComfyUI-Manager lists, works too; only one can be installed.",
                [_pack("Comfyui_Minimax_h3_latent_Upscaler")], restart=True),
        Feature("upscale.h3_long", "upscale", "H3 context windows node pack (optional)",
                "For a ComfyUI before 0.44, or to choose it over ComfyUI's own: comfyui-obvpm-timeline's "
                "context windows, for H3 takes over 5.5 s.",
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
                "Qwen-Image 2.1's multiple-angles LoRA (and Qwen-Image 2.1 itself): the surest turn. "
                f"Without it, Turn runs on any edit model installed ({_edit_models()}), told the "
                "turn in words (Made with › Turns with).",
                [Item("model", R.TURN_LORA, folder="loras", url=R.TURN_LORA_URL)] + _target_items("qwen_image_21")),
        Feature("refs.relight", "refs", "Relight a plate or a sequence",
                "A relight is an edit of the plate: it runs on the episode's edit model (Made "
                f"with), any of {_edit_models()}. The default is Qwen-Image 2.1: these files.",
                _target_items(TG.DEFAULT_EDIT_TARGET)),
        Feature("hosted.comfy_api", "hosted", "Comfy API: Router models, Cloud, deployments",
                f"{len(hosted_video)} video models ({_names(hosted_video)}) and "
                f"{len(hosted_image)} picture models ({_names(hosted_image)}) "
                "on Comfy Router, and renders on Comfy Cloud or a deployment: paid per run, "
                "nothing to download. A Comfy API key (platform.comfy.org) in Settings, and "
                "comfy-sdk, which they run on, in the Python seriesmith runs on.",
                [Item("key", "api_key"),
                 Item("pip", SDK.REQUIREMENT, where="seriesmith", module="comfy_sdk")]),
        Feature("tools.proxy", "tools", "comfy-api-proxy",
                "Local renders through comfy-api-proxy (Settings › Through comfy-api-proxy) "
                "instead of straight to ComfyUI: the Comfy API in front of your own ComfyUI. "
                "Optional; seriesmith starts it when it's installed.",
                [Item("pip", "comfy-api-proxy", where="seriesmith", module="comfy_api_proxy")]),
        Feature("tools.seriesmith_nodes", "tools", "seriesmith's node pack",
                "Its shot loader and saver, the chain, upscale and post nodes: latent continuity, "
                "kept latents, upscales and posts. Installed with ComfyUI-Manager, or linked "
                "from this repo into ComfyUI's custom_nodes. Without it, shots render through "
                "ComfyUI's own nodes.", [OWN_PACK], restart=True),
        Feature("tools.ffmpeg", "tools", "ffmpeg and ffprobe",
                "A full ffmpeg build in seriesmith's own folder, used before the built-in fallbacks "
                "(or set your own folder in Settings): assemble, master, publish, the XML "
                "import's proxies.", [Item("ffmpeg", "ffmpeg")]),
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
    api_key_set: bool | None = None          # a Comfy API key in Settings (or COMFY_API_KEY)
    hub_has: Callable[[Item], bool | None] = lambda item: None   # a hub item (hubcache.present)


def shell_line(cmd: list[str]) -> str:
    """`cmd` as one line for this system's shell: on Windows an argument with
    a character cmd or PowerShell would read (a version spec's < or >) is
    quoted too, which list2cmdline leaves bare."""
    import shlex
    import subprocess
    if os.name != "nt":
        return shlex.join(cmd)
    return " ".join(f'"{a}"' if any(c in a for c in '<>|&^') and " " not in a
                    else subprocess.list2cmdline([a]) for a in cmd)


def pip_command(item: Item, python: str | None) -> str:
    """The pip line that puts `item` in `python` ("python" when it isn't
    known), quoted for this system's shell."""
    return shell_line([python or "python", "-m", "pip", "install", item.name, *item.pip_args])


KEY_HOW = ("Set your Comfy API key (platform.comfy.org) in Settings › Comfy API key, or in "
           "the COMFY_API_KEY environment variable.")


def how(item: Item, env: Env) -> str:
    """How you put in a pack, a pip package or a key seriesmith doesn't install."""
    if item.kind == "key":
        return KEY_HOW
    if item.kind == "pack":
        # some packs aren't in Manager's list (2026-10-28: the LBH latent upscaler), so
        # the clone is always offered too
        return (f"Install {item.name} with ComfyUI-Manager (Custom Nodes Manager, search "
                f"\"{item.name}\"), or if it isn't listed there, clone {item.url} into "
                f"custom_nodes (git clone, or Manager's Install via Git URL); then restart ComfyUI.")
    if item.kind == "pip":
        line = f"Run: {pip_command(item, env.python_for(item.where))}"
        if item.where == "align":
            # align runs in the Python of the server it's started from: the command is this one's
            line += (" Align runs in the Python of the server you start it from: seriesmith's own "
                     "server uses seriesmith's Python, the editor inside ComfyUI uses ComfyUI's. "
                     "This command is for this server's; install it in the one you run align from.")
        return line
    return ""


def item_status(item: Item, env: Env) -> str:
    """installed | missing | restart (a pack cloned but not loaded yet) | unknown"""
    if item.kind == "model":
        got = env.model_exists(item.folder, item.name)
        if got:
            return "installed"
        if item.alt and env.hub_has(Item("hub", item.alt, folder="torch")):
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
    if item.kind == "key":
        return "unknown" if env.api_key_set is None else "installed" if env.api_key_set else "missing"
    if item.kind == "hub":
        got = env.hub_has(item)
        return "installed" if got else ("missing" if got is False else "unknown")
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
    """Every model file with a recorded download, by name, and every hub
    item, by its repo or path: what the What's missing window may ask for by
    name (the server never takes a URL from the page)."""
    from seriesmith import targets as TG
    out: dict[str, Item] = {}
    for f in features or catalog():
        for i in f.items:
            if i.kind in ("model", "hub") and i.url:
                out.setdefault(i.name, i)
    for t in TG.list_targets():
        for name, d in t.downloads.items():
            if d.get("url") and d.get("folder"):
                base = name.replace("\\", "/").rsplit("/", 1)[-1]
                out.setdefault(base, Item("model", base, folder=d["folder"], url=d["url"], target=t.id))
    return out


def missing_core(known) -> dict[str, list[str]]:
    """Of ComfyUI's own node classes seriesmith's graphs use (CORE_CLASSES), those this
    ComfyUI doesn't have (`known`: its /object_info, or any collection of class names),
    each with the shipped targets whose renders need it ([] for one only seriesmith's own
    graphs use: upscale, post, refs). Run at startup: a ComfyUI that renamed or dropped a
    node, or one older than a model, says which models it stops."""
    from seriesmith import edit as E
    from seriesmith import targets as TG
    gone = sorted(c for c in CORE_CLASSES if c not in known)
    if not gone:
        return {}
    users: dict[str, list[str]] = {c: [] for c in gone}
    for t in TG.list_targets():
        if TG.is_hosted(t.spec):
            continue
        try:
            need = E.target_nodes(t)
        except Exception:                                 # noqa: BLE001  a target that can't say
            continue
        for c in gone:
            if c in need and need[c].get("tier") != "optional":
                users[c].append(t.id)
    return users


def pack_for_class(cls: str) -> Item | None:
    if cls in OWN_PACK.classes or cls.startswith("Seriesmith"):
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
            if str(name) in known and known[str(name)].kind == "hub":
                items.append(known[str(name)])            # a repo, by its whole name
            elif base in known:
                items.append(known[base])
            else:
                skipped.append(f"{base}: no recorded download")
    for cls in classes:
        p = pack_for_class(cls)
        if p:
            items.append(p)
        elif cls in CORE_CLASSES:
            skipped.append(f"{cls}: one of ComfyUI's own nodes: update ComfyUI and restart it")
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


def feature_label_of(item: Item, features: list[Feature] | None = None) -> str:
    """The label of the first feature that has `item` ("" if none does)."""
    for f in features or catalog():
        if any(i.key == item.key for i in f.items):
            return f.label
    return ""


def managed_ffmpeg_dir() -> str:
    """Where tools.ffmpeg puts the build: beside the settings file."""
    from seriesmith.settings import settings_path
    return os.path.join(os.path.dirname(settings_path()), "ffmpeg")


__all__ = ["CORE_CLASSES", "Env", "Feature", "GROUPS", "Item", "PACKS", "catalog",
           "feature_label_of", "fetch_items", "how", "item_status", "known_files",
           "managed_ffmpeg_dir", "nodes_hub", "pack_for_class", "pip_command", "resolve",
           "shell_line", "status", "whisper_item"]
