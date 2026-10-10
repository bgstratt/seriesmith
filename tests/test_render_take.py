"""
A take made through a backend (docs/DESIGN.md, "seriesmith writes the takes"):
the portable graph (the shot and its files go up as inputs, nothing reads the
episode folder), collecting what the saver reports into the take, and
`seriesmith render` end to end on the fake backend.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import render  # noqa: E402
from seriesmith import shotnodes as SN  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from test_render import build_episode  # noqa: E402

NODES = os.path.join(ROOT, "comfy_nodes", "shot.py")


def h3_shot(doc: dict) -> int:
    """A plain H3 shot of the kitchen_sink episode: no held frames."""
    for i, s in enumerate(doc["shots"]):
        if not s.get("hold") and s.get("audio_policy") == "generate":
            return i
    raise AssertionError("no plain H3 shot in the fixture")


def saver_outputs(graph: dict, *, status: str = "ok", record: bool = True) -> dict:
    """What SeriesmithSaveTake reports for the take `graph` renders."""
    saver = J.node_of(graph, J.PORTABLE_SAVER)
    loader = J.node_of(graph, J.PORTABLE_LOADER)
    shot_id = json.loads(graph[loader]["inputs"]["shotlist"])["shots"][0]["id"]
    stem = T.stem(shot_id, graph[saver]["inputs"]["take"])
    items = [(f"{stem}.mp4", "video", b"mp4 bytes"), (f"{stem}.jpg", "image", b"jpg"),
             (f"{stem}_strip.jpg", "image", b"strip"),
             (f"{stem}.latent.safetensors", "latent", b"latent")]
    if record:
        items.append((stem + SN.RECORD_SUFFIX, "file", json.dumps({
            "shot": shot_id, "take": graph[saver]["inputs"]["take"], "status": status,
            "finished": "2026-10-10T12:00:00-04:00", "frames": 73, "fps": 24.0,
            "mp4": f"{stem}.mp4", "thumb": f"{stem}.jpg", "strip": f"{stem}_strip.jpg",
            "latent": f"{stem}.latent.safetensors", "save_notes": f"{stem}: mp4 written",
            "loaded_refs": ["ada (character) ada.png [512x512, body of 4 panels]"]}).encode()))
    return {saver: items, "999": [("preview.png", "image", b"not the take's")]}


class Episode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        build_episode(self.root)
        self.doc = J.load_shotlist(self.root, "final")
        self.index = h3_shot(self.doc)
        self.shot_id = self.doc["shots"][self.index]["id"]
        self.base, _ = J.resolve_workflow(None, J.WORKFLOW_NAME, None, prefer_repo=True)

    def job(self) -> J.Job:
        return J.plan_job(self.root, "final", self.doc, self.index,
                          J.RenderRequest(self.shot_id), {})


class PortableGraphTest(Episode):
    def test_the_loader_is_given_the_shot_and_its_files(self):
        job = self.job()
        take = J.start_job(job)
        g = J.graph_for(self.base, job, take, portable=True)
        loader = g[J.node_of(g, J.PORTABLE_LOADER)]["inputs"]
        self.assertNotIn("project_root", loader)
        self.assertNotIn("shotlist_file", loader)
        with open(take.paths.shotlist, encoding="utf-8") as fh:
            self.assertEqual(json.loads(loader["shotlist"]), json.load(fh))
        files = json.loads(loader["files"])
        self.assertEqual(files, J.shot_files(job))
        self.assertTrue(files)
        for i, rel in enumerate(files):
            f = loader[SN.file_input(i)]
            self.assertIsInstance(f, File)
            self.assertEqual(os.path.normcase(f.path),
                             os.path.normcase(os.path.join(self.root, rel)))

    def test_the_saver_gets_a_folder_of_its_own_and_nothing_reads_the_episode(self):
        job = self.job()
        take = J.start_job(job)
        g = J.graph_for(self.base, job, take, portable=True)
        saver = g[J.node_of(g, J.PORTABLE_SAVER)]["inputs"]
        self.assertEqual(saver["take"], take.take)
        self.assertIn(take.paths.stem, saver["run"])
        for k in ("project_root", "subfolder", "sidecar"):
            self.assertNotIn(k, saver)
        self.assertEqual(render.episode_bound(g), [])
        self.assertNotEqual(J.run_name(job, take), J.run_name(job, take))

    def test_everything_else_is_the_graph_h3pipe_queues(self):
        job = self.job()
        take = J.start_job(job)
        plain = J.graph_for(self.base, job, take)
        g = J.graph_for(self.base, job, take, portable=True)
        loader, saver = J.node_of(g, J.PORTABLE_LOADER), J.node_of(g, J.PORTABLE_SAVER)
        self.assertEqual({k: v for k, v in g.items() if k not in (loader, saver)},
                         {k: v for k, v in plain.items() if k not in (loader, saver)})
        for nid in (loader, saver):
            kept = {k: v for k, v in plain[nid]["inputs"].items()
                    if k not in ("project_root", "shotlist_file", "subfolder", "sidecar")}
            self.assertEqual({k: g[nid]["inputs"][k] for k in kept}, kept)

    def test_a_workflow_with_another_saver_is_not_portable(self):
        job = self.job()
        take = J.start_job(job)
        base = json.loads(json.dumps(self.base))
        base[J.node_of(base, "H3SaveShot")]["class_type"] = "SomeoneElsesSaver"
        with self.assertRaises(J.NotPortable):
            J.make_portable(base, job, take, J.node_of(base, "H3ShotListLoader"),
                            J.node_of(base, "SomeoneElsesSaver"))


class CollectTest(Episode):
    def run_take(self, fb: FakeBackend):
        job = self.job()
        take = J.start_job(job)
        g = J.graph_for(self.base, job, take, portable=True)
        run = fb.submit(g)
        J.mark_submitted(take, fb.name, run.id)
        return take, J.collect_take(take, run, J.node_of(g, J.PORTABLE_SAVER), run.watch())

    def test_the_savers_files_and_record_make_the_take(self):
        take, status = self.run_take(FakeBackend(outputs=saver_outputs))
        self.assertEqual(status, "ok")
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual((sc["status"], sc["mp4"], sc["frames"], sc["backend"]),
                         ("ok", os.path.basename(take.paths.mp4), 73, "local"))
        self.assertEqual(sc["latent"], os.path.basename(take.paths.latent))
        self.assertTrue(sc["comfy_prompt_id"].startswith("fake-"))
        self.assertIn("loaded_refs", sc)
        # the planning half of the record is still there
        self.assertEqual(sc["seed"], take.sidecar["seed"])
        for p in (take.paths.mp4, take.paths.thumb, take.paths.strip, take.paths.latent):
            self.assertTrue(os.path.isfile(p), p)
        names = os.listdir(take.paths.dir)
        self.assertNotIn("preview.png", names)
        self.assertFalse([n for n in names if n.endswith(SN.RECORD_SUFFIX) or n.endswith(".part")])
        # the take is a take like any other
        self.assertEqual(T.take_numbers(self.root, "final", self.shot_id), [take.take])

    def test_a_failed_job_fails_the_take(self):
        take, status = self.run_take(FakeBackend(final="failed", error="CUDA out of memory"))
        self.assertEqual(status, "failed")
        self.assertIn("CUDA out of memory", T.read_sidecar(take.paths.sidecar)["save_notes"])

    def test_no_record_fails_the_take(self):
        take, status = self.run_take(
            FakeBackend(outputs=lambda g: saver_outputs(g, record=False)))
        self.assertEqual(status, "failed")
        self.assertIn("reported no record", T.read_sidecar(take.paths.sidecar)["save_notes"])


class RenderCommandTest(Episode):
    def test_render_makes_a_take_on_the_backend(self):
        fb = FakeBackend("fake", "cloud", outputs=saver_outputs, progress=[0.5, 1.0])
        with mock.patch.object(render, "available", return_value={"fake": fb}), \
                mock.patch("builtins.print"):
            rc = render.main([self.root, "--only", self.shot_id, "--backend", "fake"])
        self.assertEqual(rc, 0)
        (take,) = T.list_takes(self.root, "final", self.shot_id)
        self.assertEqual((take.sidecar["status"], take.sidecar["backend"]), ("ok", "fake"))
        self.assertEqual(len(fb.submitted), 1)
        # a second run finds the take and does nothing
        with mock.patch.object(render, "available", return_value={"fake": fb}), \
                mock.patch("builtins.print"):
            self.assertEqual(render.main([self.root, "--only", self.shot_id,
                                          "--backend", "fake"]), 0)
        self.assertEqual(len(fb.submitted), 1)

    def test_a_backend_that_doesnt_answer_runs_nothing(self):
        fb = FakeBackend("fake", "cloud", down="nobody home")
        with mock.patch.object(render, "available", return_value={"fake": fb}), \
                mock.patch("builtins.print"):
            self.assertEqual(render.main([self.root, "--only", self.shot_id,
                                          "--backend", "fake"]), 1)
        self.assertEqual(fb.submitted, [])
        self.assertEqual(T.list_takes(self.root, "final", self.shot_id), [])


class NodeContractTest(unittest.TestCase):
    """The pipeline's view of the nodes (seriesmith/shotnodes.py) matches the
    nodes themselves, which can't be imported here (they need torch)."""

    def setUp(self):
        with open(NODES, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_the_file_inputs(self):
        self.assertEqual(int(re.search(r"^MAX_FILES = (\d+)", self.src, re.M).group(1)),
                         SN.MAX_FILES)
        self.assertIn('return f"file_{i:02d}"', self.src)
        self.assertEqual(SN.file_input(3), "file_03")

    def test_the_record_and_the_classes(self):
        self.assertIn('record_file = f"{stem}.record.json"', self.src)
        self.assertEqual(SN.RECORD_SUFFIX, ".record.json")
        for cls in (J.PORTABLE_LOADER, J.PORTABLE_SAVER):
            self.assertIn(f'"{cls}": {cls},', self.src)


if __name__ == "__main__":
    unittest.main()
