"""Which requests `seriesmith serve` answers: only the editor's own page, and programs.

The server has no password, so a web page open in the same browser must not be able to
use it: post to it (a `text/plain` body needs no permission from the browser), read its
answers, or open its live connection. Three checks, in `refused`:

- **Origin.** A browser names the page a request comes from. When it does, that page must
  be this server: the Origin's host and port are the ones the request was sent to (its
  Host). The editor's page always passes; a page from anywhere else never does. A request
  with no Origin (curl, `seriesmith mcp`, the CLI) passes, unless the browser marks it
  cross-site (Sec-Fetch-Site).
- **Host** (DNS rebinding: a site whose name resolves to 127.0.0.1 is the same origin as
  itself). On this machine only (the default), the request must be addressed to localhost,
  127.0.0.1 or ::1. On the network (`--host 0.0.0.0`, run_seriesmith_ext.bat), an address,
  a plain machine name, or a `.local`, `.lan`, `.home.arpa` or `.ts.net` name (Tailscale)
  passes; `--allow-host` (or SERIESMITH_ALLOWED_HOSTS) adds others.
- **A body** must be JSON or a multipart upload (views.make_view), so a form or a
  `text/plain` post from another page is refused before it's read.

Inside ComfyUI, seriesmith's routes check the Origin the same way (`guarded`); the names
ComfyUI answers to are ComfyUI's to decide.

Nothing here is a password: on the network, anyone who can reach the server can still use
it, as the launcher says.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}
NETWORK_SUFFIXES = (".local", ".lan", ".home.arpa", ".ts.net", ".localhost")
ENV_HOSTS = "SERIESMITH_ALLOWED_HOSTS"


def split_host(value: str) -> tuple[str, str]:
    """A Host header's (or an origin's netloc's) name, lowercased and without brackets, and
    its port ("" when there is none)."""
    value = (value or "").strip().lower()
    if value.startswith("["):                                  # [::1]:8190
        name, _, rest = value[1:].partition("]")
        return name, rest[1:] if rest.startswith(":") else ""
    if value.count(":") == 1:
        name, port = value.split(":")
        return name, port
    return value, ""                                           # a bare name, or a bare IPv6


def is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def allowed_hosts(extra: list[str] | None = None) -> set[str]:
    """Names added by --allow-host and SERIESMITH_ALLOWED_HOSTS (comma-separated)."""
    names = list(extra or []) + os.environ.get(ENV_HOSTS, "").split(",")
    return {n.strip().lower() for n in names if n.strip()}


def host_ok(name: str, local_only: bool, extra: set[str]) -> bool:
    if name in LOCAL_NAMES or name.endswith(".localhost") or name in extra:
        return True
    if local_only:
        return False
    return is_ip(name) or "." not in name or name.endswith(NETWORK_SUFFIXES)


def refused(method: str, host: str | None, origin: str | None, fetch_site: str | None,
            local_only: bool, extra: set[str] | None = None, check_host: bool = True) -> str | None:
    """Why a request is refused, or None to answer it. `check_host` False: the Origin only
    (inside ComfyUI, which decides the names it answers to)."""
    extra = extra or set()
    if host and check_host:
        name, _ = split_host(host)
        if not host_ok(name, local_only, extra):
            return (f"this server doesn't answer to {name!r}"
                    + (" (it's listening on this machine only)" if local_only else
                       f" (add it with --allow-host {name})"))
    if origin is not None:
        if origin == "null":
            return "a request from a page with no origin isn't answered"
        parts = urlsplit(origin)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return "a request from that page isn't answered"
        if not host or split_host(parts.netloc) != split_host(host):
            return f"a request from another site ({parts.netloc}) isn't answered"
        return None
    if (fetch_site or "").lower() == "cross-site":
        return "a request from another site isn't answered"
    return None


def guarded(view):
    """An aiohttp view that refuses a request from another web page first (inside ComfyUI,
    where seriesmith's routes sit on ComfyUI's own server and its middleware isn't ours)."""
    import functools
    from aiohttp import web

    @functools.wraps(view)
    async def checked(request):
        why = refused(request.method, request.headers.get("Host"), request.headers.get("Origin"),
                      request.headers.get("Sec-Fetch-Site"), local_only=False, check_host=False)
        if why:
            return web.json_response({"error": why}, status=403)
        return await view(request)
    return checked
