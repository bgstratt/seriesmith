"""
What a request may reach on disk (api.py: check_source, put_config, get_browse; the node
pack's _inputs): from the PC running seriesmith, the whole disk, as it's how project folders
are chosen and files brought in; from another device, the project folders only. The project
folders are changed on that PC alone, and never to a whole drive or the user's own folder.
A node's file input stays inside ComfyUI's input, output and temp folders.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import api as A  # noqa: E402
from seriesmith import xmlimport as XI  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.shows = os.path.join(self.tmp, "Shows")
        self.elsewhere = os.path.join(self.tmp, "Elsewhere")
        for d in (self.shows, self.elsewhere, os.path.join(self.shows, "a")):
            os.makedirs(d, exist_ok=True)
        for d, name in ((self.shows, "in.png"), (self.elsewhere, "out.png")):
            with open(os.path.join(d, name), "wb") as fh:
                fh.write(b"x")
        self.ctx = A.Context(os.path.join(self.tmp, "user"), "http://127.0.0.1:0", env={})
        self.assertEqual(A.put_config(self.ctx, {"roots": [self.shows]})[0], 200)

    def remote(self):
        self.ctx.local = False
        return self.ctx


class ProjectFoldersTest(Base):
    def test_changed_on_this_pc_only(self):
        status, out = A.put_config(self.remote(), {"roots": [self.shows, self.elsewhere]})
        self.assertEqual(status, 403)
        self.assertIn("only on the PC", out["error"])
        # the same folders (review_copy alone) is fine from anywhere
        self.assertEqual(A.put_config(self.ctx, {"roots": [self.shows], "review_copy": True})[0], 200)
        self.ctx.local = True
        self.assertEqual(A.put_config(self.ctx, {"roots": [self.shows, self.elsewhere]})[0], 200)

    def test_never_a_whole_drive_or_the_users_folder(self):
        drive = os.path.splitdrive(self.tmp)[0] + os.sep if os.name == "nt" else "/"
        home = os.path.expanduser("~")
        for wide in (drive, home, os.path.dirname(home)):
            status, out = A.put_config(self.ctx, {"roots": [self.shows, wide]})
            self.assertEqual(status, 400, wide)
            self.assertIn("too wide", out["error"])


class BrowseTest(Base):
    def test_this_pc_browses_anywhere(self):
        status, out = A.get_browse(self.ctx, {"path": self.elsewhere, "files": "image"})
        self.assertEqual(status, 200)
        self.assertEqual([f["name"] for f in out["files"]], ["out.png"])

    def test_another_device_browses_the_project_folders(self):
        status, out = A.get_browse(self.remote(), {})
        self.assertEqual([d["path"] for d in out["dirs"]], [os.path.abspath(self.shows)])
        status, out = A.get_browse(self.ctx, {"path": self.shows})
        self.assertEqual((status, out["parent"]), (200, ""))     # up: the list of them
        self.assertEqual(A.get_browse(self.ctx, {"path": self.elsewhere})[0], 403)
        self.assertEqual(A.get_browse(self.ctx, {"path": os.path.join(self.shows, "..", "Elsewhere")})[0], 403)


class ImportsTest(Base):
    def test_a_source_path(self):
        out_png = os.path.join(self.elsewhere, "out.png")
        in_png = os.path.join(self.shows, "in.png")
        self.assertEqual(A.check_source(self.ctx, out_png), out_png)
        self.assertEqual(A.check_source(self.remote(), in_png), in_png)
        with self.assertRaises(A.ApiError) as cm:
            A.check_source(self.ctx, out_png)
        self.assertEqual(cm.exception.status, 403)
        for bad in ("in.png", "", None, "C:\\x\0y"):
            with self.assertRaises(A.ApiError):
                A.check_source(self.ctx, bad)

    def test_an_xmls_media_from_another_device(self):
        out_mov = os.path.join(self.elsewhere, "a.mov")
        xml = f"""<xmeml version="4"><sequence><name>S</name><rate><timebase>24</timebase></rate>
          <media><video><track><clipitem id="c1"><name>a</name><start>0</start><end>24</end>
          <in>0</in><out>24</out><file id="f1"><pathurl>file:///{out_mov.replace(os.sep, '/')}</pathurl>
          </file></clipitem></track></video></media></sequence></xmeml>"""
        p = XI.plan(xml, self.shows, "e.xml", "Show", allow=lambda p: A.in_roots(self.ctx, p))
        self.assertTrue(any("outside the project folders" in w for w in p["warnings"]), p["warnings"])


def load_inputs():
    spec = importlib.util.spec_from_file_location(
        "seriesmith_nodes_inputs_test", os.path.join(ROOT, "comfy_nodes", "_inputs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NodeInputsTest(unittest.TestCase):
    """A node's file input, against a stand-in for ComfyUI's folder_paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        dirs = {k: os.path.join(self.tmp, k) for k in ("input", "output", "temp")}
        for d in dirs.values():
            os.makedirs(d)

        def annotated(name):
            for k in ("output", "temp", "input"):
                if name.endswith(f" [{k}]"):
                    return os.path.join(dirs[k], name[:-len(k) - 3])
            return os.path.join(dirs["input"], name)
        fp = types.SimpleNamespace(get_annotated_filepath=annotated,
                                   get_input_directory=lambda: dirs["input"],
                                   get_output_directory=lambda: dirs["output"],
                                   get_temp_directory=lambda: dirs["temp"])
        sys.modules["folder_paths"] = fp
        self.addCleanup(sys.modules.pop, "folder_paths", None)
        self.I = load_inputs()
        self.dirs = dirs

    def test_inside_comfyuis_folders(self):
        self.assertEqual(self.I.input_file("a.mp4"), os.path.join(self.dirs["input"], "a.mp4"))
        self.assertEqual(self.I.input_file("run/x.latent [output]"),
                         os.path.join(self.dirs["output"], "run/x.latent"))
        self.assertEqual(self.I.input_file("  "), "")

    def test_nowhere_else(self):
        outside = os.path.join(self.tmp, "secret.txt")
        for name in ("../secret.txt", outside, "../../x [output]"):
            with self.assertRaises(ValueError, msg=name):
                self.I.input_file(name)


if __name__ == "__main__":
    unittest.main()
