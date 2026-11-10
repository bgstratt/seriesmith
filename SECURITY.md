# Security

seriesmith runs on your own PC, as a ComfyUI node pack or as a server of its own
(`seriesmith serve`). It reads and writes files in your project folders, runs ffmpeg, talks to
ComfyUI and to the hosted services you give it keys for, and downloads the models you ask for in
Settings → Features. This page says what it reaches and what keeps each of those in bounds,
so you (or a reviewer) can check it against the code.

## Reporting a problem

Use **Report a vulnerability** on the repository's Security tab
(https://github.com/bgstratt/seriesmith/security). It stays private until it's fixed. Please
don't open a public issue for it.

## Who the server answers

- **This PC.** `seriesmith serve` listens on 127.0.0.1 unless you start it on the network
  (`run_seriesmith_ext.bat`, `--host 0.0.0.0`).
- **Not other web pages** (`seriesmith/server/guard.py`). A request from a browser must come
  from seriesmith's own page: its Origin must match the server's address, and a request the
  browser marks cross-site is refused. A request body must be JSON or a file upload, so a plain
  form on another site can't post to it. On this PC only, the request must be addressed to
  localhost, which stops DNS rebinding. Inside ComfyUI, seriesmith's routes check the Origin
  the same way.
- **Other devices pair once** (`seriesmith/server/pairing.py`). On the network, a laptop or
  phone gets nothing but the page and a code form until it enters the six-digit code that
  Settings → Other devices shows on the PC. The code lasts five minutes, allows five tries and
  pairs one device. The device then keeps a cookie (HttpOnly, SameSite=Strict); the PC stores
  only its SHA-256, and Settings can remove the device. Stopping the server, adding a project
  folder, browsing or importing outside the project folders, and choosing which ffmpeg or
  ComfyUI folder to use are refused from any device but the PC.

## Files

- **Project folders.** The editor works on episodes inside the folders you set in Settings. You
  can't set one to a whole drive or a folder that holds your user folder, and only the PC can
  change them.
- **A show's own paths** (`seriesmith/core/paths.py`, `show_file`). A path in a series config,
  a script, a mix or a take's record must lead inside the show or a project folder; anything
  else is refused, including a link that leads outside. A show someone hands you can't make a
  render read a file from elsewhere on your disk, or upload one to a hosted model. Importing a
  file copies it into the show.
- **The node pack's inputs** (`comfy_nodes/_inputs.py`). A file a node is given must be inside
  ComfyUI's input, output or temp folder.
- **Writes** go through `seriesmith/core/fileio.py`: atomic, never a partial file.

## Programs it runs

- **ffmpeg and ffprobe** (`seriesmith/ff.py`): found once (PATH, imageio-ffmpeg, PyAV), run
  with an argument list, never through a shell.
- **Its own tools** (align, the stills and sheets helpers): run as seriesmith's own modules
  through `seriesmith/_run.py`. Nothing else can be named: never `python -c`, never a script by
  path, never `cmd /c`. The helpers refuse any command but ffmpeg or ffprobe (or PyAV's
  stand-in for ffprobe, seriesmith's own `ffprobe_av.py`). The tools run
  without your API keys in their environment.
- **A show's own models** (`<show>/targets/`): only seriesmith's built-in code, chosen by
  name. A show can't bring Python of its own.

## Keys and the network

- **The Comfy API key** goes only to comfy.org, comfy.app or this PC.
- **The Hugging Face token** goes only to Hugging Face's own hosts, never on a redirect
  elsewhere.
- **A provider's key** stays with the hosts it was saved for. If the provider's definition
  later names other hosts, the saved key is dropped and must be entered again.
- **ComfyUI's queue**, as seriesmith passes it on to the page, keeps each job's number and id
  only. A job's extra data, which can hold a key, is left out.
- **Keys are kept** in the settings file on this PC (Settings shows where), or taken from the
  environment. They are never written into a show.

## What it downloads and installs

- **Settings → Features** downloads only the URLs written in seriesmith's own code and its
  models' definitions, into ComfyUI's model folders. Hashes aren't pinned for these downloads
  yet: that's the next item on the list.
- **No Python package or node pack is installed at runtime.** Features says how to add one
  (ComfyUI-Manager, or the pip command for the right Python) instead. `requirements.txt` is
  what Manager installs.
- **Releases** are published to the Comfy Registry only from `main` by the version bump, with
  every GitHub Action pinned to a commit and comfy-cli pinned to a version.

## Not covered

- **ComfyUI's own server.** ComfyUI started with `--listen` answers anyone on the network:
  that is ComfyUI's, not seriesmith's. seriesmith's routes on it still ask other devices to
  pair.
- **A reverse proxy on the PC** (`tailscale serve`, nginx) makes every request look as if it
  came from the PC itself. Open seriesmith on the network with `run_seriesmith_ext.bat` or
  `--host` instead.
- **Port-forwarding** the server to the internet. Don't.
