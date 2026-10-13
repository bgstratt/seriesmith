# Setting up seriesmith

## Install

Python 3.10 or newer. A virtual environment of its own keeps seriesmith apart
from ComfyUI's Python:

    python -m venv .venv
    .venv\Scripts\activate            (Windows; source .venv/bin/activate elsewhere)
    pip install -e .

That brings comfy-sdk, which every backend uses.

## Your own GPU: ComfyUI and comfy-api-proxy

seriesmith talks to your ComfyUI through **comfy-api-proxy**, which serves the
same Comfy API v2 as Comfy Cloud in front of it. Install it in the same
environment and start it beside ComfyUI:

    pip install comfy-api-proxy
    comfy-api-proxy start --comfyui http://127.0.0.1:8188 --port 8189 --state-dir "%LOCALAPPDATA%\seriesmith\proxy"

- `--state-dir` matters: without it, a restart of the proxy forgets the files it
  has uploaded and the jobs it has run.
- It listens on 127.0.0.1 only. To reach it from another machine it needs
  `--token`, and seriesmith's `local_url` set to match.
- `comfy-api-proxy status` / `stop` manage the background process.
- The proxy can't see ComfyUI's model lists or installed nodes; seriesmith asks
  ComfyUI for those directly (`comfyui_url`).
- You rarely start it yourself: `seriesmith serve`, and every command that
  queues work on `local` (render, upscale, post, master, tour, kreagen), start
  it when it isn't running and ComfyUI is.

Check it:

    seriesmith backends               # each backend, and whether it answers
    seriesmith backends --try local   # a picture up through ComfyUI and back

## The seriesmith nodes

Everything seriesmith sends a backend runs on its own nodes (`comfy_nodes/`):
the shot loader and saver, the `continuous: latent` chain, the upscale loaders
and saver, and the upscale and post compute nodes. h3pipe's node pack isn't
needed (the runner refuses a graph that would use it). Link the folder into
ComfyUI's `custom_nodes` and restart ComfyUI:

    mklink /J "<ComfyUI>\custom_nodes\seriesmith" "<seriesmith>\comfy_nodes"     (Windows)
    ln -s "<seriesmith>/comfy_nodes" "<ComfyUI>/custom_nodes/seriesmith"           (elsewhere)

They sit happily beside h3pipe's node pack if you keep it for h3pipe. With
the seriesmith package installed in ComfyUI's own Python (`pip install -e
<seriesmith> comfy-api-proxy` with that Python), the pack also serves the
editor inside ComfyUI: the same app as `seriesmith serve` (INSTALL.md, "The
editor inside ComfyUI"). A target's own model nodes (H3's
`H3SLAAttention` from ComfyUI-PlagueKind-Nodes, for one) are still needed;
`seriesmith render --dry-run` writes the graph a shot would run.

## Comfy Cloud, deployments and Router

All three use your Comfy API key (platform.comfy.org). Keep it in the
environment rather than in a file:

    setx COMFY_API_KEY comfyui-...    (Windows; export COMFY_API_KEY=... elsewhere)

Router also needs it when everything else runs locally: a hosted model fetches its
reference pictures from Comfy Cloud, so they are uploaded there (a few models take
them inline in the request instead).

The editor's **Settings** window sets the key too (saved in the settings file below);
`seriesmith backends` says whether one is set.

### Comfy Router models

A hosted model is a target like any other, on the `router` backend only: no GPU, no
model files. seriesmith ships the video and image models it has tried (Seedance, Kling,
Wan, Veo, Runway, hosted H3; Nano Banana, Seedream, GPT Image, Flux, Qwen, Krea 2 and
more), and others as **drafts**, which stay out of the pickers until you probe one and **Enable** it in the editor's **Models**
window. That window also adds any other model from Router's catalog
([EDITOR.md](EDITOR.md), "Comfy Router models").

What a hosted take costs is the provider's, billed to the key's account. Runs on Cloud,
Router or a deployment are counted in the Jobs window, and `paid_limit` (below) caps
them per server session.

## Settings

Anything not in the environment can go in a settings file,
`%APPDATA%\seriesmith\settings.json` (Windows) or
`~/.config/seriesmith/settings.json`:

```json
{
  "local_url": "http://127.0.0.1:8189",
  "comfyui_url": "http://127.0.0.1:8188",
  "deployments": {"minimax_h3_ref2va": "https://<your-build>.run.comfy.app"}
}
```

The other keys, most of them written by the editor rather than by hand:

- `cloud_url` (default `https://cloud.comfy.org`) and `api_key` (better kept in
  `COMFY_API_KEY`).
- `paid_limit`: how many paid runs one server session may queue (none: no cap).
- `enabled_drafts`: the built-in draft models switched on for every show (the Models
  window's **Enable**).
- `target_limits`: this machine's changes to a built-in model's limits (its **Limits**
  form; **Back to shipped** removes one).

Beside the settings file live the models you saved for every show (`targets/<id>/`),
the editor's project folders (`default/seriesmith/config.json`) and the queue's journal
(`queue.json`; `queue-comfyui.json` for the editor inside ComfyUI). A model saved for one
show only goes in `<show>/targets/<id>/` instead.

The environment wins over the file: `SERIESMITH_LOCAL_URL`,
`SERIESMITH_COMFYUI_URL`, `SERIESMITH_CLOUD_URL`, `COMFY_API_KEY`;
`SERIESMITH_SETTINGS` names another file. These are this machine's settings;
nothing here goes in the series config, which gets shared.
