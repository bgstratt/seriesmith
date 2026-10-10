"""
Job planning rules (seriesmith.jobs) and graph patching. h3pipe's end-to-end
render tests against a fake ComfyUI stayed behind: seriesmith renders through
a backend (tests/test_render_take.py).
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seriesmith import jobs as J  # noqa: E402
from seriesmith import takes as T  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "kitchen_sink")
WORKFLOW = os.path.join(ROOT, "seriesmith", "targets", "video", "minimax_h3_ref2va", "workflow.json")
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
           PYTHONPATH=os.pathsep.join(filter(None, [ROOT, os.environ.get("PYTHONPATH")])))


def build_episode(root: str, refs: bool = True) -> None:
    for flags in ([], ["--proxy"]):
        subprocess.run([sys.executable, "-m", "seriesmith", "build",
                        os.path.join(FIXTURE, "series.json"),
                        os.path.join(FIXTURE, "script.md"), "-o", root, *flags],
                       check=True, capture_output=True, env=ENV)
    if refs:
        stub_refs(root)


def stub_refs(root: str) -> None:
    """An empty file at every reference path the build asked for, so shots
    aren't blocked for missing refs (these tests are about takes)."""
    for name in ("refs_todo.json", "refs_todo_proxy.json"):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        for item in json.load(open(p, encoding="utf-8")):
            f = os.path.join(root, item["path"])
            os.makedirs(os.path.dirname(f), exist_ok=True)
            if not os.path.isfile(f):
                open(f, "wb").close()
    # the dialogue recording dub shots read isn't in refs_todo
    for name in ("shotlist.json", "shotlist_proxy.json"):
        p = os.path.join(root, "shotlist", name)
        track = (json.load(open(p, encoding="utf-8")).get("defaults", {}).get("master_track")
                 if os.path.isfile(p) else None)
        if track:
            f = os.path.join(root, track)
            os.makedirs(os.path.dirname(f), exist_ok=True)
            if not os.path.isfile(f):
                open(f, "wb").close()


