# kreagen — reference images

`seriesmith/kreagen.py` (`seriesmith refs <episode>`) reads the same `refs_todo.json`
build already writes, generates every image asset on an image target (krea2 turbo
unless you choose another), and writes each result straight to the path build expects.
No copying files around, no renaming.

```bash
seriesmith refs Shows/ep01 --list                           # the same, through the CLI
python -m seriesmith.kreagen --project-root . --list        # what would run
python -m seriesmith.kreagen --project-root . --dry-run     # the exact prompts
python -m seriesmith.kreagen --project-root .               # generate
python -m seriesmith.kreagen --project-root . --only sam --redo
```

The numbers below come from one real episode: 18 image assets — 13 plates,
3 sheets, 2 props — plus 4 voice samples, which are skipped here because they
aren't images. Jobs run most-blocking first, so the lead's sheet (19 shots) and
the busiest plate (6) come out before anything that gates a single shot.
Existing files are skipped unless `--redo`, which can be combined with `--only`.

## Which graph runs

The image target decides: `--target`, else each ref's override, the episode's choice
(the editor), the series config's `refs.target`, else `krea2`. Any target other than
krea2 uses its own workflow (`seriesmith/targets/image/<id>/`), or one Router call for
a hosted one (`krea_2_router`, `gpt_image_2`, `nano_banana_pro`, ... :
`builtin:router_image`); an image workflow of your own is a target too
(`builtin:workflow_image`, proposed by the inspector). The rest of this section is krea2.

`--workflow <file>` drives a specific ComfyUI workflow. With no flag, kreagen
looks for `$KREA_WORKFLOW`, then `krea2_refs_t2i.json` as saved in the running
ComfyUI, then `$COMFYUI_PATH`'s workflows folder, then the repo copy
(`seriesmith/targets/image/krea2/workflow.json`) — found means used. `--no-workflow` forces the built-in graph, whose
model files are in `seriesmith/targets/image/krea2/target.json`. The run header says which
one it took.

Per run, `--unet`, `--lora` and `--lora-strength` override what the graph says;
`--lora` splices a `LoraLoader` into a graph that has none. Per image, kreagen
sets only the prompt, size, seed, steps, cfg and save prefix — everything else
is yours.

## Sheets are generated as four separate squares

This is the one real design decision. `refs_todo.md` asks for a single
4096×1024 four-panel strip, and no diffusion model will give you that — a 4:1
canvas four times wider than anything in its training distribution comes back
as smeared repetition.

So each view is generated on its own at 1024×1024 and `seriesmith/mksheet.py` stitches
them, which is exactly what mksheet's docstring says it's for: *"Generate the
four views however you like… this assembles them into the one layout H3
actually wants."* Four square panels stitch to exactly 4096×1024, which is the
size hint build writes in refs_todo.

The four views of one character share a seed, which is most of what keeps them
on model. Per-view files land in `views/<char>/` so you can regenerate one bad
angle and re-stitch without redoing the set.

The view prompts are built from the series config's `design` sentence plus a framing
clause, not from the strip prompt in `refs_todo.md` — same source text, so the
sheet and the 27 shot prompts still cannot drift.

## Three fixes to the base graph

The krea2 target's workflow (`seriesmith/targets/image/krea2/workflow.json`, saved in
ComfyUI as `krea2_refs_t2i.json`) is a krea2 turbo text-to-image graph with three
changes from the stock one. kreagen drives that file — save your own copy as
`krea2_refs_t2i.json` among ComfyUI's workflows, or point `--workflow` at it — and
otherwise builds the same shape of graph in API form from the krea2 target
(`seriesmith/targets/image/krea2/target.json` and `graph.py`). Driving the file is the better habit: the model, LoRA, sampler
and scheduler then live on the canvas, where you can see them.

**1. 1280×720 → 1344×768.** 720 isn't divisible by 32. H3's shot loader raises on it
rather than letting H3 fail deep in the graph, so every plate generated at 720 would
have been unusable.

