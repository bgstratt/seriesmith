# The thirty-second install

seriesmith runs inside the ComfyUI you already have. It uses the models you already have
in it. You don't install anything into ComfyUI's Python, you don't need other node packs,
and you don't need ffmpeg.

You need:

- a ComfyUI that runs (developed against 0.38 and later);
- git.

## 1. Clone, and link the node pack into ComfyUI

Windows, in an ordinary Command Prompt (`mklink /J` needs no administrator rights):

```
git clone https://github.com/bgstratt/seriesmith.git C:\code\seriesmith
mklink /J "C:\AI\ComfyUI\ComfyUI\custom_nodes\seriesmith" "C:\code\seriesmith\comfy_nodes"
```

Linux/macOS:

```
git clone https://github.com/bgstratt/seriesmith.git ~/seriesmith
ln -s ~/seriesmith/comfy_nodes /path/to/ComfyUI/custom_nodes/seriesmith
```

The paths are only examples. Link the folder rather than copying it: seriesmith finds
the rest of itself through the link, and a `git pull` updates what ComfyUI loads.

## 2. Start ComfyUI

seriesmith shows up in ComfyUI:
- **seriesmith Shots** and **seriesmith Refs** in the sidebar;
- **seriesmith Timeline** in the bottom panel.

It renders on that ComfyUI. To start, open **seriesmith Shots** and choose **Simple** at
the top of the sidebar, then **A clip**. Under **What happens?**, describe the shot, pick
who's in it and where, and press **Generate**.

## Or: the editor on a page of its own

With ComfyUI running, double-click **`run_seriesmith.bat`** in the repo (Linux/macOS:
`./run_seriesmith.sh`).
- **The first time**, it sets itself up in the repo's `.venv`. That takes a minute or two
  and needs Python 3.10 or later.
- **Then** it opens http://127.0.0.1:8190 in your browser.

It's the same app as the one inside ComfyUI, with the same projects and settings.

## Which models it uses

When seriesmith starts and sees ComfyUI, it checks which models have all their files
installed. A series that doesn't name a model renders on the first one it finds:

| For | It looks for, in order |
|---|---|
| video | MiniMax H3 Ref2VA, LTX-2.5, LTX-2.3 ingredients, then the Wan 2.2 models (VACE, I2V, 5B) |
| pictures (characters, places, props) | Krea 2, FLUX.2 Klein, Z-Image Turbo, Qwen-Image 2.1, FLUX.3 Klein, ... |

- **New projects:** new series and Simple-mode projects write the choice into their
  series config, so they keep rendering on it.
- **Your own pick:** choose another in **Settings** (Video model, Picture model).
- **Paid models:** hosted Comfy Router models (Seedance, Kling, Veo, ...) are never picked
  by themselves. Add a Comfy API key in Settings to use them (and Comfy Cloud). Saving the
  key also installs what those need (Comfy's SDK) in the background, in a few seconds.

**No models yet?** Every model picker has a **What's missing** button. It lists each file
the model needs, the ComfyUI folder it goes in, and the download link. With ComfyUI
running, `seriesmith targets` prints the same list from the command line. The smallest
complete set is the default pair: MiniMax H3 Ref2VA for video and Krea 2 for pictures
([INSTALL.md, The minimum set](../INSTALL.md#the-minimum-set)).

## What works now, and what's extra

With just this, you can do all of the following on the models you have:
- write and build episodes;
- render shots;
- make reference pictures;
- cut the episode;
- export it.

Some things need extra node packs, model files or software:
- MiniMax H3 at full quality (its sparse-attention node);
- generated voice samples;
- upscaling;
- post-processing (enhancement, motion blur);
- matching recorded dialogue;
- 360s of a place, and turning a character.

**Settings → Features…** installs any of them for you: tick what you want and press
Install. [Full setup](FULL_SETUP.md) lists each one with what it needs.
