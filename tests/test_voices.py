"""
A take's voice stem and the mix's voices only (seriesmith/voices.py, docs/SOUND.md "Voices
only"): mix.json's `voices_only` and `voices`, a stem's state (missing, ok, stale, queued,
failed), what the Dialogue track plays for a clip (its stem, its whole sound, or silence for a
shot with no lines), the job on the queue (a fake backend plays the split), the routes, and
assemble's mix, stems, XML and speech curve with it on and off.

Nothing here runs Demucs: the node is the vocal stem's (test_vocals.py), measured live on
Ballroom ep02 (docs/SOUND.md).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import voices as VO  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner, wait  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FPS = 24
ON = {"tracks": {"dialogue": {"voices_only": True}}}


class MixTest(unittest.TestCase):
    def test_check(self):
        mix = MX.check({"tracks": {"dialogue": {"voices_only": True, "gain_db": -2}},
                        "voices": {"sh010": {"voices_only": False}, "sh020": {"voices_only": True}}})
        self.assertEqual(mix, {"tracks": {"dialogue": {"gain_db": -2.0, "voices_only": True}},
                               "voices": {"sh010": {"voices_only": False}, "sh020": {"voices_only": True}}})
        self.assertEqual(MX.check({"tracks": {"dialogue": {"voices_only": False}}}),
                         {"tracks": {"dialogue": {"voices_only": False}}})     # kept as given
        for bad, says in (({"tracks": {"music": {"voices_only": True}}}, "dialogue track's"),
                          ({"tracks": {"dialogue": {"voices_only": "yes"}}}, "true or false"),
                          ({"voices": {"sh010": {"voices_only": 1}}}, "true or false"),
                          ({"voices": {"sh010": {}}}, "true or false"),
                          ({"voices": {"sh010": {"whole": True}}}, "take voices_only"),
                          ({"voices": {"a b": {"voices_only": True}}}, "named by its id"),
                          ({"voices": ["sh010"]}, "")):
            with self.assertRaisesRegex((ValueError, AttributeError), says):
                MX.check(bad)

    def test_a_dialogue_track_of_its_own_has_no_voices_only(self):
        tl = [{"id": "dialogue", "kind": "dialogue"}, {"id": "adr", "kind": "dialogue"}]
        with self.assertRaisesRegex(ValueError, "not adr's"):
            MX.check({"track_list": tl, "tracks": {"adr": {"voices_only": True}}})

    def test_resolution_and_active(self):
        self.assertFalse(MX.voices_only({}))
        self.assertFalse(MX.active({"tracks": {"dialogue": {"voices_only": False}}}))
        self.assertTrue(MX.active(ON))
        self.assertTrue(MX.voices_only(ON, "sh010"))
        mix = {**ON, "voices": {"sh010": {"voices_only": False}}}
        self.assertFalse(MX.voices_only(mix, "sh010"))
        self.assertTrue(MX.voices_only(mix, "sh020"))
        one = {"voices": {"sh030": {"voices_only": True}}}               # a shot alone
        self.assertTrue(MX.active(one) and MX.voices_any(one) and MX.voices_only(one, "sh030"))
        self.assertFalse(MX.voices_only(one, "sh010"))

    def test_plays(self):
        self.assertEqual(VO.plays(False, None, "ok", True), "whole")
        self.assertEqual(VO.plays(True, None, "ok", True), "voice")
        self.assertEqual(VO.plays(True, None, "stale", True), "whole")       # never silence
        self.assertEqual(VO.plays(True, None, "missing", True), "whole")
        self.assertEqual(VO.plays(True, None, "ok", False), "silence")       # no lines
        self.assertEqual(VO.plays(True, None, "missing", False), "silence")
        self.assertEqual(VO.plays(True, True, "ok", False), "voice")         # asked of the shot
        self.assertEqual(VO.plays(True, True, "missing", False), "whole")
        self.assertEqual(VO.plays(True, None, "sourced", True), "whole")
        self.assertEqual(VO.plays(True, None, "silent", False), "whole")


def ff(*args) -> None:
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", *args], capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


def tone(path: str, seconds: float, hz: int, amp: float = 0.3) -> None:
    ff("-f", "lavfi", "-i", f"sine=frequency={hz}:sample_rate=48000:duration={seconds}",
       "-af", f"volume={amp}", "-ac", "2", "-c:a", "pcm_s16le", path)


def clip(path: str, frames: int, sound: str | None) -> None:
    """A testsrc clip of exactly `frames` frames with `sound` (a wav) under it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    args = ["-f", "lavfi", "-i", f"testsrc=size=64x64:rate={FPS}"]
    args += ["-i", sound, "-c:a", "aac", "-b:a", "192k"] if sound else ["-an"]
    ff(*args, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path)