**2. The LoRA's CLIP output was going nowhere.** In the stock graph, `CLIPTextEncode`
took its CLIP straight off `CLIPLoader`, so a style LoRA's `strength_clip` had
no effect at all — you got the model side of the LoRA only. Now, when a LoRA is
in play, the text encoder reads the LoRA's CLIP; `--no-lora-clip` restores the
original wiring, and it's worth generating one plate each way before committing
the set.

No style LoRA is loaded by default, because the sheets have to match whatever
look `series.json` asks for and a realism LoRA fights a storybook one. Add one
per run with `--lora <file> --lora-strength 0.7`. For photoreal work a Krea2
realism LoRA earns its place; for flat 2D shows, none usually beats any.

**3. Prompt box** says that kreagen sets it per image (paste a prompt from
`refs_todo.md` to test by hand) instead of holding a prompt left over from another
project.

## Negatives

Krea 2 has no negative prompt field, and turbo runs at `cfg: 1.0`, where there
is no classifier-free guidance branch to apply one to. Both facts point the
same way: on this stack a negative prompt does nothing, which is why the
shipped graph wires `ConditioningZeroOut` instead of a second text encode.

kreagen therefore leaves the negative side of a workflow exactly as you saved
it. A turbo graph keeps its zeroed branch; a graph built around
[NAG](https://comfyui-wiki.com/en/news/2026-08-10-comfyui-krea2-nag) or
[negpip](https://github.com/blue-pen5805/ComfyUI-krea2-negpip) — the two nodes
that restore suppression at cfg 1 — is passed through untouched. Wire either
one in ComfyUI and point `--workflow` at that file.

`--negative-file` exists for the other case: a model that does expect guidance.
Above `--cfg 1.0` its text is written to the sampler's negative input, and an
encoder is added if the graph has none. At cfg 1.0 it prints a warning and is
ignored.

To steer a turbo graph without extra nodes, put the exclusions in the positive
text — that is, in the series config's `style.look` and `design` sentences, where they
also reach every H3 shot prompt.

**H3 itself takes no negative prompt at all.** The render graph guides with
`BasicGuider` at cfg 1, so an episode's `negative.txt` never touches a rendered
shot; it only ever shaped reference art.

## Output paths

```
<project_root>/
  refs/_bg/<location>.png                    1344x768   13 plates
  refs/props/<name>.png                      1024x1024   2 props
  refs/<char>/<char>_sheet_4panel.png        4096x1024   3 sheets
  refs/_takes/<ref>/<ref>[_<view>]_tNN.png   every candidate, with a .json sidecar
  refs/_picks.json                           which take is live
```

Each image is a take (seriesmith/refs.py). A ref with no file yet gets its first good
take picked, which copies it to the path above (a character's sheet is stitched
once all four views are picked). `--redo` adds a take without touching the live
file; `--pick` puts it live.

`seriesmith/kreagen.py` expects `seriesmith/mksheet.py` beside it — keep both in `seriesmith/`, or pass
`--mksheet`. Every take is a job on seriesmith's queue (this process's own),
made on `--backend` (`local`, `cloud`, `deployment:<target>`; default: each target's
own, usually `local`, a Router target's `router`): the graph keeps its SaveImage, and
the picture the backend hands back closes the take.

The same command does the rest of a ref's takes: `--clear` / `--discard` a pick or a
candidate, `--edit REF --instruction "..."` (with `--with` for another ref's picture)
on an edit target, and `--voices` for the voice refs on the audio target
(`ltx2_voice` by default) or `--from-take` to cut one out of a rendered take.

## After a run

```bash
seriesmith check Shows/ep01                      # references N/22 on disk
python -m seriesmith.mksheet refs/sam/sam_sheet_4panel.png --check
```

`mksheet --check` reports the strip's short side and what H3's `ref_image_size:
max` will do to it. Short side must be ≥1024 or `max` is upscaling from mush.

## Order to work in

1. `--only sam` first. It gates 19 of 27 shots and sets the look everything
   else is matched against. Iterate on it alone.
2. `--only core_wide` next — most complex space, gates 6 shots, and no plate
   has been proven under this style yet. If it comes back noisy that's a
   location-description problem in the series config, not a graph problem.
3. Then let the rest run; the ordering is already most-blocking first.
