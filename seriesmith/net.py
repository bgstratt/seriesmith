"""
net — an address from outside (a docs page a request names, a provider's redirect, a result's
URL) fetched without letting it reach this PC or its network.

    address_problem(url)     why `url` isn't fetched (None: it may be)
    opener()                 urllib's opener with http and https only (never file: or ftp:),
                             every redirect checked the same way before it's followed
    read(url)                the body, up to a limit

The rule: https, to a public host. A host that is, or resolves to, this PC, a private
network or a link-local address (a router's page, a cloud machine's metadata service) is
refused, so a web page or another device can't have the server fetch one and hand the
answer back. `local=True` is for an address the user set on this PC themselves (a provider
running on it): http and this PC are allowed there, nothing else changes.

Stdlib only.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

LOCAL_NAMES = ("localhost", "127.0.0.1", "::1")
MAX_REDIRECTS = 5


def is_loopback(host: str) -> bool:
    host = (host or "").lower()
    if host in LOCAL_NAMES or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _public(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_global and not a.is_multicast


def address_problem(url: str, local: bool = False, resolve=socket.getaddrinfo) -> str | None:
    """Why `url` isn't fetched, or None. `local`: this PC too, and http to it."""
    try:
        u = urllib.parse.urlsplit(url or "")
        host = (u.hostname or "").lower()
        port = u.port
    except ValueError:
        return "that isn't an address"
    if u.scheme not in ("http", "https") or not host:
        return "only an https address is fetched"
    if u.username or u.password:
        return "an address with a name and password in it isn't fetched"
    if is_loopback(host):
        return None if local else "an address on this PC isn't fetched"
    if u.scheme != "https":
        return "only an https address is fetched"
    try:
        found = {i[4][0] for i in resolve(host, port or 443, type=socket.SOCK_STREAM)}
    except (OSError, UnicodeError):
        return f"{host} wasn't found"
    if not found or not all(_public(ip) for ip in found):
        return f"{host} is on a private network: only a public address is fetched"
    return None


class Refused(urllib.error.URLError):
    """An address net wouldn't fetch (a URLError: callers that say "no answer" say it for this)."""


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, local: bool):
        self.local = local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = address_problem(newurl, self.local)
        if why:
            raise Refused(f"redirected to {urllib.parse.urlsplit(newurl).netloc}: {why}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener(local: bool = False, context=None, redirects: bool = True,
           extra=()) -> urllib.request.OpenerDirector:
    """An opener that speaks http and https and nothing else (urllib's own also opens file:
    and ftp: addresses, which a redirect could name). `redirects` False: a redirect comes
    back as its HTTPError, for a caller that follows them by hand."""
    o = urllib.request.OpenerDirector()
    # UnknownHandler: any other scheme is an error, where no handler at all answers None
    for h in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(), urllib.request.HTTPHandler(),
              urllib.request.HTTPSHandler(context=context),
              urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(),
              *([_CheckedRedirects(local)] if redirects else []), *extra):
        o.add_handler(h)
    return o


def read(url: str, limit: int, timeout: float = 30.0, headers: dict | None = None,
         local: bool = False, context=None) -> bytes:
    """Up to `limit` bytes of `url`'s body. Refused (a URLError) for an address that isn't fetched."""
    why = address_problem(url, local)
    if why:
        raise Refused(why)
    req = urllib.request.Request(url, headers=headers or {})
    with opener(local, context).open(req, timeout=timeout) as r:
        return r.read(limit)