def episode(root: str, tmp: str, frames: int = 24) -> dict[str, T.Take]:
    """Three one-second shots, each take's sound a 300 Hz tone (its "music"); sh010 and
    sh020 have lines, sh030 none."""
    T.write_json(os.path.join(root, "shotlist", "shotlist.json"),
                 {"episode": "ep01", "defaults": {"width": 64, "height": 64, "fps": FPS},
                  "shots": [{"id": s, "length": frames, "audio_policy": "generate"}
                            for s in ("sh010", "sh020", "sh030")]})
    T.write_json(os.path.join(root, "shotlist", "shots.json"), {"episode": "ep01", "sequences": [
        {"id": "sq01", "location": "park", "shots": [
            {"id": "sh010", "dialogue": [{"speaker": "a", "line": "King me."}]},
            {"id": "sh020", "dialogue": [{"speaker": "b", "line": "Lucky."}]},
            {"id": "sh030", "dialogue": []}]}]})
    whole = os.path.join(tmp, "whole.wav")
    tone(whole, frames / FPS, 300)
    src = os.path.join(tmp, "src.mp4")
    clip(src, frames, whole)
    takes = {}
    for s in ("sh010", "sh020", "sh030"):
        t = T.reserve_take(root, "final", s, {"status": "queued"})
        shutil.copy(src, t.paths.mp4)
        T.update_sidecar(t.paths.sidecar, status="ok", frames=frames, fps=FPS)
        takes[s] = T.get_take(root, "final", s, t.take)
    return takes


def split(take: T.Take, hz: int = 1000, seconds: float = 1.0) -> None:
    """A finished voice stem for `take`: a `hz` tone (its "voice"), as the job leaves it."""
    tone(take.paths.voice, seconds, hz, amp=0.2)
    VO.update(take, status="ok", source=VO.signature(VO.source_file(take)), finished=T.now())


def rms(buf, a: float, b: float) -> float:
    np = MX._np()
    seg = buf[int(a * MX.RATE): int(b * MX.RATE)]
    return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))


