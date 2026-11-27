# Kandinsky SR 2.0: tried and dropped

Dropped 2026-11-27, with nothing of it left in seriesmith. This is the record of what was
tried and why, so it isn't tried again blind. Bring it back only if a newer version does
better, or someone asks for it.

## What it was

Kandinsky Lab's two super-resolution models, both released 2026-11-25/26 under the MIT licence:

- **Video SR 2.0** (`kandinskylab/Kandinsky-6.0-VSR-2.0-distilled2steps-Diffusers`, 17.4 GB;
  the official `kandinsky6-sr` pack). It upscales the whole clip in its own video VAE's
  latent space, x2, x2.25 or x4, with a 2-step SR model over tiles. Clips can be up to 361
  frames.
- **ImageSR 2.0** (`kandinskylab/Kandinsky-ImageSR-2.0`; the community's
  `comfyui-ksr-unofficial` pack on a 10.25 GB single-file repack, `hmdlsk/Kandinsky-ImageSR-2.0-ComfyUI`,
  with FLUX.1's VAE). A one-step diffusion SR for pictures, x2 or x4, with a creativity setting
  from 0 to 8.

Both were built in (on branch kandinsky-sr, then reverted in full):

- `method: "kandinsky"`: Kandinsky's smallest scale that covers the size asked, then lanczos
  down to it. The frames were held to 1 + 8k, and the node was told 24 fps so it kept every
  frame.
- `kandinsky_imagesr` as a pixel model, offered by name beside `rtx_vsr`. It also upscaled a
  plate's crop, from a button in the Refs tab.
- Features items for both models.
- The installer's nested models folder.

## Why it was dropped

**On a 32 GB card the pack as published doesn't run.** This was an RTX 5090 with torch 2.15
cu132, cuDNN 9.26 and ComfyUI 0.45. The video VAE decodes each tile 16 frames at a time:
- At x4 it aborted ComfyUI ("Fatal Python error: Aborted" in conv3d).
- At x2 it raised CUDA out of memory.

Either way the CUDA context was poisoned and ComfyUI had to be restarted.

The encode is a second limit. It runs on the whole clip, untiled, 16 frames at a time, so an
input of 2688x1536 (H3's 2x) aborted in the encoder.

Patched on this machine to decode 1 latent frame and encode 4 frames at a time
(`video_kvae/cached_model.py`), it fit in 28 to 30 GB. A change to another pack can't be
shipped, and an update of the pack undoes it. Nothing was sent to Kandinsky Lab.

**With the patches it didn't earn a place.** The comparison used the three last-light takes of
docs/LTX_UPSCALE.md, upscaled to 4K. The other methods' files were measured again with one
script:
- detail: the luma's mean |Laplacian|
- shimmer: the frame-to-frame change of the fine detail, against the take's own
- face: the mean |Laplacian| on sh060's face

| | sh030 detail | sh030 shimmer | sh060 face (take 0.92) | sh060 shimmer | sh060 time |
|---|---|---|---|---|---|
| SeedVR2 7B | 3.64 | 2.00x | 2.41 | 1.63x | 5.4 min |
| H3 latent + SeedVR2 | 3.64 | 1.95x | 2.93 | 1.60x | 7.0 min |
| LTX Refine Details | 1.72 | 1.23x | 1.57 | 1.13x | 10.4 min |
| Kandinsky Video SR (x4) | 1.71 | 1.30x | 1.42 | 1.11x | 15.3 min |
| Kandinsky ImageSR per frame (x4) | 3.52 | 2.93x | | | |

- **Video SR from the take:** steady, and faithful to the face (cleaner than LTX Refine's,
  which ghosts), but it adds little detail. sh030's spray stayed a haze. It was also the
  slowest, at about 13 s a frame to 4K.
- **H3 latent 2x into Kandinsky** (both patches; sh060, 15.5 min): softer than just stretching
  H3's 2x to 4K. Face sharpness was 1.96, against 2.32 for the stretch and 3.37 for H3 + SeedVR2.
  It lost the lash and brow detail H3 drew. Its one gain, a little less shimmer, the H3
  re-sample already had.
- **ImageSR per frame:** SeedVR2's detail with half again its shimmer, at about 14 s a frame.
- **ImageSR on a single picture:** the most detail of any of them (sh060's still to 4K in 15 s,
  25.7 GB). But it redraws rather than sharpens: the eyes changed shape a little, and motion
  blur came out sharp. It wasn't kept for pictures either, because nothing else in seriesmith
  upscales a picture that way, and the user doesn't expect to use it.

The files are in `F:\ComfyProjects\_ltxup_test\_compare\`:
- `kand_sh030_f20.png`: sh030 frame 20, the splash, by each method.
- `kand_sh060_face.png`: sh060's face by each method.
- `kand_h3_sh060_face.png`: H3 latent 2x stretched, + SeedVR2, and + Kandinsky.
- `ksr_face.png`, `ksr_case.png`: ImageSR on sh060's still.
- `kand_sh0x0.json`: the measurements.
