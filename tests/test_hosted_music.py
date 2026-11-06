"""Music on a provider of the user's own: Suno on Atlas, Eleven Music on ElevenLabs. Songs and score
as one call, what that call sends, and a second track kept as a take. Nothing paid: a local server."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from seriesmith import api as A  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import providers as PR  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends.http import HttpBackend, planned_calls  # noqa: E402
from seriesmith.backends.router import ROUTING  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
from test_cue import _Runner, anchor, episode  # noqa: E402
from test_finish_queue import wait_for  # noqa: E402
from test_providers import KEY, Fake  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
SONG = {"kind": "song", "sections": [{"name": "verse", "bars": 8, "lyrics": "porch light on\nleave it on"},
                                     {"name": "chorus", "bars": 8, "lyrics": "come on home"}]}


def wav_bytes(folder: str, name: str, hz: float) -> bytes:
    path = os.path.join(folder, name)
    t = np.arange(int(4 * MX.RATE)) / MX.RATE
    tone = (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    MX.write_wav(path, np.stack([tone, tone], axis=1))
    with open(path, "rb") as fh:
        return fh.read()


def shipped(name: str, base: str) -> dict:
    with open(os.path.join(os.path.dirname(PR.__file__), "presets", "providers", f"{name}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    d["base_url"] = base
    for step in d["steps"]:
        if step.get("until"):
            step["until"]["every"] = 0.01
    return d


class WithEpisode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "Shows", "ep01")
        os.makedirs(self.root)
        episode(self.root)

    def spec(self, **kw):
        return CU.check_spec({"id": "m01", "in": anchor("sh010"), "out": anchor("sh030", 120), "bpm": 92, **kw})

    def call(self, tid, **kw):
        target = TG.load_target(tid)
        p = CU.plan(self.root, "final", self.spec(model=tid, **kw), {})
        self.assertFalse(p.get("blocked"))
        model, args = CU.hosted_call(target, p, 2 ** 40 + 3)
        return p, model, args


class TheCall(WithEpisode):
    def test_suno_score_is_instrumental_with_its_description_as_the_style(self):
        p, model, args = self.call("suno_chirp_v6")
        self.assertEqual(model, "suno/chirp-v6")
        self.assertIs(args["custom"], True)
        self.assertIs(args["instrumental"], True)
        self.assertEqual(args["style"], p["prompt"]["prompt"])
        self.assertIn("92 BPM", args["style"].replace(str(int(p["fit"]["ask_bpm"])), "92"))
        self.assertNotIn("prompt", args)                 # lyrics, and a score has none
        self.assertNotIn("seed", args)                   # it takes none
        self.assertEqual(args[ROUTING]["values"], {"endpoint": "generateAudio", "type": "audio"})

    def test_suno_song_sends_its_lyrics_under_their_tags(self):
        _, _, args = self.call("suno_chirp_v6", **SONG)
        self.assertEqual(args["prompt"], "[Verse]\nporch light on\nleave it on\n\n[Chorus]\ncome on home")
        self.assertNotIn("instrumental", args)

    def test_suno_length_is_whole_seconds_in_its_range(self):
        p, _, args = self.call("suno_chirp_v6")
        self.assertTrue(10 <= args["duration"] <= 360)
        self.assertGreaterEqual(args["duration"], p["ask_seconds"])

    def test_eleven_score_forces_instrumental_with_a_length_in_milliseconds(self):
        p, model, args = self.call("elevenlabs_music")
        self.assertEqual(model, "music_v2_5")
        self.assertIs(args["force_instrumental"], True)
        self.assertEqual(args["prompt"], p["prompt"]["prompt"])
        self.assertEqual(args["music_length_ms"] % 1000, 0)
        self.assertGreaterEqual(args["music_length_ms"], p["ask_seconds"] * 1000)
        self.assertNotIn("seed", args)                   # its API refuses one with a prompt
        self.assertEqual(args[ROUTING]["values"]["use"], "music")

    def test_eleven_song_has_its_lyrics_in_the_prompt(self):
        _, _, args = self.call("elevenlabs_music", **SONG)
        self.assertNotIn("force_instrumental", args)
        self.assertIn("Lyrics:\n[Verse]\nporch light on", args["prompt"])

    def test_a_song_with_no_lyrics_is_stopped_before_anything_is_paid(self):
        for tid in ("suno_chirp_v6", "elevenlabs_music"):
            p = CU.plan(self.root, "final", self.spec(model=tid, kind="song", sections=[{"name": "verse", "bars": 8}]), {})
            self.assertIn("sings words", p["blocked"])

    def test_pika_is_unchanged_with_no_routing_of_its_own(self):
        _, _, args = self.call("pika_music")
        self.assertNotIn(ROUTING, args)
        self.assertNotIn("instrumental", args)

    def test_they_are_on_their_providers_and_offered_for_songs(self):
        for tid, service in (("suno_chirp_v6", "atlas"), ("elevenlabs_music", "elevenlabs")):
            t = TG.load_target(tid)
            self.assertEqual((t.kind, t.backends, TG.service_of(t.spec)), ("music", ["api"], service))
            self.assertTrue(t.capabilities()["lyrics"])
            self.assertFalse(t.draft)
        self.assertIn("licence unverified", TG.load_target("suno_chirp_v6").label)


class TheRequest(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.addCleanup(self.fake.close)

    def test_eleven_music_posts_to_its_own_address_and_the_answer_is_the_file(self):
        self.fake.routes[("POST", "/v1/music")] = (200, b"mp3 bytes", {"Content-Type": "audio/mpeg"})
        b = HttpBackend(shipped("elevenlabs", self.fake.url), KEY)
        run = b.call("music_v2_5", {"prompt": "strings", "music_length_ms": 30000, "force_instrumental": True,
                                    ROUTING: {"values": {"use": "music", "type": "audio"}}})
        self.assertEqual(run.watch(), "succeeded")
        (out,) = run.outputs()
        self.assertEqual(out.type, "audio")
        sent = self.fake.calls[0]
        self.assertEqual(sent["headers"]["xi-api-key"], KEY)
        self.assertEqual(json.loads(sent["body"]), {"model_id": "music_v2_5", "prompt": "strings",
                                                    "music_length_ms": 30000, "force_instrumental": True})

    def test_a_voice_still_goes_where_it_went(self):
        d = shipped("elevenlabs", self.fake.url)
        calls = planned_calls(d, "eleven_v3", {"text": "Hi.", ROUTING: {"values": {"voice": "v1"}}})
        self.assertIn("/v1/text-to-speech/v1", json.dumps(calls))

    def test_the_panel_shows_the_music_address(self):
        d = shipped("elevenlabs", self.fake.url)
        calls = planned_calls(d, "music_v2_5", {"prompt": "x", ROUTING: {"values": {"use": "music"}}})
        self.assertIn("/v1/music", json.dumps(calls))
        self.assertNotIn("text-to-speech", json.dumps(calls))

    def test_suno_comes_back_as_two_audio_files(self):
        f = self.fake
        f.routes[("POST", "/model/generateAudio")] = {"data": {"id": "p1"}}
        f.routes[("GET", "/model/prediction/p1")] = {"data": {"status": "completed", "outputs": [f.url + "/a.mp3", f.url + "/b.mp3"]}}
        run = HttpBackend(shipped("atlas", f.url), KEY).call("suno/chirp-v6", {
            "custom": True, "style": "strings", "instrumental": True, ROUTING: {"values": {"endpoint": "generateAudio", "type": "audio"}}})
        self.assertEqual(run.watch(), "succeeded")
        self.assertEqual([o.type for o in run.outputs()], ["audio", "audio"])
        self.assertEqual(json.loads(f.calls[0]["body"])["model"], "suno/chirp-v6")


class TheRoute(WithEpisode):
    def setUp(self):
        super().setUp()
        self.ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={}, runner=_Runner())
        code, _ = A.put_config(self.ctx, {"roots": [os.path.dirname(self.root)]})
        self.assertEqual(code, 200)

    def do(self, fn, arg, status=200):
        code, data = fn(self.ctx, arg)
        self.assertEqual(code, status, data)
        return data

    def render(self, model):
        self.do(A.put_cue, {"ep": self.root, "cue": {"id": "m01", "in": anchor("sh010"), "out": anchor("sh020", 60),
                                                     "bpm": 92, "model": model}})
        return {"ep": self.root, "pass": "final", "cue": "m01", "takes": 1, "backend": "local"}

    def test_no_key_says_whose_and_nothing_is_reserved(self):
        for model, who in (("suno_chirp_v6", "Atlas Cloud"), ("elevenlabs_music", "ElevenLabs")):
            err = self.do(A.post_cue_render, self.render(model), 409)["error"]
            self.assertIn(who, err)
            self.assertIn("key", err)
        self.assertEqual(self.ctx.runner.asked, [])
        self.assertEqual(CU.list_takes(self.root, "m01"), [])

    def test_a_take_is_a_call_on_its_provider_whatever_the_body_asked(self):
        self.ctx.runner.backends.add("api:atlas")
        self.do(A.post_cue_render, self.render("suno_chirp_v6"))
        self.assertEqual([(g, b) for _, _, g, b in self.ctx.runner.asked], [(None, "api:atlas")])
        self.assertEqual(self.ctx.runner.calls[0][0], "suno/chirp-v6")
        self.assertEqual(self.ctx.runner.tracks, 2)

    def test_a_model_of_one_track_asks_for_one(self):
        self.ctx.runner.backends.add("api:elevenlabs")
        self.do(A.post_cue_render, self.render("elevenlabs_music"))
        self.assertEqual(self.ctx.runner.tracks, 1)


@unittest.skipUnless(HAVE_FF, "ffmpeg isn't installed")
class BothTracks(WithEpisode):
    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        f = self.fake
        f.routes[("POST", "/model/generateAudio")] = {"data": {"id": "p1"}}
        f.routes[("GET", "/model/prediction/p1")] = {
            "data": {"status": "completed", "outputs": [f.url + "/a.wav", f.url + "/b.wav"]}}
        f.routes[("GET", "/a.wav")] = wav_bytes(self._tmp.name, "a.wav", 330.0)
        f.routes[("GET", "/b.wav")] = wav_bytes(self._tmp.name, "b.wav", 440.0)
        self.events = []
        self.backend = HttpBackend(shipped("atlas", f.url), KEY)
        self.runner = Runner(Queue(), {self.backend.name: self.backend}, emit=lambda e, d: self.events.append((e, d)))

    def run_one(self):
        target = TG.load_target("suno_chirp_v6")
        spec = CU.check_spec({"id": "m01", "in": anchor("sh010"), "out": anchor("sh020", 60), "bpm": 92, "model": target.id})
        CU.save_spec(self.root, spec)
        p = CU.plan(self.root, "final", spec, {})
        n = CU.reserve(self.root, "m01", {"pass": "final", "target": target.id, "seed": 5,
                                          "prompt": p["prompt"], "rendered_for": CU.fingerprint(p)})
        q = self.runner.enqueue_cue(self.root, "m01", n, None, p, self.backend.name,
                                    call=CU.hosted_call(target, p, 5), tracks=2)
        job = self.runner.queue.jobs[q]
        wait_for(lambda: job.status in ("succeeded", "failed", "canceled"), timeout=60.0)
        return job

    def test_each_track_is_a_take(self):
        job = self.run_one()
        self.assertEqual(job.status, "succeeded", (job.error, job.log))
        takes = {t["take"]: t for t in CU.list_takes(self.root, "m01")}
        self.assertEqual(sorted(takes), [1, 2])
        self.assertEqual([takes[1]["status"], takes[2]["status"]], ["ok", "ok"])
        self.assertEqual((takes[2]["track"], takes[2]["track_of"], takes[2]["target"]), (2, 1, "suno_chirp_v6"))
        self.assertEqual(takes[2]["rendered_for"], takes[1]["rendered_for"])
        for n in (1, 2):
            self.assertTrue(os.path.isfile(CU.take_paths(self.root, "m01", n)["wav"]))
        self.assertIn(("seriesmith.cue", 2), [(e, d.get("take")) for e, d in self.events])

    def test_a_paid_call_counts_once_for_both(self):
        self.run_one()
        self.assertEqual(len([c for c in self.fake.calls if c["method"] == "POST"]), 1)

    def test_a_second_track_that_fails_leaves_the_first(self):
        self.fake.routes[("GET", "/b.wav")] = b"not audio"
        job = self.run_one()
        self.assertEqual(job.status, "succeeded", (job.error, job.log))
        takes = {t["take"]: t for t in CU.list_takes(self.root, "m01")}
        self.assertEqual((takes[1]["status"], takes[2]["status"]), ("ok", "failed"))
        self.assertIn("track 2 wasn't kept", "\n".join(str(x) for x in job.log))


if __name__ == "__main__":
    unittest.main()