def band(buf, a: float, b: float, hz: int) -> float:
    """How much of `buf` from a to b seconds is near `hz` (dB of its spectrum's peak there)."""
    np = MX._np()
    seg = buf[int(a * MX.RATE): int(b * MX.RATE)].mean(1)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / MX.RATE)
    near = spec[(f > hz * 0.9) & (f < hz * 1.1)]
    return float(20 * np.log10(near.max() / len(seg) + 1e-12))


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        self.takes = episode(self.root, self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_ok_stale_queued_failed(self):
        t = self.takes["sh010"]
        self.assertEqual(t.paths.voice, os.path.join(t.paths.dir, "sh010_t01.voice.wav"))
        self.assertEqual(VO.state(t), ("missing", "t01 hasn't been split"))
        split(t)
        self.assertEqual(VO.state(t), ("ok", None))
        now = time.time() + 5
        os.utime(t.paths.mp4, (now, now))                                    # rendered again
        self.assertEqual(VO.state(t), ("stale", "t01 was rendered again since it was split"))
        VO.update(t, status="queued", queue_id="q1")
        self.assertEqual(VO.state(t)[0], "queued")
        self.assertEqual(VO.state(t, alive=lambda q: q == "q1")[0], "queued")
        self.assertEqual(VO.state(t, alive=lambda q: False)[0], "missing")  # its job is gone
        VO.update(t, status="failed", error="CUDA out of memory")
        self.assertEqual(VO.state(t), ("failed", "CUDA out of memory"))
        self.assertEqual(VO.state(None)[0], "missing")

    def test_shots_say_what_plays(self):
        split(self.takes["sh010"])
        split(self.takes["sh030"])
        mix = {**ON, "voices": {"sh020": {"voices_only": True}}}
        rows = {r["shot"]: r for r in VO.shots(self.root, "final", mix)}
        self.assertEqual([(r["state"], r["plays"], r["lines"], r["override"]) for r in rows.values()],
                         [("ok", "voice", True, None), ("missing", "whole", True, True),
                          ("ok", "silence", False, None)])
        self.assertEqual(rows["sh010"]["path"], "renders/sh010/sh010_t01.voice.wav")
        s = VO.summary(list(rows.values()), mix)
        self.assertEqual((s["voices_only"], s["split"], s["of"], s["queued"]), (True, 2, 3, 0))
        off = {r["shot"]: r["plays"] for r in VO.shots(self.root, "final", {})}
        self.assertEqual(set(off.values()), {"whole"})
        # a shot the cut gives sound of its own keeps it
        T.save_cut(self.root, {"final": [{"shot": "sh010", "audio": {"source": "none"}},
                                         {"shot": "sh020"}, {"shot": "sh030"}]})
        rows = {r["shot"]: r for r in VO.shots(self.root, "final", mix)}
        self.assertEqual((rows["sh010"]["state"], rows["sh010"]["plays"]), ("sourced", "whole"))

    def test_on_layout_hears_the_stems(self):
        split(self.takes["sh010"])
        lay = [{"id": s, "trim_in": 0, "used": 24, "dissolve_in": 0, "sound": self.takes[s].paths.mp4,
                "sound_start": 0.0} for s in ("sh010", "sh020", "sh030")]
        self.assertIs(VO.on_layout(self.root, "final", lay, {}), lay)
        got = VO.on_layout(self.root, "final", lay, ON)
        self.assertEqual([os.path.basename(x["sound"] or "-") for x in got],
                         ["sh010_t01.voice.wav", "sh020_t01.mp4", "-"])

    def test_queue_skips_what_is_made(self):
        class R:
            def __init__(self):
                self.asked = []

            def enqueue_voice(self, root, pass_, shot, take, backend):
                self.asked.append((shot, take.take, backend))
                return f"job-{shot}"
        split(self.takes["sh010"])
        r = R()
        queued, skipped = VO.queue(r, self.root, "final")
        self.assertEqual([q["shot"] for q in queued], ["sh020", "sh030"])
        self.assertEqual(skipped, [{"shot": "sh010", "why": "its voice stem is made"}])
        queued, _ = VO.queue(r, self.root, "final", ["sh010", "sh999"], redo=True)
        self.assertEqual([q["shot"] for q in queued], ["sh010"])


def wav_bytes(seconds: float = 1.0, rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x10\x00" * 2 * int(seconds * rate))
    return buf.getvalue()


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class JobTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        self.takes = episode(self.root, self._tmp.name)
        self.events = []

    def tearDown(self):
        self._tmp.cleanup()

    def runner(self, **kw) -> tuple[Runner, FakeBackend]:
        fb = FakeBackend("local", "local", outputs={"save": [("vocals_00001_.flac", "audio", wav_bytes())]}, **kw)
        return Runner(Queue(), {"local": fb}, emit=lambda e, d: self.events.append((e, d))), fb

    def test_the_job_splits_the_take_and_keeps_it_beside(self):
        runner, fb = self.runner()
        t = self.takes["sh020"]
        job = runner.enqueue_voice(self.root, "final", "sh020", t, "local")
        self.assertEqual(VO.record(t)["status"], "queued")
        self.assertEqual(wait(runner.queue, [job], timeout=60)[job], "succeeded")
        self.assertEqual(VO.state(t), ("ok", None))
        rec = VO.record(t)
        self.assertEqual(rec["source"]["file"], "sh020_t01.mp4")
        self.assertLess(rec["measured"]["voice_rms_db"], rec["measured"]["whole_rms_db"])
        self.assertEqual(fb.submitted[0]["split"]["class_type"], "SeriesmithVocals")
        sent = fb.uploaded[0]
        self.assertTrue(sent.endswith(".wav") and not os.path.exists(sent))   # staged, then removed
        with wave.open(t.paths.voice) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth()), (2, 3))
        ev = [d for e, d in self.events if e == "seriesmith.voice"]
        self.assertEqual((ev[-1]["shot"], ev[-1]["status"]), ("sh020", "ok"))
        self.assertTrue(any(e == "seriesmith.episode" for e, _ in self.events))

    def test_a_failed_split_is_recorded(self):
        runner, _ = self.runner(final="failed", error="CUDA out of memory")
        t = self.takes["sh010"]
        job = runner.enqueue_voice(self.root, "final", "sh010", t, "local")
        self.assertEqual(wait(runner.queue, [job], timeout=60)[job], "failed")
        self.assertEqual(VO.state(t), ("failed", "CUDA out of memory"))
        self.assertFalse(os.path.exists(t.paths.voice))


