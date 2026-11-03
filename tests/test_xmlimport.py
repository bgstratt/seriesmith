"""xmlimport: an edit (FCP7 XML) into a new show and episode.

The Premiere-shaped fixture (tests/fixtures/xml/premiere_edit.xml) read back; its media
made with ffmpeg's testsrc and imported each way (handles, reference, proxies) and the
result assembled; and a round trip: a tiny episode exported with `assemble --xml`,
imported, its cut and mix the same.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from seriesmith import ff as FF  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import takeimport as TI  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import xmlimport as XI  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FIXTURE = os.path.join(HERE, "fixtures", "xml", "premiere_edit.xml")
NTSC = "24000/1001"


def ffmpeg(*args: str) -> None:
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", *args], capture_output=True,
                       text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)


def video(path: str, frames: int, codec: str = "libx264", rate: str = NTSC,
          size: str = "64x36") -> None:
    """`frames` of testsrc with a stereo tone: H.264 (an mp4) or another codec."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fps = eval(rate)                                       # noqa: S307  a fraction we wrote
    vc = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"] \
        if codec == "libx264" else ["-c:v", codec, "-q:v", "5"]
    ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}",
           "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
           "-frames:v", str(frames), "-t", f"{frames / fps:.6f}", *vc, "-ac", "2",
           "-c:a", "aac", path)


def tone(path: str, seconds: float) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", str(seconds), path)


def frames_of(path: str) -> int:
    r = subprocess.run([*FF.tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
                        "-count_frames", "-show_entries", "stream=nb_read_frames", "-of",
                        "csv=p=0", path], capture_output=True, text=True, timeout=120)
    return int(r.stdout.strip())


def media_url(folder: str) -> str:
    """The folder as a pathurl's path, as Premiere writes one (C%3a/...)."""
    p = os.path.abspath(folder).replace(os.sep, "/").lstrip("/")
    return quote(p, safe="/").replace("%3A", "%3a")


def fixture_text(media: str) -> str:
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read().replace("__MEDIA__", media_url(media))


