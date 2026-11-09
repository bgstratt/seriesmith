"""publish: the series intro + the cut + the outro, the episode title drawn on.

The end-to-end tests build a tiny episode with testsrc clips of different sizes
and check the output's size, rate and length: a cut assemble encoded has its
picture copied frame for frame, any other cut is re-encoded. Skipped when
ffmpeg or ffprobe is not on PATH, or no font file is found.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import edit as E  # noqa: E402
from seriesmith import publish as P  # noqa: E402
from seriesmith import ff as FF  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FONT = next((f for f in ("C:/Windows/Fonts/segoescb.ttf", "C:/Windows/Fonts/arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                         "/Library/Fonts/Arial.ttf") if os.path.isfile(f)), None)


def make_clip(path: str, seconds: float, size: str, rate: int, sound: bool = True) -> None:
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000"]
    cmd += ["-t", f"{seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac"] if sound else []
    r = subprocess.run(cmd + [path], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)


class Helpers(unittest.TestCase):
    def test_episode_title(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ep07.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n= ep07  Cul-de-sac\n\n// = not this\n# sq01  street\n")
            self.assertEqual(P.episode_title(p), "Cul-de-sac")
            with open(p, "w", encoding="utf-8") as f:
                f.write("= ep07\n")
            self.assertEqual(P.episode_title(p), "")

    def test_config_defaults(self):
        c = P.publish_config({"publish": {"intro": "a.mp4", "subtitle": {"size": 0.1}}})
        self.assertEqual(c["intro"], "a.mp4")
        self.assertEqual(c["subtitle"]["size"], 0.1)
        self.assertEqual(c["subtitle"]["intro_in"], P.SUBTITLE["intro_in"])
        self.assertEqual(P.publish_config({})["subtitle"], P.SUBTITLE)

    def test_alpha(self):
        self.assertEqual(P.alpha_expr([4, 5]), "clip((t-4)/1,0,1)")
        self.assertEqual(P.alpha_expr([0, 1], [4.5, 5.5]),
                         "clip((t-0)/1,0,1)*(1-clip((t-4.5)/1,0,1))")
        self.assertEqual(P.alpha_expr([2, 2]), "gte(t,2)")

    def test_cut_tags(self):
        cut = {"sar": "N/A", "color_range": None, "color_primaries": None,
               "color_transfer": None, "color_space": None}
        self.assertEqual(P.cut_tags(cut), "setsar=0,setparams=range=unknown:color_primaries="
                                          "unknown:color_trc=unknown:colorspace=unknown")
        cut.update(sar="1:1", color_range="tv")
        self.assertTrue(P.cut_tags(cut).startswith("setsar=1,setparams=range=tv:"))

    def test_graph_inputs(self):
        cut = {"width": 960, "height": 544, "fps": 24, "duration": 10, "audio": False}
        clip = {"width": 1376, "height": 768, "fps": 24, "duration": 8, "audio": True}
        g = P.filter_graph(cut, clip, clip, P.SUBTITLE)
        self.assertIn("[3:a]", g)            # the silence stands in for the cut's sound
        self.assertIn("concat=n=3", g)
        g = P.filter_graph(cut, None, None, P.SUBTITLE)
        self.assertIn("concat=n=1", g)
        self.assertNotIn("drawtext", g)

    def test_title_font(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            mine = os.path.join(d, "mine.ttf")
            open(mine, "wb").close()
            self.assertEqual(P.title_font(mine, named=True), mine)
            # one the series config named and isn't there: said, not replaced
            with self.assertRaisesRegex(P.PublishError, "isn't there"):
                P.title_font(os.path.join(d, "gone.ttf"), named=True)
            # the default missing: the first fallback that's here
            with mock.patch.object(P, "FONT_FALLBACKS", (os.path.join(d, "no.ttf"), mine)), \
                    contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(P.title_font(os.path.join(d, "segoescb.ttf"), named=False), mine)
            self.assertIn("using", said.getvalue())
            with mock.patch.object(P, "FONT_FALLBACKS", ()), \
                    self.assertRaisesRegex(P.PublishError, "Set publish.subtitle.font"):
                P.title_font(os.path.join(d, "segoescb.ttf"), named=False)

    def test_find_font(self):
        # a path as it is; a relative one from the show folder; a bare name, any case and its
        # extension optional, from the show folder, else the machine's font folders
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            show, fonts = os.path.join(d, "show"), os.path.join(d, "Fonts")
            os.makedirs(os.path.join(show, "fonts"))
            os.makedirs(os.path.join(fonts, "truetype"))
            mine = os.path.join(show, "fonts", "Title.otf")
            sys_font = os.path.join(fonts, "truetype", "Georgia.ttf")
            for f in (mine, sys_font):
                open(f, "wb").close()
            with mock.patch.object(P, "font_dirs", lambda: [fonts]):
                self.assertEqual(P.installed_fonts(), {"georgia.ttf": sys_font})
                self.assertEqual(P.find_font(mine), mine)
                self.assertEqual(P.find_font("fonts/Title.otf", show), os.path.normpath(mine))
                self.assertIsNone(P.find_font("fonts/Title.otf"))
                for name in ("Georgia.ttf", "georgia", "GEORGIA.TTF"):
                    self.assertEqual(P.find_font(name, show), sys_font, name)
                self.assertIsNone(P.find_font("nope.ttf", show))
                self.assertIsNone(P.find_font("fonts/Georgia.ttf", show))
                self.assertEqual(P.title_font("georgia", named=True, home=show), sys_font)
                with self.assertRaisesRegex(P.PublishError, "folder holding series.json"):
                    P.title_font("nope.ttf", named=True, home=show)

    def test_title_from_the_intros_end(self):
        # negative times count back from the clip's end, so a long montage intro keeps the
        # title to its last seconds; 0 or more count from its start, as they always did
        self.assertEqual(P.from_end([-4, -3], 8), [4, 5])
        self.assertEqual(P.from_end([-4, -3], 40), [36, 37])
        self.assertEqual(P.from_end([-0.5, 0], 10), [9.5, 10])
        self.assertEqual(P.from_end([4, 5], 40), [4, 5])
        self.assertEqual(P.from_end([-60, -59], 8), [0.0, 0.0])
        clip = {"width": 1376, "height": 768, "fps": 24, "duration": 40, "audio": False}
        cut = {**clip, "duration": 10}
        g = P.filter_graph(cut, clip, None, P.SUBTITLE)
        self.assertIn(P.alpha_expr([36, 37]), g)

    def test_graph_levels(self):
        # a title clip's level goes first on its own sound, never on the cut's or the silence
        cut = {"width": 960, "height": 544, "fps": 24, "duration": 10, "audio": True}
        clip = {"width": 1376, "height": 768, "fps": 24, "duration": 8, "audio": True}
        g = P.filter_graph(cut, clip, clip, P.SUBTITLE, {"intro": "volume=-3.00dB"})
        self.assertIn("[0:a]volume=-3.00dB,aresample=48000", g)
        self.assertIn("[1:a]aresample=48000", g)
        self.assertIn("[2:a]aresample=48000", g)
        silent = {**clip, "audio": False}
        g = P.filter_graph(cut, silent, None, P.SUBTITLE, {"intro": "volume=-3.00dB"})
        self.assertNotIn("volume", g)
        self.assertEqual(P.publish_config({})["loudness"], P.LEVEL)


@unittest.skipUnless(HAVE_FF and FONT, "needs ffmpeg, ffprobe and a font")
class EndToEnd(unittest.TestCase):
    def episode(self, show: str, assembled: bool, legacy: bool = False) -> str:
        """ep07 with 2 s titles (tagged BT.709, like ComfyUI's) and a 3 s cut:
        encoded by assemble.conform, or a foreign ultrafast encode tagged
        BT.709, or (`legacy`) one untagged, as cuts were before the colour fix."""
        ep = os.path.join(show, "ep07")
        os.makedirs(os.path.join(ep, "renders"))
        os.makedirs(os.path.join(show, "_titles"))
        for name in ("INTRO", "OUTRO"):
            raw = os.path.join(show, "_titles", f"{name}_raw.mp4")
            make_clip(raw, 2, "1376x768", 24)
            r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", raw, "-c", "copy",
                                "-color_primaries", "bt709", "-color_trc", "bt709",
                                "-colorspace", "bt709", "-color_range", "tv",
                                os.path.join(show, "_titles", f"{name}.mp4")],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
        cut = os.path.join(ep, "renders", "ep07.mp4")
        if assembled:
            raw = os.path.join(show, "raw.mp4")
            make_clip(raw, 3, "320x176", 24, sound=False)
            P.ASM.conform(raw, cut, None, 24, 72, quality="review")
        elif legacy:
            make_clip(cut, 3, "320x176", 24, sound=False)
        else:
            raw = os.path.join(show, "raw.mp4")
            make_clip(raw, 3, "320x176", 24, sound=False)
            r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", raw, "-c", "copy",
                                "-color_primaries", "bt709", "-color_trc", "bt709",
                                "-colorspace", "bt709", "-color_range", "tv", cut],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(ep, "ep07.md"), "w", encoding="utf-8") as f:
            f.write("= ep07  Cul-de-sac\n")
        with open(os.path.join(ep, "series.json"), "w", encoding="utf-8") as f:
            json.dump({"series": {"id": "t", "title": "T"},
                       "publish": {"intro": "../_titles/INTRO.mp4",
                                   "outro": "../_titles/OUTRO.mp4",
                                   "subtitle": {"font": FONT, "intro_in": [0.5, 1],
                                                "outro_out": [1, 1.5]}}}, f)
        return ep

    def publish(self, ep: str) -> tuple[str, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = P.publish(ep)
        self.assertEqual(out, os.path.join(ep, "publish", "ep07.mp4"))
        got = P.probe(out)
        self.assertEqual((got["width"], got["height"], got["fps"]), (320, 176, 24))
        self.assertEqual(got["frames"], 48 + 72 + 48)
        self.assertTrue(got["audio"])
        return out, buf.getvalue()

    def bt709(self, path: str) -> None:
        got = P.probe(path)
        self.assertEqual([got[k] for k in ("color_range", "color_space", "color_primaries",
                                           "color_transfer")], ["tv", "bt709", "bt709", "bt709"])

    def test_assembled_cut_is_copied(self):
        with tempfile.TemporaryDirectory() as show:
            ep = self.episode(show, assembled=True)
            out, said = self.publish(ep)
            self.assertIn("picture copied", said)
            self.assertNotIn("re-encoding the whole cut", said)
            self.bt709(out)
            cut = os.path.join(ep, "renders", "ep07.mp4")
            got, src = P.probe(out), P.probe(cut)
            self.assertEqual(P.frame_hashes(out, 48, 72, got), P.frame_hashes(cut, 0, 72, src))

    def test_editor_publish(self):
        # the route's helper: _titles in the show folder by convention, no
        # publish block needed; the output relative to the episode
        with tempfile.TemporaryDirectory() as show:
            ep = self.episode(show, assembled=True)
            cfg = os.path.join(ep, "series.json")
            with open(cfg, encoding="utf-8") as f:
                doc = json.load(f)
            doc["publish"] = {"subtitle": doc["publish"]["subtitle"]}
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            res = E.publish_episode(ep, "renders/ep07.mp4")
            self.assertTrue(res["ok"], res["report"])
            self.assertEqual(res["output"], "publish/ep07.mp4")
            self.assertEqual(P.probe(os.path.join(ep, res["output"]))["frames"], 48 + 72 + 48)
            shutil.rmtree(os.path.join(show, "_titles"))
            res = E.publish_episode(ep, "renders/ep07.mp4")
            self.assertFalse(res["ok"])
            self.assertIn("no intro or outro", res["error"])

    def test_foreign_cut_is_reencoded(self):
        with tempfile.TemporaryDirectory() as show:
            _, said = self.publish(self.episode(show, assembled=False))
            self.assertIn("re-encoding the whole cut: the title clips can't be encoded", said)

    def test_a_cut_from_before_the_colour_fix_is_converted(self):
        # untagged (BT.601): re-encoded, and comes out BT.709 throughout
        with tempfile.TemporaryDirectory() as show:
            out, said = self.publish(self.episode(show, assembled=False, legacy=True))
            self.assertIn("the cut isn't BT.709", said)
            self.bt709(out)

    def run_with_progress(self, ep: str) -> tuple[int, list, str]:
        """publish as master runs it: through edit.run_tool, --progress."""
        events = []
        rc, out, err = E.run_tool("publish.py", [ep, "--progress"], ep, 600,
                                       progress=lambda tool, ev: events.append((tool, ev)))
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("##publish", out)            # progress lines don't reach the log
        return rc, events, out

    def test_progress_says_the_picture_was_copied(self):
        with tempfile.TemporaryDirectory() as show:
            _, events, _ = self.run_with_progress(self.episode(show, assembled=True))
            self.assertTrue(all(tool == "publish" for tool, _ in events))
            stages = [ev["stage"] for _, ev in events]
            for want in ("titles", "join", "verify"):
                self.assertIn(want, stages)
            self.assertEqual(events[-1][1]["stage"], "done")
            self.assertEqual((events[-1][1]["picture"], events[-1][1]["why"]), ("copied", ""))

    def test_progress_says_the_picture_was_reencoded(self):
        with tempfile.TemporaryDirectory() as show:
            _, events, _ = self.run_with_progress(self.episode(show, assembled=False))
            done = events[-1][1]
            self.assertEqual(done["picture"], "re-encoded")
            self.assertIn("the title clips can't be encoded", done["why"])
            counted = [ev for _, ev in events if ev["stage"] == "reencode" and ev["total"]]
            self.assertTrue(counted)                     # ffmpeg's frame count, as it went
            self.assertEqual(counted[0]["total"], 48 + 72 + 48)

    def two_clip_cut(self, show: str, ep: str) -> str:
        """The episode's cut as assemble joins one: two 36-frame clips, each encoded by
        conform (so the second starts on a keyframe), joined by the concat demuxer."""
        parts = []
        for k in (0, 1):
            raw = os.path.join(show, f"raw{k}.mp4")
            make_clip(raw, 1.5, "320x176", 24, sound=False)
            parts.append(os.path.join(show, f"part{k}.mp4"))
            P.ASM.conform(raw, parts[-1], None, 24, 36, quality="review")
        lst = os.path.join(show, "parts.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("".join(f"file '{p.replace(os.sep, '/')}'\n" for p in parts))
        cut = os.path.join(ep, "renders", "ep07.mp4")
        r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0",
                            "-i", lst, "-c", "copy", cut], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return cut

    def cold_open(self, at: int) -> tuple[str, str, str]:
        """Published with the cold open ending at frame `at`: (output, its log, the cut)."""
        from unittest import mock
        show = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, show, True)
        ep = self.episode(show, assembled=True)
        cut = self.two_clip_cut(show, ep)
        buf = io.StringIO()
        with mock.patch.object(P, "cold_open_split", lambda *a: at), contextlib.redirect_stdout(buf):
            out = P.publish(ep)
        got = P.probe(out)
        self.assertEqual(got["frames"], at + 48 + (72 - at) + 48)
        # the cut's head, the intro, the rest of the cut, the outro: each side of the break
        # looks like the cut's frame there (a re-encode changes the pixels a little)
        for o, c in ((at - 1, at - 1), (at + 48, at)):
            self.assertLess(self.apart(out, o, cut, c), 6.0, (o, c))
        self.assertGreater(self.apart(out, at, cut, at), 6.0)       # the intro, not the cut
        return out, buf.getvalue(), cut

    @staticmethod
    def thumb(path: str, n: int) -> bytes:
        r = subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-i", path, "-vf",
                            f"select=eq(n\\,{n}),scale=16:9,format=gray", "-frames:v", "1",
                            "-f", "rawvideo", "-"], capture_output=True, timeout=120)
        return r.stdout

    def apart(self, a: str, na: int, b: str, nb: int) -> float:
        """How far frame `na` of `a` is from frame `nb` of `b`: their 16x9 greys' mean difference."""
        x, y = self.thumb(a, na), self.thumb(b, nb)
        self.assertEqual(len(x), 144)
        return sum(abs(p - q) for p, q in zip(x, y)) / len(x)

    def test_cold_open_on_a_clip_boundary_is_copied(self):
        out, said, cut = self.cold_open(36)
        self.assertIn("cold open: the intro goes in at frame 36", said)
        self.assertIn("picture copied (split at the cold open)", said)
        got, src = P.probe(out), P.probe(cut)
        self.assertEqual(P.frame_hashes(out, 0, 36, got), P.frame_hashes(cut, 0, 36, src))
        self.assertEqual(P.frame_hashes(out, 84, 36, got), P.frame_hashes(cut, 36, 36, src))

    def test_cold_open_mid_clip_is_reencoded(self):
        _, said, _ = self.cold_open(20)
        self.assertIn("isn't a keyframe", said)
        self.assertIn("re-encoding the whole cut", said)

    def intro_lufs(self, out: str) -> float:
        """The published file's first 2 s (the intro), measured as the mix measures."""
        from seriesmith import mix as MX
        head = os.path.join(os.path.dirname(out), "head.wav")
        r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", out, "-t", "2", "-vn",
                            head], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return MX.measure(head, -16, -1)["input_i"]

    def test_title_sound_brought_to_the_episode_loudness(self):
        # the intro's sine (about -21 LUFS as made) comes out at the episode's -16, or under
        # it by under_lu; "match": false leaves it as it came
        with tempfile.TemporaryDirectory() as show:
            ep = self.episode(show, assembled=True)
            out, said = self.publish(ep)
            self.assertIn("intro sound:", said)
            self.assertAlmostEqual(self.intro_lufs(out), -16, delta=1.0)
            cfg = os.path.join(ep, "series.json")
            with open(cfg, encoding="utf-8") as f:
                doc = json.load(f)
            doc["publish"]["loudness"] = {"under_lu": 4}
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            out, _ = self.publish(ep)
            self.assertAlmostEqual(self.intro_lufs(out), -20, delta=1.0)
            doc["publish"]["loudness"] = {"match": False}
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            out, said = self.publish(ep)
            self.assertNotIn("intro sound:", said)
            raw = P.probe(os.path.join(show, "_titles", "INTRO.mp4"))
            self.assertTrue(raw["audio"])
            self.assertGreater(abs(self.intro_lufs(out) + 16), 2.0)

    def test_clip_level_limits_a_loud_clip(self):
        from seriesmith import mix as MX
        with tempfile.TemporaryDirectory() as d:
            loud = os.path.join(d, "loud.wav")
            r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                                "sine=frequency=60:sample_rate=48000,volume=0.99", "-t", "3", loud],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            # asked for 0 LUFS: the gain would cross the ceiling, so the limiter holds it
            level, words = P.clip_level(loud, {"target_lufs": -5, "true_peak_db": -1})
            self.assertIn("volume=", level)
            self.assertIn("alimiter", level)
            self.assertIn("limited to -2 dBTP", words)
            quiet = os.path.join(d, "quiet.wav")
            subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                            "anullsrc=r=48000:cl=stereo", "-t", "2", quiet],
                           capture_output=True, timeout=120)
            self.assertEqual(P.clip_level(quiet, MX.LOUDNESS)[0], None)

    def test_missing_clip(self):
        with tempfile.TemporaryDirectory() as ep:
            make_clip(os.path.join(ep, "cut.mp4"), 1, "320x176", 24)
            with open(os.path.join(ep, "x.md"), "w", encoding="utf-8") as f:
                f.write("= x  X\n")
            with open(os.path.join(ep, "series.json"), "w", encoding="utf-8") as f:
                json.dump({"series": {"id": "t", "title": "T"},
                           "publish": {"intro": "nope.mp4", "subtitle": {"font": FONT}}}, f)
            with self.assertRaises(P.PublishError):
                P.publish(ep, os.path.join(ep, "cut.mp4"))


if __name__ == "__main__":
    unittest.main()
