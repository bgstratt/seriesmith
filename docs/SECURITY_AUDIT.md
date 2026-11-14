# Security audit, 2026-11-14

The record and checklist of a security pass over what ships to the Comfy Registry
(`seriesmith/`, `comfy_nodes/`, `__init__.py`). `SECURITY.md` is the user's and the
reviewer's page and says what holds now; this says what was found, what was done, and what
is still open. Tests: `tests/test_security.py`.

## Why

The Registry's scanner has flagged every version. Its reasons, read on 2026-11-14 from
`https://api.comfy.org/nodes/seriesmith/versions?include_status_reason=true&statuses=NodeVersionStatusFlagged`:

| Versions | Reason |
|---|---|
| 0.1.0 to 0.1.18 | mostly `arbitrary-file-read, too-many-findings`; 0.1.1 `code-execution`; 0.1.3, 0.1.7 `command-injection`; 0.1.5 `credential-exfiltration` |
| 0.1.21 | `policy-v0.9: arbitrary-file-read, too-many-findings` |
| 0.1.22 | `policy-v0.9: code-execution, too-many-findings` |
| 0.1.23, 0.1.24 | pending, no reason yet |

The Registry's published standards name three security rules: no `eval` / `exec`, no
package installed through a subprocess at runtime, no obfuscated code. The shipped code
breaks none of them, so the flags come from the scanner's own policy, which isn't
published. The audit therefore read the code against the four categories the reasons
name, and against what `SECURITY.md` promises.

Who is assumed hostile: a show folder, series config, script, mix, take record or FCP7 XML
handed over by someone else; a workflow from the internet; a web page open in the user's
browser; another device on the network, paired or not; an MCP client steered by what it
reads; and a server that answers a request (a ComfyUI on another machine, a provider, the
Hub).

## Fixed in this pass

Each line: what could happen, then what stops it now.

### Code execution

- [x] **Features downloaded a URL from a model's definition into any folder.** A `downloads`
  record was never checked, and its `folder` was joined as written, so an imported
  workflow (one "download missing" click), a paired device or an MCP client could put a
  `.py` in `custom_nodes`. Now `core/downloads.py` bounds every record (a model file,
  https from Hugging Face or Civitai, a models folder by name); `Target.downloads` drops
  the URL and folder of one that isn't, `inspector.validate_spec` says so on save, and the
  installer refuses the folder again where it writes.
- [x] **`fetches` records and the Hub's listing were joined into paths as written.** A repo
  is `owner/name`, patterns stay inside it, the commit is 40 hex digits, and a listed file
  name can't climb out of the folder it goes in.
- [x] **Which Python is run could be set from another machine.** `installer.place_from_url`
  took `/internal/folder_paths` from a non-local ComfyUI when `comfyui_dir` was set, and a
  network folder passed its check. Only a ComfyUI on this PC is asked now, and a network
  path in its answer is dropped.
- [x] **`seriesmith align` ran with the current folder first on the module path**
  (`python -m`), so a `json.py` in a show folder would run. It goes through `_run.py` as
  every other tool does.

### Command injection

- [x] **The title's settings went into ffmpeg's filter graph as written.** A series config's
  `publish.subtitle.color` could append filters of its own (draw a local text file into the
  video, write a file). `publish.subtitle_checked` holds each to what it is: a colour, a
  number, two times, a font file.

### Files

- [x] **A job's output names were joined into the take's folder as paths.** A ComfyUI at the
  configured address (or anything answering in its place over http) could name an absolute
  path. `backends.Output` keeps the file name only.
- [x] **The path guards looked at a network path before refusing it**, which on Windows
  signs in to that host (the NTLM hash). `core.paths.real` returns a network path as
  written, untouched, unless it's under a project folder on that share; the API's checks
  and `show_file` use it, and the node pack's `_inputs.py` refuses an absolute or network
  name by its text.
- [x] **A project folder that is a share's own root never matched** (`os.path.commonpath`
  refuses it). Containment is by the normalised text now.
- [x] **A take record's `master` path** (an imported edit's original footage) could name a
  network path, and a job's answer could write the key. Network paths are refused there;
  a job's record never sets `master`.
- [x] **An imported FCP7 XML** could name a network host and any file as audio. A share that
  isn't a project folder is treated as missing, and only video, sound and stills are
  brought in.
- [x] **Ids joined into paths**: `DELETE /seriesmith/targets/custom` and the cue routes took
  an id that could be a path; `safe_id` kept `..`. Each is matched as an id first.

### Keys and the network

- [x] **The Comfy API key went wherever `comfyui_url` pointed** when a job had a partner
  node. The local backend sends such a job only where `comfy_key_ok` allows: this PC.
- [x] **A paired device could change where jobs and keys go.** The addresses, keys,
  deployments and the paid limit in Settings, a provider's definition and key, and the
  paid limit's reset are the PC's alone.
- [x] **A removed provider's key was inherited** by a new provider of the same name. The
  key goes when the provider goes, and a new definition never takes an old key.
- [x] **Provider redirects were followed to any address**, `file:` included. `net.py`:
  http and https only, https to a public host for any address a provider's answer names,
  each hop checked; a provider's own hosts are https (http on this PC).
- [x] **The provider draft fetched any address from the PC** and returned the body. Public
  https only, redirects checked; an address on this PC only when the PC itself asks.
- [x] **`X-API-Key` was re-sent on a redirect** by `http_json`. It stays with the address
  asked.

