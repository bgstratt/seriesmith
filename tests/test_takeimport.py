"""
Takes from outside (seriesmith/takeimport.py; docs/API.md "Takes from
outside"): POST /seriesmith/take/import (a video on disk or uploaded: an H.264
mp4 copied, anything else converted) and POST /seriesmith/take/copy (another
shot's take), on the built kitchen_sink episode. Small test videos are made
with ffmpeg.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import takeimport as TI  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402


def tearDownModule():
    test_api.tearDownModule()


def make_video(path: str, *codec: str, seconds: float = 1.0, audio: bool = True) -> str:
    """A small test pattern (24 fps, 320x180), with a tone if `audio`."""
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
           f"testsrc=size=320x180:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    subprocess.run(cmd + list(codec) + ["-shortest", path], check=True, capture_output=True)
    return path


def read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class TakeImportTest(ApiTest):
    def setUp(self):
        super().setUp()
        self.h264 = make_video(os.path.join(self.tmp, "clip.mp4"), "-c:v", "libx264",
                               "-pix_fmt", "yuv420p", "-c:a", "aac")
        self.shots = E_order(self.ep)

    def imp(self, status=200, **body):
        res = A.post_take_import(self.ctx, dict({"ep": self.ep, "shot": self.shots[1]}, **body))
        return self.ok(res) if status == 200 else self.err(res, status)

    def test_an_h264_mp4_is_copied_as_it_is(self):
        got = self.imp(source_path=self.h264, note="from the phone")
        t = T.get_take(self.ep, "proxy", self.shots[1], got["take"])
        self.assertEqual(read(t.paths.mp4), read(self.h264))
        sc = t.sidecar
        self.assertEqual((sc["status"], sc["source"], sc["source_path"], sc["converted"]),
                         ("ok", "imported", self.h264, False))
        self.assertEqual((sc["frames"], sc["fps"], sc["width"], sc["height"]), (24, 24.0, 320, 180))
        self.assertIsNone(sc["seed"])
        self.assertEqual(sc["note"], "from the phone")
        self.assertTrue(os.path.isfile(t.paths.thumb) and os.path.isfile(t.paths.strip))
        self.assertFalse(got["picked"])
        # in the episode: usable, never stale, with its own length
        st = self.ok(A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))
        shot = next(s for s in st["shots"] if s["shot"] == self.shots[1])
        tk = next(x for x in shot["takes"] if x["take"] == got["take"])
        self.assertEqual((tk["status"], tk["stale"], tk["frames"]), ("ok", [], 24))
        self.assertEqual((tk["source"], tk["original_name"], tk["copied_from"]),
                         ("imported", "clip.mp4", None))
        rendered = [x for s in st["shots"] for x in s["takes"] if x["take"] != got["take"]]
        self.assertTrue(all("source" not in x for x in rendered))
        self.assertEqual(self.events[-1], ("seriesmith.episode", {"ep": self.ep}))

    def test_anything_else_is_converted(self):
        mov = make_video(os.path.join(self.tmp, "clip.mov"), "-c:v", "mpeg4", "-c:a", "pcm_s16le")
        got = self.imp(source_path=mov, pick=True)
        t = T.get_take(self.ep, "proxy", self.shots[1], got["take"])
        self.assertTrue(t.sidecar["converted"])
        self.assertTrue(TI.playable(t.paths.mp4))
        self.assertEqual(t.sidecar["frames"], 24)
        self.assertTrue(got["picked"])
        cut = T.load_cut(self.ep)["proxy"]
        self.assertEqual(next(e for e in cut if e["shot"] == self.shots[1])["take"], got["take"])
        # an H.264 .mov is converted too (only an mp4 is copied)
        self.assertFalse(TI.playable(make_video(os.path.join(self.tmp, "h.mov"), "-c:v", "libx264",
                                                "-pix_fmt", "yuv420p", "-c:a", "aac")))

    def test_an_upload_keeps_its_name(self):
        up = A.Upload(self.h264, "My Clip.mp4", os.path.getsize(self.h264))
        got = self.imp(file=up)
        sc = got["sidecar"]
        self.assertEqual((sc["original_name"], sc["source_path"]), ("My Clip.mp4", None))
        self.assertIn("uploaded as My Clip.mp4", sc["save_notes"])

    def test_refusals(self):
        self.imp(404, shot="sh999", source_path=self.h264)
        self.imp(404, source_path=os.path.join(self.tmp, "nothing.mp4"))
        self.imp(400, source_path="clip.mp4")
        self.imp(400)
        png = os.path.join(self.tmp, "still.png")
        with open(png, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
        self.assertIn("a take is a video", self.imp(400, source_path=png))
        fake = os.path.join(self.tmp, "fake.mp4")
        with open(fake, "wb") as fh:
            fh.write(b"not a video")
        self.imp(400, source_path=fake)
        # a refused file leaves no take behind ... except a failed record
        nums = T.take_numbers(self.ep, "proxy", self.shots[1])
        for n in nums:
            self.assertNotEqual(T.get_take(self.ep, "proxy", self.shots[1], n).sidecar.get("status"),
                                "queued")

    def test_a_locked_entry_keeps_its_take(self):
        first = self.imp(source_path=self.h264, pick=True)
        self.ok(A.put_cut(self.ctx, {"ep": self.ep, "pass": "proxy", "entries": [
            {"shot": s, **({"take": first["take"], "locked": True} if s == self.shots[1] else {})}
            for s in self.shots]}))
        second = self.imp(source_path=self.h264, pick=True)
        self.assertFalse(second["picked"])
        self.assertIn("locked", second["why"])

    def test_copy_from_another_shot(self):
        src = self.imp(source_path=self.h264)
        got = self.ok(A.post_take_copy(self.ctx, {"ep": self.ep, "shot": self.shots[2],
                                                  "from_shot": self.shots[1], "take": src["take"],
                                                  "pick": True}))
        t = T.get_take(self.ep, "proxy", self.shots[2], got["take"])
        self.assertEqual(read(t.paths.mp4), read(self.h264))
        self.assertEqual(t.sidecar["copied_from"]["shot"], self.shots[1])
        self.assertEqual(t.sidecar["copied_from"]["take"], src["take"])
        self.assertEqual(t.sidecar["note"], f"from {self.shots[1]} t{src['take']:02d}")
        self.assertTrue(got["picked"])
        # into its own shot and pass: a pick, not a copy; a take that isn't there: 404
        self.err(A.post_take_copy(self.ctx, {"ep": self.ep, "shot": self.shots[1],
                                             "from_shot": self.shots[1], "take": src["take"]}), 400)
        self.err(A.post_take_copy(self.ctx, {"ep": self.ep, "shot": self.shots[2],
                                             "from_shot": self.shots[1], "take": 99}), 404)
        # from the other pass
        got = self.ok(A.post_take_copy(self.ctx, {"ep": self.ep, "pass": "final",
                                                  "shot": self.shots[1], "from_shot": self.shots[1],
                                                  "take": src["take"], "from_pass": "proxy"}))
        self.assertEqual(got["pass"], "final")

    def hold(self, status=200, **body):
        res = A.post_take_hold(self.ctx, dict({"ep": self.ep, "shot": self.shots[1]}, **body))
        return self.ok(res) if status == 200 else self.err(res, status)

    def picture(self, name="card.png", size="300x300"):
        path = os.path.join(self.tmp, name)
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"color=c=red:size={size}", "-frames:v", "1", path],
                       check=True, capture_output=True)
        return path

    def test_a_picture_held(self):
        from seriesmith import edit as E
        from seriesmith import jobs as J
        got = self.hold(source_path=self.picture(), seconds=2, pick=True)
        t = T.get_take(self.ep, "proxy", self.shots[1], got["take"])
        sc = t.sidecar
        fps = E.pass_fps(self.ep, "proxy")
        d = J.load_shotlist(self.ep, "proxy")["defaults"]
        self.assertEqual((sc["status"], sc["source"], sc["held"]),
                         ("ok", "imported", {"seconds": 2.0, "name": "card.png"}))
        self.assertEqual((sc["frames"], sc["fps"]), (round(2 * fps), fps))
        self.assertEqual((sc["width"], sc["height"]), (d["width"], d["height"]))
        self.assertTrue(TI.playable(t.paths.mp4))
        self.assertTrue(got["picked"])
        st = self.ok(A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))
        tk = next(x for s in st["shots"] if s["shot"] == self.shots[1]
                  for x in s["takes"] if x["take"] == got["take"])
        self.assertEqual(tk["held"]["name"], "card.png")
        # an upload; seconds as a form gives them; by default the shot's duration
        up = A.Upload(self.picture("x.jpg"), "Two hours later.jpg", 1)
        got = self.hold(file=up, seconds="1.5")
        self.assertEqual(got["sidecar"]["held"], {"seconds": 1.5, "name": "Two hours later.jpg"})
        got = self.hold(source_path=self.picture())
        self.assertGreater(got["sidecar"]["frames"], 0)

    def test_a_freeze_frame(self):
        src = self.imp(source_path=self.h264)
        got = self.hold(shot=self.shots[2], from_shot=self.shots[1], take=src["take"],
                        frame=12, seconds=1)
        held = got["sidecar"]["held"]
        self.assertEqual(held, {"seconds": 1.0, "from": {"shot": self.shots[1],
                                "take": src["take"], "pass": "proxy", "frame": 12}})
        self.assertEqual(got["sidecar"]["note"], f"frame 12 of {self.shots[1]} t{src['take']:02d}")
        # past its last frame, a take that isn't there
        self.assertIn("no frame 99", self.hold(400, from_shot=self.shots[1], take=src["take"],
                                               frame=99))
        self.hold(404, from_shot=self.shots[1], take=99, frame=0)

    def test_hold_refusals(self):
        self.hold(400)
        self.assertIn("an image", self.hold(400, source_path=self.h264))
        self.hold(400, source_path=self.picture(), seconds=0)
        self.hold(400, source_path=self.picture(), seconds="soon")
        self.hold(400, source_path=self.picture(), seconds=TI.HOLD_MAX_SECONDS + 1)
        self.hold(404, source_path=os.path.join(self.tmp, "none.png"))
        self.hold(404, shot="sh999", source_path=self.picture())

    def test_routes_are_registered(self):
        got = {(m, p): takes for m, p, _f, takes in A.ROUTES}
        self.assertEqual(got[("POST", "/seriesmith/take/import")], "form")
        self.assertEqual(got[("POST", "/seriesmith/take/copy")], "body")
        self.assertEqual(got[("POST", "/seriesmith/take/hold")], "form")
        self.assertGreater(A.post_take_import.max_upload, A.MAX_UPLOAD)


def E_order(ep: str) -> list[str]:
    from seriesmith import edit as E
    return E.script_order(ep, "proxy")


if __name__ == "__main__":
    unittest.main()


class UploadLimitTest(unittest.TestCase):
    """The take route's own upload limit, through seriesmith serve's app: past
    the general one (made 1 MB here), a take's video still goes in; a ref's
    picture doesn't."""

    def test_a_video_may_be_bigger_than_a_picture(self):
        try:
            import aiohttp
            from aiohttp.test_utils import TestClient, TestServer
        except ImportError as exc:                       # pragma: no cover
            self.skipTest(f"the server needs aiohttp: {exc}")
        import asyncio
        import shutil
        import tempfile
        from unittest import mock
        from seriesmith.server import standalone
        from seriesmith.settings import Settings
        from test_render import FIXTURE, build_episode
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        shows = os.path.join(tmp, "Shows")
        ep = os.path.join(shows, "ks01")
        os.makedirs(ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(ep, "ks01.md"))
        build_episode(ep)
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(tmp, "user", "settings.json")
        self.addCleanup(os.environ.pop, "SERIESMITH_SETTINGS", None)
        # a 2 MB video: one long second of noise
        big = make_video(os.path.join(tmp, "big.mp4"), "-vf", "noise=alls=100:allf=t",
                         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "20M", "-c:a", "aac",
                         audio=True)
        self.assertGreater(os.path.getsize(big), 2 << 20)    # past the app's client_max_size too
        shot = E_order(ep)[0]

        async def go():
            with mock.patch.object(A, "MAX_UPLOAD", 1 << 20):
                app = standalone.make_app([shows], Settings(comfyui_url="http://127.0.0.1:0"))
                async with TestClient(TestServer(app)) as c:
                    def form(**fields):
                        f = aiohttp.FormData()
                        for k, v in fields.items():
                            f.add_field(k, v)
                        f.add_field("file", open(big, "rb"), filename="big.mp4")
                        return f
                    r = await c.post("/seriesmith/take/import", data=form(ep=ep, shot=shot))
                    take = (r.status, await r.json())
                    r = await c.post("/seriesmith/refs/import",
                                     data=form(ep=ep, ref="subject:ada", view="01_threequarter"))
                    return take, r.status
        (status, got), ref_status = asyncio.run(go())
        self.assertEqual(status, 200, got)
        self.assertEqual(got["sidecar"]["original_name"], "big.mp4")
        self.assertEqual(ref_status, 413)
