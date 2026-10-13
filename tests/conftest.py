"""Tests run seriesmith's modules as subprocesses (python -m seriesmith.<x>):
make sure those import this checkout, installed or not."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [ROOT, os.environ.get("PYTHONPATH")]))

# No test reaches a real backend: this machine's settings file, its proxy, its
# ComfyUI and Comfy Cloud are all pointed at nothing (port 9 doesn't answer).
# A test that wants a backend gives it one (tests/fakes.py, test_render's
# play_runner).
_NOWHERE = "http://127.0.0.1:9"
os.environ["SERIESMITH_SETTINGS"] = os.path.join(ROOT, "tests", "_no_settings.json")
os.environ["SERIESMITH_LOCAL_URL"] = _NOWHERE
os.environ["SERIESMITH_COMFYUI_URL"] = _NOWHERE
os.environ["SERIESMITH_CLOUD_URL"] = _NOWHERE
os.environ.pop("COMFY_API_KEY", None)

_PINNED = {k: os.environ[k] for k in ("SERIESMITH_SETTINGS", "SERIESMITH_LOCAL_URL",
                                      "SERIESMITH_COMFYUI_URL", "SERIESMITH_CLOUD_URL")}

try:
    import pytest

    @pytest.fixture(autouse=True)
    def _this_machine_stays_out():
        """Every test starts on the settings above, whatever the one before did:
        a test that points SERIESMITH_SETTINGS at a scratch file and pops it
        when done left the next ones on this machine's real settings -- and
        its models for every show (a user's Wan workflow, saved beside them,
        turned up in the built-in lists, 2026-10-12). The targets' cache is
        dropped too: its listing doesn't know which settings it was made on."""
        os.environ.update(_PINNED)
        from seriesmith import targets as TG
        TG.forget_targets()
        yield
        os.environ.update(_PINNED)
        TG.forget_targets()
except ImportError:                                      # pragma: no cover (unittest alone)
    pass
