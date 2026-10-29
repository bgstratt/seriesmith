"""
Every workflow target renders portably (docs/PLAN.md, step 5): a kitchen_sink
shot retargeted to each, staged for a portable render (stage_portable: its
keyframes, and a composed reference sheet where the target makes one), and
its graph made portable. Nothing in it may read the episode folder, the saver
is seriesmith's, and every picture it loads is a local file to upload.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import render  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File, files_in  # noqa: E402
from seriesmith.backends.smoke import png  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402

try:
    import PIL  # noqa: F401  (the reference sheets are composed with it)
except ImportError:                                   # pragma: no cover
    PIL = None


def workflow_targets() -> list[TG.Target]:
    # not a hosted model's, nor hold's (ffmpeg here: no graph)
    return [t for t in TG.list_targets("video")
            if not t.spec.get("router") and not t.spec.get("local_render")]


@unittest.skipUnless(PIL, "composing reference sheets needs Pillow")
class PortableTargetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = cls._tmp.name
        build_episode(cls.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), cls.root)
        # real pictures where the stubs are empty: sheets get composed from them
        for dp, _, fns in os.walk(os.path.join(cls.root, "refs")):
            for fn in fns:
                p = os.path.join(dp, fn)
                if fn.endswith(".png") and os.path.getsize(p) == 0:
                    with open(p, "wb") as fh:
                        fh.write(png(64, 32, (90, 120, 150)))
        cls.doc = J.load_shotlist(cls.root, "final")
        cls.index = next(i for i, s in enumerate(cls.doc["shots"])
                         if s.get("subjects") and not s.get("hold"))
        cls.shot_id = cls.doc["shots"][cls.index]["id"]
        # both keyframes, for the targets that read them
        kdir = os.path.join(cls.root, "refs", "shots", cls.shot_id)
        os.makedirs(kdir, exist_ok=True)
        for end in ("first", "last"):
            with open(os.path.join(kdir, f"{end}.png"), "wb") as fh:
                fh.write(png(64, 36, (200, 180, 40)))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def portable(self, target: TG.Target):
        job = J.plan_job(self.root, "final", self.doc, self.index,
                         J.RenderRequest(self.shot_id, target=target.id, redo=True), {})
        self.assertTrue(job.runs, f"{target.id}: {job.action} {job.error}")
        base, _ = J.target_workflow(target, None, None)
        take = render.start_job_portable(job)
        return job, take, J.graph_for(base, job, take, review_copy=False, portable=True)

    def test_every_workflow_target(self):
        seen = []
        for t in workflow_targets():
            with self.subTest(target=t.id):
                job, take, g = self.portable(t)
                self.assertEqual(render.episode_bound(g), [])
                self.assertIn(J.PORTABLE_SAVER, {v["class_type"] for v in g.values()})
                self.assertNotIn("H3SaveShot", {v["class_type"] for v in g.values()})
                ups = [f.path for _, _, f in files_in(g)]
                for p in ups:
                    self.assertTrue(os.path.isfile(p), p)
                # no input still names a file in ComfyUI's input folder
                left = [(k, n, v) for k, node in g.items()
                        for n, v in (node.get("inputs") or {}).items()
                        if isinstance(v, str) and v.startswith(J.INPUT_SUBFOLDER + "/")]
                self.assertEqual(left, [])
                seen.append((t.id, len(ups)))
        # every target took at least one picture (a keyframe, a sheet or its refs)
        self.assertEqual([s for s in seen if s[1] == 0], [])

    def test_a_composed_sheet_goes_up_from_the_take(self):
        job, take, g = self.portable(TG.load_target("ltx2_ingredients", "video"))
        sheets = [f.path for _, _, f in files_in(g) if f.path.endswith("_refsheet.png")]
        self.assertEqual(len(sheets), 1)
        self.assertEqual(os.path.dirname(sheets[0]), take.paths.dir)
        self.assertIn("reference sheet", [r["slot"] for r in take.sidecar["refs"]])


if __name__ == "__main__":
    unittest.main()
