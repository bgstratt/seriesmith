"""
installer — puts in what the Features window asks for (seriesmith.features):
model files downloaded into ComfyUI's models folders, node packs cloned into
custom_nodes (their requirements pip-installed into ComfyUI's Python), pip
packages, a full ffmpeg build. One item at a time, on a thread of its own;
`state()` says how far it has got, for the window to poll.

Where things go (`Place`):

    inside ComfyUI      folder_paths: its own models folders, custom_nodes,
                        and its Python (sys.executable)
    the standalone      ComfyUI's GET /internal/folder_paths when it runs on
    server              this machine (settings comfyui_dir otherwise), and
                        the Python beside that ComfyUI (python_embeded, a venv)

A download goes to `<file>.part` first and is moved into place whole; a
.part left by a stopped download is resumed (an HTTP Range request). A
Hugging Face download sends the token from the settings (hf_token or
HF_TOKEN); a gated file without one fails saying where to accept its licence.
A node pack wants ComfyUI restarted, and `state()["restart"]` says so.

Stdlib only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from typing import Callable

from seriesmith import features as FT

CHUNK = 1 << 20
FFMPEG_BUILDS = {
    # gyan.dev's release essentials (Windows), John Van Sickle's static build (Linux x86-64)
    "win32": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
}


class InstallError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# where things go
# ---------------------------------------------------------------------------

@dataclass
class Place:
    """ComfyUI's folders and Python, as far as they're known here."""
    model_dirs: dict[str, list[str]] = field(default_factory=dict)   # folder -> its paths
    custom_nodes: str | None = None
    python: str | None = None           # ComfyUI's Python
    why_not: str = ""                   # why nothing can be installed here, if so

    def models_dir(self, folder: str) -> str | None:
        """Where a new file of `folder` goes: the path named after the folder
        (diffusion_models, not the legacy unet ComfyUI lists first), else
        the first; None when ComfyUI's folders aren't known."""
        paths = self.model_dirs.get(folder) or []
        for p in paths:
            if os.path.basename(os.path.normpath(p)).lower() == folder.lower():
                return p
        if paths:
            return paths[0]
        root = self.root()
        return os.path.join(root, "models", folder) if root else None

    def root(self) -> str | None:
        return os.path.dirname(os.path.normpath(self.custom_nodes)) if self.custom_nodes else None

    def find(self, folder: str, name: str) -> bool | None:
        """Whether `name` is in one of `folder`'s paths (None: can't tell)."""
        paths = self.model_dirs.get(folder) or ([self.models_dir(folder)] if self.root() else [])
        if not paths:
            return None
        return any(os.path.isfile(os.path.join(p, name)) for p in paths if p)

    def pack_dirs(self) -> set | None:
        if not self.custom_nodes or not os.path.isdir(self.custom_nodes):
            return None
        return {d for d in os.listdir(self.custom_nodes)
                if os.path.isdir(os.path.join(self.custom_nodes, d))}

    def to_json(self) -> dict:
        return {"root": self.root(), "custom_nodes": self.custom_nodes, "python": self.python,
                "why_not": self.why_not or None}


def comfy_python(root: str | None) -> str | None:
    """The Python a ComfyUI at `root` (the folder with main.py) runs on: the
    portable build's python_embeded, else a venv inside it."""
    if not root:
        return None
    exe = "python.exe" if os.name == "nt" else "python"
    sub = "Scripts" if os.name == "nt" else "bin"
    for p in (os.path.join(os.path.dirname(root), "python_embeded", exe),
              os.path.join(root, "venv", sub, exe), os.path.join(root, ".venv", sub, exe),
              os.path.join(os.path.dirname(root), "venv", sub, exe)):
        if os.path.isfile(p):
            return p
    return None


def place_in_comfyui() -> Place:
    """Inside ComfyUI: its own folder_paths and Python."""
    import folder_paths
    dirs = {k: list(v[0]) for k, v in folder_paths.folder_names_and_paths.items()}
    cn = (dirs.get("custom_nodes") or [None])[0]
    return Place(dirs, cn, sys.executable)


