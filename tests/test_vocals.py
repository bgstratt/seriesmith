"""
The vocal stem (seriesmith/vocals.py, docs/SOUND.md phase 7): optional and off by
default. Its cache beside the recording, its job on the queue (a fake backend plays
the split), align's --vocals, the series config's `audio.dub_from: "vocals"` (the
shotlist's dub_track, what a dub shot's window is cut from), and the routes.

Nothing here runs Demucs: the node's own function is checked against a song by hand
(docs/SOUND.md phase 7 says how it was measured).
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import unittest
import wave
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import build as BLD  # noqa: E402
from seriesmith import edit as E  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import track as K  # noqa: E402
from seriesmith import vocals as VOC  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner, wait  # noqa: E402
from seriesmith.targets import held_audio as HA  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_phase9c_track import fake_words, script_lines, write_wav  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg"))


def tearDownModule():
    test_api.tearDownModule()


def wav_bytes(seconds: float = 0.3, rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * 2 * int(seconds * rate))
    return buf.getvalue()


def stem_backend(**kw) -> FakeBackend:
    """A local backend whose SaveAudio hands back a short stereo wav."""
    return FakeBackend("local", "local", outputs={"save": [("vocals_00001_.flac", "audio",
                                                            wav_bytes())]}, **kw)


class CacheTest(unittest.TestCase):
    def test_a_stem_is_kept_while_it_is_as_new_as_the_recording(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            rec = os.path.join(d, "song.wav")
            write_wav(rec, 0.1)
            self.assertEqual(VOC.stem_path(rec), rec + ".vocals.wav")
            self.assertIsNone(VOC.fresh(rec))
            write_wav(VOC.stem_path(rec), 0.1)
            now = time.time()
            os.utime(rec, (now - 10, now - 10))
            os.utime(VOC.stem_path(rec), (now, now))
            self.assertEqual(VOC.fresh(rec), VOC.stem_path(rec))
            os.utime(rec, (now + 10, now + 10))          # the recording replaced since
            self.assertIsNone(VOC.fresh(rec))

    def test_the_graph_loads_splits_and_saves(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            rec = os.path.join(d, "song.wav")
            write_wav(rec, 0.1)
            g = VOC.graph(rec)
            self.assertIsInstance(g["load"]["inputs"]["audio"], File)
            self.assertEqual(g["split"]["class_type"], "SeriesmithVocals")
            self.assertEqual(g["save"]["inputs"]["audio"], ["split", 0])   # the vocals, not the band

    def test_dub_from_is_the_recording_unless_asked(self):
        self.assertEqual(VOC.dub_from({}), "recording")
        self.assertEqual(VOC.dub_from({"audio": {"dub_from": "nonsense"}}), "recording")
        self.assertEqual(VOC.dub_from({"audio": {"dub_from": "vocals"}}), "vocals")


class DubTrackTest(unittest.TestCase):
    def test_a_shotlist_gains_dub_track_only_when_asked(self):
        doc = {"defaults": {"master_track": "audio/song.wav"}}
        BLD.with_dub_track(doc, {"audio": {"track": "audio/song.wav"}})
        self.assertNotIn("dub_track", doc["defaults"])           # off: the shotlist as it was
        BLD.with_dub_track(doc, {"audio": {"dub_from": "vocals"}})
        self.assertEqual(doc["defaults"]["dub_track"], "audio/song.wav.vocals.wav")
        self.assertEqual(doc["defaults"]["master_track"], "audio/song.wav")   # the episode's sound

    def test_a_dub_window_is_cut_from_the_stem_its_own_file_first(self):
        doc = {"defaults": {"master_track": "a/song.wav"}}
        dub = {"audio_policy": "dub", "audio_in": 1.0, "audio_out": 3.0}
        self.assertEqual(HA.recording_slot(doc, dub)[0]["path"], "a/song.wav")
        doc["defaults"]["dub_track"] = "a/song.wav.vocals.wav"
        self.assertEqual(HA.recording_slot(doc, dub)[0]["path"], "a/song.wav.vocals.wav")
        self.assertEqual(HA.dub_recording(doc, dict(dub, audio_file="b/take.wav")), "b/take.wav")


@unittest.skipUnless(HAVE_FF, "the stem is written by ffmpeg")
class JobTest(ApiTest):
    def setUp(self):
        super().setUp()
        self.rec = os.path.join(self.ep, "audio", "song.wav")
        write_wav(self.rec, 0.3)
        self.fb = stem_backend()
        self.runner = Runner(Queue(), {"local": self.fb},
                             emit=lambda e, d: self.events.append((e, d)))

    def test_the_job_writes_the_stem_beside_the_recording(self):
        job = self.runner.enqueue_vocals(self.rec, "local", ep=self.ep)
        self.assertEqual(wait(self.runner.queue, [job], timeout=30)[job], "succeeded")
        self.assertEqual(VOC.fresh(self.rec), VOC.stem_path(self.rec))
        with wave.open(VOC.stem_path(self.rec)) as w:
            self.assertEqual((w.getnchannels(), w.getframerate(), w.getsampwidth()), (2, 44100, 3))
        self.assertEqual(self.fb.submitted[0]["split"]["class_type"], "SeriesmithVocals")
        ev = [d for e, d in self.events if e == "seriesmith.vocals"]
        self.assertEqual((ev[-1]["status"], ev[-1]["ep"]), ("ok", self.ep))

    def test_ensure_makes_it_once(self):
        self.assertEqual(VOC.ensure(self.rec, runner=self.runner, log=None), VOC.stem_path(self.rec))
        self.assertEqual(VOC.ensure(self.rec, runner=self.runner, log=None), VOC.stem_path(self.rec))
        self.assertEqual(len(self.fb.submitted), 1)                # the second read the cache

    def test_a_failed_split_says_why_and_leaves_nothing(self):
        runner = Runner(Queue(), {"local": stem_backend(final="failed", error="CUDA out of memory")})
        with self.assertRaisesRegex(RuntimeError, "out of memory"):
            VOC.ensure(self.rec, runner=runner, log=None)
        self.assertFalse(os.path.exists(VOC.stem_path(self.rec)))

    def test_a_comfyui_without_the_node_is_told_to_restart(self):
        self.fb.has_node = lambda c: False
        with self.assertRaisesRegex(RuntimeError, "restart ComfyUI"):
            VOC.ensure(self.rec, runner=self.runner, log=None)
        self.assertEqual(self.fb.submitted, [])


class RoutesTest(ApiTest):
    def setUp(self):
        super().setUp()
        self.rec = os.path.join(self.ep, "audio", "song.wav")
        write_wav(self.rec, 0.3)
        self.ok(A.post_track(self.ctx, {"ep": self.ep, "source_path": self.rec}))

    def series(self) -> dict:
        return json.load(open(os.path.join(self.ep, "series.json"), encoding="utf-8"))

    def test_the_track_says_whether_a_stem_is_there_and_where_dubs_come_from(self):
        t = E.episode_track(self.ep)
        self.assertEqual((t["vocals"], t["vocals_words"], t["dub_from"]), (False, False, "recording"))
        write_wav(VOC.stem_path(self.rec), 0.3)
        self.assertTrue(E.episode_track(self.ep)["vocals"])

    def test_dub_from_is_written_and_taken_out_again(self):
        data = self.ok(A.post_dub_from(self.ctx, {"ep": self.ep, "dub_from": "vocals"}))
        self.assertEqual(data["track"]["dub_from"], "vocals")
        self.assertEqual(self.series()["audio"]["dub_from"], "vocals")
        self.assertEqual(self.series()["audio"]["mode"], "source_track")
        self.ok(A.post_dub_from(self.ctx, {"ep": self.ep, "dub_from": "recording"}))
        self.assertNotIn("dub_from", self.series()["audio"])     # the default leaves no key
        self.err(A.post_dub_from(self.ctx, {"ep": self.ep, "dub_from": "band"}), 400)

    def test_post_vocals_queues_it_and_answers_a_fresh_one_at_once(self):
        with mock.patch.object(self.ctx.runner, "enqueue_vocals", return_value="q1") as enq:
            self.assertEqual(self.ok(A.post_vocals(self.ctx, {"ep": self.ep}))["job"], "q1")
            enq.assert_called_once()
            write_wav(VOC.stem_path(self.rec), 0.3)
            data = self.ok(A.post_vocals(self.ctx, {"ep": self.ep}))
            self.assertEqual((data["job"], data["stem"]), (None, "song.wav.vocals.wav"))
            self.assertEqual(enq.call_count, 1)
            self.ok(A.post_vocals(self.ctx, {"ep": self.ep, "redo": True}))
            self.assertEqual(enq.call_count, 2)

    def test_align_passes_vocals_and_makes_the_stem_first(self):
        seen = {}

        def fake_stream(cmd, cwd, timeout, on_progress, stop=None):
            seen["cmd"] = cmd
            with open(cmd[cmd.index("--json") + 1], "w", encoding="utf-8") as fh:
                json.dump({"ok": True, "changes": []}, fh)
            return 0, "done"

        made = []

        def fake_ensure(rec, runner=None, backend="local", log=print):
            made.append(rec)
            write_wav(VOC.stem_path(rec), 0.3)
            return VOC.stem_path(rec)

        with mock.patch.object(K, "_stream", fake_stream), \
                mock.patch.object(K, "align_ready", lambda py=None: {"ready": True, "missing": []}), \
                mock.patch.object(VOC, "ensure", fake_ensure):
            self.ok(self.waited(A.post_align(self.ctx, {"ep": self.ep, "dry_run": True})))
            self.assertNotIn("--vocals", seen["cmd"])               # off by default
            self.assertEqual(made, [])
            self.ok(self.waited(A.post_align(self.ctx, {"ep": self.ep, "dry_run": True,
                                                        "vocals": True})))
            self.assertIn("--vocals", seen["cmd"])
            self.assertEqual(made, [os.path.normpath(self.rec)])
            self.ok(self.waited(A.post_align(self.ctx, {"ep": self.ep, "dry_run": True,
                                                        "vocals": True})))
            self.assertEqual(len(made), 1)                          # the stem was there
        self.err(A.post_align(self.ctx, {"ep": self.ep, "vocals": "yes"}), 400)



@unittest.skipUnless(HAVE_FF, "align needs ffmpeg")
class AlignVocalsTest(ApiTest):
    """The real align --vocals, with the stem and its transcript already beside the
    recording (nothing is split or transcribed)."""

    def test_it_hears_the_stem_and_points_the_series_config_at_the_recording(self):
        rec = os.path.join(self.ep, "audio", "song.wav")
        words, seconds = fake_words(script_lines(self.ep))
        write_wav(rec, seconds)
        stem = VOC.stem_path(rec)
        write_wav(stem, seconds)
        with open(E.words_cache(stem), "w", encoding="utf-8") as fh:
            json.dump(words, fh)
        res = K.align(self.ep, track=rec, check_deps=False, vocals=True)
        self.assertTrue(res["vocals"])
        self.assertIn("hearing the vocal stem", res["log"])
        self.assertEqual(res["recording"], "audio/song.wav")
        cfg = json.load(open(os.path.join(self.ep, "series.json"), encoding="utf-8"))
        self.assertEqual(cfg["audio"]["track"], "audio/song.wav")
        self.assertFalse(os.path.exists(E.words_cache(rec)))      # the mix wasn't transcribed


if __name__ == "__main__":
    unittest.main()
