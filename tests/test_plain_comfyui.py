"""
A local ComfyUI without seriesmith's node pack: its shots are lowered to
ComfyUI's own nodes (cloud.without_pack), the take saying so and the page told
once (seriesmith.notice); Features offers to link the pack (its `link` item).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import cloud as C  # noqa: E402
from seriesmith import features as FT  # noqa: E402
from seriesmith import installer as INS  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith.backends import Run  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.backends.native import ComfyUIBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
from test_cloud import Episode, cloud_info  # noqa: E402


class Local(ComfyUIBackend):
    """This machine's ComfyUI, with or without the pack, its node list given."""
    def __init__(self, info, pack: bool):
        super().__init__("local", "http://127.0.0.1:9")
        self.info, self.pack = info, pack

    def has_node(self, ctype):
        return self.pack or not ctype.startswith("Seriesmith")

    def object_info(self):
        return self.info


class LowerTest(Episode):
    def test_without_the_pack_a_shot_goes_as_comfyuis_own_nodes(self):
        job, take, g = self.portable()
        b = Local(cloud_info(g), pack=False)
        lowered, plan = b.prepare(g, job, take)
        self.addCleanup(C.done_sending, plan)
        self.assertTrue(b.without_pack)
        self.assertFalse([v for v in lowered.values() if v["class_type"].startswith("Seriesmith")])
        self.assertEqual(plan["where"], C.LOCAL)
        self.assertEqual(plan["notes"][0], C.PACK_NOTE)

    def test_with_the_pack_it_goes_as_it_is(self):
        job, take, g = self.portable()
        b = Local(cloud_info(g), pack=True)
        self.assertEqual(b.prepare(g, job, take), (g, None))
        self.assertFalse(b.without_pack)

    def test_a_latent_chain_needs_the_pack(self):
        job, take, g = self.portable()
        g["999"] = {"class_type": C.CHAIN_NODES[0], "inputs": {}}
        with self.assertRaisesRegex(J.NotPortable, "need seriesmith's node pack in this ComfyUI"):
            Local(cloud_info(g), pack=False).prepare(g, job, take)


class NoticeTest(unittest.TestCase):
    def test_the_page_is_told_once(self):
        said = []
        runner = Runner(Queue(), {}, emit=lambda e, d: said.append((e, d)))
        b = FakeBackend("local", "local")
        b.without_pack = True
        run = Run()
        run.cancel = lambda: None
        lines = []

        class Q:
            cancel_asked, cancel_run = False, None
        for _ in range(3):
            runner.started(Q(), run, b, lambda **k: lines.append(k.get("line")))
        notices = [d for e, d in said if e == "seriesmith.notice"]
        self.assertEqual(len(notices), 1)
        self.assertEqual((notices[0]["level"], notices[0]["key"]), ("warn", "no-pack:local"))
        self.assertIn("Features", notices[0]["text"])
        self.assertEqual(lines.count("without seriesmith's node pack: through ComfyUI's own nodes"), 3)


class LinkTest(unittest.TestCase):
    def test_its_status_and_the_classes_that_say_so(self):
        item = FT.OWN_PACK
        self.assertIs(FT.pack_for_class("SeriesmithSaveTake"), item)
        self.assertEqual(FT.item_status(item, FT.Env(node_classes={"SeriesmithSaveTake"})), "installed")
        self.assertEqual(FT.item_status(item, FT.Env(node_classes=set(), pack_dirs={"seriesmith"})),
                         "restart")
        self.assertEqual(FT.item_status(item, FT.Env(node_classes=set(), pack_dirs=set())), "missing")
        self.assertIn("tools.seriesmith_nodes", {f.id for f in FT.catalog()})

    def test_installing_it_links_this_repo(self):
        root = tempfile.mkdtemp()
        cn = os.path.join(root, "custom_nodes")
        os.makedirs(cn)
        ran = []

        def runner(cmd, cwd=None, timeout=0):
            ran.append(cmd)
            os.makedirs(cmd[-2])                     # mklink /J <dest> <src>: made
            return ""
        place = INS.Place({}, cn, None)
        ins = INS.Installer(lambda: place, runner=runner, downloader=None)
        if os.name == "nt":
            st = ins.wait(ins.start([FT.OWN_PACK]) and 10)
            self.assertEqual(st["tasks"][0]["status"], "done", st)
            self.assertTrue(st["restart"])
            self.assertEqual(ran[0][:4], ["cmd", "/c", "mklink", "/J"])
            self.assertEqual(ran[0][4], os.path.join(cn, "seriesmith"))
            self.assertTrue(ran[0][5].endswith("comfy_nodes"))
        # already there: nothing done
        os.makedirs(os.path.join(cn, "seriesmith"), exist_ok=True)
        ins = INS.Installer(lambda: place, runner=runner, downloader=None)
        st = ins.wait(ins.start([FT.OWN_PACK]) and 10)
        self.assertEqual(st["tasks"][0]["note"], "already there")


if __name__ == "__main__":
    unittest.main(verbosity=2)