def shot_ids(root: str, pass_: str = "final") -> list[str]:
    return [s["id"] for s in J.load_shotlist(root, pass_)["shots"]]


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = cls._tmp.name
        build_episode(cls.root)
        cls.doc = J.load_shotlist(cls.root, "final")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        for sub in ("renders", "renders_proxy"):
            d = os.path.join(self.root, sub)
            if os.path.isdir(d):
                import shutil
                shutil.rmtree(d)

    def plan(self, i=0, ov=None, **req):
        sid = self.doc["shots"][i]["id"]
        return J.plan_job(self.root, "final", self.doc, i, J.RenderRequest(sid, **req), ov,
                          rng=random.Random(7))

    def finished_take(self, sid, n=None):
        t = T.reserve_take(self.root, "final", sid, {"status": "queued"}, take=n)
        T.update_sidecar(t.paths.sidecar, status="ok")
        open(t.paths.mp4, "wb").close()
        return t

    def test_first_render_uses_built_seed(self):
        j = self.plan()
        self.assertEqual((j.action, j.take, j.seed_source), ("render", 1, "stable"))
        self.assertEqual(j.seed, self.doc["shots"][0]["seed"])

    def test_skip_then_redo_gets_new_seed(self):
        self.finished_take("sh010")
        self.assertEqual(self.plan().action, "skip")
        j = self.plan(redo=True)
        self.assertEqual((j.action, j.take, j.seed_source), ("redo", 2, "new"))
        self.assertNotEqual(j.seed, self.doc["shots"][0]["seed"])
        self.assertLess(j.seed, 2 ** J.NEW_SEED_BITS)

    def test_seed_modes(self):
        self.finished_take("sh010")
        built = self.doc["shots"][0]["seed"]
        self.assertEqual(self.plan(redo=True, seed_mode="same").seed, built)
        self.assertEqual(self.plan(redo=True, seed=5).seed_source, "typed")
        self.assertEqual(self.plan(seed_mode="new").seed_source, "new")
        ov = T.set_override({}, "sh010", seed=99)
        j = self.plan(redo=True, ov=ov)
        self.assertEqual((j.seed, j.seed_source), (99, "override"))
        self.assertEqual(self.plan(redo=True, ov=ov, seed_mode="new").seed_source, "new")
        self.assertEqual(self.plan(redo=True, ov=ov, seed=5).seed, 5)

    def test_queued_take_is_busy_failed_is_retried_with_built_seed(self):
        T.reserve_take(self.root, "final", "sh010", {"status": "queued"})
        self.assertEqual(self.plan().action, "busy")
        T.update_sidecar(T.take_paths(self.root, "final", "sh010", 1).sidecar, status="failed")
        j = self.plan()
        self.assertEqual((j.action, j.take, j.seed_source), ("retry", 2, "stable"))

    def test_forced_take(self):
        self.finished_take("sh010")
        j = self.plan(take=1)
        self.assertEqual((j.action, j.take, j.forced), ("overwrite", 1, True))

    def test_overrides_and_request_precedence(self):
        ov = T.set_override({}, "sh010", "final", prompt="custom", base_hash="stale",
                            steps=11, model="ov_model.safetensors",
                            loras=[{"name": "a", "strength": 0.5}])
        j = self.plan(ov=ov)
        self.assertEqual((j.prompt, j.steps, j.model), ("custom", 11, "ov_model.safetensors"))
        self.assertEqual(j.loras, [{"name": "a", "strength": 0.5}])
        self.assertEqual(j.overridden, ["loras", "model", "prompt", "steps"])
        self.assertTrue(j.override_stale)
        j = self.plan(ov=ov, steps=3, loras=[])
        self.assertEqual((j.steps, j.loras), (3, []))
        T.set_override(ov, "sh010", "final", base_hash=J.story_hash(self.doc["shots"][0]))
        self.assertFalse(self.plan(ov=ov).override_stale)

    def test_size_request_override_and_take(self):
        built = (self.doc["defaults"]["width"], self.doc["defaults"]["height"])
        self.assertNotIn(built, ((1024, 576), (960, 544)))
        self.assertIsNone(self.plan().size)
        # an override renders every take of the pass at its size; a request beats it
        ov = T.set_override({}, "sh010", "final", size="1024x576")
        j = self.plan(ov=ov)
        self.assertEqual((j.size, j.width, j.height), ((1024, 576), 1024, 576))
        self.assertIn("size", j.overridden)
        self.assertEqual(self.plan(ov=ov, size="960x544").size, (960, 544))
        # the shotlist's own size is no override at all
        self.assertIsNone(self.plan(size=f"{built[0]}x{built[1]}").size)
        # off H3's 32 grid: that shot's error, naming the nearest legal sizes
        bad = self.plan(size="1350x768")
        self.assertEqual(bad.action, "error")
        self.assertIn("1344", bad.error)
        # the take renders and records it; a size is how it renders, not what the shot is
        take = J.start_job(j)
        s = T.read_json(take.paths.shotlist)["shots"][0]
        sc = T.read_json(take.paths.sidecar)
        self.assertEqual((s["width"], s["height"], sc["width"], sc["height"]), (1024, 576, 1024, 576))
        self.assertEqual(sc["shot_hash"], J.story_hash(self.doc["shots"][0]))
        self.assertEqual(sc["preset_hash"], J.preset_hash(self.doc, self.doc["shots"][0]))
        self.assertEqual(J.parse_size([960, 544]), (960, 544))
        with self.assertRaises(ValueError):
            J.parse_size("big")

    def test_lora_from_shotlist(self):
        # kitchen_sink sh040 has `lora: none`; others inherit the series LoRA
        idx = {s["id"]: i for i, s in enumerate(self.doc["shots"])}
        self.assertEqual(self.plan(idx["sh040"]).loras, [])
        self.assertEqual(self.plan(idx["sh010"]).loras,
                         [{"name": "series_turbo_8step.safetensors", "strength": 1.0}])
        self.assertEqual(self.plan(idx["sh210"]).loras,
                         [{"name": "seq_lora.safetensors", "strength": 1.0}])

    def test_parse_lora(self):
        self.assertEqual(J.parse_lora("none"), [])
        self.assertEqual(J.parse_lora("a.safetensors:0.6"), [{"name": "a.safetensors", "strength": 0.6}])
        self.assertEqual(J.parse_lora("C:/x/a.safetensors"),
                         [{"name": "C:/x/a.safetensors", "strength": 1.0}])

    def test_start_job_writes_frozen_shotlist_and_sidecar(self):
        ov = T.set_override({}, "sh010", "final", prompt=["one", "two"])
        j = self.plan(ov=ov, seed=42, note="hello")
        take = J.start_job(j)
        frozen = T.read_json(take.paths.shotlist)
        self.assertEqual(len(frozen["shots"]), 1)
        s = frozen["shots"][0]
        self.assertEqual((s["seed"], s["prompt"], s["id"]), (42, ["one", "two"], "sh010"))
        self.assertEqual(frozen["subjects"], self.doc["subjects"])
        sc = T.read_json(take.paths.sidecar)
        self.assertEqual((sc["status"], sc["seed"], sc["seed_source"], sc["note"]),
                         ("queued", 42, "typed", "hello"))
        self.assertEqual(sc["shot_hash"], J.story_hash(self.doc["shots"][0]))
        self.assertEqual([r["slot"] for r in sc["refs"]][-2:], ["Picture 1", "Picture 4"])
        self.assertEqual(sc["refs"][0]["sha1"], T.file_sha1(os.path.join(self.root, sc["refs"][0]["path"])))
        self.assertEqual(sc["missing_refs"], [])