class _Runner:
    def __init__(self):
        self.asked = []

    def enqueue_voice(self, root, pass_, shot, take, backend):
        self.asked.append((shot, take.take, backend))
        return f"job{shot}"


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class RouteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ep01")
        os.makedirs(self.ep)
        self.takes = episode(self.ep, self._tmp.name)
        self.ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={},
                             runner=_Runner())
        self.call(A.put_config, {"roots": [self.shows]})

    def tearDown(self):
        self._tmp.cleanup()

    def call(self, fn, arg, status=200):
        code, data = fn(self.ctx, arg)
        self.assertEqual(code, status, data)
        return data

    def test_make_and_report(self):
        split(self.takes["sh010"])
        r = self.call(A.post_voices, {"ep": self.ep, "pass": "final"})
        self.assertEqual([q["shot"] for q in r["queued"]], ["sh020", "sh030"])
        self.assertEqual(self.ctx.runner.asked, [("sh020", 1, "local"), ("sh030", 1, "local")])
        r = self.call(A.post_voices, {"ep": self.ep, "pass": "final", "shots": ["sh010"], "redo": True})
        self.assertEqual([q["shot"] for q in r["queued"]], ["sh010"])
        self.call(A.post_voices, {"ep": self.ep, "pass": "final", "shots": "sh010"}, 400)
        self.call(A.post_voices, {"ep": self.ep, "pass": "final", "redo": "yes"}, 400)
        got = self.call(A.get_mix, {"ep": self.ep, "pass": "final"})["voices"]
        self.assertEqual((got["voices_only"], got["of"]), (False, 3))
        self.assertEqual([s["plays"] for s in got["shots"]], ["whole"] * 3)
        self.call(A.put_mix, {"ep": self.ep, "pass": "final", "mix": {**ON, "voices": {"sh010": {"voices_only": False}}}})
        got = self.call(A.get_mix, {"ep": self.ep, "pass": "final"})["voices"]
        self.assertTrue(got["voices_only"])
        self.assertEqual([(s["shot"], s["override"], s["plays"]) for s in got["shots"]],
                         [("sh010", False, "whole"), ("sh020", None, "whole"), ("sh030", None, "silence")])
        self.call(A.put_mix, {"ep": self.ep, "pass": "final", "mix": {"tracks": {"music": {"voices_only": True}}}}, 400)
        self.call(A.put_mix, {"ep": self.ep, "pass": "final", "mix": {"voices": {"sh010": True}}}, 400)

    def test_the_speech_curve_hears_the_stems(self):
        split(self.takes["sh010"])
        base = self.call(A.get_mix_duck, {"ep": self.ep, "pass": "final"})["curve"]
        self.call(A.put_mix, {"ep": self.ep, "pass": "final", "mix": ON})
        on = self.call(A.get_mix_duck, {"ep": self.ep, "pass": "final"})["curve"]
        self.assertGreater(min(base[56:59]), 0.5)                         # sh030's tone: speech
        self.assertLess(max(on[56:59]), 0.25)                             # silent: no lines (released)


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class AssembleTest(unittest.TestCase):
    """Three one-second clips whose sound is a 300 Hz tone; sh010's stem a 1 kHz tone."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        self.takes = episode(self.root, self._tmp.name)
        split(self.takes["sh010"])
        self.stems = os.path.join(self.root, "renders", "ep01_stems")

    def tearDown(self):
        self._tmp.cleanup()

    def assemble(self, *args):
        r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", self.root, *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_off_is_the_whole_sound_and_no_mix(self):
        MX.save(self.root, {"final": {"tracks": {"dialogue": {"voices_only": False}}}})
        out = self.assemble()
        self.assertNotIn("voices only", out)
        self.assertFalse(os.path.isdir(self.stems))                       # no mix: the cut as it was

    def test_on_plays_the_stem_whole_where_it_cant_and_silence_without_lines(self):
        MX.save(self.root, {"final": ON})
        out = self.assemble()
        self.assertIn("voices only: 1 of 3 shot(s) play their voice stem, 1 with no lines silent (sh030)", out)
        self.assertIn("sh020's voice stem is missing", out)
        dia = MX.decode(os.path.join(self.stems, "dialogue.wav"))
        self.assertGreater(band(dia, 0.1, 0.9, 1000), band(dia, 0.1, 0.9, 300) + 30)   # sh010: the voice
        self.assertGreater(band(dia, 1.1, 1.9, 300), band(dia, 1.1, 1.9, 1000) + 30)   # sh020: whole
        self.assertLess(rms(dia, 2.1, 2.9), -60)                                        # sh030: silent (but the AAC's bleed)
        # a shot set to keep its whole sound, and the one with no lines asked for its voice
        split(self.takes["sh030"])
        MX.save(self.root, {"final": {**ON, "voices": {"sh010": {"voices_only": False},
                                                       "sh030": {"voices_only": True}}}})
        self.assemble()
        dia = MX.decode(os.path.join(self.stems, "dialogue.wav"))
        self.assertGreater(band(dia, 0.1, 0.9, 300), band(dia, 0.1, 0.9, 1000) + 30)
        self.assertGreater(band(dia, 2.1, 2.9, 1000), band(dia, 2.1, 2.9, 300) + 30)

    def test_stale_plays_whole(self):
        MX.save(self.root, {"final": ON})
        now = time.time() + 5
        os.utime(self.takes["sh010"].paths.mp4, (now, now))
        out = self.assemble()
        self.assertIn("sh010's voice stem is stale", out)
        dia = MX.decode(os.path.join(self.stems, "dialogue.wav"))
        self.assertGreater(band(dia, 0.1, 0.9, 300), band(dia, 0.1, 0.9, 1000) + 30)

    def test_xml_lays_the_stem(self):
        MX.save(self.root, {"final": ON})
        self.assemble("--xml")
        xml = open(os.path.join(self.root, "renders", "ep01.xml"), encoding="utf-8").read()
        self.assertIn("sh010_t01.voice.wav", xml)
        self.assertIn("sh020_t01.mp4", xml)
        MX.save(self.root, {"final": {}})
        self.assemble("--xml")
        xml = open(os.path.join(self.root, "renders", "ep01.xml"), encoding="utf-8").read()
        self.assertNotIn("voice.wav", xml)


if __name__ == "__main__":
    unittest.main()
