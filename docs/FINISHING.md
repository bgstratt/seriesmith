# Finishing: render size, upscale, master, post and titles

How a series goes from takes to a delivered master: the size its takes render at, the
upscale methods, the master recipe in the series config and what `seriesmith master`
does with it, the post pass, and the intro and outro. The config blocks themselves, and
what to write when starting a series, are in [AUTHORING.md](AUTHORING.md) (**Render size
and delivery**); this page is the why and the how behind them. The commands are in
[COMMANDS.md](COMMANDS.md) (**Finishing**), the files each method needs in
[FULL_SETUP.md](FULL_SETUP.md) (**Upscaling**, **Post-processing**).

## Render size: at size, or small and upscaled

`series.width` / `series.height` is the size every final take renders at, and
`proxy.width` / `proxy.height` the proxy pass's. The usual setups:

| | final | proxy | shape | a 3 s take | upscaled (picks only) | delivers |
|---|---|---|---|---|---|---|
| **Render at size** (the default) | 1344×768 | 896×512 | 7:4 | ~53 s | not needed | 1344×768 as rendered |
| **Render small, upscale to 1080p** | 960×544 | 864×480 | ≈7:4 | ~20 s | re-sample 2x → 1920×1088, ~25–35 s | 1920×1080 (8 rows cropped) |
| **Render 16:9, upscale to 1080p or 4K** | 1024×576 | 512×288 | 16:9 | ~23–24 s (est.) | re-sample 2x → 2048×1152 (scaled down to 1080p; for 4K, then an upscale model) | 1920×1080 or 3840×2160, exactly |
| **Render at size, master 1440p** | 1344×768 | 960×544 (8 steps) | 7:4 | ~53 s | re-sample 2x → 2688×1536, ~75 s | 2560×1440 (scaled down, 23 rows cropped) |

(Measured on an RTX 5090 with the 8-step turbo LoRA; the 1024×576 time is estimated from
its 13% more pixels than 960×544, since attention grows a little faster than the pixel
count.)

**A proxy smaller than 480p is too small to judge a shot by**: faces, hands and small props
blur into each other. 896×512 is the default for a new series: the same 7:4 shape as
1344×768 exactly, so a proxy take can stand in for a final one in a cut (a proxy of
another shape is scaled to fit there). 448×256 renders quicker, for a rough check of timing
only.

**The shape matters as much as the size.** 1344×768 is 7:4 (1.75), not 16:9
(1.78): H3 sizes are multiples of 32, and 1344×768 is the model's native size. A 7:4 take
delivered at a 16:9 size is either cropped (1344×768 to 4K loses 18 rows top and bottom,
1.6%) or padded (30 px of black each side); the upscale's **Output size** does either
(`--deliver 4k --fit crop|pad`; the dialog's Crop to fill / Pad with bars). 1024×576 is the
16:9 size on H3's 32 grid (512×288 its proxy), so nothing is lost at 1080p or 4K, at the
cost of a slightly smaller frame than 1344×768. The LTX and Wan targets snap a size down to
their own grid (LTX-2's is 64: a 512×288 proxy renders there at 512×256, a little wider than
16:9); the H3 targets refuse a size off theirs, naming the nearest.

- **Render small and upscale** when the episode renders on `minimax_h3_ref2va`,
  `fasth3_omni` or `minimax_h3_fl2va` with the latent upscaler installed (INSTALL.md, **The upscaler**), on
  `ltx2`, which upscales with its own second stage and needs nothing extra, or on
  `ltx2_ingredients` with LTX-2.3's latent upsampler installed (INSTALL.md, **For
  upscaling**; `seriesmith targets` says `upscale ready` for each). Every take you try costs under half as much, and only the ones the cut
  keeps are upscaled, once, after the cut is locked. The upscale re-samples the take from
  late in its schedule under its own prompt, references and seed, with its audio held, so
  the performance and the lip sync are the take's; it adds detail a 960×544 frame is short
  of (hands, small props, texture). It can't add a face the render didn't draw: at 960×544 a
  face in a medium-wide or wider is a few of H3's 16-pixel cells, and the re-sample
  sharpens what's there (see [Faces need room](AUTHORING.md#faces-need-room)). A live-action series that lives on
  faces and dialogue renders at 1344×768 (**Delivering 1440p** below).