class PathTest(unittest.TestCase):
    def test_file_urls(self):
        if os.name == "nt":
            self.assertEqual(XI.local_path("file://localhost/C%3a/My%20Show/a.mov"),
                             r"C:\My Show\a.mov")
            self.assertEqual(XI.local_path("file:///D:/clips/b%20c.mp4"), r"D:\clips\b c.mp4")
            self.assertEqual(XI.local_path("file://server/share/x.mov"), r"\\server\share\x.mov")
        else:
            self.assertEqual(XI.local_path("file:///Users/me/My%20Show/a.mov"),
                             "/Users/me/My Show/a.mov")
        self.assertIsNone(XI.local_path(None))

    def test_moved_beside_the_xml(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.mov"), "wb").close()
            got = XI.local_path("file:///nowhere/at/all/a.mov", base_dir=d)
            self.assertEqual(os.path.normcase(got), os.path.normcase(os.path.join(d, "a.mov")))


class ReadTest(unittest.TestCase):
    """The fixture as read, nothing probed."""

    def setUp(self):
        self.ed = XI.read(fixture_text("C:/media"))

    def test_the_sequence(self):
        self.assertEqual(self.ed["name"], "The Lighthouse (rough cut)")
        self.assertEqual(self.ed["fps"], 23.976)
        self.assertEqual(self.ed["size"], (64, 36))

    def test_v1_with_its_transitions_given_back(self):
        a, b, c, d = self.ed["v1"]
        # A: -1 end resolved by its length; its fade in from the start-black transition
        self.assertEqual((a["start"], a["end"], a["in"], a["out"], a["fade_in"]), (0, 66, 10, 76, 12))
        # B: -1 start, so its full span from the centred dissolve's start
        self.assertEqual((b["start"], b["end"], b["in"], b["out"], b["dissolve"]), (54, 120, 8, 74, 12))
        self.assertEqual((c["start"], c["end"], c["fade_out"]), (132, 192, 12))
        self.assertEqual(c["links"], ["clipitem-13"])
        self.assertTrue(d["path"].endswith("missing.mov"))
        self.assertEqual(self.ed["upper"], [{"track": 2, "name": "Logo bug", "start": 0, "end": 48}])

    def test_a_dissolve_written_at_the_edit_is_given_its_handles(self):
        """seriesmith's own export cuts at a dissolve's middle (nle_xml.lay): the frames
        either side are the clips' own, taken back."""
        from seriesmith import nle_xml as NX
        c = {"name": "x", "path": "C:/m/a.mp4", "frames": 100, "fps": 24.0, "size": (64, 64),
             "in": 0, "used": 56, "dissolve_in": 0, "fade_in": 0, "fade_out": 0, "marker": None,
             "audio": None}
        ed = XI.read(NX.write("e", 24.0, (64, 64), [c, dict(c, name="y", in_=0, used=22,
                                                                  dissolve_in=8)]))
        a, b = ed["v1"]
        self.assertEqual((a["start"], a["end"], a["out"]), (0, 56, 56))
        self.assertEqual((b["start"], b["end"], b["in"], b["dissolve"]), (48, 70, 0, 8))

    def test_audio_and_markers(self):
        tracks = sorted({a["track"] for a in self.ed["audio"]})
        self.assertEqual(tracks, [1, 2, 3, 4, 5])
        theme = next(a for a in self.ed["audio"] if a["name"] == "theme")
        self.assertEqual((theme["level"], theme["keys"], theme["fade_in"]), (0.5, [(50, 0.5), (100, 0.25)], 24))
        door = next(a for a in self.ed["audio"] if a["name"] == "door_sfx")
        self.assertFalse(door["enabled"])
        self.assertEqual([(m["name"], m["comment"], m["at"]) for m in self.ed["markers"]],
                         [("Arrival", "", 0), ("door slam", "hit", 70), ("Night falls", "", 140)])

    def test_not_an_edit(self):
        for text in ("<nope", "<fcpxml version='1.9'/>", "<xmeml version='4'/>"):
            with self.assertRaises(XI.XmlImportError):
                XI.read(text)

    def test_action_lines_read_as_action(self):
        self.assertEqual(XI._action("A001_C003.mov"), "A001_C003.mov")
        self.assertEqual(XI._action("INT. HOUSE: DAY"), "INT. HOUSE: DAY")     # not a speaker
        self.assertEqual(XI._action("KEEPER (V.O.): hello"), "Clip KEEPER (V.O.): hello")
        self.assertEqual(XI._action("camera: wide"), "Clip camera: wide")
        self.assertEqual(XI._action("# 4"), "Clip # 4")


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class ImportTest(unittest.TestCase):
    """The fixture's media made, and the edit imported each way."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.TemporaryDirectory()
        m = cls.media = cls._media.name
        video(os.path.join(m, "a.mov"), 100, codec="mpeg4")        # not H.264: no browser plays it
        video(os.path.join(m, "c.mp4"), 80)
        tone(os.path.join(m, "Music", "theme.wav"), 10)
        tone(os.path.join(m, "Music", "song.wav"), 4)
        tone(os.path.join(m, "door_sfx.wav"), 2)
        cls.text = fixture_text(m)

    @classmethod
    def tearDownClass(cls):
        cls._media.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, media="handles", run=True, **kw):
        s = XI.make(self.text, self.shows, "premiere_edit.xml", media=media, **kw)
        if run:
            for g in s["groups"]:
                res = XI.run_group(s["ep"], XI.load_group(s["ep"], g["index"]))
                self.assertEqual(res["failed"], [])
        return s

    def assemble(self, ep, *args) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", ep, "--partial", *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_dry_run_writes_nothing(self):
        s = XI.public(XI.plan(self.text, self.shows, "premiere_edit.xml"))
        self.assertEqual(os.listdir(self.shows), [])
        self.assertEqual(s["show"], "The_Lighthouse_rough_cut")
        self.assertEqual((s["shots"], s["black"], s["takes"]), (5, 1, 4))
        self.assertEqual(s["missing"], ["sh050"])
        self.assertEqual(s["sequences"], ["Arrival", "sq02"])
        self.assertEqual((s["audio_items"], s["hits"]), (3, 1))
        self.assertEqual(s["tracks"], ["effects", "music", "music2"])
        said = "\n".join(s["warnings"])
        for bit in ("Logo bug", "12-frame gap", "missing.mov"):
            self.assertIn(bit, said)

    def test_handles(self):
        s = self.make("handles")
        ep = s["ep"]
        self.assertTrue(s["build"]["ok"], s["build"])
        cut = {e["shot"]: e for e in T.load_cut(ep)["final"]}
        # A: frames 10..76 of a.mov, a second (24 frames) of handle either side as the file allows
        self.assertEqual(cut["sh010"], {"shot": "sh010", "take": 1, "trim_in": 10, "trim_out": 24,
                                        "fade_in": 12})
        self.assertEqual(cut["sh020"], {"shot": "sh020", "take": 1, "trim_in": 8, "trim_out": 24,
                                        "dissolve": 12})
        # C's own sound at half level; the gap black (its own silence); D has no take
        self.assertEqual(cut["sh040"]["audio"], {"source": "take", "shot": "sh040", "take": 1,
                                                 "pass": "final", "gain": 0.5})
        self.assertEqual(cut["sh050"], {"shot": "sh050", "note": cut["sh050"]["note"]})
        t = T.get_take(ep, "final", "sh010", 1)
        self.assertEqual((t.sidecar["frames"], t.sidecar["length"], t.sidecar["source"]),
                         (100, 100, "imported"))
        self.assertTrue(TI.playable(t.paths.mp4))
        self.assertEqual(frames_of(T.get_take(ep, "final", "sh020", 1).paths.mp4), 98)
        self.assertEqual(frames_of(T.get_take(ep, "final", "sh030", 1).paths.mp4), 12)
        # the cut plays the XML's timeline: 66 + 66 - 12 (the dissolve) + 12 (black) + 60
        self.assertIn("missing (1): sh050", self.assemble(ep).stdout)
        self.assertEqual(frames_of(os.path.join(ep, "renders", "ep01.mp4")), 192)
        # the script and the series config
        with open(os.path.join(ep, "ep01.md"), encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn("# Arrival  footage", script)
        self.assertIn("# sq02  footage\n// Night falls", script)
        self.assertIn("## sh010\ndur: 2.753\nWide on the pier", script)
        with open(os.path.join(ep, "series.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.assertEqual(cfg["series"], {"id": "the_lighthouse_rough_cut",
                                         "title": "The Lighthouse (rough cut)", "fps": 23.976,
                                         "width": 64, "height": 36, "target": "hold"})

    def test_the_mix(self):
        s = self.make("handles", run=False)
        mix = MX.load(s["ep"])
        self.assertEqual(mix["final"], mix["proxy"])
        m = mix["final"]
        items = {i["label"]: i for i in m["items"]}
        theme = items["theme"]
        self.assertEqual(theme["track"], "music")
        self.assertEqual(theme["path"], "audio/theme.wav")
        self.assertEqual((theme["in"], theme["gain_db"], theme["fade_in"]),
                         ({"shot": "sh010", "frame": 34}, -6.02, 24))
        # its keyframes (source frames 50 and 100: cut frames 74 and 124) as points
        self.assertEqual(theme["points"], [{"at": {"shot": "sh020", "frame": 28}, "db": 0.0},
                                           {"at": {"shot": "sh030", "frame": 4}, "db": -6.02}])
        # it runs past the last shot that has a file, so its end is on that one
        self.assertEqual(theme["out"]["shot"], "sh040")
        self.assertEqual(items["door_sfx"]["track"], "effects")
        self.assertTrue(items["door_sfx"]["mute"])
        self.assertAlmostEqual(items["door_sfx"]["offset"], 12 / 23.976, places=2)   # the mix keeps ms
        self.assertEqual(items["song"]["track"], "music2")
        self.assertEqual(m["track_list"][-1], {"id": "music2", "kind": "music", "label": "Music 2"})
        self.assertEqual(m["tracks"]["music"], {"gain_db": 0.0, "duck_db": 0.0})
        self.assertEqual(m["hits"], [{"id": "h1", "name": "door slam",
                                      "at": {"shot": "sh020", "frame": 24}}])
        for f in ("theme.wav", "song.wav", "door_sfx.wav"):
            self.assertTrue(os.path.isfile(os.path.join(s["ep"], "audio", f)), f)

    def test_reference(self):
        s = self.make("reference")
        self.assertEqual(s["unplayable"], ["sh010", "sh020"])
        ep = s["ep"]
        cut = {e["shot"]: e for e in T.load_cut(ep)["final"]}
        self.assertEqual((cut["sh010"]["trim_in"], cut["sh010"]["trim_out"]), (10, 24))
        self.assertEqual((cut["sh040"]["trim_in"], cut["sh040"]["trim_out"]), (5, 15))
        t = T.get_take(ep, "final", "sh010", 1)
        # the source itself, linked where the volume allows (the temp folders share one)
        self.assertTrue(os.path.samefile(t.paths.mp4, os.path.join(self.media, "a.mov"))
                        or t.sidecar["save_notes"].find("copied") > 0)
        self.assertEqual(frames_of(t.paths.mp4), 100)

    def test_proxies(self):
        s = self.make("proxies")
        self.assertEqual(s["proxies"], ["sh010", "sh020"])
        ep = s["ep"]
        a = os.path.join(self.media, "a.mov")
        proxy = XI.proxy_path(ep, a)
        self.assertTrue(os.path.isfile(proxy))
        self.assertTrue(TI.playable(proxy))
        self.assertEqual(frames_of(proxy), 100)                    # every frame of the original
        for shot in ("sh010", "sh020"):
            t = T.get_take(ep, "final", shot, 1)
            self.assertTrue(TI.playable(t.paths.mp4))
            self.assertEqual(t.sidecar["master"]["path"], os.path.abspath(a))
            self.assertEqual(TI.master_file(t), os.path.abspath(a))
        c = T.get_take(ep, "final", "sh040", 1)                     # H.264 already: no proxy
        self.assertNotIn("master", c.sidecar)
        # made once per source: a second run keeps it
        self.assertEqual(XI.ensure_proxy(ep, a), (proxy, False))
        # the cut is made from the original; the XML export points at it
        r = self.assemble(ep)
        self.assertIn("2 clip(s) cut from their originals", r.stdout)
        self.assertEqual(frames_of(os.path.join(ep, "renders", "ep01.mp4")), 192)
        self.assemble(ep, "--xml")
        with open(os.path.join(ep, "renders", "ep01.xml"), encoding="utf-8") as fh:
            back = XI.read(fh.read())
        self.assertEqual(os.path.normcase(back["v1"][0]["path"]), os.path.normcase(os.path.abspath(a)))

    def test_a_show_already_there(self):
        self.make("handles", run=False)
        from seriesmith import source as S
        with self.assertRaises(S.SourceError) as e:
            self.make("handles", run=False)
        self.assertEqual(e.exception.status, 409)
        s = self.make("handles", run=False, name="Another go")
        self.assertTrue(s["ep"].endswith(os.path.join("Another_go", "ep01")))

    def test_a_shows_next_episode(self):
        # the first import makes the show; the second, into it, is its ep02 with ep01's cast
        show = os.path.dirname(self.make("handles", run=False)["ep"])
        cfg_path = os.path.join(show, "ep01", "series.json")
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["subjects"] = {"mara": {"name": "Mara", "design": "a lighthouse keeper in a yellow oilskin"}}
        cfg["series"].update(fps=24, width=1920, height=1080, target="ltx2")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        dry = XI.public(XI.plan(self.text, show, "premiere_edit.xml", name="Night shift", in_show=True))
        self.assertEqual((dry["episode"], dry["ep"]), ("ep02", os.path.join(show, "ep02")))
        self.assertFalse(os.path.exists(dry["ep"]))
        self.assertIn("the show is 1920x1080 at 24 fps", "\n".join(dry["warnings"]))
        s = XI.make(self.text, show, "premiere_edit.xml", name="Night shift", in_show=True)
        self.assertTrue(s["build"]["ok"], s["build"])
        with open(os.path.join(s["ep"], "series.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        self.assertEqual(got["subjects"], {"mara": {"name": "Mara", "design": "a lighthouse keeper in a yellow oilskin"}})
        self.assertEqual((got["series"]["fps"], got["series"]["width"], got["series"]["target"]),
                         (23.976, 64, "hold"))
        self.assertIn("footage", got["locations"])
        with open(os.path.join(s["ep"], "ep02.md"), encoding="utf-8") as fh:
            self.assertTrue(fh.read().startswith("= ep02  Night shift"))
        # a folder with no episode yet: the edit's own series config
        empty = os.path.join(self.shows, "Empty")
        os.mkdir(empty)
        s = XI.public(XI.plan(self.text, empty, "premiere_edit.xml", in_show=True))
        self.assertEqual((s["episode"], s["from"]), ("ep01", None))

    def test_bad_options(self):
        for kw in ({"media": "copy"}, {"handles": -1}, {"handles": "x"}):
            with self.assertRaises(XI.XmlImportError):
                XI.plan(self.text, self.shows, **kw)

    def test_the_command(self):
        from seriesmith import commands as C
        xml = os.path.join(self.shows, "edit.xml")
        with open(xml, "w", encoding="utf-8") as fh:
            fh.write(self.text)
        self.assertEqual(C.main(["import-xml", xml, "--into", self.shows, "--dry-run"]), 0)
        self.assertEqual(sorted(os.listdir(self.shows)), ["edit.xml"])
        # D's file is missing: said, and the rest made
        self.assertEqual(C.main(["import-xml", xml, "--into", self.shows, "--name", "Cmd",
                                 "--handles", "0.5"]), 0)
        t = T.get_take(os.path.join(self.shows, "Cmd", "ep01"), "final", "sh010", 1)
        self.assertEqual(t.sidecar["frames"], 66 + 12 + 10)        # 10..76, 12 frames each side
        with self.assertRaises(SystemExit) as e:                    # argparse's own usage error
            C.main(["import-xml", xml, "--media", "nope"])
        self.assertEqual(e.exception.code, 2)


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class ApiTest(ImportTest):
    """POST /seriesmith/import/xml: written and built at once, the media on the queue."""

    def setUp(self):
        super().setUp()
        from seriesmith import api as A
        self.A = A
        self.ctx = A.Context(os.path.join(self.shows, "_user"), "http://127.0.0.1:0", env={})
        code, data = A.put_config(self.ctx, {"roots": [self.shows]})
        self.assertEqual(code, 200, data)
        self.xml = os.path.join(self.shows, "_user", "edit.xml")
        with open(self.xml, "w", encoding="utf-8") as fh:
            fh.write(self.text)

    def tearDown(self):
        self.settle()
        super().tearDown()

    def settle(self):
        from test_render import settle
        settle(self.ctx.runner, timeout=120)

    def post(self, status=200, **body):
        code, data = self.A.post_import_xml(self.ctx, body)
        self.assertEqual(code, status, data)
        json.dumps(data)
        self.settle()
        for jid in data.get("jobs") or []:
            job = self.ctx.runner.queue.jobs[jid]
            self.assertEqual(job.status, "succeeded", job.error)
            self.assertEqual(job.kind, "xmlmedia")
            self.assertEqual(job.lane, "cpu")
        return data

    def test_dry_run_then_import(self):
        s = self.post(path=self.xml, dry_run="true", media="proxies")
        self.assertEqual(s["proxies"], ["sh010", "sh020"])
        self.assertFalse(os.path.exists(s["ep"]))
        s = self.post(path=self.xml, media="handles", handles="0.5", name="Via the API")
        self.assertEqual(len(s["jobs"]), 3)
        self.assertTrue(s["build"]["ok"])
        t = T.get_take(s["ep"], "final", "sh010", 1)
        self.assertEqual(t.sidecar["frames"], 88)
        self.assertIn(("POST", "/seriesmith/import/xml"), {(m, p) for m, p, *_ in self.A.ROUTES})

    def test_an_upload(self):
        up = self.A.Upload(self.xml, "My Edit.xml", os.path.getsize(self.xml))
        s = self.post(file=up, dry_run=True)
        self.assertEqual(s["sequence"], "The Lighthouse (rough cut)")

    def test_errors(self):
        self.post(400)
        self.post(400, path="edit.xml")
        self.post(404, path=os.path.join(self.shows, "nope.xml"))
        self.post(400, path=self.xml, media="copy")
        self.post(403, path=self.xml, parent=os.path.dirname(self.shows))
        self.post(path=self.xml, name="Twice")
        self.post(409, path=self.xml, name="Twice")

    # ImportTest's own tests aren't run again here
    test_dry_run_writes_nothing = test_handles = test_the_mix = test_reference = None
    test_proxies = test_a_show_already_there = test_bad_options = test_the_command = None


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class RoundTripTest(unittest.TestCase):
    """A tiny episode exported with `assemble --xml` and imported: its cut and mix again."""

    def test_round_trip(self):
        from test_assemble import make_clip
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Show", "ep01")
            shots = (("sh010", 56, "sq01"), ("sh020", 39, "sq01"), ("sh030", 56, "sq02"))
            T.write_json(os.path.join(root, "shotlist", "shotlist.json"),
                         {"episode": "ep01", "defaults": {"width": 64, "height": 64, "fps": 24},
                          "shots": [{"id": s, "length": n, "audio_policy": "keep", "sequence": q}
                                    for s, n, q in shots]})
            for s, n, _q in shots:
                t = T.reserve_take(root, "final", s, {"status": "queued"})
                make_clip(t.paths.mp4, n, "64x64")
                T.update_sidecar(t.paths.sidecar, status="ok", frames=n, fps=24.0)
            tone(os.path.join(root, "sound", "m01", "t01.wav"), 5)
            cut = [{"shot": "sh010", "take": 1, "trim_in": 4, "fade_in": 6},
                   {"shot": "sh020", "take": 1, "trim_out": 5, "dissolve": 8},
                   {"shot": "sh030", "take": 1, "trim_in": 2, "fade_out": 10}]
            T.save_cut(root, {"final": cut, "proxy": []})
            MX.write(root, "final", {
                "items": [{"id": "m01", "track": "music", "path": "sound/m01/t01.wav",
                           "in": {"shot": "sh010", "frame": 10}, "out": {"shot": "sh030", "frame": 30},
                           "gain_db": -3, "fade_in": 12,
                           "points": [{"at": {"shot": "sh020", "frame": 5}, "db": -6}]}],
                "hits": [{"id": "h1", "name": "door", "at": {"shot": "sh020", "frame": 12}}]})
            r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", root, "--xml"],
                               capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(root, "renders", "ep01.xml"), encoding="utf-8") as fh:
                text = fh.read()
            shows = os.path.join(tmp, "Imported")
            os.makedirs(shows)
            s = XI.make(text, shows, "ep01.xml", media="reference")
            self.assertEqual(s["warnings"], [])
            self.assertEqual(s["sequences"], ["sq01", "sq02"])
            for g in s["groups"]:
                XI.run_group(s["ep"], XI.load_group(s["ep"], g["index"]))
            # the same shots, takes, trims and joins (the takes are the originals, whole)
            self.assertEqual(T.load_cut(s["ep"])["final"], cut)
            m = MX.load(s["ep"])["final"]
            (item,) = m["items"]
            # the music track's fader is 0 dB on import, so its -12 is in the item's level
            self.assertEqual((item["track"], item["in"], item["out"], item["gain_db"], item["fade_in"]),
                             ("music", {"shot": "sh010", "frame": 10}, {"shot": "sh030", "frame": 30},
                              -15.0, 12))
            self.assertEqual(item["points"], [{"at": {"shot": "sh020", "frame": 5}, "db": -6.0}])
            self.assertEqual(m["hits"], [{"id": "h1", "name": "door",
                                          "at": {"shot": "sh020", "frame": 12}}])
            # and it exports to the same timeline
            r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", s["ep"], "--xml"],
                               capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(s["ep"], "renders", "ep01.xml"), encoding="utf-8") as fh:
                again = XI.read(fh.read())
            first = XI.read(text)
            pick = (lambda ed: [(c["start"], c["end"], c["in"], c["out"], c["dissolve"],
                                 c["fade_in"], c["fade_out"]) for c in ed["v1"]])
            self.assertEqual(pick(again), pick(first))


if __name__ == "__main__":
    unittest.main()
