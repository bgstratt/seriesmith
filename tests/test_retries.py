"""
retries: the retry ladder's decisions after a checked take (a new seed, the target's fallback
from its first frame, or stop, and why), and the extra-check hook takecheck keeps for a
vision-language model.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import retries as RT  # noqa: E402
from seriesmith import takecheck as TC  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402


def _take(tmp: str, checks: dict | None, status: str = "ok", backend: str = "local",
          target: str = "minimax_h3_ref2va", n: int = 3) -> T.Take:
    d = os.path.join(tmp, "renders", "sh020")
    os.makedirs(d, exist_ok=True)
    mp4 = os.path.join(d, f"sh020_t{n:02d}.mp4")
    with open(mp4, "wb") as fh:
        fh.write(b"x" * 100)
    sc = {"status": status, "backend": backend, "target": target}
    if checks is not None:
        sc["checks"] = {"v": TC.VERSION, "size": 100, "cut_score": 12.0, "words_match": 0.85, **checks}
    with open(os.path.join(d, f"sh020_t{n:02d}.json"), "w", encoding="utf-8") as fh:
        json.dump(sc, fh)
    return T.get_take(tmp, "final", "sh020", n)


CUT = {"cuts": [{"frame": 14, "t": 0.58, "score": 42.4}], "words": None}
CLEAN = {"cuts": [], "words": {"want": "Cut it.", "heard": "Cut it.", "match": 1.0}}


def fallback_of(tid: str):
    return TG.load_target(tid, "video").retry_fallback


class DecideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="retries-")

    def test_a_failed_take_gets_a_new_seed_then_the_fallback(self):
        t = _take(self.tmp, CUT)
        nxt = RT.decide(t, RT.Plan(tries=2, fallback=True), picked=False, fallback_of=fallback_of)
        self.assertEqual((nxt.do, nxt.target, nxt.plan.tries), ("seed", "minimax_h3_ref2va", 1))
        self.assertEqual(nxt.note, "retry 1 after t03: a cut at 0.58 s")
        nxt = RT.decide(t, RT.Plan(tries=0, fallback=True), picked=False, attempt=3, fallback_of=fallback_of)
        self.assertEqual((nxt.do, nxt.target), ("fallback", "minimax_h3_fl2va"))
        self.assertFalse(nxt.plan.fallback)                 # the fallback's own take ends it
        self.assertEqual(RT.decide(t, RT.Plan(tries=0, fallback=False), picked=False,
                                   fallback_of=fallback_of).do, "stop")

    def test_the_fallbacks_first_frame(self):
        late = {"cuts": [{"frame": 30, "t": 1.25, "score": 20}], "words": None}
        early = {"cuts": [{"frame": 5, "t": 0.21, "score": 20}], "words": None}
        words = {"cuts": [], "words": {"want": "Cut it.", "heard": "Cut.", "match": 0.5}}
        plan = RT.Plan(tries=0, fallback=True)
        for checks, has_first, frame in ((late, True, "live"), (early, True, "live"), (late, False, "take"),
                                         (words, False, "take"), (early, False, "make")):
            with self.subTest(checks=checks, has_first=has_first):
                nxt = RT.decide(_take(self.tmp, checks), plan, False, fallback_of=fallback_of, has_first=has_first)
                self.assertEqual((nxt.do, nxt.frame), ("fallback", frame))
        # a registered check may be about the frame itself: its first frame isn't trusted
        look = {"cuts": [], "words": None, "more": {"look": {"flag": True, "why": "two of Mara"}}}
        self.assertEqual(RT.decide(_take(self.tmp, look), plan, False, fallback_of=fallback_of).frame, "make")

    def test_the_fallback_by_hand_needs_no_failure(self):
        clean = _take(self.tmp, CLEAN)
        nxt = RT.fallback_now(clean, fallback_of)
        self.assertEqual((nxt.do, nxt.target, nxt.frame), ("fallback", "minimax_h3_fl2va", "take"))
        self.assertEqual(RT.fallback_now(_take(self.tmp, None), fallback_of).frame, "take")   # not checked yet
        self.assertEqual(RT.fallback_now(clean, fallback_of, has_first=True).frame, "live")
        self.assertEqual(RT.fallback_now(_take(self.tmp, {"cuts": [{"frame": 2, "t": 0.08, "score": 30}],
                                                          "words": None}), fallback_of).frame, "make")
        self.assertEqual(RT.fallback_now(_take(self.tmp, CLEAN, target="minimax_h3_fl2va"), fallback_of).do, "stop")
        self.assertEqual(RT.fallback_now(_take(self.tmp, CLEAN, status="queued"), fallback_of).do, "stop")

    def test_a_fallback_take_that_fails_stops(self):
        t = _take(self.tmp, CUT, target="minimax_h3_fl2va")
        nxt = RT.decide(t, RT.Plan(tries=0, fallback=True), picked=False, fallback_of=fallback_of)
        self.assertEqual(nxt.do, "stop")
        self.assertIn("out of retries", nxt.why)

    def test_it_stops(self):
        self.assertIn("passed", RT.decide(_take(self.tmp, CLEAN), RT.Plan(2), False).why)
        self.assertIn("checked", RT.decide(_take(self.tmp, None), RT.Plan(2), False).why)
        self.assertIn("picked", RT.decide(_take(self.tmp, CUT), RT.Plan(2), picked=True).why)
        self.assertIn("failed", RT.decide(_take(self.tmp, CUT, status="failed"), RT.Plan(2), False).why)
        paid = _take(self.tmp, CUT, backend="cloud")
        self.assertIn("costs", RT.decide(paid, RT.Plan(2), False).why)
        self.assertEqual(RT.decide(paid, RT.Plan(2, paid=True), False).do, "seed")

    def test_the_plan_as_asked(self):
        self.assertEqual(RT.Plan.from_json({"tries": 2}).to_json(), {"tries": 2, "fallback": True, "paid": False})
        for bad in ({"tries": 9}, {"tries": "2"}, {"tries": 1, "fallback": "yes"}, [1]):
            with self.assertRaises(ValueError):
                RT.Plan.from_json(bad)
        self.assertFalse(RT.Plan.from_json(None).asks)

    def test_each_ref2va_family_target_falls_back_to_its_fl2va(self):
        self.assertEqual({t: fallback_of(t) for t in ("minimax_h3_ref2va", "fasth3_omni", "h3_singularity",
                                                      "pika_h3_flex", "minimax_h3_fl2va")},
                         {"minimax_h3_ref2va": "minimax_h3_fl2va", "fasth3_omni": "fasth3_fl2va",
                          "h3_singularity": "h3_singularity_fl2va", "pika_h3_flex": "pika_h3_flex_fl2va",
                          "minimax_h3_fl2va": None})
        for t in ("minimax_h3_fl2va", "fasth3_fl2va", "h3_singularity_fl2va", "pika_h3_flex_fl2va"):
            TG.load_target(t, "video")                      # each one is there


class StepTest(unittest.TestCase):
    """api's retry step on a built episode, its queue stood in for."""

    def setUp(self):
        import shutil
        from test_render import FIXTURE, build_episode
        self._t = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._t.name, "ks01")
        os.makedirs(self.root)
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)

    def tearDown(self):
        self._t.cleanup()

    def test_the_step_waits_then_asks_for_the_next_rung(self):
        import subprocess
        from types import SimpleNamespace
        from seriesmith import api as A
        from seriesmith import ff as FF
        from seriesmith import refs as R
        steps, asked, alive = [], [], {"q1"}

        def enqueue_step(title, work, after=None, info=None, wait=None, spec=None):
            steps.append(SimpleNamespace(title=title, work=work, wait=wait, spec=spec))
            return f"s{len(steps)}"
        runner = SimpleNamespace(queue=SimpleNamespace(alive=lambda: alive), enqueue_step=enqueue_step,
                                 ask=lambda path, body: (asked.append(body) or (200, {"queued": [{"shot": "sh020", "take": 9}], "errors": []})))
        ctx = SimpleNamespace(runner=runner, emit=lambda *a: None)
        t = T.reserve_take(self.root, "final", "sh020", {"status": "queued", "comfy_prompt_id": "q1",
                                                         "target": "minimax_h3_ref2va", "backend": "local"})
        p = {"ep": self.root, "pass": "final", "shot": "sh020", "take": t.take,
             "retry": {"tries": 1, "fallback": True, "paid": False}, "attempt": 1}
        A._retry_step(ctx, p)
        step = steps[0]
        self.assertEqual(step.spec, {"step": "retry", "params": p})
        self.assertIs(A.STEPS["retry"], A._retry_step)
        self.assertTrue(step.wait())                       # still rendering
        # it finished with a cut in it (checks are off in the tests: the step doesn't wait for them)
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=128x72:d=1",
                        "-pix_fmt", "yuv420p", t.paths.mp4], check=True)
        T.update_sidecar(t.paths.sidecar, status="ok", checks={
            "v": TC.VERSION, "size": os.path.getsize(t.paths.mp4), "cuts": [{"frame": 18, "t": 0.75, "score": 30}],
            "words": None})
        alive.clear()
        self.assertFalse(step.wait())
        lines = []
        self.assertEqual(step.work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertEqual(asked[-1], {"ep": self.root, "pass": "final", "shots": ["sh020"], "redo": True,
                                     "seed_mode": "new", "target": "minimax_h3_ref2va",
                                     "note": f"retry 1 after t{t.take:02d}: a cut at 0.75 s",
                                     "retry": {"tries": 0, "fallback": True, "paid": False}, "retry_attempt": 2})
        # its tries spent: the fallback, from the take's first frame
        A._retry_step(ctx, {**p, "retry": {"tries": 0, "fallback": True, "paid": False}, "attempt": 2})
        self.assertEqual(steps[1].work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertEqual((asked[-1]["target"], asked[-1]["retry"]), ("minimax_h3_fl2va", {"tries": 0, "fallback": False, "paid": False}))
        kf = R.find_ref(R.load_series(self.root), "shot:sh020:first")
        self.assertTrue(os.path.isfile(kf.file))
        self.assertIn(f"from t{t.take:02d}'s first frame", asked[-1]["note"])
        made = len(R.list_takes(kf, None))
        # now it has a first keyframe of its own: the fallback keeps it
        A._retry_step(ctx, {**p, "retry": {"tries": 0, "fallback": True, "paid": False}, "attempt": 2})
        self.assertEqual(steps[2].work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertIn("the shot's own first keyframe", asked[-1]["note"])
        self.assertEqual(len(R.list_takes(kf, None)), made)
        # no first keyframe, and a cut at the take's opening: one is made on the keyframe model
        R.clear_pick(R.load_series(self.root), kf, None)
        T.update_sidecar(t.paths.sidecar, checks={**T.read_sidecar(t.paths.sidecar)["checks"],
                                                  "cuts": [{"frame": 5, "t": 0.21, "score": 30}]})
        gen = []
        n_asked = len(asked)
        with mock.patch.object(A, "_generate", lambda c, body: (gen.append(body) or (200, {"queued": [{"prompt_id": "g1", "take": 99}]}))):
            A._retry_step(ctx, {**p, "retry": {"tries": 0, "fallback": True, "paid": False}, "attempt": 2})
            self.assertEqual(steps[3].work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertEqual(gen, [{"ep": self.root, "ref": "shot:sh020:first", "count": 1}])
        self.assertEqual(len(asked), n_asked)                # the render waits for the picture
        frame_step = steps[4]
        self.assertEqual(frame_step.spec["step"], "retry_frame")
        self.assertIs(A.STEPS["retry_frame"], A._retry_frame_step)
        self.assertEqual(frame_step.work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertIn("didn't come out", str(lines[-1]))    # none made: it ends there
        self.assertEqual(len(asked), n_asked)
        # one made (here: a candidate already there, as the picture would be): it goes live, then the render
        have = R.list_takes(kf, None)[-1]
        A._retry_frame_step(ctx, {**frame_step.spec["params"], "take": have.take})
        self.assertEqual(steps[-1].work(lambda **kw: lines.append(kw)), "succeeded")
        self.assertTrue(os.path.isfile(kf.file))
        self.assertEqual(len(asked), n_asked + 1)
        self.assertEqual(asked[-1]["target"], "minimax_h3_fl2va")
        # a take picked in the cut: nothing more
        from seriesmith import edit as E
        E.pick_take(self.root, "final", "sh020", t.take)
        n = len(asked)
        A._retry_step(ctx, p)
        steps[-1].work(lambda **kw: lines.append(kw))
        self.assertEqual(len(asked), n)
        self.assertIn("picked", str(lines[-1]))


class MoreChecksTest(unittest.TestCase):
    """The hook a vision-language model's look joins by."""

    def tearDown(self):
        TC.CHECKERS.clear()

    def test_a_registered_check_flags_and_retries_like_a_cut(self):
        TC.register("look", lambda root, take, shot: {"flag": True, "why": "two of Mara"})
        TC.register("quiet", lambda root, take, shot: None)
        TC.register("broken", lambda root, take, shot: 1 / 0)
        tmp = tempfile.mkdtemp(prefix="retries-")
        t = _take(tmp, CLEAN)
        with mock.patch.object(TC, "scores", return_value=[0.0] * 10):
            got = TC.check(tmp, t, words=False)["more"]
        self.assertEqual(set(got), {"look", "broken"})
        self.assertIn("broken failed", got["broken"]["why"])
        checks = {**t.sidecar["checks"], "more": got}
        self.assertEqual(TC.flags(checks), ["look"])
        self.assertEqual(TC.reasons(checks), ["look: two of Mara"])
        T.update_sidecar(t.paths.sidecar, checks=checks)
        nxt = RT.decide(T.get_take(tmp, "final", "sh020", 3), RT.Plan(1), False)
        self.assertEqual(nxt.do, "seed")
        with self.assertRaises(ValueError):
            TC.register("cut", lambda *a: None)


if __name__ == "__main__":
    unittest.main()