def place_from_url(comfyui_url: str, comfyui_dir: str | None = None) -> Place:
    """The standalone server: ComfyUI's /internal/folder_paths when it runs on
    this machine, else settings comfyui_dir."""
    from urllib.parse import urlparse
    host = urlparse(comfyui_url).hostname or ""
    dirs: dict = {}
    if host in ("127.0.0.1", "localhost", "::1") or comfyui_dir:
        try:
            with urllib.request.urlopen(comfyui_url.rstrip("/") + "/internal/folder_paths",
                                        timeout=10) as r:
                got = json.loads(r.read() or b"{}")
            dirs = {k: [p for p in (v if isinstance(v, list) else []) if isinstance(p, str)]
                    for k, v in got.items()}
            if dirs and not all(os.path.isdir(p) for p in (dirs.get("custom_nodes") or ["?"])):
                dirs = {}                                 # another machine's paths
        except (OSError, ValueError):
            dirs = {}
    cn = (dirs.get("custom_nodes") or [None])[0]
    if not cn and comfyui_dir and os.path.isdir(os.path.join(comfyui_dir, "custom_nodes")):
        cn = os.path.join(comfyui_dir, "custom_nodes")
    why = "" if cn else (f"ComfyUI at {comfyui_url} isn't on this machine, or isn't running: "
                         "start it, or set its folder in Settings (ComfyUI folder)")
    p = Place(dirs, cn, None, why)
    p.python = comfy_python(p.root())
    return p


# ---------------------------------------------------------------------------
# the pieces of work
# ---------------------------------------------------------------------------

def download(url: str, dest: str, token: str | None = None,
             progress: Callable[[int, int | None], None] | None = None,
             cancelled: Callable[[], bool] = lambda: False, opener=None) -> None:
    """`url` to `dest`, through `dest`.part (resumed when one is there); a
    Hugging Face URL with `token`. InstallError saying why it failed."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    req = urllib.request.Request(url, headers={"User-Agent": "seriesmith"})
    if token and "huggingface.co" in url:
        req.add_header("Authorization", f"Bearer {token}")
    if have:
        req.add_header("Range", f"bytes={have}-")
    try:
        if opener is not None:
            r = opener(req, timeout=60)
        else:
            # certifi's CAs where it's there: Windows' own store can hold an
            # expired root Python picks over the good one (backends.tls)
            from seriesmith.backends import tls
            r = urllib.request.urlopen(req, timeout=60,
                                       context=tls() if url.startswith("https") else None)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:                        # the .part is already whole
            os.replace(part, dest)
            return
        if e.code in (401, 403) and "huggingface.co" in url:
            page = url.split("/resolve/")[0]
            raise InstallError(
                ("gated: accept the licence at " + page + (", then try again" if token else
                 " and set a Hugging Face token in Settings"))
                if not token or e.code == 403 else
                f"Hugging Face refused the token ({e.code}): check it in Settings, and accept "
                f"the licence at {page}") from None
        raise InstallError(f"{e.code} {e.reason} from {url}") from None
    except (urllib.error.URLError, OSError) as e:
        raise InstallError(f"can't reach {url}: {getattr(e, 'reason', e)}") from None
    with r:
        resumed = getattr(r, "status", 200) == 206
        if not resumed:
            have = 0
        length = r.headers.get("Content-Length")
        total = (int(length) + have) if length and length.isdigit() else None
        done = have
        with open(part, "ab" if resumed else "wb") as fh:
            while True:
                if cancelled():
                    raise InstallError("stopped (the .part is kept: it resumes next time)")
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total is not None and done < total:
        raise InstallError(f"the download ended early ({done} of {total} bytes; it resumes next time)")
    os.replace(part, dest)


def run(cmd: list[str], cwd: str | None = None, timeout: int = 1800) -> str:
    """A command to its end; InstallError with the end of its output if it fails."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise InstallError(f"{cmd[0]} isn't installed") from None
    except subprocess.TimeoutExpired:
        raise InstallError(f"{os.path.basename(cmd[0])} took longer than {timeout}s") from None
    if r.returncode:
        tail = "\n".join((r.stderr or r.stdout or "").strip().splitlines()[-5:])
        raise InstallError(f"{os.path.basename(cmd[0])} failed: {tail[-600:]}")
    return r.stdout


