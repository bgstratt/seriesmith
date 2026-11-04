"""
The startup checks for a ComfyUI that changed under seriesmith: the parts of its Python the
node pack calls (comfy_nodes/_compat.py), and its own node classes seriesmith's models use
(features.missing_core, said by standalone.core_nodes_line).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith import features as FT  # noqa: E402
from seriesmith.server import standalone as S  # noqa: E402


def load_compat():
    spec = importlib.util.spec_from_file_location("seriesmith_nodes_compat",
                                                  os.path.join(ROOT, "comfy_nodes", "_compat.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_comfy(drop: set[str]) -> dict[str, types.ModuleType]:
    """ComfyUI's modules as _compat looks them up, every listed part there but `drop`."""
    C = load_compat()
    mods: dict[str, types.ModuleType] = {}
    for mod, attr, _ in C.INTERNALS:
        m = mods.setdefault(mod, types.ModuleType(mod))
        if f"{mod}.{attr}" not in drop:
            setattr(m, attr, object())
    mods["comfy"] = types.ModuleType("comfy")
    return mods


class InternalsTest(unittest.TestCase):
    def test_a_renamed_part_is_named_with_what_it_breaks(self):
        C = load_compat()
        with mock.patch.dict(sys.modules, fake_comfy(set())):
            self.assertEqual(C.missing(), [])
        with mock.patch.dict(sys.modules, fake_comfy({"comfy.nested_tensor.NestedTensor"})):
            self.assertEqual(C.missing(), [("comfy.nested_tensor.NestedTensor",
                                            "latent chains, kept latents, the latent upscaler")])
            with self.assertLogs("seriesmith", "WARNING") as log:
                C.report()
            self.assertIn("comfy.nested_tensor.NestedTensor", log.output[0])

    def test_every_part_the_nodes_call_is_listed(self):
        # what comfy_nodes/*.py calls of model_management (as mm), comfy.utils and
        # folder_paths: each is in INTERNALS, so a new use can't go unchecked
        import re
        C = load_compat()
        listed = {f"{m}.{a}" for m, a, _ in C.INTERNALS}
        used = set()
        for name in os.listdir(os.path.join(ROOT, "comfy_nodes")):
            if not name.endswith(".py") or name == "_compat.py":
                continue
            with open(os.path.join(ROOT, "comfy_nodes", name), encoding="utf-8") as fh:
                src = fh.read()
            used |= {f"comfy.model_management.{a}" for a in re.findall(r"\bmm\.([a-z_]+)\(", src)}
            used |= {f"comfy.utils.{a}" for a in re.findall(r"comfy\.utils\.([A-Za-z_]+)", src)}
            used |= {f"folder_paths.{a}" for a in re.findall(r"folder_paths\.([a-z_]+)", src)}
        self.assertEqual(used - listed, set())


class CoreNodesTest(unittest.TestCase):
    def test_a_missing_class_names_the_models_it_stops(self):
        everything = set(FT.CORE_CLASSES)
        self.assertEqual(FT.missing_core(everything), {})
        got = FT.missing_core(everything - {"MiniMaxMusic3TextEncode", "YuE2GenerateABC", "SolidMask"})
        self.assertEqual(got["MiniMaxMusic3TextEncode"], ["minimax_music3"])
        self.assertEqual(got["YuE2GenerateABC"], ["yue2"])
        self.assertEqual(got["SolidMask"], [])          # only seriesmith's own graphs

    def test_the_log_line(self):
        def ctx():
            return None
        with mock.patch.object(S.A, "comfy_object_info", return_value=set(FT.CORE_CLASSES)):
            self.assertIsNone(S.core_nodes_line(ctx))
        with mock.patch.object(S.A, "comfy_object_info",
                               return_value=set(FT.CORE_CLASSES) - {"YuE2GenerateABC", "SolidMask"}):
            line = S.core_nodes_line(ctx)
        self.assertIn("lacks 2", line)
        self.assertIn("YuE2GenerateABC (yue2)", line)
        self.assertIn("SolidMask (seriesmith's own graphs)", line)


if __name__ == "__main__":
    unittest.main()
