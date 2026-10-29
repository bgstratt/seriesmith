"""
P5: a location's camera tour (tour.py) and a character's views turned from
one it has (refs.plan_edit `from_view` / `turn`).

The tour's ComfyUI run and its stills step are faked: the graph it queues,
what it refuses, and what happens to its holds (takes of the location's
`tour` view, never picked there, copied into an angle as a candidate) are
what is checked.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import refs as R  # noqa: E402
from seriesmith import tour as TOUR  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from test_render import png_bytes  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "kitchen_sink")


class FakeComfy:
    def __init__(self, video: bytes = b"mp4"):
        self.queued, self.uploaded, self.video = [], [], video

    def upload_input(self, path, name):
        self.uploaded.append(name)
        return name

    def queue(self, g):
        self.queued.append(g)
        return f"pid{len(self.queued)}"

    def wait(self, pid, timeout):
        return {"92": {"images": [{"filename": "tour_00001.mp4", "subfolder": "h3pipe/tours",
                                   "type": "output"}]}}

    def view(self, f):
        return self.video


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ep = os.path.join(self._tmp.name, "ks01")
        os.makedirs(self.ep)
        with open(os.path.join(FIXTURE, "series.json"), encoding="utf-8") as fh:
            c = json.load(fh)
        c["locations"]["kitchen_on_sink"] = {"of": "kitchen", "description": "the sink",
                                             "plate": "refs/_bg/kitchen_on_sink.png"}
        with open(os.path.join(self.ep, "series.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ks01.md"))
        from seriesmith import edit as E
        self.assertTrue(E.build_episode(self.ep)["ok"])
        s = R.load_series(self.ep)
        self.png = os.path.join(self._tmp.name, "p.png")
        with open(self.png, "wb") as fh:
            fh.write(png_bytes(1344, 768))
        kitchen = R.find_ref(s, "location:kitchen")
        R.pick_take(s, kitchen, None, R.import_take(s, kitchen, None, self.png).take)
        ada = R.find_ref(s, "subject:ada")
        R.pick_take(s, ada, "01_threequarter", R.import_take(s, ada, "01_threequarter", self.png).take)
        self.s = R.load_series(self.ep)

    def tearDown(self):
        self._tmp.cleanup()


class TourTest(Base):
    def tour(self, move="turn left and hold", found=None, mode="node", seconds=6.0):
        """One tour on seriesmith's queue (Runner.enqueue_tour), its backend
        playing the graph (FakeComfy `mode`), its holds `found`: the sidecar."""
        from test_render import FakeComfy as Played, settle
        c = Played()
        self.addCleanup(c.close)
        c.mode = mode
        ref = R.find_ref(self.s, "location:kitchen")
        with mock.patch.object(TOUR, "find_holds", return_value=found or {"fps": 24, "holds": []}):
            ((side, g),) = TOUR.plan_tours(self.s, ref, move, None, seconds)
            n, qid = c.runner.enqueue_tour(self.s, ref, side, g, "local")
            settle(c.runner)
        return next(d for d in TOUR.list_tours(ref) if d["tour"] == n)

    def test_the_graph_gets_the_frame_move_length_and_seed(self):
        ref = R.find_ref(self.s, "location:kitchen")
        ((side, g),) = TOUR.plan_tours(self.s, ref, "The camera turns left and holds", None, 5)
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        self.assertIsNone(by["LoadImage"]["image"])     # the plate, put in as it's queued
        self.assertTrue(by["MiniMaxH3ImageToVideo"]["prompt"].startswith(
            "The camera turns left and holds. Nothing in the place moves"))
        self.assertEqual(by["PrimitiveFloat"]["value"], 5.0)
        self.assertEqual(by["RandomNoise"]["noise_seed"], side["seed"])
        self.assertEqual((side["status"], side["comfy_prompt_id"]), ("queued", None))
        self.assertEqual([d["tour"] for d in TOUR.list_tours(ref)], [1])

    def test_what_is_refused(self):
        ref = R.find_ref(self.s, "location:kitchen")
        for args, why in ((("", 6, 1), "needs a move"), (("go", 30, 1), "seconds"),
                          (("go", 6, 9), "count")):
            with self.subTest(args=args), self.assertRaisesRegex(TOUR.TourError, why):
                TOUR.check_request(ref, *args)
        with self.assertRaisesRegex(TOUR.TourError, "not a location"):
            TOUR.check_request(R.find_ref(self.s, "subject:ada"), "go", 6, 1)
        with self.assertRaisesRegex(TOUR.TourError, "no live plate"):
            TOUR.check_request(R.find_ref(self.s, "location:kitchen_on_sink"), "go", 6, 1)

    def test_holds_land_on_the_tour_view_and_copy_into_an_angle(self):
        ref = R.find_ref(self.s, "location:kitchen")
        holds_dir = os.path.join(self._tmp.name, "holds")
        os.makedirs(holds_dir)
        found = {"fps": 24, "holds": []}
        for k in (1, 2):
            p = os.path.join(holds_dir, f"hold_{k:02d}.png")
            shutil.copy(self.png, p)
            found["holds"].append({"hold": k, "start": k - 1.0, "end": k - 0.5, "frame": k,
                                   "sharpness": 1.0, "path": p})
        side = self.tour(found=found)
        self.assertEqual(side["status"], "ok", side.get("error"))
        self.assertEqual(len(side["holds"]), 2)
        js = R.ref_json(self.s, ref)
        self.assertEqual([t["take"] for t in js["tour_holds"]], side["holds"])
        self.assertEqual(js["tours"][0]["status"], "ok")
        with self.assertRaisesRegex(R.RefError, "isn't picked where it is"):
            R.pick_take(self.s, ref, R.TOUR_VIEW, side["holds"][1])
        angle = R.find_ref(self.s, "location:kitchen_on_sink")
        t = R.copy_take(self.s, ref, R.TOUR_VIEW, side["holds"][1], angle)
        self.assertEqual(t.sidecar["copied_from"]["source"], "tour")
        self.assertIn("tour t01 hold 2", t.sidecar["note"])

    def test_a_failed_tour_says_why(self):
        side = self.tour(mode="error")
        self.assertEqual(side["status"], "failed")
        self.assertIn("boom", side["error"])


class TourQueueTest(Base):
    """A tour on seriesmith's queue (Runner.enqueue_tour), on the fake backend:
    the plate goes up as the LoadImage, and the video that comes back is kept
    and its holds found."""

    def test_a_queued_tour_uploads_its_plate_and_keeps_its_holds(self):
        import time
        from seriesmith import takes as T
        from seriesmith.backends import File
        from seriesmith.backends.fake import FakeBackend
        from seriesmith.queue import Queue
        from seriesmith.runner import Runner

        fb = FakeBackend("local", "local", outputs=lambda g: {"92": [("tour_00001.mp4", "video", b"mp4")]})
        events = []
        runner = Runner(Queue(), {"local": fb}, emit=lambda e, d: events.append((e, d)))
        self.addCleanup(setattr, T, "MANAGED", None)
        ref = R.find_ref(self.s, "location:kitchen")
        found = {"fps": 24, "holds": [{"hold": 1, "start": 0.0, "end": 0.5, "frame": 3,
                                       "sharpness": 1.0, "path": self.png}]}
        with mock.patch.object(TOUR, "find_holds", return_value=found):
            ((side, g),) = TOUR.plan_tours(self.s, ref, "turn left and hold", None)
            n, qid = runner.enqueue_tour(self.s, ref, side, g, "local")
            end = time.time() + 15
            while runner.queue.jobs[qid].status not in ("succeeded", "failed") and time.time() < end:
                time.sleep(0.02)
        job = runner.queue.jobs[qid]
        self.assertEqual(job.status, "succeeded", (job.error, job.log))
        image = next(v for v in fb.submitted[0].values() if v["class_type"] == "LoadImage")
        self.assertIsInstance(image["inputs"]["image"], File)
        self.assertEqual(image["inputs"]["image"].path, ref.file)
        (d,) = TOUR.list_tours(ref)
        self.assertEqual((d["tour"], d["status"], d["comfy_prompt_id"], d["queue"]),
                         (n, "ok", qid, "seriesmith"))
        self.assertEqual(len(d["holds"]), 1)
        with open(R.ref_file(self.s.ep, d["video"]), "rb") as fh:
            self.assertEqual(fh.read(), b"mp4")
        self.assertIn(("seriesmith.ref", {"ep": self.s.ep, "ref": ref.id, "view": R.TOUR_VIEW,
                                      "take": d["holds"][0], "status": "ok"}), events)


class AngleTourTest(Base):
    def test_an_angle_with_no_plate_tours_from_its_place(self):
        angle = R.find_ref(self.s, "location:kitchen_on_sink")
        kitchen = R.find_ref(self.s, "location:kitchen")
        self.assertFalse(os.path.isfile(angle.file))
        self.assertEqual(TOUR.tour_source(self.s, angle), kitchen.file)
        ((side, g),) = TOUR.plan_tours(self.s, angle, "The camera pushes in and holds", None)
        self.assertEqual(side["frame"], R.ep_rel(self.s.ep, kitchen.file))
        # the place's own plate, once it has one
        R.pick_take(self.s, angle, None, R.import_take(self.s, angle, None, self.png).take)
        s2 = R.load_series(self.ep)
        a2 = R.find_ref(s2, "location:kitchen_on_sink")
        self.assertEqual(TOUR.tour_source(s2, a2), a2.file)
        # no plate anywhere: it says why
        os.remove(kitchen.file)
        os.remove(a2.file)
        s3 = R.load_series(self.ep)
        with self.assertRaises(TOUR.TourError) as cm:
            TOUR.plan_tours(s3, R.find_ref(s3, "location:kitchen_on_sink"), "pushes in", None)
        self.assertIn("nor has kitchen", str(cm.exception))

    def test_an_angle_with_no_plate_makes_its_360_from_its_place(self):
        kitchen = R.find_ref(self.s, "location:kitchen")
        req = R.GenRequest("location:kitchen_on_sink", None, pano={"engine": "qwen"})
        jobs = R.plan_generate(self.s, req)
        self.assertEqual(jobs[0].references[0]["path"], kitchen.file)
        self.assertEqual(jobs[0].ref.id, "location:kitchen_on_sink")   # it lands on the angle


class LostTourTest(Base):
    def test_a_tour_the_server_lost_in_a_restart_is_failed(self):
        from seriesmith import takes as T
        ref = R.find_ref(self.s, "location:kitchen")
        ((side, g),) = TOUR.plan_tours(self.s, ref, "turn left and hold", None)
        side.update(comfy_prompt_id="lost", queue="seriesmith", backend="local")
        TOUR.save_side(ref, side)
        self.addCleanup(setattr, T, "MANAGED", T.MANAGED)
        # this queue's records only (takes.lost_job): set here, not left by another test
        self.addCleanup(setattr, T, "QUEUE", T.QUEUE)
        T.QUEUE = "seriesmith"
        T.MANAGED = lambda: {"lost"}                 # still on the queue: left alone
        self.assertEqual(TOUR.list_tours(ref)[0]["status"], "queued")
        T.MANAGED = lambda: set()                   # the server restarted
        (d,) = TOUR.list_tours(ref)
        self.assertEqual(d["status"], "failed")
        self.assertIn("restarted", d["error"])


class TurnTest(Base):
    def test_a_view_is_turned_from_another(self):
        req = R.GenRequest("subject:ada", "03_back",
                           edit={"take": None, "from_view": "01_threequarter", "turn": True})
        (job,) = R.plan_generate(self.s, req, rng=random.Random(0))
        self.assertEqual(job.view, "03_back")
        self.assertEqual(job.references[0]["view"], "01_threequarter")
        self.assertEqual(job.target.id, R.TURN_TARGET)
        self.assertEqual(job.prompt, R.VIEW_TURNS["03_back"])
        self.assertEqual(job.loras, [{"name": R.TURN_LORA, "strength": R.TURN_STRENGTH}])
        self.assertEqual(job.edit["view"], "01_threequarter")
        self.assertTrue(job.edit["turn"])

    def test_turning_is_for_a_characters_views(self):
        with self.assertRaisesRegex(R.RefError, "no views"):
            R.plan_generate(self.s, R.GenRequest("location:kitchen", prompt="x",
                                                 edit={"take": None, "from_view": "02_side"}))
        with self.assertRaisesRegex(R.RefError, "no picked take"):
            R.plan_generate(self.s, R.GenRequest("subject:ada", "01_threequarter",
                                                 edit={"take": None, "from_view": "02_side",
                                                       "turn": True}))


if __name__ == "__main__":
    unittest.main()


class TurningPointTest(unittest.TestCase):
    """h3_stills.turning_points: a pan that reverses without holding still
    dips in motion for a few frames, too briefly for a hold."""

    def setUp(self):
        from seriesmith.helpers import stills as h3_stills
        self.H = h3_stills

    def test_a_reversal_is_found(self):
        motion = [1, 1] + [8] * 50 + [1.5, 1.5] + [12] * 50 + [0.2] * 40
        found = self.H.holds(motion, 3.0, 6)
        turns = self.H.turning_points(motion, 24.0, found)
        self.assertEqual(len(turns), 1)
        self.assertTrue(50 <= turns[0][0] <= 53, turns)

    def test_a_steady_pan_has_none(self):
        motion = [1, 1] + [8] * 100 + [0.2] * 40
        found = self.H.holds(motion, 3.0, 6)
        self.assertEqual(self.H.turning_points(motion, 24.0, found), [])


@unittest.skipUnless(FF.have("ffmpeg") and FF.have("ffprobe"), "needs ffmpeg")
class GrabFrameTest(Base):
    def test_any_moment_becomes_a_hold(self):
        import subprocess
        ref = R.find_ref(self.s, "location:kitchen")
        ((side, _g),) = TOUR.plan_tours(self.s, ref, "turn left and hold", None)
        mp4 = TOUR._tour_file(ref, side["tour"], ".mp4")
        subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=size=320x180:rate=24:duration=2", "-pix_fmt", "yuv420p", mp4],
                       check=True)
        side.update(status="ok", video=R.ep_rel(self.s.ep, mp4), fps=24)
        TOUR.T.write_json(TOUR._tour_file(ref, side["tour"], ".json"), side)
        t = TOUR.grab_frame(self.s, ref, side["tour"], 1.0)
        self.assertEqual(t.sidecar["frame"], 24)
        self.assertEqual((t.sidecar["width"], t.sidecar["height"]), (320, 180))
        self.assertIn(t.take, TOUR.list_tours(ref)[0]["holds"])
        with self.assertRaisesRegex(TOUR.TourError, "no finished tour"):
            TOUR.grab_frame(self.s, ref, 9, 1.0)
