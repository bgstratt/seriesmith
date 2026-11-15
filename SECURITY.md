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
- **What counts as this PC.** A request is the PC's own when it comes from the PC's address
  and is addressed to it as localhost or 127.0.0.1. One that arrives under any other name
  (a web page whose name was re-pointed at 127.0.0.1, a proxy on the PC passing requests on)
  is treated as another device: it must pair, and it gets no PC-only operation. This holds
  inside ComfyUI too, whatever names ComfyUI itself answers to.
- **Other devices pair once** (`seriesmith/server/pairing.py`). On the network, a laptop or
  phone gets nothing but the page and a code form until it enters the six-digit code that
  Settings → Other devices shows on the PC. The code lasts five minutes, allows five tries and
  pairs one device. The device then keeps a cookie (HttpOnly, SameSite=Strict); the PC stores
  only its SHA-256, and Settings can remove the device.
- **Only the PC itself** can stop the server, add a project folder, browse or import outside
  the project folders, choose which ffmpeg or ComfyUI folder to use, change where jobs are
  sent (the ComfyUI and Comfy Cloud addresses, deployments), set or change a key, add, change
  or remove a provider, and raise or reset the paid jobs' limit. A paired device works on the
  shows and can save the other settings (which model each kind starts on, a model's limits);
  it can't redirect your files or keys.

## Files

- **Project folders.** The editor works on episodes inside the folders you set in Settings. You
  can't set one to a whole drive or a folder that holds your user folder, and only the PC can
  change them.
- **A show's own paths** (`seriesmith/core/paths.py`, `show_file`). A path in a series config,
  a script, a mix or a take's record must lead inside the show or a project folder; anything
  else is refused, including a link that leads outside. A show someone hands you can't make a
  render read a file from elsewhere on your disk, or upload one to a hosted model. Importing a
  file copies it into the show. The one exception is an edit imported with proxies: the
  original footage stays where it was, and the export reads it only while its size and
  modified time still match what the import recorded.
- **Network paths** (`\\host\share\...`). On Windows, merely looking at one signs the PC in
  to that host. So a network path named by a show, an imported XML or a node's input is
  refused by its text, before anything touches it, unless it is inside a project folder
  you set on that share yourself.
- **An imported edit** (FCP7 XML) brings in video, sound and stills only; a file of any
  other kind that the XML names is left out.
- **What a job sends back.** The file names a ComfyUI or a hosted model reports for its
  outputs are used as file names only, inside the take's folder: never as a path.
- **Ids** in a request (a cue, a model of the show's own) are checked as ids before they
  name a folder.
- **A file sent to the page** is one a route has checked to be inside the episode, sent
  with its type stated (`X-Content-Type-Options: nosniff`); a kind the page doesn't show is
  sent as a download, never opened in the browser.
- **The MCP server** (`seriesmith mcp`) works for a model client, which reads scripts and
  pages that may try to steer it. So its calls aren't yours at the PC: it can change none
  of the PC-only settings, and from outside the project folders it imports only what a
  show is made of, by the file's name: a picture, a video, a sound (or an edit's `.xml`)
  on this PC's own disks. A key, a document or a settings file is refused, as is a
  network path.
- **The node pack's inputs** (`comfy_nodes/_inputs.py`). A file a node is given must be inside
  ComfyUI's input, output or temp folder.
- **Writes** go through `seriesmith/core/fileio.py`: atomic, never a partial file.

## Programs it runs

- **One place starts them** (`seriesmith/proc.py`; the node pack's is `comfy_nodes/_ff.py`).
  A program is started from an argument list, never a shell line, and without your keys in
  its environment (the Comfy API key, a provider's key, the Hugging Face token). The one
  exception: seriesmith's own align tool keeps the Hugging Face token, for Whisper's models.
- **ffmpeg and ffprobe** (`seriesmith/ff.py`): found once (PATH, imageio-ffmpeg, PyAV), run
  with an argument list, never through a shell. What they may read is limited on every
  command (`ff.limited`): a file on this PC, never an address, and only video, sound and
  pictures. A playlist or a list of other files saved under a video's name is refused
  instead of being followed. What a series config sets for the episode
  title (its colours, size, timing and font) is written into ffmpeg's filter graph, so each
  is checked to be what it says: a colour, a number, a font file.
- **ComfyUI's Python** (the count check, the Features window's "is it installed"): the one
  beside the ComfyUI folder set on this PC, or the one a ComfyUI running on this PC reports.
  Another machine's ComfyUI is never asked where it is.
- **Its own tools** (align, the stills and sheets helpers): run as seriesmith's own modules
  through `seriesmith/_run.py`, or as one of the package's own helper files. Nothing a show
  or a request names is ever run: never `python -c`, never a script from outside the
  package, never `cmd /c`. The helpers refuse any command but ffmpeg or ffprobe (or PyAV's
  stand-in for ffprobe, seriesmith's own `ffprobe_av.py`).
- **A show's own models** (`<show>/targets/`): only seriesmith's built-in code, chosen by
  name. A show can't bring Python of its own. Its workflow is a file in the model's own
  folder, by name; it can't point at a file elsewhere or at an environment variable that
  isn't a workflow's.
- **The count check's detectors** (`seriesmith/countcheck.py`, `helpers/counts.py`): two YOLOv8
  weight files, which are PyTorch pickles and so can run code as they load. The helper loads
  one only when its sha256 is the one written in `countcheck.WEIGHTS`, checked just before
  loading; any other file of that name is refused, never loaded. It runs in ComfyUI's Python
  (ultralytics comes with the Impact Subpack) as one of seriesmith's own modules.

## Keys and the network

- **The Comfy API key** goes only to comfy.org, comfy.app or this PC. A Comfy partner node
  reads the key from the job it runs in, so a job with one is sent only to a ComfyUI on
  this PC: with ComfyUI on another machine it is refused, saying so. If your ComfyUI is on
  another machine and you want paid nodes there, Settings on the PC has a box for it: the
  key is then sent to that one address (https, or http on your own network only), and to
  no other if the address changes.
- **The Hugging Face token** goes only to Hugging Face's own hosts, never on a redirect
  elsewhere.
- **A provider's key** stays with the hosts it was saved for. If the provider's definition
  later names other hosts, the saved key is dropped and must be entered again; removing a
  provider removes its key. Requests to a provider go over https (http only to one running
  on this PC).
- **Addresses from outside** (`seriesmith/net.py`): a docs page you give when setting up a
  provider, a redirect, the address a provider gives for a result. Each is fetched only
  over https from a public host, every redirect checked again: never a `file:` address,
  this PC, or an address on your network.
- **A key sent in a header** is not carried on to wherever a request redirects.
- **ComfyUI's queue**, as seriesmith passes it on to the page, keeps each job's number and id
  only. A job's extra data, which can hold a key, is left out.
- **Keys are kept** in the settings file on this PC (Settings shows where), or taken from the
  environment. They are never written into a show.

## What it downloads and installs

- **Settings → Features** downloads only the URLs written in seriesmith's own code and its
  models' definitions, into ComfyUI's model folders. A model's definition can come from
  outside (a workflow you import, a show's own model), so what it may ask for is bounded
  (`seriesmith/core/downloads.py`): a model file (`.safetensors`, `.sft`, `.gguf`), over
  https from Hugging Face or Civitai, into a models folder by name. Anything else is listed
  as missing and never downloaded, and nothing is ever written into `custom_nodes`.
  A download follows the address its record names (a model's current file on the Hub,
  ffmpeg's current release build), so you get the version that is there when you ask;
  files aren't held to a pinned hash. A model's definition may name its file's `sha256`,
  and then the download is kept only if it matches. The count check's two detector files,
  which are pickles, are loaded only at their pinned sha256.
- **No Python package or node pack is installed at runtime.** Features says how to add one
  (ComfyUI-Manager, or the pip command for the right Python) instead. `requirements.txt` is
  what Manager installs.
- **Releases** are published to the Comfy Registry only from `main` by the version bump, with
  every GitHub Action pinned to a commit and comfy-cli pinned to a version.

## The page

- **It asks no other site for anything.** Its icons and typefaces are built into its own
  files; nothing is loaded from a CDN.
- **It runs only its own scripts** (`Content-Security-Policy`, `seriesmith/server/views.py`):
  the script files the server sends, and the one short script built into the page, by its
  hash. If a show's text (a note, a name, an imported edit) ever reached the page as markup,
  the browser would run nothing in it. Pictures, video, sound and typefaces come from the
  server only, and the page connects only to it.
- **It can't be framed by another site**, loads no plugin, and its links to a provider's
  docs or key page open https addresses only.

## Not covered

- **ComfyUI's own server.** ComfyUI started with `--listen` answers anyone on the network:
  that is ComfyUI's, not seriesmith's. seriesmith's routes on it still ask other devices to
  pair.
- **A reverse proxy on the PC** (`tailscale serve`, nginx) passes requests on from the PC's
  own address. They arrive under the proxy's name, so they are treated as another device
  and must pair; a proxy that rewrites the name to localhost would make them the PC's own.
  Open seriesmith on the network with `run_seriesmith_ext.bat` or `--host` instead.
- **Port-forwarding** the server to the internet. Don't.
