"""Tests run seriesmith's modules as subprocesses (python -m seriesmith.<x>):
make sure those import this checkout, installed or not."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [ROOT, os.environ.get("PYTHONPATH")]))
