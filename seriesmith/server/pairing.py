"""Pairing: another device (a laptop on Wi-Fi or Tailscale) is let in once, with a code.

The editor answers the PC it runs on as always. On the network (run_seriesmith_ext, a
ComfyUI listening on it) a request from any other device needs that device paired: Settings
on the PC shows a six-digit code (good for five minutes, five tries), the device's editor
asks for it once, and the server gives the device a cookie of its own that keeps it paired.
Settings on the PC lists the paired devices, each with Remove.

What a device may ask unpaired: the page and its files (to show the form), and the pairing
routes. Everything else (the API, the live connection, ComfyUI's lists passed on) answers
401 with `pair: true` until it pairs. A device's cookie is kept here only as its SHA-256, in
`devices.json` beside the settings.

    POST /seriesmith/pair/code       this PC only: a new code {code, expires}
    GET  /seriesmith/pair            {local, paired}: whether this device needs to pair
    POST /seriesmith/pair            {code, name?}: the device paired (its cookie set)
    GET  /seriesmith/devices         this PC only: the paired devices
    POST /seriesmith/devices/remove  this PC only: {id}, that device unpaired
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time

COOKIE = "seriesmith_device"
CODE_SECONDS = 300
CODE_TRIES = 5
KEEP_SECONDS = 400 * 24 * 3600                            # a cookie's life (browsers cap it there)
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

PATHS = [("POST", "/seriesmith/pair/code"), ("GET", "/seriesmith/pair"),
         ("POST", "/seriesmith/pair"), ("GET", "/seriesmith/devices"),
         ("POST", "/seriesmith/devices/remove")]
# what a device that isn't paired may still ask: the page, its files, pairing itself
OPEN_PATHS = {"/", "/favicon.ico", "/seriesmith/pair", "/api/seriesmith/pair"}
OPEN_PREFIXES = ("/assets/",)


class PairError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Pairing:
    """The code on offer and the paired devices (`devices.json` at `path`)."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        self.code: dict | None = None                     # {code, expires, tries}

    def _load(self) -> dict:
        from seriesmith.core.fileio import read_json_or
        data = read_json_or(self.path, {})
        devices = data.get("devices") if isinstance(data, dict) else None
        return devices if isinstance(devices, dict) else {}

    def _save(self, devices: dict) -> None:
        from seriesmith.core.fileio import write_json
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        write_json(self.path, {"devices": devices})

    def new_code(self) -> dict:
        """A new code, replacing any on offer."""
        with self.lock:
            code = f"{secrets.randbelow(10 ** 6):06d}"
            self.code = {"code": code, "expires": time.time() + CODE_SECONDS, "tries": 0}
            return {"code": code, "expires": int(self.code["expires"]), "seconds": CODE_SECONDS}

    def pair(self, code: str, name: str = "", address: str = "") -> str:
        """The new device's token, for its cookie; PairError when the code isn't right."""
        code = "".join(ch for ch in str(code or "") if ch.isdigit())
        with self.lock:
            offer = self.code
            if not offer or time.time() > offer["expires"]:
                self.code = None
                raise PairError(403, "no code is on offer: open Settings on the PC running "
                                     "seriesmith and make a new one")
            if not hmac.compare_digest(code, offer["code"]):
                offer["tries"] += 1
                if offer["tries"] >= CODE_TRIES:
                    self.code = None
                    raise PairError(403, "that's not the code, and it was the last try: make "
                                         "a new one on the PC")
                raise PairError(403, "that's not the code")
            self.code = None                              # one device per code
            token = secrets.token_urlsafe(32)
            h = _hash(token)
            devices = self._load()
            now = int(time.time())
            devices[h[:12]] = {"hash": h, "name": (name or "A device")[:80], "added": now,
                               "seen": now, "address": address}
            self._save(devices)
            return token

    def known(self, token: str | None, address: str = "") -> bool:
        if not token:
            return False
        h = _hash(token)
        with self.lock:
            devices = self._load()
            d = devices.get(h[:12])
            if not d or not hmac.compare_digest(d.get("hash", ""), h):
                return False
            now = int(time.time())
            if now - int(d.get("seen") or 0) > 3600:        # written at most hourly
                d["seen"], d["address"] = now, address or d.get("address", "")
                self._save(devices)
            return True

    def devices(self) -> list[dict]:
        with self.lock:
            return [{"id": k, **{f: v.get(f) for f in ("name", "added", "seen", "address")}}
                    for k, v in sorted(self._load().items(), key=lambda kv: kv[1].get("added") or 0)]

    def remove(self, device_id: str) -> bool:
        with self.lock:
            devices = self._load()
            if devices.pop(str(device_id or ""), None) is None:
                return False
            self._save(devices)
            return True


_PAIRING: Pairing | None = None


def pairing() -> Pairing:
    """The one this process keeps (both hosts in it share it)."""
    global _PAIRING
    if _PAIRING is None:
        from seriesmith.settings import settings_path
        _PAIRING = Pairing(os.path.join(os.path.dirname(settings_path()), "devices.json"))
    return _PAIRING


def is_local(request) -> bool:
    return (request.remote or "") in LOOPBACK


def is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def refused(request) -> bool:
    """Whether a request needs this device paired first (and it isn't)."""
    if is_local(request) or is_open(request.path):
        return False
    return not pairing().known(request.cookies.get(COOKIE), request.remote or "")


def refusal():
    from aiohttp import web
    return web.json_response({"error": "this device isn't paired with seriesmith yet: enter "
                                       "the code from Settings on the PC running it",
                              "pair": True}, status=401)


def routes() -> list[tuple[str, str, object]]:
    from aiohttp import web

    def local_only(request):
        if not is_local(request):
            return web.json_response({"error": "only on the PC running seriesmith"}, status=403)
        return None

    async def make_code(request):
        return local_only(request) or web.json_response(pairing().new_code())

    async def status(request):
        local = is_local(request)
        return web.json_response({"local": local, "paired": local or pairing().known(
            request.cookies.get(COOKIE), request.remote or "")})

    async def pair(request):
        try:
            body = await request.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        try:
            token = pairing().pair(body.get("code"), str(body.get("name") or ""),
                                   request.remote or "")
        except PairError as e:
            return web.json_response({"error": str(e)}, status=e.status)
        r = web.json_response({"paired": True})
        r.set_cookie(COOKIE, token, max_age=KEEP_SECONDS, path="/", httponly=True,
                     samesite="Strict", secure=request.secure)
        return r

    async def devices(request):
        return local_only(request) or web.json_response({"devices": pairing().devices()})

    async def remove(request):
        no = local_only(request)
        if no:
            return no
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if not pairing().remove((body or {}).get("id")):
            return web.json_response({"error": "no such device"}, status=404)
        return web.json_response({"devices": pairing().devices()})

    views = {("POST", "/seriesmith/pair/code"): make_code, ("GET", "/seriesmith/pair"): status,
             ("POST", "/seriesmith/pair"): pair, ("GET", "/seriesmith/devices"): devices,
             ("POST", "/seriesmith/devices/remove"): remove}
    return [(m, p, views[(m, p)]) for m, p in PATHS]