def extract_ffmpeg(archive: str, into: str) -> None:
    """ffmpeg and ffprobe out of a build's archive, into `into` (flat)."""
    want = {"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"}
    os.makedirs(into, exist_ok=True)
    got = set()
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                base = n.rsplit("/", 1)[-1]
                if base in want:
                    with z.open(n) as src, open(os.path.join(into, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    got.add(base)
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                base = m.name.rsplit("/", 1)[-1]
                if base in want and m.isfile():
                    with t.extractfile(m) as src, open(os.path.join(into, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.chmod(os.path.join(into, base), 0o755)
                    got.add(base)
    if not {g.replace(".exe", "") for g in got} >= {"ffmpeg", "ffprobe"}:
        raise InstallError(f"the build had no ffmpeg and ffprobe (found {sorted(got) or 'nothing'})")


# ---------------------------------------------------------------------------
# the queue
# ---------------------------------------------------------------------------

class Installer:
    """One item at a time, on a thread of its own. `token()` gives the
    Hugging Face token at the moment it's needed (the settings can change)."""

    def __init__(self, place: Callable[[], Place], token: Callable[[], str | None] = lambda: None,
                 runner=run, downloader=download, on_change: Callable[[], None] | None = None):
        self._place = place
        self._token = token
        self._run = runner
        self._download = downloader
        self._on_change = on_change
        self._lock = threading.Lock()
        self._tasks: list[dict] = []
        self._items: dict[str, FT.Item] = {}
        self._cancel = False
        self._thread: threading.Thread | None = None
        self.restart = False

    # -- what the window sees ------------------------------------------------

    def state(self) -> dict:
        with self._lock:
            running = any(t["status"] in ("queued", "running") for t in self._tasks)
            return {"running": running, "tasks": [dict(t) for t in self._tasks],
                    "restart": self.restart}

    def _set(self, key: str, **kw) -> None:
        with self._lock:
            for t in self._tasks:
                if t["key"] == key:
                    t.update(kw)
        if self._on_change:
            try:
                self._on_change()
            except Exception:                             # noqa: BLE001
                pass

    # -- asking ---------------------------------------------------------------

    def start(self, items: list[FT.Item]) -> dict:
        """Queue `items` (one already queued or running is left alone) and
        start the worker if it isn't running."""
        with self._lock:
            # a finished list makes way for the new one
            if not any(t["status"] in ("queued", "running") for t in self._tasks):
                self._tasks = [t for t in self._tasks if t["status"] == "failed"
                               and t["key"] not in {i.key for i in items}][-20:]
            live = {t["key"] for t in self._tasks if t["status"] in ("queued", "running")}
            for i in items:
                if i.key in live:
                    continue
                self._tasks = [t for t in self._tasks if t["key"] != i.key]
                self._tasks.append({"key": i.key, "kind": i.kind, "name": i.name,
                                    "folder": i.folder, "status": "queued", "bytes": 0,
                                    "total": None, "error": None, "note": None})
                self._items[i.key] = i
            self._cancel = False
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, daemon=True,
                                                name="seriesmith-installer")
                self._thread.start()
        return self.state()

    def cancel(self) -> dict:
        with self._lock:
            self._cancel = True
            for t in self._tasks:
                if t["status"] == "queued":
                    t["status"] = "canceled"
        return self.state()

    def wait(self, timeout: float = 60.0) -> dict:
        """Until the queue is done (tests, the CLI)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end and self.state()["running"]:
            time.sleep(0.02)
        return self.state()

    # -- doing ---------------------------------------------------------------

    def _next(self) -> dict | None:
        with self._lock:
            for t in self._tasks:
                if t["status"] == "queued":
                    t["status"] = "running"
                    return dict(t)
        return None

    def _work(self) -> None:
        while True:
            t = self._next()
            if t is None:
                return
            item = self._items[t["key"]]
            try:
                note = self._do(item)
                self._set(t["key"], status="done", note=note)
            except InstallError as e:
                self._set(t["key"], status="canceled" if self._cancel else "failed", error=str(e))
            except Exception as e:                        # noqa: BLE001  a task fails, the rest go on
                self._set(t["key"], status="failed", error=f"{type(e).__name__}: {e}")

    def _do(self, item: FT.Item) -> str | None:
        place = self._place()
        if item.kind == "model":
            return self._model(item, place)
        if item.kind == "pack":
            return self._pack(item, place)
        if item.kind == "pip":
            return self._pip(item, place)
        if item.kind == "ffmpeg":
            return self._ffmpeg(item)
        raise InstallError(f"can't install a {item.kind}")

    def _progress(self, key):
        last = [0.0]

        def report(done, total):
            now = time.monotonic()
            if now - last[0] > 0.25 or (total and done >= total):
                last[0] = now
                self._set(key, bytes=done, total=total)
        return report

    def _model(self, item: FT.Item, place: Place) -> str | None:
        if not item.url:
            raise InstallError("no recorded download for it")
        d = place.models_dir(item.folder)
        if not d:
            raise InstallError(place.why_not or "ComfyUI's models folders aren't known here")
        dest = os.path.join(d, item.name)
        if os.path.isfile(dest):
            return "already there"
        self._download(item.url, dest, self._token(), self._progress(item.key), lambda: self._cancel)
        return f"saved in {d}"

    def _pack(self, item: FT.Item, place: Place) -> str | None:
        if not place.custom_nodes:
            raise InstallError(place.why_not or "ComfyUI's custom_nodes folder isn't known here")
        dest = os.path.join(place.custom_nodes, item.name)
        note = None
        if os.path.isdir(dest):
            note = "already cloned"
        else:
            self._run(["git", "clone", "--depth", "1", item.url, dest], timeout=900)
        req = os.path.join(dest, "requirements.txt")
        if os.path.isfile(req):
            if not place.python:
                raise InstallError(f"cloned, but its requirements need ComfyUI's Python, which "
                                   f"isn't known here: run pip install -r \"{req}\" with it")
            self._run([place.python, "-m", "pip", "install", "--disable-pip-version-check",
                       "-r", req], timeout=1800)
            note = (note + "; requirements installed") if note else "requirements installed"
        with self._lock:
            self.restart = True
        return note or "cloned"

    def _pip(self, item: FT.Item, place: Place) -> str | None:
        py = which_python(item.where, place)
        if not py:
            raise InstallError(place.why_not or "ComfyUI's Python isn't known here: run "
                               f"pip install {item.name} with it")
        self._run([py, "-m", "pip", "install", "--disable-pip-version-check", item.name,
                   *item.pip_args], timeout=1800)
        return f"installed in {py}"

    def _ffmpeg(self, item: FT.Item) -> str | None:
        url = FFMPEG_BUILDS.get("win32" if os.name == "nt" else sys.platform)
        if not url:
            raise InstallError("no ffmpeg build to download for this system: install it with "
                               "your package manager (brew install ffmpeg), or set its folder "
                               "in Settings")
        into = FT.managed_ffmpeg_dir()
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, url.rsplit("/", 1)[-1])
            self._download(url, archive, None, self._progress(item.key), lambda: self._cancel)
            extract_ffmpeg(archive, into)
        from seriesmith import ff as FF
        FF.forget()
        return f"in {into}"


# ---------------------------------------------------------------------------
# what's installed, for features.status()
# ---------------------------------------------------------------------------

_PY_HAS: dict[tuple, tuple[bool, float]] = {}


def which_python(where: str, place: Place) -> str | None:
    """The Python a pip item goes in: ComfyUI's, seriesmith's, or align's (the
    interpreter align picks: track.align_python)."""
    if where == "seriesmith":
        return sys.executable
    if where == "align":
        from seriesmith import track as K
        try:
            return K.align_python()
        except Exception:                                 # noqa: BLE001
            return sys.executable
    return place.python


def python_has(python: str | None, module: str) -> bool | None:
    """Whether `python` can import `module` (asked once a minute at most)."""
    if not python:
        return None
    if os.path.normcase(os.path.abspath(python)) == os.path.normcase(os.path.abspath(sys.executable)):
        import importlib.util
        return importlib.util.find_spec(module) is not None
    key = (python, module)
    hit = _PY_HAS.get(key)
    if hit and time.monotonic() - hit[1] < 60:
        return hit[0]
    try:
        r = subprocess.run([python, "-c", f"import importlib.util,sys; "
                            f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"],
                           capture_output=True, timeout=30)
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return None
    _PY_HAS[key] = (ok, time.monotonic())
    return ok


def env_for(place: Place, readiness: dict, object_info: dict | None) -> FT.Env:
    from seriesmith import ff as FF
    return FT.Env(
        model_exists=place.find,
        node_classes=set(object_info) if object_info is not None else None,
        pack_dirs=place.pack_dirs(),
        readiness=readiness or {},
        python_has=lambda where, module: python_has(which_python(where, place), module),
        ffmpeg_installed=FF.managed() is not None)


__all__ = ["FFMPEG_BUILDS", "InstallError", "Installer", "Place", "comfy_python", "download",
           "env_for", "extract_ffmpeg", "place_from_url", "place_in_comfyui", "python_has"]
