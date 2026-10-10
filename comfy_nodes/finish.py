"""
The upscale and post passes' compute nodes, for any backend: h3pipe's
H3PixelUpscale, H3FinishUpscale, H3HoldAudio (comfy_nodes/h3_upscale.py) and
H3FramesToBatch, H3MotionBlur (h3_post.py), copied unchanged under seriesmith's
names so the two packs can be installed side by side.

SeriesmithPixelUpscale    an upscale model over the frames a few at a time,
                          each batch resized to the target size, finished
                          (frequency split, keep soft, grain)
SeriesmithFinishUpscale   that finish, for frames something else upscaled
                          (SeedVR2's)
SeriesmithHoldAudio       a noise mask that re-samples the picture of a joint
                          AV latent and keeps its audio as it is
SeriesmithFramesToBatch   a list of image batches back into one batch
SeriesmithMotionBlur      shutter blur along each pixel's optical flow
"""
from __future__ import annotations

import torch

PRECISIONS = ("fp16", "fp32")


# Ideas from sajb0t/comfyui_ensemble_upscale (no licence, so nothing copied: the
# maths is the ordinary low/high band split), fitted to video: every
# measurement that could change from frame to frame is taken once per clip.

BAND_SIGMA = 1.5          # the band cutoff, in the source's pixels


