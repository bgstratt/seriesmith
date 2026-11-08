"""The gallery's Sound tab (seriesmith/soundgallery.py): every take of an episode's sound, a
section per cue, place, shot, voice and line, the one in use marked; what a take was made
with, read when it's opened; the routes."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import api as A  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import fx as FX  # noqa: E402
from seriesmith import lines as LN  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import soundgallery as SG  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402


def silent_wav(path: str, seconds: float = 1.0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))


def anchor(shot: str, frame: int = 0) -> dict:
    return {"shot": shot, "frame": frame}


class SoundGalleryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ep01")
        os.makedirs(os.path.join(self.ep, "shotlist"))
        T.write_json(os.path.join(self.ep, "series.json"), {
            "series": {"id": "t", "title": "T"}, "style": {"look": "film"}, "subjects": {},
            "locations": {"diner": {"description": "a diner", "ambience": "room tone of a diner"}}})
        T.write_json(os.path.join(self.ep, "shotlist", "shots.json"), {
            "episode": "ep01", "sequences": [{"id": "sq01", "location": "diner", "shots": [{"id": "sh010"}]}]})
        # a cue with three takes: two finished, one queued; the second in the final mix
        CU.save_spec(self.ep, {"id": "m01", "in": anchor("sh010"), "out": anchor("sh010", 48), "label": "Opening"})
        for n, status in ((1, "ok"), (2, "ok"), (3, "queued")):
            p = CU.take_paths(self.ep, "m01", n)
            sc = {"pass": "final", "target": "stable_audio3", "seed": 100 + n, "status": status,
                  "prompt": {"prompt": f"a warm oud, take {n}"}, "rendered_for": {"bpm": 92, "bars": 2}}
            if status == "ok":
                silent_wav(p["wav"], 2.0)
                sc.update(file=p["rel"], finished="2026-11-08T10:00:00-06:00", measured={"bpm_heard": 91.5, "score": 0.8})
            F.write_json(p["sidecar"], sc)
        # two effects takes for sh010, the first in the mix
        for n in (1, 2):
            p = FX.take_paths(self.ep, "final", "sh010", n)
            silent_wav(p["wav"])
            F.write_json(p["sidecar"], {"pass": "final", "shot": "sh010", "target": "h3_foley", "seed": n,
                                        "prompt": "gravel footsteps", "status": "ok", "take_seconds": 1.0,
                                        "source": {"pass": "final", "take": 1}})
        MX.save(self.ep, {"final": {"items": [{"id": "m01", "track": "music", "path": CU.take_paths(self.ep, "m01", 2)["rel"],
                                               "in": anchor("sh010")}],
                                    "fx": {"sh010": {"take": 1}}}})
        # a line with two takes, the second picked
        LN.save(self.ep, {"lines": {"sh010_l1": {"picked": 2, "takes": [
            {"take": n, "status": "ok", "text": "Coffee's cold.", "voice_name": "Ada", "target": "elevenlabs_tts",
             "file": f"audio/lines/sh010_l1_t{n:02d}.wav", "seconds": 1.0} for n in (1, 2)]}}})
        for n in (1, 2):
            silent_wav(os.path.join(self.ep, "audio", "lines", f"sh010_l1_t{n:02d}.wav"))
        # the diner's bed: one finished take, picked
        s = R.load_series(self.ep)
        ref = R.find_ref(s, "ambience:diner")
        t = R.reserve_take(ref, None, {"status": "ok", "seed": 7, "prompt": "room tone", "finished": "2026-11-08T09:00:00-06:00"}, ext=".wav")
        silent_wav(t.paths.image, 3.0)
        R.save_picks(ref.home, {"version": 1, "refs": {ref.id: {"take": 1}}})

    def tearDown(self):
        self._tmp.cleanup()

    def test_listing(self):
        got = SG.listing(self.ep, "final")
        self.assertEqual(got["errors"], [])
        by = {(s["kind"], s["id"]): s for s in got["sections"]}
        self.assertEqual(list(by), [("music", "m01"), ("ambience", "ambience:diner"), ("effects", "sh010"), ("lines", "sh010_l1")])
        m = by[("music", "m01")]
        # finished takes only, newest first; the queued one counted; the mix's marked
        self.assertEqual([(i["take"], i["use"]) for i in m["items"]], [(2, True), (1, False)])
        self.assertEqual((m["name"], m["queued"], m["failed"]), ("Opening (m01)", 1, 0))
        self.assertEqual(m["items"][0]["path"], "sound/m01/t02.wav")
        self.assertAlmostEqual(m["items"][0]["seconds"], 2.0, places=2)
        self.assertEqual([(i["take"], i["use"]) for i in by[("effects", "sh010")]["items"]], [(2, False), (1, True)])
        lines = by[("lines", "sh010_l1")]
        self.assertEqual([(i["take"], i["use"], i["text"], i["who"]) for i in lines["items"]],
                         [(2, True, "Coffee's cold.", "Ada"), (1, False, "Coffee's cold.", "Ada")])
        amb = by[("ambience", "ambience:diner")]["items"]
        self.assertEqual([(i["take"], i["use"]) for i in amb], [(1, True)])
        self.assertTrue(amb[0]["path"].endswith(".wav"))
        # the proxy pass has no mix: nothing in it, the same takes otherwise (its own effects: none)
        proxy = {(s["kind"], s["id"]): s for s in SG.listing(self.ep, "proxy")["sections"]}
        self.assertFalse(any(i["use"] for i in proxy[("music", "m01")]["items"]))
        self.assertNotIn(("effects", "sh010"), proxy)

    def test_a_theme_says_so(self):
        cfg = T.read_json(os.path.join(self.ep, "series.json"))
        cfg["sound"] = {"themes": {"opening": {"ep": "ep01", "cue": "m01", "take": 1}}}
        T.write_json(os.path.join(self.ep, "series.json"), cfg)
        m = next(s for s in SG.listing(self.ep, "final")["sections"] if s["id"] == "m01")
        self.assertEqual({i["take"]: i["theme"] for i in m["items"]}, {2: None, 1: "opening"})

    def test_take_detail(self):
        d = SG.take_detail(self.ep, "final", "music", "m01", 2)
        self.assertEqual(d["prompt"], "a warm oud, take 2")
        rows = dict(d["rows"])
        self.assertEqual((rows["Model"], rows["Seed"], rows["Asked"], rows["Heard"]),
                         ("stable_audio3", "102", "92 BPM, 2 bars", "91.5 BPM"))
        d = SG.take_detail(self.ep, "final", "effects", "sh010", 1)
        self.assertEqual((d["prompt"], dict(d["rows"])["Made from"]), ("gravel footsteps", "sh010 t01 (final)"))
        self.assertEqual(SG.take_detail(self.ep, "final", "lines", "sh010_l1", 1)["prompt"], "Coffee's cold.")
        self.assertEqual(SG.take_detail(self.ep, "final", "ambience", "ambience:diner", 1)["prompt"], "room tone")
        with self.assertRaises(KeyError):
            SG.take_detail(self.ep, "final", "music", "m01", 9)

    def test_routes(self):
        ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={})
        A.put_config(ctx, {"roots": [self.shows]})
        code, got = A.get_sound_gallery(ctx, {"ep": self.ep, "pass": "final"})
        self.assertEqual((code, len(got["sections"])), (200, 4))
        code, d = A.get_sound_gallery_take(ctx, {"ep": self.ep, "pass": "final", "kind": "music", "id": "m01", "take": "1"})
        self.assertEqual((code, d["prompt"]), (200, "a warm oud, take 1"))
        code, _ = A.get_sound_gallery_take(ctx, {"ep": self.ep, "pass": "final", "kind": "music", "id": "m01", "take": "9"})
        self.assertEqual(code, 404)
        code, _ = A.get_sound_gallery_take(ctx, {"ep": self.ep, "pass": "final", "kind": "video", "id": "m01", "take": "1"})
        self.assertEqual(code, 400)
        # the takes play and download through /seriesmith/file
        for s in got["sections"]:
            code, f = A.get_file(ctx, {"ep": self.ep, "path": s["items"][0]["path"]})
            self.assertEqual(code, 200, (s["kind"], f))


if __name__ == "__main__":
    unittest.main()