# ---------------------------------------------------------------------------
# graph patching
# ---------------------------------------------------------------------------

class GraphTest(unittest.TestCase):
    def setUp(self):
        self.base = J.load_graph(WORKFLOW)

    def test_lora_chain(self):
        g = json.loads(json.dumps(self.base))
        J.apply_loras(g, [{"name": "a", "strength": 1.0}, {"name": "b", "strength": 0.6},
                          {"name": "c", "strength": 0.3}])
        loras = {k: v for k, v in g.items() if v["class_type"] == J.LORA}
        self.assertEqual(len(loras), 3)
        first = next(k for k, v in loras.items() if v["inputs"]["lora_name"] == "a")
        b = next(k for k, v in loras.items() if v["inputs"]["lora_name"] == "b")
        c = next(k for k, v in loras.items() if v["inputs"]["lora_name"] == "c")
        self.assertEqual(g[b]["inputs"]["model"], [first, 0])
        self.assertEqual(g[c]["inputs"]["model"], [b, 0])
        self.assertEqual(g[c]["inputs"]["strength_model"], 0.3)
        # whatever read the first LoRA now reads the last one, and nothing else does
        readers = [k for k, v in g.items() for x in v["inputs"].values() if x == [c, 0]]
        self.assertEqual(readers, ["3"])
        self.assertFalse([k for k, v in g.items() if k not in (b,)
                          for x in v["inputs"].values() if x == [first, 0]])

    def test_no_lora_is_strength_zero(self):
        g = json.loads(json.dumps(self.base))
        J.apply_loras(g, [])
        self.assertEqual(g["2"]["inputs"]["strength_model"], 0.0)

    def test_graph_for(self):
        with tempfile.TemporaryDirectory() as root:
            build_episode(root)
            doc = J.load_shotlist(root, "proxy")
            j = J.plan_job(root, "proxy", doc, 0, J.RenderRequest("sh010"), {})
            take = J.start_job(j)
            g = J.graph_for(self.base, j, take, review_copy=False)
            li, si = g["11"]["inputs"], g["42"]["inputs"]
            self.assertEqual(li["index"], 0)
            self.assertEqual(os.path.normpath(os.path.join(root, li["shotlist_file"])),
                             os.path.normpath(take.paths.shotlist))
            self.assertEqual(si["take"], 1)
            self.assertEqual(si["subfolder"], "renders_proxy")
            self.assertEqual(os.path.normpath(os.path.join(root, si["sidecar"])),
                             os.path.normpath(take.paths.sidecar))
            self.assertEqual(g["1"]["inputs"]["unet_name"], j.model)
            self.assertEqual(g["2"]["inputs"]["lora_name"], "proxy_turbo_4step.safetensors")
            self.assertFalse([v for v in g.values() if v["class_type"] == "SaveVideo"])

    def test_graph_leaves_lora_alone_when_none_named(self):
        with tempfile.TemporaryDirectory() as root:
            build_episode(root)
            doc = J.load_shotlist(root, "final")
            doc["defaults"]["lora"] = ""
            j = J.plan_job(root, "final", doc, 0, J.RenderRequest("sh010"), {})
            self.assertIsNone(j.loras)
            take = T.Take("sh010", 1, "final", T.take_paths(root, "final", "sh010", 1))
            g = J.graph_for(self.base, j, take)
            self.assertEqual(g["2"]["inputs"], self.base["2"]["inputs"])


if __name__ == "__main__":
    unittest.main()
