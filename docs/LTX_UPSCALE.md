# LTX-2.5 detail pass: an upscale method

The design record and checklist of the `ltx` upscale method: a take's frames upscaled by
LTX-2.5 with one of Lightricks' detail IC-LoRAs (Refine Details, Restore), sampled in
overlapping tiles that share one canvas (ComfyUI-LTXVideo's Tiled Fusion sampler). Started
2026-11-13.

## Why

Comfy's LTX VFX release (November 2026) brought a V2V upscale to FullHD, 4K or 8K with open
weights: `LTX-2.5_V2V_TiledFusion_Upscale.json` in ComfyUI-LTXVideo's examples. We ran it
against the methods seriesmith has on three last-light takes (1344×768 H3 Ref2VA) to 4K,
2026-11-13, RTX 5090:

| | sh010 EWS, 107 f | sh060 MS speaking, 73 f | sh060 face sharpness (source 1.18) | shimmer vs source | drift from source |
|---|---|---|---|---|---|
| H3 latent 2x | 3.3 min | 1.1 min | 1.55 | 1.07–1.38x | 2.1–3.1 |
| H3 latent 2x + SeedVR2 | 11.3 min | 7.0 min | 2.79 | 1.20–1.44x | 2.2–3.1 |
| H3 VAE 2x | 1.7 min | 1.2 min | 1.51 | 0.94–1.32x | 3.1–4.0 |
| H3 VAE 2x + SeedVR2 | 11.5 min | 7.5 min | 2.49 | 1.13–1.29x | 3.2–4.0 |
| SeedVR2 7B | 8.8 min | 5.4 min | 2.42 | 1.23–1.57x | 1.3 |
| LTX Refine Details | 19.4 min | 10.4 min | 1.56 | 0.99–1.14x | 3.5–3.9 |
| LTX Restore | 19.9 min | 10.8 min | 1.56 | 1.13–1.23x | 4.1–4.9 |

(shimmer: frame-to-frame change of the fine detail, against the source's own; drift: mean
difference from the source at 480×270; face sharpness: mean Laplacian on the face crop.)

What it is good at: the steadiest of the generated-detail methods (Refine's shimmer is the
source's), plausible texture in water, spray and surfaces, no tile seams. What it isn't:
faces come out soft (no better than the H3 latent re-sample's, well behind SeedVR2's), and it
is the slowest (about 10 s a frame at 4K; a 4.5 s take peaked at 30.4 GB). Restore regrades
the picture (more saturated); the colour finish after it takes the tone back from the take.
H3's VAE route starts where LTX does (the take's frames, no kept latent) and still draws the
face cleanly, at a tenth of LTX's time: what keeps a face is H3 re-sampling the shot under its
own prompt and references, not the latent.

So it is offered as a method beside SeedVR2, for takes with no latent to re-sample (imported
footage, other models' takes) and for wides where steadiness matters more than faces. No
recommendation in the user docs (the user judges the look).

## Design

- `method: "ltx"`, with `ltx_lora`: `refine` (Refine Details, the default), `restore`, or a
  LoRA file name. A recipe field and a per-shot field like `seedvr2_model`; the dialog's
  method radio and the master recipe's method list. Any take, of any target: no latent, no
  prompt of the take's.
- The size: the scale (or `deliver`'s covering frame, as SeedVR2's), rounded up onto LTX's
  32 grid; the saver crops or pads to the delivery as for every method. 1344×768 to 4K:
  3840×2208, cropped to 3840×2160.
- The frames: the loader holds the last frame to 8n+1 (LTX's), `ImageFromBatch` keeps the
  take's count after the decode.
- The graph, flattened from the example (it is subgraphs): `UNETLoader` (the distilled
  transformer the `ltx2` target uses), `LTXICLoRALoaderModelOnly`, `CLIPLoader` (Gemma,
  `ltxv`), the LTX-2.5 video VAE, `LTXVConditioning`, `ImageScale` (lanczos to the canvas) as
  the guide, `EmptyLTXVLatentVideo`, `LTXAddVideoICLoRAGuide` (streaming in windows),
  `KSamplerSelect` euler, `ManualSigmas` (the example's 8 distilled steps),
  `LTXVTiledFusionSampler`, `VAEDecodeTiled`, then our `SeriesmithFinishUpscale` (colour and
  tone from the take, as after SeedVR2) and the saver, the take's audio copied on. No prompt
  enhancer and no audio branch: the saver copies the take's sound.
- Tiles and windows planned in seriesmith (`ltx_tiling`), the rules of ComfyUI-LTXVideo's
  `tiled_fusion_sizes.py` (2026-11-12): the HD tile (1280 long edge, the take's own size when
  within 200 px), overlap 0.5, `tile_frames` 97, or the clip itself up to 121.
- The prompt: look only (light, palette, sharpness, grain). Lightricks: a named thing can
  stamp into every tile.
- The seed: the take's.
- Readiness: the nodes (ComfyUI-LTXVideo as of 2026-11-12 for `LTXVTiledFusionSampler`), the
  transformer, Gemma and VAE (the int8 or bf16 file, whichever is installed), the LoRA.
- Features: "LTX-2.5 detail pass" under Upscale: the pack, the `ltx2` target's transformer,
  text encoder and video VAE, the two LoRAs (gated, as LTX-2.5).
- Not in it (yet): on top of an earlier upscale (`from_upscale`), as a `then` step after a
  re-sample, the Native 4K/8K two-stage graph, SDR to HDR.

## Checklist

- [x] The comparison (above): sh010, sh030, sh060 of last-light, every method, 4K.
- [x] H3 VAE route in the comparison.
- [x] `seriesmith/upscale.py`: the method, its plan, size, graph, readiness, record, recipe
      field, CLI flags.
- [x] `api.py` (request, options), `mcp.py`.
- [x] Features: the item.
- [x] The editor: Upscale dialog, master recipe, record's text; types.
- [x] Tests.
- [x] Docs: FINISHING, COMMANDS, API, FULL_SETUP, INSTALL (generated); site regenerated.
- [x] Live, from the command line: sh030 t03 of the scratch copy to 4K (`--method ltx --deliver
      4k`), 6.1 min, 3840×2160, its 39 frames, its audio copied, the int8 files chosen.
- [ ] Live (you): from the Upscale dialog, and from a recipe with `"method": "ltx"`.