- **Render at size** when shots render on Wan (`wan22_i2v`, `wan22_ti2v`, `wan22_vace`:
  they re-sample, a pixel model then their own sampler, but slowly: minutes a shot), when
  the upscaler isn't installed, or when 1344×768 is the delivery. Upscaling a 1344×768 take to 2688×1536 works
  but adds little: that frame already holds most of what the model can draw.
- Pick one per series. A single take can still render at another size: the New take
  dialog's **Size** (that take only; `seriesmith render --size 1344x768`), or the shot's override
  (the inspector's **Size**, `seriesmith override --size 1344x768`: every later take of that pass).
  A master with `"scale": "auto"` re-samples each take by its own size, so a cut that mixes
  960×544 and 1344×768 takes delivers one 1080p master. Switching the series size later only
  changes the takes rendered after the switch.

```json
"series": { "id": "porchlight", "title": "Porchlight", "fps": 24,
            "width": 960, "height": 544, "steps": 8 }
```

For 16:9 (exact 1080p or 4K):

```json
"series": { "id": "porchlight", "title": "Porchlight", "fps": 24,
            "width": 1024, "height": 576, "steps": 8 },
"proxy": { "width": 512, "height": 288 }
```

An upscale starts 7/8 of the way through the take's schedule (step 7 of 8), which keeps a
speaking mouth exactly as the take had it. A shot with no dialogue can take more detail with
`seriesmith upscale <ep> --only sh100 --redo --detail 2` (two steps earlier: more change, check
it).

Takes on a show's own targets (and any take, by choice) can still be upscaled by the
**pixel method**: an upscale model (RealESRGAN, UltraSharp, from
ComfyUI's `models/upscale_models`) over the frames, with the take's audio copied on. It is
fast and needs nothing but the model, but it only sharpens what's there; it draws no new
detail the way a re-sample does. `seriesmith upscale <ep> --method pixel` uses it for any take.
On an NVIDIA RTX card, **RTX Video Super Resolution** is offered among the upscale models
(`--pixel-model rtx_vsr`; INSTALL.md says how to add it): no model file, and about 15 s a
5 s shot at 2x against RealESRGAN_x2's two minutes (SeedVR2 7B: seven to nine). It is a
little softer than RealESRGAN and a little steadier frame to frame, and likewise draws
nothing new. Its default level (ULTRA) is the one for generated takes; HIGHBITRATE_ULTRA
leaves a clean take nearly as it was. It goes wherever an
upscale model goes (the pixel method, `--then-pixel rtx_vsr`, a Wan re-sample's start, a post).

**SeedVR2** is the third method, for any take too: a one-step video restoration model
(ComfyUI's own nodes; files in INSTALL.md). It gives the sharpest single frames of the three,
in about a minute a shot, with no prompt (so nothing ties it to the take's performance but
the picture); its frames change a little more from one to the next than a re-sample's, and
the colour finish after it halves that. `seriesmith upscale <ep> --method seedvr2` (the 7B;
`--seedvr2-model 3b` for the smaller one). It can also follow a re-sample in the same job,
in place of an upscale model: `seriesmith upscale <ep> --then-seedvr2 --deliver 4k` (the dialog's
Then: SeedVR2), so the take is redrawn under its own prompt with its lips held, then
restored to the output size.

`--scale` is any number above 1, up to 4 (a pixel upscale lands on even sides, an H3
re-sample on the 32 grid, so 1.5x, 2x, 3x of 1024×576 all work; the LTX targets' is 2x
only). For 4x with generated detail, re-sample then upscale in one go:
`seriesmith upscale <ep> --then-pixel RealESRGAN_x2.pth` (re-sample 2x, then the model 2x more).
The editor's Upscale dialog offers the same, and shows the size each choice makes. An
upscale you already have can be taken further later with the pixel method alone:
`seriesmith upscale <ep> --only sh100 --method pixel --from-upscale` (the dialog's "On top of the
existing upscale").

A pixel model has a fixed factor of its own (RealESRGAN_x2 makes 2x, RealESRGAN_x4 4x), but
the upscale is resized to whatever scale you ask for: RealESRGAN_x2 at 1.5x is the model's
2x shrunk to 1.5x, which is sharp and cheap. So pair a 2x model with 1.5x or 2x and a 4x
model with 3x or 4x (a 4x model at 1.5x does four times the work to throw most of it away).
**Output size** (`--deliver 1080p|1440p|4k|WxH`, `--fit crop|pad`; the dialog's Output
size) makes the upscale exactly that size instead of a multiple: the last step that can
make any size (the upscale model, SeedVR2) is scaled to cover it (crop) or fit inside it
(pad), and the rest is trimmed or barred. A 4K master from a 1344×768 take: `seriesmith upscale
<ep> --then-pixel RealESRGAN_x2.pth --deliver 4k` (re-sample 2x to 2688×1536, the model to
3840×2196, 36 rows cropped); from 1024×576 the same makes 3840×2160 with nothing cropped. A
re-sample alone keeps its own scale and is resized to the output size (a downscale is fine;
a stretch up is noted, and an upscale model after it is the better way). Every upscale of a
cut at the same output size assembles without resizing. Past 4K the output is heavy to make
and to play: up to 4096 wide upscales encode on the GPU (NVENC); past it they're written
with x264 on the CPU, which takes a couple of minutes but plays in the editor (the GPU
encoder can only write HEVC that big, which browsers often show as black).

A pixel model's output is finished before it's saved. By default its colour and tone come
from the original frames and only its fine detail from the model (upscale models shift
colour a little; this keeps an upscaled clip matching the cut around it). Two more, off by
default: **keep soft areas soft** fades the detail the model invents where the original was
out of focus, so shallow depth of field stays shallow (`--keep-soft 1`), and **grain** puts
back the film grain the model scrubbed away (`--grain 0.02` is light).

## Masters: one recipe for every shot

A **master** is the locked cut delivered at one size, every shot upscaled the same way.
The series config says how, once, in `upscale.master` (the **recipe**):

```json
"upscale": { "save_latents": "final",
  "master": { "deliver": "4k", "fit": "crop", "quality": "master",
    "finish": { "frequency_split": true },
    "targets": {
      "minimax_h3_*": { "method": "latent", "then": "RealESRGAN_x2.pth" },
      "fasth3_*":     { "method": "latent" },
      "ltx2*":        { "method": "latent" },
      "wan22_*":      { "method": "seedvr2" },
      "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x2.pth" } } } }
```

- `deliver` (1080p, 1440p, 4k or WxH), `fit` (crop or pad) and `quality` (`master`: x264
  CRF 12, for delivery; `review` is quicker) are the whole master's: one size, one encoding.
- `targets` has a section per video target (an id or a glob; the exact id wins, then the
  most specific glob, then `"*"`). A take is always upscaled through its own target: an H3
  shot re-samples with H3, an LTX shot with LTX. FastH3 Omni (`fasth3_omni`) re-samples as H3
  does but isn't `minimax_h3_*`: give it its own section, or its shots fall to `"*"`. A section takes `method` (latent, pixel,
  seedvr2), `scale`, `detail`, `pixel_model`, `seedvr2_model`, `then` (an upscale model
  file, or `"seedvr2"`, after a re-sample), `then_scale`, and the finish (`keep_soft`,
  `grain`); `finish` sets those for every section. `"scale": "auto"` (a re-sample alone)
  picks, per take, the smallest scale on the target's grid that covers `deliver`: 2x for a
  960×544 take, 1.5x for a 1344×768 one (2016×1152, scaled down to 1920 and cropped), so an
  episode that renders some shots at 1344×768 masters with no wasted pixels.
- `window` (seconds) is for a long H3 re-sample. A take longer than one window is sampled
  in overlapping windows along time (5.5 s with 1.25 s of overlap by default: a usual 4–5 s
  shot still re-samples in one pass), so a 2x
  re-sample of 1344×768 (2688×1536) fits a 32 GB card at any length. Shorter takes are
  sampled in one pass, as before. Set a longer window if your card holds it, or `0` to
  turn windowing off. It needs the `comfyui-obvpm-timeline` node pack (its H3 Context
  Windowing); without it, a long shot's upscale says so instead of running out of memory.
- A **continuity shot** (its first keyframe the previous shot's last frame) starts its
  upscale from the previous shot's *upscaled* last frame, so the two meet on one picture.
  Re-sampling each from the same low-res frame gave two different 2x pictures of it, which
  shows as a colour jump at a cut that should be seamless. Every upscale keeps its last
  frame (`<take>.up_last.png`). The master queues a source before the shot that continues
  it, and makes either upscale again when it was made before this (never a Keep).
- A **`continuous: latent` shot** does the same in latent space: its re-sample holds its
  first frames on the previous shot's upscaled latent, which that upscale keeps
  (`<take>.up.latent.safetensors`, about 60 MB for 5 s at 2x) only when the next shot in
  the cut is such a shot. The master queues the source first and makes an upscale again
  when the source kept no latent, or the chained shot wasn't held (it ran first).
- A shot can have its own recipe over its target's (a dialogue close-up kept light, a wide
  given `detail: 1`, a shot SeedVR2 got wrong sent to the pixel method): the editor's
  Upscale dialog, **Choose for this run**, then **Save as sh020's recipe**.

`seriesmith master Shows\ep05 --wait` (or the cut menu's **Master…**) goes through the cut:

- a shot with no upscale, one made from an older take, or one that failed is upscaled by
  the recipe;
- a fresh upscale made with the recipe's settings is used as it is;
- a fresh upscale made with **other settings** (an older recipe, or before upscales
  recorded theirs) is **kept**, not redone: `--conform` (the dialog's Conform) redoes those;
- an upscale marked **Keep** (the take menu's **Keep upscale**, `seriesmith upscale --only sh020
  --keep`) is never redone by Master, even with `--conform`;
- a shot with no usable pick, or a kept upscale at another size, is a **gap**: no master is
  made until it's fixed, unless `--allow-gaps`.

Then it assembles the master from the upscales into `Shows\ep05\master\`
(`ep05_master_3840x2160.mp4`, with `--prores` a ProRes 422 HQ `.mov` too; a master already
made gets its `.mov` without assembling again from `--prores-only`, or the dialog's
**ProRes from this master**) and writes
`ep05_master.md` / `.json`: every shot's take, target, recipe and status. It never changes
the cut: lock the picks first. Several episodes, or a whole show folder, master in one go
(`seriesmith master Shows`); an episode with gaps is skipped, not half-made. `--check` shows the
plan without queueing anything.

The upscales are queued **in cut order** by default: watch them land, and if one is off you
can stop there knowing everything before it is good. For a batch you'll leave running
(overnight, over lunch), `--order target` (the dialog's Queue: Grouped by target) runs the
shots that load the same model together, so ComfyUI loads each model once instead of at
every change of target; the dialog remembers the choice.

### Delivering 1080p

Render small and re-sample 2x; nothing after it. Per picked take the re-sample costs about
as much as one 960×544 render, and it redraws detail at full size under the take's own
prompt, references and seed with its audio held, which no pixel upscale of a bigger render
matches. Rendering at 1344×768 costs every take ~53 s instead of ~20 s and still needs an
upscale to reach 1080p. With about 4 takes a shot, a 100-shot episode is roughly 3 hours
this way against about 7 at 1344×768 (extrapolated from 3–5 s shots: master one real
episode before planning a season on it).

- **960×544** (proxy 448×256) when the shots are mostly H3: the re-sample makes 1920×1088,
  cropped by 8 rows (0.7%, invisible).
- **1024×576** (proxy 512×288) when many shots are on LTX, or for a touch more crispness:
  it's on both H3's 32 grid and LTX's 64 (LTX snaps 960×544 to 960×512, whose 2x is
  stretched about 5% to fill 1080), and the 2048×1152 re-sample is scaled down to exactly
  1920×1080. About 15–25% more time a take and an upscale.
- Wan shots: SeedVR2 7B (about a minute a shot), or a pixel model (about 40 s) when time
  matters more; Wan's own re-sample takes minutes and isn't worth it at 1080p.
- Some shots at **1344×768** (dialogue-heavy mediums the small render doesn't hold): give
  the H3 section `"scale": "auto"`. Those takes re-sample 1.5x to 2016×1152 (about the
  pixels of a 960×544 take's 2x), scaled down to 1920 wide and cropped by 18 rows; the
  960×544 takes still re-sample 2x. A fixed 2x would take them to 2688×1536 only to throw
  most of it away.

```json
"upscale": { "save_latents": "final",
  "master": { "deliver": "1080p", "fit": "crop", "quality": "master",
    "finish": { "frequency_split": true },
    "targets": {
      "minimax_h3_*": { "method": "latent" },
      "ltx2*":        { "method": "latent" },
      "wan22_*":      { "method": "seedvr2", "seedvr2_model": "7b" },
      "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x2.pth" } } } }
```

`save_latents: "final"` (the default) lets the re-sample start from the take's latent
instead of re-encoding its video. A wide shot without dialogue that looks soft can take its
own recipe with `detail: 1`; don't raise `detail` for every shot, it can change a speaking
mouth.

### Delivering 1440p

Render at 1344×768 and re-sample 2x; nothing after it. The take holds faces and mouths a
960×544 render can't (see [Faces need room](AUTHORING.md#faces-need-room)), and the 2x re-sample to 2688×1536 is
scaled down about 5% to 2560×1463 and cropped by 23 rows, so the master is slightly
supersampled. Measured on an RTX 5090: **about 75 s a shot**, and cleaner than re-sampling
1.5x and finishing with RealESRGAN, which took 210–230 s (the upscale model's pass at
1440p is the slow part). Uploaded to YouTube at 1440p, it also streams better to viewers
watching at 1080p than a 1080p upload does.

- **Proxy at 960×544, on the 8-step LoRA at 8 steps** (`"proxy": {"width": 960, "height":
  544, "steps": 8, "lora": "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"}`):
  a proxy then looks like a final, so a good one can stand in. Its 2x is only 1920×1088,
  stretched to 1440p: give such a shot its own recipe at `"scale": 2.75` (960→2640), on a
  short shot only.
- **Long shots:** a 2x re-sample of 1344×768 is heavy. Up to about 6–7 s it fits a 32 GB
  card; a 10 s shot at 2x ran out of VRAM and stalled. Give long shots their own recipe at
  `"scale": 1.5` with `"then": "RealESRGAN_x2.pth"`.
- Keep `"scale": 2`, not `"auto"`: auto would also choose 2x for a 1344×768 take, but takes
  at other sizes would re-sample differently.

```json
"upscale": { "save_latents": "final",
  "master": { "deliver": "1440p", "fit": "crop", "quality": "master",
    "finish": { "frequency_split": true },
    "targets": {
      "minimax_h3_*": { "method": "latent", "scale": 2 },
      "ltx2*":        { "method": "latent", "scale": 2 },
      "wan22_*":      { "method": "seedvr2", "seedvr2_model": "7b" },
      "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x2.pth" } } } }
```

### Delivering 4K

The same small render, the same 2x re-sample, then an upscale model the rest of the way:
`"then": "RealESRGAN_x2.pth"` with `"deliver": "4k"`. From 960×544 the model makes an
exact 2x of the 1920×1088 re-sample (3840×2176, 16 rows cropped), so it runs at its own
factor with no resize; from 1024×576 it takes 2048×1152 to exactly 3840×2160. Measured (RTX 5090, 3 s shots,
master quality): **about 3 minutes a shot** on H3 (the re-sample ~30 s, the model's pass at
4K ~2 minutes, the encode ~11 s), nearer 4 on LTX, about 2 for a Wan shot through
RealESRGAN_x4, against well under a minute a shot for 1080p. For a 100-shot episode that's
some 5 hours of upscaling at 4K against under an hour at 1080p: master 1080p as you go and
4K when it's asked for.

- Don't re-sample 4x in one go: a single refine step on a 4x latent is unmeasured and heavy
  on VRAM. Re-sample 2x, then a model.
- The model after the re-sample is the steadiest frame to frame. SeedVR2 there
  (`"then": "seedvr2"`) gives the sharpest stills but is several minutes a shot at 4K:
  give it to the shots that earn it, as their own recipe, not the whole series.
- Rendering at 1344×768 for 4K works (re-sample 2x to 2688×1536, the model the last 1.43x)
  but costs every take more and the re-sample more, for little.
- Wan shots: a 4x model (`RealESRGAN_x4.pth`, about 3x from 1280×704), or SeedVR2 for the few
  that need it.

```json
"upscale": { "save_latents": "final",
  "master": { "deliver": "4k", "fit": "crop", "quality": "master",
    "finish": { "frequency_split": true },
    "targets": {
      "minimax_h3_*": { "method": "latent", "then": "RealESRGAN_x2.pth" },
      "ltx2*":        { "method": "latent", "then": "RealESRGAN_x2.pth" },
      "wan22_*":      { "method": "pixel", "pixel_model": "RealESRGAN_x4.pth" },
      "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x4.pth" } } } }
```

**Both 1080p and 4K** from one cut: a take keeps one upscale, so make the 4K master and
scale it down for 1080p, rather than upscaling every shot twice (switching the recipe's
`deliver` makes the 1080p upscales the wrong size for a 4K master, and `--conform` replaces
them).

`fit: crop` unless they'd rather keep the whole frame with bars (`pad`).

## Post-process: the `post` block

A **post** finishes a shot's upscale, at the same size: a clean-up pass over the whole
frame, then motion blur. It is for what H3's latents leave behind even after the re-sample:
blocky edges and shadows, and moving things that smear in blocks instead of blurring.

```json
"post": { "master": { "enhance": "production", "motion_blur": 0.3 } }
```

- `enhance`:
  - `"production"` is SeedVR2 7B at the upscale's size, the one to use. It was chosen on
    Porchlights ep01 against the upscale alone, an earlier re-sample start, SeedVR2 3B, an
    upscale model and SUPIR. It cleaned edges, lettering, hairnets and faces in motion
    best, and took about 4.5 minutes a 5 s shot at 1080p. At 1440p it's about 100 seconds per second of
    footage (11 minutes for a 6.6 s shot, against 4 for its 2x re-sample), so post the shots
    that need it, or plan an overnight run.
  - `"draft"` is an upscale model at 1x: a quick sharpen that also sharpens the blocks.
  - `"cinematic"` is SUPIR: about 30 minutes a shot, frame by frame.
  - `"none"` skips the clean-up.
- `motion_blur`: a fraction of the frame interval, 0 to 1. 0.3 smooths blocky motion; 0.5 is
  a 180° film shutter. Still areas are left alone.
- A shot can have its own over it in overrides.json: `"post": {"sh040": {"motion_blur": 0},
  "sh050": {"enhance": "none"}}`.
- Face detailing (redrawing faces with an image model) was tried and dropped: it changed who
  the characters were (docs/POST_PROCESSING.md).

`seriesmith post Shows\ep05` posts every upscaled shot of the cut by the recipe (`--only`,
`--redo`, or `--enhance` / `--blur` for a one-off), and the editor's take and cut menus
have **Post-process…**. The Master dialog's **Post-process** says what the master is made from:

- **Off**: the upscales.
- **Where present** (`seriesmith master Shows\ep05 --post present`): each shot's fresh post where
  it has one, its upscale otherwise; nothing is post-processed and no `post` block is needed.
  The way to post only the shots that need it: upscale, scrub the cut, **Post-process…** the
  ones that need it from the take menu, then master.
- **All by recipe** (`seriesmith master Shows\ep05 --post --wait`): every shot by the `post`
  block; a shot without an upscale gets its post queued right behind the upscale.

## Series intro and outro: the `publish` block

The show's opening and closing are two clips made once for the whole series, not shots
in each script: every episode then opens on the same picture, and a model never has to
spell the episode's name. Put them in the show folder as `_titles\INTRO.mp4` and
`_titles\OUTRO.mp4`, and every master (`seriesmith master`, or Master in the editor) is made
with them: the intro, the episode, the outro, with the episode's title from its `=` line
written under the series title the clips carry, in one font, size and colour for every
episode. Without the files a master is made plain. `seriesmith publish Shows\ep05` does
the same to the review cut, into `ep05\publish\` (the editor's Publish button).

The cut's picture is copied, not re-encoded: only the two title clips are encoded, to
match it, and the result is checked frame by frame at each join (a cut that can't be
matched is re-encoded whole, and publish says why). To use other clips, name them in the
series config, relative to the episode folder:

```json
"publish": { "intro": "../_titles/INTRO.mp4", "outro": "../_titles/OUTRO.mp4" }
```

An optional `subtitle` object sets `font`,
`size` and `y` (fractions of the frame height), `color`, `glow`, and the fades in seconds:
`intro_in`, `outro_in`, `outro_out` (see `seriesmith/publish.py` for the defaults).
