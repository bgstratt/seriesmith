"""
Simple mode's clips (seriesmith/clips.py, api.post_clips_ensure /
post_clip_queue): the Clips project made on first use, and a clip queued with
a picture it still needs -- the picture first, made live, then its takes.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_render import settle  # noqa: E402

CLIP = """= clips  Clips

# cl001  pier

## c001
size: wide
dur: 3.04
A long wooden pier at dusk, waves washing between its posts.
"""


class ClipsTest(ApiTest):
    def clips(self) -> str:
        res = self.ok(A.post_clips_ensure(self.ctx, {}))
        return res["ep"]

    def test_the_clips_project_is_made_once(self):
        first = self.ok(A.post_clips_ensure(self.ctx, {}))
        self.assertTrue(first["made"])
        self.assertEqual(first["ep"], os.path.join(self.shows, "Clips", "clips"))
        cfg = json.load(open(os.path.join(first["ep"], "series.json"), encoding="utf-8"))
        self.assertEqual((cfg["subjects"], cfg["locations"]), ({}, {}))
        self.assertFalse(self.ok(A.post_clips_ensure(self.ctx, {}))["made"])
        # an empty one builds (nothing in it yet)
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": first["ep"]}))["ok"])

    def test_a_clip_makes_its_picture_first_then_its_takes(self):
        ep = self.clips()
        p = os.path.join(ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["locations"]["pier"] = {"description": "a long wooden pier at dusk",
                                    "plate": "../refs/_bg/pier.png"}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        with open(os.path.join(ep, "clips.md"), "w", encoding="utf-8") as fh:
            fh.write(CLIP)
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": ep}))["ok"])

        res = self.ok(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c001", "takes": 2}))
        self.assertEqual([r["ref"] for r in res["refs"]], ["location:pier"])
        self.assertTrue(res["step"])
        self.assertEqual(res["renders"], [])
        settle(self.ctx.runner, 60)
        plate = os.path.join(self.shows, "Clips", "refs", "_bg", "pier.png")
        self.assertTrue(os.path.isfile(plate))                      # made live
        takes = T.list_takes(ep, "proxy", "c001")
        self.assertEqual([t.status for t in takes], ["ok", "ok"], [t.sidecar for t in takes])
        step = self.ctx.runner.queue.jobs[res["step"]]
        self.assertEqual(step.status, "succeeded", (step.error, step.log))

        # every picture there now: a second queue renders at once
        res = self.ok(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c001"}))
        self.assertEqual((res["refs"], res["step"]), ([], None))
        self.assertEqual(len(res["renders"]), 1)
        settle(self.ctx.runner, 60)
        self.assertEqual(len(T.list_takes(ep, "proxy", "c001")), 3)

    def test_a_shot_that_isnt_built_is_refused(self):
        ep = self.clips()
        self.err(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c009"}), 404)
        self.err(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c009", "takes": 9}), 400)


if __name__ == "__main__":
    unittest.main()