### Who the server answers

- [x] **Inside ComfyUI, a page re-pointed at 127.0.0.1 (DNS rebinding) was the PC itself.**
  `guard.from_this_pc`: the PC's address and the PC's name (localhost, 127.0.0.1). Anything
  else pairs first. The same test decides `ctx.local`, pairing and the stop route.
- [x] **A request with no Origin marked `same-site`** (another program's page on this PC)
  was answered. Only `same-origin` and `none` are.
- [x] **The pairing route answered 500** on digits outside ASCII.

## Fixed after the first pass (2026-11-14)

- [x] **One place starts a program.** The 62 `subprocess` calls in 35 files go through
  `seriesmith/proc.py` (the node pack's 17 through `comfy_nodes/_ff.py`): an argument
  list, never a shell, and an environment without the keys, which ffmpeg and the proxy
  used to inherit (seriesmith's own align keeps the Hugging Face token, for Whisper's
  models). A test holds the rule. `installer.run`, a generic runner nothing called, is
  gone; the pip lines (`sdk.command`, `features.pip_command`) are text.
- [x] **A Python of seriesmith's is started one way**: `proc.module`, through `_run.py`,
  by a module's name. The helpers that were run by their file's path (`erp`, `colorstats`,
  `probe`, `stills`, `refsheet`) go that way too. `ffprobe_av.py`, PyAV's stand-in for
  ffprobe, is still named by its path: the helpers accept it as a command by that path.
- [x] **ffmpeg read a playlist as media.** `ff.limited`, applied by `proc` to every ffmpeg
  and ffprobe command: each input gets `-protocol_whitelist file,pipe,fd`, and
  `-format_whitelist` (video, sound, pictures) unless the command names the format itself
  (`lavfi`, a `concat` list seriesmith wrote, raw frames from a pipe). Tried on ffmpeg
  8.1.2 and imageio-ffmpeg's 7.1. Not covered: ffprobe through PyAV, used only where
  there is no ffprobe at all.
- [x] **A download's hash, where its record has one.** Decided: downloads are not held to
  pinned files. The user chooses what to download, and a model's `main` or a tool's
  "release" address is the version wanted; pinning every file would mean keeping up with
  every version of every model. A `downloads` record may carry a `sha256`, and the file is
  then kept only if it matches; one without downloads as before.
- [x] **Partner nodes on a ComfyUI on another machine.** Refused by default (the key rides
  in the job). `comfyui_key_url`, set on the PC only by a box under the ComfyUI address in
  Settings, names the one address trusted with it: https, or http on a private network;
  a changed address is untrusted again.
- [x] **A file a route sends** is an `api.Served`, which only the routes that checked the
  path make; the server streams nothing else.
- [x] **Headers.** `X-Content-Type-Options: nosniff` on every answer; a type the page
  doesn't show is sent as a download; the standalone page can't be framed by another site
  (`frame-ancestors 'self'`, `X-Frame-Options`), loads no plugin, keeps its base address.
  The page's assets are served with their types stated, not this PC's registry's.
- [x] **The page asks no other site for anything.** PrimeIcons (woff2 only, 35 KB) and the
  two typefaces (DM Sans, Newsreader: 340 KB) are built into the page's own files.
- [x] **MCP ran with the PC's rights.** Its calls say who they are (`X-Seriesmith-Client:
  mcp`) and get a paired device's reach: an imported file must be inside a project folder,
  and no PC-only setting changes.
- [x] **A show's own `target.json`**: `binding.workflow` is a file name in the target's
  folder; `binding.env` a variable whose name ends in `WORKFLOW`.
- [x] **A provider's links** (`docs`, `key_url`, `voices.browse`) are https addresses.
- [x] **Smaller**: the ComfyUI passthrough routes take a folder's or a node's name only; a
  concat list escapes `'` (`ff.concat_line`); `modelid`'s cache is beside the settings.

## Open

- [ ] **A stricter Content-Security-Policy** (`script-src 'self'`). The page has one inline
  script (the theme, before first paint) and inline styles; it needs each given a hash or
  moved, then checking in a browser.
- [ ] **The containment check has two copies**: `core/paths.py` and the node pack's
  `_inputs.py`, which must work in a pack copied without seriesmith.
- [ ] **A take's `master` stamps live in the show.** A forged show supplies the path, size
  and time together; reading a local media file that way needs its size and its modified
  time to the second. Keeping the stamps beside the settings would close it.
- [ ] **A provider key from the environment** (`SERIESMITH_KEY_<ID>`) isn't dropped when
  the definition's hosts change. Definitions are the PC's alone now, which bounds it.
- [ ] **Smaller**: the count check hashes a weight file, then opens it again; `python -m
  demucs` in `comfy_nodes/shot.py` (demucs loads its own checkpoint, a pickle, unpinned);
  the launchers ship in the Registry's zip.

## Checked and sound

The Origin and Host rules on `seriesmith serve`; pairing (the code, the cookie, what's
stored); `comfy_key_ok` and the Hugging Face token's host match; `_run.py` and
`edit.tool_cmd`; the target module loader (identifiers only, a show brings no code); the
node pack's file inputs and saver names; the ffmpeg archive's extraction (fixed names);
the XML parser (no external entities); the page (no HTML injection sinks, no keys
returned by any route, nothing secret in the browser's storage). No telemetry, no TLS
verification switched off, no package or node pack installed at runtime.
