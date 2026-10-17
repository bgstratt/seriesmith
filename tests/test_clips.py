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

    def test_a_project_of_its_own(self):
        """+ New project: a show of its own, marked simple, which builds; the
        episode list says which episodes are Simple's (Clips is, by its path)."""
        res = self.ok(A.post_clips_new(self.ctx, {"title": "Storm at the lighthouse"}))
        ep = os.path.join(self.shows, "Storm_at_the_lighthouse", "storm_at_the_lighthouse")
        self.assertEqual(res["ep"], ep)
        cfg = json.load(open(os.path.join(ep, "series.json"), encoding="utf-8"))
        self.assertIs(cfg["simple"], True)
        self.assertEqual(cfg["series"]["title"], "Storm at the lighthouse")
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": ep}))["ok"])
        self.assertEqual(A.post_clips_new(self.ctx, {"title": "Storm at the lighthouse"})[0], 409)
        self.assertEqual(A.post_clips_new(self.ctx, {"title": "  ?? "})[0], 400)
        clips = self.clips()
        cfg = os.path.join(clips, "series.json")
        old = json.load(open(cfg, encoding="utf-8"))
        old.pop("simple")                                  # a Clips made before the marker
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump(old, fh)
        simple = {e["ep"]: e["simple"] for e in self.ok(A.get_episodes(self.ctx, {}))}
        self.assertTrue(simple[ep] and simple[clips])
        self.assertFalse(any(v for k, v in simple.items() if k not in (ep, clips)))

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

    def test_a_clips_step_is_made_again_after_a_restart(self):
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
        queue = self.ctx.runner.queue
        # the picture held on its lane, the step waiting on it
        for name in list(self.ctx.runner.backends):
            queue.pause(name)
        status, res = A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c001", "takes": 1})
        self.assertEqual(status, 200, res)
        lane = queue.jobs[res["refs"][0]["prompt_id"]].lane
        step = queue.jobs[res["step"]]
        self.assertEqual(step.resume["step"], "clip")
        # journaled, though it has no record of its own
        queue.journal = os.path.join(self.tmp, "queue.json")
        self.addCleanup(setattr, queue, "journal", None)
        queue.write_journal()
        kept = queue.read_journal()[step.id]
        self.assertEqual((kept["status"], kept["resume"]["params"]["refs"]),
                         ("queued", ["location:pier"]))
        # the server stops: the step is lost, the picture still on its way;
        # made again from the journal, it waits on the picture, not a job id
        queue.cancel(step.id)
        again = A.rebuild_step(self.ctx, kept["resume"])
        self.assertEqual(queue.jobs[again].status, "queued")
        queue.pause(lane, False)
        settle(self.ctx.runner, 60)
        self.assertEqual(queue.jobs[again].status, "succeeded", queue.jobs[again].log)
        self.assertEqual([t.status for t in T.list_takes(ep, "proxy", "c001")], ["ok"])

    def test_a_shot_that_isnt_built_is_refused(self):
        ep = self.clips()
        self.err(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c009"}), 404)
        self.err(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c009", "takes": 9}), 400)



class WordsOnlyTest(ApiTest):
    """A place or a person with no picture (a description only) builds on H3:
    written in words, no Picture slot, nothing to wait for."""

    def test_a_place_and_a_person_in_words(self):
        ep = self.ok(A.post_clips_ensure(self.ctx, {}))["ep"]
        p = os.path.join(ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["locations"]["pond"] = {"description": "a small pond at dawn, reeds, mist"}
        cfg["subjects"]["ollie"] = {"kind": "character", "name": "Ollie",
                                    "design": "an old fisherman in a yellow oilskin"}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        with open(os.path.join(ep, "clips.md"), "w", encoding="utf-8") as fh:
            fh.write("= clips  Clips\n\n# sq01  pond\n\n## sh010\nwho: ollie\nsize: medium\n"
                     "dur: 3.04\nOllie casts a line into the still water.\n")
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": ep}))["ok"])
        from seriesmith import jobs as J
        doc = J.load_shotlist(ep, "proxy")
        shot = doc["shots"][0]
        self.assertEqual((shot["subjects"], shot["background"], shot["text_place"]), ([], "", True))
        prompt = "\n".join(shot["prompt"]) if isinstance(shot["prompt"], list) else shot["prompt"]
        self.assertIn("Ollie has no reference image and is drawn from this description", prompt)
        self.assertIn("a small pond at dawn", prompt)
        self.assertNotIn("<Picture", prompt)
        self.assertEqual(J.missing_refs(ep, doc, shot), [])


class StillTest(ApiTest):
    """A picture clip: candidates of the shot's first keyframe on an image
    model, made live when the refs are next listed."""

    def test_a_picture_on_a_text_to_image_model(self):
        ep = self.ok(A.post_clips_ensure(self.ctx, {}))["ep"]
        p = os.path.join(ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["locations"]["pond"] = {"description": "a small pond at dawn"}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        with open(os.path.join(ep, "clips.md"), "w", encoding="utf-8") as fh:
            fh.write("= clips  Clips\n\n# cl001  pond\n\n## c001\n// a picture\nfirst: generate\n"
                     "size: wide\ndur: 3.04\nA heron at the water's edge.\n")
        self.assertTrue(self.ok(A.post_build(self.ctx, {"ep": ep}))["ok"])
        res = self.ok(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c001", "takes": 2, "still": True,
                                                   "image_target": "krea2"}))
        self.assertEqual((res["refs"], res["step"], res["renders"]), ([], None, []))
        self.assertEqual([q["target"] for q in res["stills"]], ["krea2", "krea2"])
        settle(self.ctx.runner, 60)
        self.ok(A.get_refs(self.ctx, {"ep": ep}))            # the listing makes one live
        ref = R.find_ref(R.load_series(ep), "shot:c001:first")
        self.assertTrue(os.path.isfile(ref.file))
        self.assertEqual(T.list_takes(ep, "proxy", "c001"), [])        # no video
        self.err(A.post_clip_queue(self.ctx, {"ep": ep, "shot": "c001", "still": True}), 400)


if __name__ == "__main__":
    unittest.main()
