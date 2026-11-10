"""What another Python has: `python probe.py <dist>=<module> ...` prints one JSON line,
{dist: its version ("" when it has none to give), or null when the module isn't there}.

Run by path in the Python being asked (align's, ComfyUI's), so it is what that Python would
really see; the standard library only, so any Python 3 runs it. Used by track.probe (Whisper)
and installer.python_has (a node pack's package)."""
import importlib.util
import json
import sys

try:
    from importlib.metadata import version
except Exception:                                         # noqa: BLE001  a very old Python
    version = None


def found(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        # a dotted name whose parent isn't there ("nvidia.cublas" without "nvidia") raises
        return False


def main(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        dist, _, module = pair.partition("=")
        module = module or dist
        if not found(module):
            out[dist] = None
            continue
        v = ""
        if version is not None:
            try:
                v = version(dist) or ""
            except Exception:                             # noqa: BLE001  no metadata for it
                v = ""
        out[dist] = v
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:])))
