"""
What every Comfy Router video model is sent, pinned byte for byte: the
kitchen_sink episode's shots retargeted to each one (as the editor's "render on"
does), planned and turned into the provider's request (router_call), offline:
nothing is sent anywhere. The request carries everything that model takes
differently: the prompt as its writer words it (a model with no sound acts the
lines out instead of quoting them), cut to its longest prompt (max_chars) with
the pictures' mentions kept, the pictures and how they go (references, frames,
Seedance's virtual library), length, size or ratio, seed and sound, and a
Seedance draft's final.

    python tests/test_router_golden.py --update     # after an intended change

then review the diff of tests/golden/router_calls/ and say why in the commit.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import ff as FF  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from test_render import FIXTURE, build_episode, wav_bytes  # noqa: E402

GOLDEN = os.path.join(HERE, "golden", "router_calls")
# one subject, generated sound / three, cloned voices / three, dubbed / none
# (a plate) / two, cloned / one with both keyframes on disk (frames mode)
SHOTS = ("sh010", "sh020", "sh110", "sh140", "sh210", "sh150")
KEYFRAMED = "sh150"
# a prompt past every model's max_chars but Wan 2.7's: the cut (router_video.fit)
# drops sentences from the start and keeps what happens, the line and the sound
LONG = ("Style: live-action, warm tungsten light, 35mm film grain. "
        + " ".join(f"The kitchen's detail {i}: a dented copper pot, a chipped blue tile, "
                   f"a calendar from a year nobody remembers on the wall." for i in range(28))
        + " Ada sets the kettle down hard and turns to Bo. ADA says: \"You know that one "
          "whistles.\" The kettle starts to whistle. Sound: the kettle's rising whistle, "
          "rain on the window, no music.")


def router_targets() -> list[str]:
    """Every shipped Router video model, drafts too."""
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "seriesmith", "targets", "video", "*",
                                           "target.json"))):
        with open(f, encoding="utf-8") as fh:
            spec = json.load(fh)
        if spec.get("code") == "builtin:router_video":
            out.append(spec["id"])
    return out


def plain(value, root: str):
    """The request as JSON: a File as its episode path and how it goes."""
    if isinstance(value, File):
        p = os.path.relpath(value.path, root).replace(os.sep, "/")
        return {"file": p, **({"via": value.via} if getattr(value, "via", None) else {})}
    if isinstance(value, dict):
        return {k: plain(v, root) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v, root) for v in value]
    return value


def capture(root: str, tid: str) -> dict:
    """{case: what planning and router_call made of it, or the error said}."""
    target = TG.load_target(tid, "video")
    out = {}
    cases = [(sid, None) for sid in SHOTS]
    cases += [("sh020", "long"), (KEYFRAMED, "long")]
    if (target.spec.get("router") or {}).get("draft"):
        cases.append(("sh010", {"task": "draft-task-1", "take": 2}))
    for sid, extra in cases:
        draft = extra if isinstance(extra, dict) else None
        key = sid + (" from its draft" if draft else " with a long prompt" if extra else "")
        doc, i = J.find_shot(root, "final", sid)
        try:
            kw = {"from_draft": {sid: draft}} if draft else {"prompt": LONG} if extra else {}
            req = J.RenderRequest(sid, target=tid, **kw)
            job = J.plan_job(root, "final", doc, i, req, {})
            t = J.job_target(job)
            model, args = t.module.router_call(t, job)
            out[key] = {"model": model, "arguments": plain(args, root),
                        "frames": job.frames, "size": [job.width, job.height],
                        "notes": list(job.notes or [])}
        except Exception as e:                           # noqa: BLE001  an answer too
            out[key] = {"error": f"{type(e).__name__}: {e}"}
    return out


def capture_all() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as root:
        build_episode(root)
        # a retargeted shot is compiled again from the episode's series config
        shutil.copy(os.path.join(FIXTURE, "series.json"), root)
        for end in ("first", "last"):                    # one shot with its keyframes made
            p = os.path.join(root, "refs", "shots", KEYFRAMED, f"{end}.png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()
        # the recording a dub shot's window is cut from (the fixture's is a stand-in)
        with open(os.path.join(root, "audio", "ks01_mix.wav"), "wb") as fh:
            fh.write(wav_bytes(12.0))
        return {tid: json.dumps(capture(root, tid), indent=1, sort_keys=True,
                                ensure_ascii=False) + "\n"
                for tid in router_targets()}


class RouterGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.got = capture_all()

    def test_every_router_model_is_pinned(self):
        self.assertGreaterEqual(len(self.got), 15)
        for tid in self.got:
            self.assertTrue(os.path.isfile(os.path.join(GOLDEN, tid + ".json")),
                            f"no golden for {tid}: python tests/test_router_golden.py --update")

    def test_each_request_is_as_pinned(self):
        for tid, text in self.got.items():
            with self.subTest(target=tid):
                with open(os.path.join(GOLDEN, tid + ".json"), encoding="utf-8") as fh:
                    self.assertEqual(text, fh.read().replace("\r\n", "\n"))


class SeedanceAudioTest(unittest.TestCase):
    """What the goldens don't pin: Seedance's audio references at their
    limits (router_video.sounds, video_prose.voice_refs)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = self._t.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)

    def tearDown(self):
        self._t.cleanup()

    def call(self, sid: str, tid: str = "seedance_2_0"):
        doc, i = J.find_shot(self.root, "final", sid)
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest(sid, target=tid), {})
        t = J.job_target(job)
        return job, t.module.router_call(t, job)[1]

    def sample(self, who: str, seconds: float) -> str:
        p = os.path.join(self.root, "audio", "voices", f"{who}_sample.wav")
        with open(p, "wb") as fh:
            fh.write(wav_bytes(seconds))
        return p

    def heard(self, args) -> list[str]:
        return [os.path.relpath(x["audio_url"]["url"].path, self.root).replace(os.sep, "/")
                for x in args["content"] if x.get("type") == "audio_url"]

    def test_a_voice_sample_too_short_is_refused(self):
        self.sample("ada", 1.0)
        with self.assertRaisesRegex(ValueError, r"Ada's voice sample is 1\.0s and Seedance hears "
                                                r"2s at the least"):
            self.call("sh020")

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_a_long_voice_sample_is_cut(self):
        from seriesmith import audiocut as AC
        self.sample("ada", 20.0)
        _, args = self.call("sh020")
        ada = self.heard(args)[0]
        self.assertTrue(ada.startswith("audio/voices/_cuts/ada_sample_"), ada)
        self.assertLessEqual(AC.duration(os.path.join(self.root, ada)), 15.0)

    def test_audio_needs_a_picture_on_2_0_not_on_2_5(self):
        shutil.rmtree(os.path.join(self.root, "refs"))
        with self.assertRaisesRegex(ValueError, "can't be sent audio without a picture"):
            self.call("sh020")
        _, args = self.call("sh020", "seedance_2_5")
        self.assertEqual(self.heard(args), ["audio/voices/ada_sample.wav",
                                            "audio/voices/bo_sample.wav"])

    def test_audio_goes_with_references_not_keyframes(self):
        """BytePlus refuses frames mixed with reference media: a clone shot with
        its keyframes on disk sends its reference pictures and its voices."""
        for end in ("first", "last"):
            p = os.path.join(self.root, "refs", "shots", "sh020", f"{end}.png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()
        job, args = self.call("sh020")
        roles = [x.get("role") for x in args["content"] if x.get("role")]
        self.assertNotIn("first_frame", roles)
        self.assertNotIn("last_frame", roles)
        self.assertIn("reference_image", roles)
        self.assertEqual(roles.count("reference_audio"), 2)
        self.assertIn("can't take a first or last frame with audio", " ".join(job.notes))
        # the audio goes inline: the Seedance library takes pictures only
        self.assertEqual({x["audio_url"]["url"].via for x in args["content"]
                          if x.get("type") == "audio_url"}, {"datauri"})

    def test_more_speakers_than_voices_is_a_build_error(self):
        t = TG.load_target("seedance_2_0", "video")
        voices = t.spec["router"]["inputs"]["voices"]
        voices["max"] = 2
        try:
            doc, i = J.find_shot(self.root, "final", "sh210")
            job = J.plan_job(self.root, "final", doc, i,
                             J.RenderRequest("sh210", target="seedance_2_0"), {})
        finally:
            voices["max"] = 3
        self.assertEqual(job.action, "error")
        self.assertIn("3 speakers", job.error)
        self.assertIn("takes at most 2", job.error)


if __name__ == "__main__":
    if "--update" in sys.argv:
        os.makedirs(GOLDEN, exist_ok=True)
        for tid, text in capture_all().items():
            with open(os.path.join(GOLDEN, tid + ".json"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print("wrote", tid)
    else:
        unittest.main(verbosity=2)
