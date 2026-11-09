"""
The storyboard's sketches (api.post_storyboard_sketch): a first frame for a shot with no model yet,
live on the shot once made, in place of its gray card but never of a picture put there.
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
from seriesmith.core import board as BD  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_render import settle  # noqa: E402

SCRIPT = """= clips  Clips

# cl001  pond

## c001
target: hold
dur: 3.5
A heron at the water's edge.

## c002
target: hold
dur: 3.5
The heron lifts off.
"""


class SketchTest(ApiTest):
    def episode(self) -> str:
        ep = self.ok(A.post_clips_ensure(self.ctx, {}))["ep"]
        p = os.path.join(ep, "series.json")
        with open(p, encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["locations"]["pond"] = {"description": "a small pond at dawn"}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        with open(os.path.join(ep, "clips.md"), "w", encoding="utf-8") as fh:
            fh.write(SCRIPT)
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": ep}))["ok"])
        return ep

    @staticmethod
    def first(ep: str, shot: str) -> str:
        return os.path.join(ep, "refs", "shots", shot, "first.png")

    def card(self, ep: str, shot: str, data: bytes | None = None) -> None:
        path = self.first(ep, shot)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(BD.gray_card() if data is None else data)

    def test_a_sketch_replaces_the_gray_card(self):
        ep = self.episode()
        self.card(ep, "c001")
        res = self.ok(A.post_storyboard_sketch(self.ctx, {"ep": ep, "shots": ["c001"]}))
        self.assertEqual([q["ref"] for q in res["queued"]], ["shot:c001:first"])
        self.assertEqual((res["skipped"], res["errors"]), ([], []))
        settle(self.ctx.runner, 60)
        step = self.ctx.runner.queue.jobs[res["step"]]
        self.assertEqual(step.status, "succeeded", (step.error, step.log))
        with open(self.first(ep, "c001"), "rb") as fh:
            self.assertNotEqual(fh.read(), BD.gray_card())

    def test_a_picture_is_never_replaced(self):
        ep = self.episode()
        self.card(ep, "c001", b"a picture of my own")
        self.card(ep, "c002")
        res = self.ok(A.post_storyboard_sketch(self.ctx, {"ep": ep, "shots": ["c001", "c002"]}))
        self.assertEqual([s["shot"] for s in res["skipped"]], ["c001"])
        self.assertEqual([q["ref"] for q in res["queued"]], ["shot:c002:first"])
        self.card(ep, "c002", b"dropped while it was being made")
        settle(self.ctx.runner, 60)
        with open(self.first(ep, "c001"), "rb") as fh:
            self.assertEqual(fh.read(), b"a picture of my own")
        with open(self.first(ep, "c002"), "rb") as fh:
            self.assertEqual(fh.read(), b"dropped while it was being made")

    def test_nothing_to_sketch_queues_nothing(self):
        ep = self.episode()
        self.card(ep, "c001", b"a picture of my own")
        res = self.ok(A.post_storyboard_sketch(self.ctx, {"ep": ep, "shots": ["c001"]}))
        self.assertEqual((res["queued"], res["step"]), ([], None))

    def test_a_bad_request(self):
        ep = self.episode()
        self.err(A.post_storyboard_sketch(self.ctx, {"ep": ep, "shots": []}), 400)
        self.err(A.post_storyboard_sketch(self.ctx, {"ep": ep, "shots": "c001"}), 400)


if __name__ == "__main__":
    unittest.main()
