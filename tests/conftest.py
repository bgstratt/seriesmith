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
