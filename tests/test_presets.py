"""
The presets the editor offers as pictures (seriesmith/presets): relighting a
ref's picture and the series' look. The data is whole (every relight preset
has a wording for what it is for; plate wordings say only the light changes),
the listing gives each sample picture once it is made, and the routes serve
the list and the pictures and nothing else.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import api as A  # noqa: E402
from seriesmith import presets as PR  # noqa: E402


class DataTest(unittest.TestCase):
    def test_every_relight_preset_says_what_it_changes(self):
        ids = set()
        for p in PR._load("relight"):
            with self.subTest(p["id"]):
                self.assertNotIn(p["id"], ids)
                ids.add(p["id"])
                words = p.get("for") or ["place", "subject"]
                for w in words:
                    self.assertTrue(p.get(w), f"no {w} wording")
                    # the edit wrapper keeps the rest; the instruction names what goes
                    self.assertTrue(p[w].startswith("Change only"), p[w])
                self.assertTrue(set(words) <= {"place", "subject"})
                # a plate's relight is an edit: a light source it names as a thing in the
                # scene gets drawn in (dusk's "street lamps lit" put streetlights in a garden)
                if p.get("place"):
                    self.assertTrue(p["place"].endswith("that aren't already there"), p["place"])

    def test_every_look_is_a_brief(self):
        for p in PR._load("look"):
            with self.subTest(p["id"]):
                # one sentence, about what can be seen: no quality adjectives (AUTHORING)
                self.assertNotIn("cinematic", p["text"].lower())
                self.assertNotIn("high quality", p["text"].lower())
                self.assertGreater(len(p["text"].split()), 12)

    def test_no_look_puts_people_or_things_in_a_place(self):
        """The look opens every picture's prompt, a place's empty plate too: wording that
        names characters, faces, figures or skin drew round little people into a moonlit
        garden. A look says how things are rendered; the cast brings the people."""
        import re
        people = re.compile(r"\b(characters?|faces?|figures?|skin|people|persons?|puppets?|silhouettes?)\b", re.I)
        # nor a place or a thing: "night streets lit by neon signs" turned a lighthouse into
        # a close-up of the lighthouse, and lamps, windows and skies get drawn in where none are
        things = re.compile(r"\b(streets?|signs?|vistas?|landscapes?|roads?(?! movie)|rooms?|lamps?|windows?|"
                            r"panels?|screens?|sky|skies|smoke|buildings?|towns?|city)\b", re.I)
        clauses = [(p["id"], p["text"]) for p in PR._load("look")]
        clauses += [(f'{r["id"]}.{o["id"]}', o["clause"]) for r in PR._load("look_builder") for o in r["options"]]
        for name, text in clauses:
            with self.subTest(name):
                self.assertIsNone(people.search(text), text)
                self.assertIsNone(things.search(text), text)

    def test_framing_and_camera_say_what_the_script_does(self):
        from seriesmith.core import framing as F
        for p in PR._load("framing"):
            with self.subTest(p["id"]):
                # every size the shot form offers is one the script reads
                self.assertIn(F.ALIASES.get(p["id"].replace("-", ""), p["id"]), F.SIZES)
        self.assertEqual([p["id"] for p in PR._load("framing")],
                         ["ecu", "cu", "mcu", "medium", "cowboy", "mws", "full", "wide", "ews",
                          "pov", "ots", "low", "high"])
        moves = [p["move"] for p in PR._load("camera")]
        self.assertEqual(len(moves), len(set(moves)))
        self.assertIn("pushes in", moves)

    def test_the_look_builder_writes_the_brief(self):
        # the same strings web/test/lookBuilder.test.ts expects: the two compose alike
        self.assertEqual(
            PR.compose_look({"medium": "live_action", "camera": "film35", "lens": "anamorphic",
                             "light": "low_key", "grade": "muted"}),
            "a live-action film; shot on 35mm film; anamorphic lenses: oval bokeh, horizontal lens "
            "flares, slight distortion at the edges; low-key practical light, pools of light and "
            "deep soft shadow; a muted, desaturated grade with lifted blacks")
        self.assertEqual(
            PR.compose_look({"medium": "anime", "camera": "film35", "light": "soft"}),
            "a hand-drawn Japanese anime: expressive line art, cel shading over richly painted "
            "backgrounds; soft naturalistic daylight, gentle shadows")
        self.assertEqual(PR.compose_look({"camera": "film35"}), "")

    def test_every_look_preset_is_in_the_builders_rows(self):
        rows = {r["id"]: {o["id"] for o in r["options"]} for r in PR._load("look_builder")}
        for p in PR._load("look"):
            with self.subTest(p["id"]):
                self.assertIn("medium", p["parts"])
                for row, opt in p["parts"].items():
                    self.assertIn(opt, rows[row], f"{row}: {opt}")
                self.assertTrue(PR.compose_look(p["parts"]))

    def test_a_ref_kind_reads_its_wording(self):
        self.assertIn("the light on the figure", PR.relight_text("neon", "character"))
        self.assertTrue(PR.relight_text("neon", "location").startswith("Change only the light:"))
        with self.assertRaises(PR.PresetError):
            PR.relight_text("rembrandt", "location")       # a figure's light only
        with self.assertRaises(PR.PresetError):
            PR.relight_text("nope", "location")


class ListingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # the package's own data, with an img folder of this test's
        for kind in PR.KINDS:
            shutil.copyfile(os.path.join(PR.HERE, f"{kind}.json"), os.path.join(tmp, f"{kind}.json"))
        os.makedirs(os.path.join(tmp, "img", "look"))
        os.makedirs(os.path.join(tmp, "img", "relight"))
        os.makedirs(os.path.join(tmp, "img", "camera"))
        open(os.path.join(tmp, "img", "camera", "arc.mp4"), "wb").write(b"mp4")
        open(os.path.join(tmp, "img", "look", "neon_noir.jpg"), "wb").write(b"\xff\xd8jpg")
        open(os.path.join(tmp, "img", "relight", "rain-place.jpg"), "wb").write(b"\xff\xd8jpg")
        patch = mock.patch.object(PR, "HERE", tmp)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_sample_picture_is_listed_once_made(self):
        looks = {p["id"]: p for p in PR.listing("look")}
        self.assertEqual(looks["neon_noir"]["image"], "look/neon_noir.jpg")
        self.assertNotIn("image", looks["anime"])
        rain = next(p for p in PR.listing("relight") if p["id"] == "rain")
        self.assertEqual(rain["images"], {"place": "relight/rain-place.jpg"})
        self.assertEqual(set(rain["texts"]), {"place", "subject"})
        rembrandt = next(p for p in PR.listing("relight") if p["id"] == "rembrandt")
        self.assertEqual(rembrandt["for"], ["subject"])

    def test_the_routes(self):
        ctx = A.Context(tempfile.mkdtemp(), "http://127.0.0.1:0", env={})
        status, data = A.get_presets(ctx, {})
        self.assertEqual((status, set(data)), (200, set(PR.KINDS)))
        self.assertEqual(set(A.get_presets(ctx, {"kind": "look"})[1]), {"look"})
        self.assertEqual(A.get_presets(ctx, {"kind": "nope"})[0], 400)
        status, data = A.get_preset_image(ctx, {"name": "look/neon_noir.jpg"})
        self.assertEqual((status, data["content_type"]), (200, "image/jpeg"))
        self.assertTrue(data["path"].endswith("neon_noir.jpg"))
        # only a made picture, by its name: nothing else under the package
        for name in ("look/anime.jpg", "../look.json", "look/../relight.json", "img/look/neon_noir.jpg",
                     "look/neon_noir.png", "", "look/.jpg"):
            with self.subTest(name):
                self.assertEqual(A.get_preset_image(ctx, {"name": name})[0], 404)
        # a camera move's sample is a clip
        status, data = A.get_preset_image(ctx, {"name": "camera/arc.mp4"})
        self.assertEqual((status, data["content_type"]), (200, "video/mp4"))
        self.assertEqual(A.get_preset_image(ctx, {"name": "camera/arc.jpg"})[0], 404)
        self.assertEqual(A.get_preset_image(ctx, {"name": "look/neon_noir.mp4"})[0], 404)
        routes = {(m, p) for m, p, _f, _t in A.ROUTES}
        self.assertIn(("GET", "/seriesmith/presets"), routes)
        self.assertIn(("GET", "/seriesmith/presets/image"), routes)


if __name__ == "__main__":
    unittest.main()


class OwnPresetTest(unittest.TestCase):
    """Your own looks and relights, kept beside this machine's settings."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"SERIESMITH_SETTINGS":
                                           os.path.join(self._tmp.name, "settings.json")})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_a_look_of_yours(self):
        p = PR.save_own("look", "Neon noir", {"text": "my noir line", "parts": {"medium": "live_action"}})
        self.assertEqual((p["id"], p["group"], p["own"]), ("neon_noir_2", "yours", True))  # the shipped id kept
        looks = PR.listing("look")
        self.assertEqual(looks[-1]["text"], "my noir line")
        self.assertEqual(len([x for x in looks if x.get("own")]), 1)
        PR.save_own("look", "Neon noir", {"text": "changed"}, pid="neon_noir_2")
        self.assertEqual([x["text"] for x in PR.listing("look") if x.get("own")], ["changed"])
        PR.delete_own("look", "neon_noir_2")
        self.assertFalse(any(x.get("own") for x in PR.listing("look")))

    def test_a_relight_of_yours_relights(self):
        from seriesmith import relight as RL
        p = PR.save_own("relight", "Flashback haze", {"place": "Change only the light: hazy amber memory"},
                        picture=b"\xff\xd8jpeg")
        self.assertEqual(p["for"], ["place"])
        self.assertTrue(p["images"]["place"].startswith("own/relight/flashback_haze.jpg?v="))
        self.assertTrue(PR.image_path(p["images"]["place"]).endswith("flashback_haze.jpg"))
        self.assertEqual(RL.instruction("flashback_haze"), "Change only the light: hazy amber memory")
        self.assertEqual(RL.default_suffix("flashback_haze"), "flashback_haze")
        self.assertEqual(PR.relight_text("flashback_haze", "location"),
                         "Change only the light: hazy amber memory")

    def test_what_is_refused(self):
        for kind, label, fields, why in (("framing", "x", {}, "not a 'framing'"),
                                         ("look", " ", {"text": "t"}, "needs a name"),
                                         ("look", "x", {}, "look line"),
                                         ("relight", "x", {}, "instruction")):
            with self.subTest(why), self.assertRaisesRegex(PR.PresetError, why):
                PR.save_own(kind, label, fields)
        with self.assertRaisesRegex(PR.PresetError, "no look preset 'nope'"):
            PR.save_own("look", "x", {"text": "t"}, pid="nope")
        self.assertIsNone(PR.image_path("own/look/../../settings.json"))

    def test_the_routes(self):
        ctx = mock.Mock()
        code, p = A.post_preset_own(ctx, {"kind": "look", "label": "Mine", "text": "a look"})
        self.assertEqual((code, p["id"]), (200, "mine"))
        self.assertEqual(A.post_preset_own(ctx, {"kind": "look", "label": "Mine"})[0], 400)
        self.assertEqual(A.post_preset_own_delete(ctx, {"kind": "look", "id": "mine"})[0], 200)
        self.assertEqual(A.post_preset_own_delete(ctx, {"kind": "look", "id": "mine"})[0], 400)
