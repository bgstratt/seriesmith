"""
takefiles — a take's facts kept while its files are unchanged (docs/REFACTOR.md
3.4): what changes outside the editor shows on the next load, what's still on
its way is never kept, and the episode status answers the same with the cache
as without it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import api as A  # noqa: E402
from seriesmith import takefiles as TF  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from test_api import ApiTest  # noqa: E402

OLD = time.time() - 3600                      # well past fileio.RACY_S


def write(path, data=b"", when=OLD):
    with open(path, "w" if isinstance(data, str) else "wb") as fh:
        fh.write(data)
    os.utime(path, (when, when))


class TakeFactsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.d = T.shot_dir(self.root, "proxy", "sh010")
        os.makedirs(self.d)
        self.kept: dict = {}
        self.tp = T.TakePaths(self.d, T.stem("sh010", 1))

    def sidecar(self, **data):
        write(self.tp.sidecar, json.dumps({"status": "ok", **data}))

    def takes(self):
        return TF.list_takes(self.root, "proxy", "sh010", kept=self.kept)

    def test_one_listing_and_the_takes_as_takes_lists_them(self):
        self.sidecar(seed=1)
        write(self.tp.mp4, b"v")
        write(os.path.join(self.d, "sh010_t03.json"), json.dumps({"status": "failed"}))
        write(os.path.join(self.d, "sh010_t030.mp4"), b"x")    # sh010_t030: take 30, not 3
        got = self.takes()
        want = T.list_takes(self.root, "proxy", "sh010")
        self.assertEqual([(t.take, t.status, t.has_video, t.sidecar) for t in got],
                         [(t.take, t.status, t.has_video, t.sidecar) for t in want])
        # the listing answers what is there: no isfile per file
        with mock.patch("os.path.isfile", side_effect=AssertionError("asked the disk")):
            self.assertTrue(got[0].has_video and got[0].exists(self.tp.mp4))
            self.assertFalse(got[0].exists(self.tp.strip))

    def test_a_change_outside_the_editor_is_read_on_the_next_load(self):
        self.sidecar(note="first")
        write(self.tp.mp4, b"v")
        self.assertEqual(self.takes()[0].sidecar["note"], "first")
        with mock.patch.object(T, "read_sidecar", side_effect=AssertionError("read again")):
            self.assertEqual(self.takes()[0].sidecar["note"], "first")        # kept
        # its sidecar edited by hand (a new size and time)
        self.sidecar(note="edited by hand, longer")
        self.assertEqual(self.takes()[0].sidecar["note"], "edited by hand, longer")
        # its mp4 deleted
        os.remove(self.tp.mp4)
        t = self.takes()[0]
        self.assertFalse(t.has_video)
        self.assertIsNone(t.facts["audio"])
        # an upscale written by something else
        write(self.tp.up_sidecar, json.dumps({"status": "ok", "width": 1920}))
        self.assertEqual(self.takes()[0].facts["up"]["width"], 1920)
        # the take deleted
        os.remove(self.tp.sidecar)
        os.remove(self.tp.up_sidecar)
        self.assertEqual(self.takes(), [])

    def test_what_is_on_its_way_or_just_written_is_not_kept(self):
        self.sidecar(status="queued")
        self.takes()
        self.assertEqual(self.kept, {})
        write(self.tp.sidecar, json.dumps({"status": "ok"}), when=time.time())   # just now
        self.takes()
        self.assertEqual(self.kept, {})
        self.sidecar(status="ok")
        write(self.tp.up_sidecar, json.dumps({"status": "queued"}))
        self.takes()
        self.assertEqual(self.kept, {})                    # its upscale is on its way
        os.remove(self.tp.up_sidecar)
        self.takes()
        self.assertEqual(len(self.kept), 1)

    def test_a_caller_changing_its_sidecar_leaves_the_kept_one(self):
        self.sidecar(note="kept")
        self.takes()[0].sidecar["note"] = "changed by a caller"
        self.assertEqual(self.takes()[0].sidecar["note"], "kept")

    def test_a_store_kept_by_another_version_starts_afresh(self):
        name, data = TF.store(self.root, "proxy")
        data["x"] = {"k": [], "v": {}}
        data["_v"] = TF.VERSION - 1
        self.assertNotIn("x", TF._store(self.root, "proxy")[1])


class EpisodeStatusTest(ApiTest):
    """GET /episode with the cache: the same answer as without it, and a take
    changed outside the editor seen on the next load."""

    def episode(self):
        return self.ok(A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))

    def test_the_same_answer_and_changes_seen(self):
        self.render("sh010", "sh020")
        for p in ("proxy",):
            d = os.path.join(self.ep, T.pass_subfolder(p))
            for dirpath, _dirs, files in os.walk(d):
                for f in files:
                    os.utime(os.path.join(dirpath, f), (OLD, OLD))
        first = self.episode()
        with mock.patch.object(TF, "take_facts", side_effect=TF.take_facts) as facts:
            again = self.episode()
        self.assertEqual(again, first)
        # without any cache at all (takes.list_takes, every file asked)
        with mock.patch.object(TF, "list_takes",
                               lambda root, pass_, sid, folder=None, kept=None, name=None:
                               T.list_takes(root, pass_, sid, folder)):
            self.assertEqual(self.episode(), first)
        # a note written into a sidecar by hand
        t = T.list_takes(self.ep, "proxy", "sh010")[-1]
        data = T.read_json(t.paths.sidecar)
        data["note"] = "written by hand"
        write(t.paths.sidecar, json.dumps(data))
        shot = next(s for s in self.episode()["shots"] if s["shot"] == "sh010")
        self.assertEqual(shot["takes"][-1]["note"], "written by hand")
        self.assertTrue(facts.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