def gaussian_blur(x, sigma: float):
    """A separable Gaussian blur of BCHW `x` (reflect padding, radius 3 sigma)."""
    import torch.nn.functional as F
    if sigma <= 0:
        return x
    r = max(1, int(-(-3.0 * sigma // 1)))
    t = torch.arange(-r, r + 1, device=x.device, dtype=torch.float32)
    k = torch.exp(-(t * t) / (2.0 * sigma * sigma))
    k = (k / k.sum()).to(x.dtype)
    c = x.shape[1]
    kx = k.view(1, 1, 1, -1).expand(c, 1, 1, -1)
    ky = k.view(1, 1, -1, 1).expand(c, 1, -1, 1)
    pr = min(r, x.shape[-1] - 1)
    pc = min(r, x.shape[-2] - 1)
    y = F.conv2d(F.pad(x, (pr, pr, 0, 0), mode="reflect"), kx[..., r - pr:r + pr + 1], groups=c)
    return F.conv2d(F.pad(y, (0, 0, pc, pc), mode="reflect"), ky[:, :, r - pc:r + pc + 1, :], groups=c)


def resize_to(x, height: int, width: int, lanczos):
    """BCHW `x` at height x width: a box average when it shrinks by a whole factor
    on both sides (a 4x model to 2x: no ringing), else `lanczos(x, w, h)`."""
    import torch.nn.functional as F
    h, w = x.shape[-2:]
    if (h, w) == (height, width):
        return x
    if h > height and h % height == 0 and w % width == 0 and h // height == w // width:
        return F.avg_pool2d(x, h // height)
    return lanczos(x, width, height)


def detail_map(src, sigma: float = BAND_SIGMA):
    """How much fine detail each pixel of BCHW `src` has (B1HW, unnormalised)."""
    high = (src - gaussian_blur(src, sigma)).abs().mean(dim=1, keepdim=True)
    return gaussian_blur(high, sigma)


def detail_scale(images, device, sigma: float = BAND_SIGMA) -> float:
    """One normalising level for the whole clip (IMAGE [T, H, W, C]): the 90th
    percentile of detail over about 8 frames. Per frame, it would flicker."""
    n = int(images.shape[0])
    pick = list(range(0, n, max(1, n // 8)))[:8]
    d = detail_map(images[pick].movedim(-1, 1).to(device).float(), sigma).flatten()
    d = d[:: max(1, d.numel() // (1 << 20))]
    return max(0.02, float(torch.quantile(d.float(), 0.9)))


def finish(src, up, *, frequency_split: bool = True, keep_soft: float = 0.0,
           level: float = 1.0, sigma: float = BAND_SIGMA):
    """The upscaled batch `up` (BCHW, target size) finished against its source
    frames `src` (BCHW): with `frequency_split`, colour and tone (the low band)
    from a bicubic enlarge of the source, only detail (the high band) from the
    model; with `keep_soft` (0-1), the model's detail faded where the source had
    none (bokeh, soft focus), `level` being the clip's detail_scale."""
    import torch.nn.functional as F
    if not frequency_split and keep_soft <= 0:
        return up
    h, w = up.shape[-2:]
    s = sigma * h / float(src.shape[-2])
    low_up = gaussian_blur(up, s)
    high = up - low_up
    if keep_soft > 0:
        d = (detail_map(src, sigma) / level).clamp(0, 1)
        d = F.interpolate(d, size=(h, w), mode="bilinear", align_corners=False).clamp(0, 1)
        high = high * (1.0 - float(keep_soft) * (1.0 - d))
    if frequency_split:
        base = F.interpolate(src, size=(h, w), mode="bicubic", align_corners=False)
        low = gaussian_blur(base, s)
    else:
        low = low_up
    return (low + high).clamp(0, 1)


def add_grain(x, amount: float, seed: int, first: int):
    """Monochrome Gaussian grain on BCHW `x`, a different pattern each frame
    (seeded by `seed` + the frame's index `first + b`, so a redo repeats it)."""
    if amount <= 0:
        return x
    out = x.clone()
    for b in range(x.shape[0]):
        g = torch.Generator().manual_seed(int(seed) * 100003 + first + b)
        noise = torch.randn((1, x.shape[-2], x.shape[-1]), generator=g)
        out[b] = (x[b] + float(amount) * noise.to(x.device, x.dtype)).clamp(0, 1)
    return out


class SeriesmithPixelUpscale:
    """Upscale frames with an upscale model (UpscaleModelLoader's), `chunk`
    frames at a time, resizing each batch to width x height (lanczos) as it
    goes: a 4x model over a hundred frames at once would need tens of GB, this
    holds one batch at the model's size and the rest at the target size."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "upscale_model": ("UPSCALE_MODEL",),
            "width": ("INT", {"default": 1920, "min": 16, "max": 16384, "step": 2}),
            "height": ("INT", {"default": 1088, "min": 16, "max": 16384, "step": 2}),
            "chunk": ("INT", {"default": 4, "min": 1, "max": 64}),
            # fp16: the model under CUDA autocast (about twice as fast, what
            # RealESRGAN is normally run at); fp32: as core's node runs it
            "precision": (list(PRECISIONS), {"default": "fp16"}),
            # colour and tone from the source, detail from the model
            "frequency_split": ("BOOLEAN", {"default": True}),
            # 0-1: fade invented detail where the source was soft (bokeh)
            "keep_soft": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05}),
            # film grain after, per frame; 0 is off
            "grain": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.2, "step": 0.005}),
            "grain_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"
    CATEGORY = "seriesmith/upscale"

    def upscale(self, images, upscale_model, width, height, chunk=4, precision="fp16",
                frequency_split=True, keep_soft=0.0, grain=0.0, grain_seed=0):
        # What core's ImageUpscaleWithModel does, but with the model loaded once
        # for the whole clip: calling that node per batch re-ran its load (and
        # logged "prepared for dynamic VRAM loading") for every batch.
        import comfy.model_management as mm
        import comfy.utils

        n, chunk = int(images.shape[0]), max(1, int(chunk))
        width, height = int(width), int(height)
        scale = max(float(getattr(upscale_model, "scale", 1.0)), 1.0)
        per_batch = images[:chunk].nelement() * images.element_size()
        mm.load_models_gpu([upscale_model.patcher],
                           memory_required=(512 * 512 * 3) * images.element_size() * scale * 384.0
                           + per_batch, force_full_load=True)
        device = upscale_model.patcher.load_device
        half = precision == "fp16" and str(device).startswith("cuda")

        def model(a):
            if not half:
                return upscale_model(a.float())
            with torch.autocast("cuda", dtype=torch.float16):
                return upscale_model(a.float()).float()
        pbar = comfy.utils.ProgressBar(n)
        out = torch.empty((n, height, width, 3), dtype=torch.float16)
        level = detail_scale(images, device) if keep_soft > 0 else 1.0

        def lanczos(x, w, h):
            return comfy.utils.common_upscale(x, w, h, "lanczos", "disabled")
        tile, overlap = 512, 32
        for i in range(0, n, chunk):
            batch = images[i:i + chunk].movedim(-1, -3).to(device)
            while True:
                try:
                    big = comfy.utils.tiled_scale(batch, model,
                                                  tile_x=tile, tile_y=tile, overlap=overlap,
                                                  upscale_amount=upscale_model.scale,
                                                  output_device=mm.intermediate_device())
                    break
                except Exception as e:
                    mm.raise_non_oom(e)            # only out-of-memory gets a smaller tile
                    tile //= 2
                    if tile < 128:
                        raise
            big = resize_to(big.clamp(0, 1), height, width, lanczos)
            big = finish(batch.float().to(big.device), big.float(), frequency_split=frequency_split,
                         keep_soft=float(keep_soft), level=level)
            big = add_grain(big, float(grain), int(grain_seed), i)
            out[i:i + big.shape[0]] = big.movedim(1, -1).to("cpu", torch.float16)
            pbar.update(big.shape[0])
        return (out,)


class SeriesmithFinishUpscale:
    """The pixel method's finish (frequency split, keep soft, grain; see finish)
    for frames something else upscaled: SeedVR2's, say. `source` is the take's
    own frames, the same count, at any size."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "source": ("IMAGE",),
            "frequency_split": ("BOOLEAN", {"default": True}),
            "keep_soft": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05}),
            "grain": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.2, "step": 0.005}),
            "grain_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            "chunk": ("INT", {"default": 8, "min": 1, "max": 64}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "finish"
    CATEGORY = "seriesmith/upscale"

    def finish(self, images, source, frequency_split=True, keep_soft=0.0, grain=0.0,
               grain_seed=0, chunk=8):
        n = min(int(images.shape[0]), int(source.shape[0]))
        if not frequency_split and keep_soft <= 0 and grain <= 0:
            return (images,)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        level = detail_scale(source, device) if keep_soft > 0 else 1.0
        h, w = int(images.shape[1]), int(images.shape[2])
        out = torch.empty((n, h, w, 3), dtype=torch.float16)
        for i in range(0, n, max(1, int(chunk))):
            up = images[i:i + chunk, :, :, :3].movedim(-1, 1).to(device).float()
            src = source[i:i + chunk, :, :, :3].movedim(-1, 1).to(device).float()
            x = finish(src, up, frequency_split=frequency_split, keep_soft=float(keep_soft),
                       level=level)
            x = add_grain(x, float(grain), int(grain_seed), i)
            out[i:i + x.shape[0]] = x.movedim(1, -1).to("cpu", torch.float16)
        return (out,)


class SeriesmithHoldAudio:
    """Re-sample the picture, keep the audio: a per-stream noise mask of ones on
    the video and zeros on the audio, on a joint AV latent. The sampler then
    sees the audio clean at every step and the lips follow it. A video mask the
    latent already has is kept (LTX's guide frames, a first frame held)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"latent": ("LATENT",)}}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "hold"
    CATEGORY = "seriesmith/upscale"

    def hold(self, latent):
        import comfy.nested_tensor

        samples = latent["samples"]
        if not getattr(samples, "is_nested", False):
            raise ValueError("SeriesmithHoldAudio needs a joint audio/video latent (H3's), "
                             "not a video-only one")
        video, audio = samples.unbind()[:2]
        mask = latent.get("noise_mask")
        vmask = mask.unbind()[0] if getattr(mask, "is_nested", False) else torch.ones_like(video)
        out = dict(latent)
        out["noise_mask"] = comfy.nested_tensor.NestedTensor((vmask, torch.zeros_like(audio)))
        return (out,)


class SeriesmithFramesToBatch:
    """A list of image batches (RebatchImages' output, run through a per-frame
    model) back into one batch, in order."""

    INPUT_IS_LIST = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",)}}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "join"
    CATEGORY = "seriesmith/post"

    def join(self, images):
        import torch
        parts = [b if b.dim() == 4 else b[None] for b in images]
        return (torch.cat([p.to(parts[0].dtype) for p in parts], dim=0),)


def _grid(h: int, w: int, device):
    """A (1, h, w, 2) sampling grid of pixel coordinates (x, y)."""
    import torch
    ys, xs = torch.meshgrid(torch.arange(h, device=device, dtype=torch.float32),
                            torch.arange(w, device=device, dtype=torch.float32), indexing="ij")
    return torch.stack((xs, ys), dim=-1)[None]


def _sample(img, pix, h: int, w: int):
    """img (n, c, h, w) sampled at pixel coordinates pix (n, h, w, 2)."""
    import torch.nn.functional as F
    norm = pix.clone()
    norm[..., 0] = norm[..., 0] * (2.0 / max(1, w - 1)) - 1.0
    norm[..., 1] = norm[..., 1] * (2.0 / max(1, h - 1)) - 1.0
    return F.grid_sample(img, norm, mode="bilinear", padding_mode="border", align_corners=True)


class SeriesmithMotionBlur:
    """Shutter blur along each pixel's motion: optical flow (RAFT, ComfyUI's
    OpticalFlowLoader) between neighbouring frames gives a velocity per pixel,
    and each pixel is averaged over `samples` points along it, centred on the
    frame, across `amount` of the frame interval (0.5: a 180-degree shutter).
    Flow is measured at `flow_width` and scaled up. Where forward and backward
    flow disagree (occlusion, flow errors) the blur fades out, motion under
    `min_motion` pixels (at flow_width) gets none (RAFT's jitter on still
    areas would otherwise soften them a little differently every frame), and no
    pixel is smeared further than `max_motion` of the frame width per frame. The frame
    count and size don't change; amount 0 passes the frames through."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "optical_flow": ("OPTICAL_FLOW",),
            "amount": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.05}),
            "samples": ("INT", {"default": 9, "min": 3, "max": 32}),
            "flow_width": ("INT", {"default": 960, "min": 256, "max": 2048, "step": 8}),
            "max_motion": ("FLOAT", {"default": 0.08, "min": 0.005, "max": 0.5, "step": 0.005}),
            "chunk": ("INT", {"default": 8, "min": 1, "max": 64}),
        }, "optional": {
            "min_motion": ("FLOAT", {"default": 0.75, "min": 0.0, "max": 8.0, "step": 0.05}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "blur"
    CATEGORY = "seriesmith/post"

    def blur(self, images, optical_flow, amount=0.25, samples=9, flow_width=960,
             max_motion=0.08, chunk=8, min_motion=0.75):
        import torch
        import torch.nn.functional as F
        import comfy.model_management as mm
        n, h, w = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        if amount <= 0 or n < 2:
            return (images,)
        device = mm.get_torch_device()
        mm.load_model_gpu(optical_flow)
        raft = optical_flow.model
        fw = max(64, min(int(flow_width), w) // 8 * 8)
        fh = max(64, int(round(h * fw / w / 8)) * 8)
        step = max(1, int(chunk))

        def small(i0, i1):
            x = images[i0:i1, :, :, :3].movedim(-1, 1).to(device, torch.float32)
            return F.interpolate(x, size=(fh, fw), mode="bilinear", align_corners=False) * 2 - 1

        # flow i -> i+1 for every i < n-1, at fh x fw, on the CPU between uses
        fwd = torch.empty((n - 1, 2, fh, fw), dtype=torch.float16)
        bwd = torch.empty((n - 1, 2, fh, fw), dtype=torch.float16)   # i+1 -> i
        with torch.no_grad():
            for i in range(0, n - 1, step):
                j = min(n - 1, i + step)
                a, b = small(i, j), small(i + 1, j + 1)
                fwd[i:j] = raft(a, b)[-1].to("cpu", torch.float16)
                bwd[i:j] = raft(b, a)[-1].to("cpu", torch.float16)

            out = torch.empty_like(images[..., :3])
            base_s = _grid(fh, fw, device)
            base = _grid(h, w, device)
            cap = float(max_motion) * fw
            offsets = torch.linspace(-amount / 2.0, amount / 2.0, int(samples), device=device)
            for i in range(0, n, step):
                j = min(n, i + step)
                vel = []
                for t in range(i, j):
                    parts = []
                    if t < n - 1:
                        f = fwd[t:t + 1].to(device, torch.float32)
                        # forward-backward check: f, then the next frame's flow back
                        back = _sample(bwd[t:t + 1].to(device, torch.float32),
                                       base_s + f.movedim(1, -1), fh, fw)
                        err = (f + back).norm(dim=1, keepdim=True)
                        conf = torch.clamp(1.0 - err / (1.0 + 0.2 * f.norm(dim=1, keepdim=True)), 0, 1)
                        parts.append(f * conf)
                    if t > 0:
                        parts.append(-bwd[t - 1:t].to(device, torch.float32))
                    v = sum(parts) / len(parts)
                    mag = v.norm(dim=1, keepdim=True)
                    if min_motion > 0:      # fade in from min_motion to twice it
                        v = v * torch.clamp((mag - min_motion) / min_motion, 0.0, 1.0)
                    v = v * torch.clamp(cap / (mag + 1e-6), max=1.0)
                    vel.append(v)
                v = torch.cat(vel, dim=0)
                v = F.interpolate(v, size=(h, w), mode="bilinear", align_corners=False)
                v = (v * torch.tensor([w / fw, h / fh], device=device).view(1, 2, 1, 1)).movedim(1, -1)
                img = images[i:j, :, :, :3].movedim(-1, 1).to(device, torch.float32)
                acc = torch.zeros_like(img)
                for s in offsets:
                    acc += _sample(img, base + v * s, h, w)
                out[i:j] = (acc / len(offsets)).movedim(1, -1).to(out.device, out.dtype)
        return (out,)


NODE_CLASS_MAPPINGS = {
    "SeriesmithPixelUpscale": SeriesmithPixelUpscale,
    "SeriesmithFinishUpscale": SeriesmithFinishUpscale,
    "SeriesmithHoldAudio": SeriesmithHoldAudio,
    "SeriesmithFramesToBatch": SeriesmithFramesToBatch,
    "SeriesmithMotionBlur": SeriesmithMotionBlur,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeriesmithPixelUpscale": "Pixel Upscale (seriesmith)",
    "SeriesmithFinishUpscale": "Finish Upscale (seriesmith)",
    "SeriesmithHoldAudio": "Hold Audio (seriesmith)",
    "SeriesmithFramesToBatch": "Frames To Batch (seriesmith)",
    "SeriesmithMotionBlur": "Motion Blur (seriesmith)",
}
