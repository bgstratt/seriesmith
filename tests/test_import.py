"""
Series import (source.import_series, POST /seriesmith/import): a series config and
a stack of scripts in, one episode folder per script out, named by its header.
"""
from __future__ import annotations

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

from seriesmith import api as A  # noqa: E402
from seriesmith import source as S  # noqa: E402
from test_render import FIXTURE  # noqa: E402


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class ImportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.shows = os.path.join(self._tmp.name, "Shows")
        os.makedirs(self.shows)
        self.series = read(os.path.join(FIXTURE, "series.json"))
        script = read(os.path.join(FIXTURE, "script.md"))
        first = script.splitlines()[0]
        self.assertTrue(first.startswith("= "), first)
        # three episodes of one series: the fixture's script under three headers
        self.scripts = [(f"episode_{n}.md", script.replace(first, f"= ep0{n}  Part {n}", 1))
                        for n in (1, 2, 3)]

    def test_each_script_becomes_an_episode_named_by_its_header(self):
        res = S.import_series(self.shows, self.series, self.scripts, show="Kitchen")
        self.assertEqual(res["show"], os.path.join(self.shows, "Kitchen"))
        self.assertEqual([e["name"] for e in res["episodes"]], ["ep01", "ep02", "ep03"])
        for e in res["episodes"]:
            self.assertTrue(os.path.isfile(os.path.join(e["ep"], "series.json")))
            self.assertTrue(os.path.isfile(os.path.join(e["ep"], f"{e['name']}.md")))
            self.assertTrue(e["check"]["ok"], e["check"])
        self.assertEqual(json.loads(read(os.path.join(res["episodes"][0]["ep"], "series.json"))),
                         json.loads(self.series))
        self.assertEqual([os.path.basename(p) for p in S.episodes_under(res["show"])],
                         ["ep01", "ep02", "ep03"])

    def test_an_episode_already_there_is_left_alone(self):
        S.import_series(self.shows, self.series, self.scripts[:1])
        res = S.import_series(self.shows, self.series, self.scripts)
        self.assertEqual([e["name"] for e in res["episodes"]], ["ep02", "ep03"])
        self.assertEqual([s["name"] for s in res["skipped"]], ["ep01"])

    def test_no_header_falls_back_to_the_file_name_and_twins_are_errors(self):
        body = "\n".join(self.scripts[0][1].splitlines()[1:])
        self.assertEqual(S.episode_id(body, "C:/x/pilot.md"), "pilot")
        res = S.import_series(self.shows, self.series,
                              [("a.md", self.scripts[0][1]), ("b.md", self.scripts[0][1])])
        self.assertEqual([e["name"] for e in res["episodes"]], ["ep01"])
        self.assertIn("ep01 too", res["errors"][0]["error"])

    def test_an_episode_can_bring_its_own_config(self):
        own = json.loads(self.series)
        own["subjects"]["newcomer"] = {"kind": "character", "name": "Newcomer",
                                       "design": "a tall stranger in a grey coat"}
        name, text = self.scripts[1]
        res = S.import_series(self.shows, self.series,
                              [self.scripts[0], (name, text, json.dumps(own))])
        by = {e["name"]: e for e in res["episodes"]}
        self.assertEqual((by["ep01"]["own_config"], by["ep02"]["own_config"]), (False, True))
        cfg = json.loads(read(os.path.join(by["ep02"]["ep"], "series.json")))
        self.assertIn("newcomer", cfg["subjects"])
        # every episode its own: no shared config needed
        res = S.import_series(self.shows, None, [("x.md", self.scripts[2][1], self.series)])
        self.assertEqual([e["name"] for e in res["episodes"]], ["ep03"])
        # nothing at all for one: an error for that one only
        res = S.import_series(os.path.join(self.shows), None,
                              [("y.md", self.scripts[0][1].replace("= ep01", "= ep09", 1))])
        self.assertIn("no series config", res["errors"][0]["error"])

    def test_a_file_without_a_header_isnt_a_script(self):
        body = "# Cast" + chr(10) + self.scripts[0][1]
        res = S.import_series(self.shows, self.series, [("CAST.md", body)])
        self.assertEqual(res["episodes"], [])
        self.assertIn("isn't an episode header", res["errors"][0]["error"])

    def test_not_a_series_config(self):
        with self.assertRaises(S.SourceError):
            S.import_series(self.shows, "{}", self.scripts)

    def test_the_route(self):
        ctx = A.Context(os.path.join(self._tmp.name, "user"),
                        env={"SERIESMITH_ROOTS": self.shows}, model_resolve=None)
        status, res = A.post_import(ctx, {"parent": self.shows, "show": "Kitchen",
                                          "series": self.series,
                                          "scripts": [{"name": n, "text": t}
                                                      for n, t in self.scripts]})
        self.assertEqual(status, 200, res)
        self.assertEqual(len(res["episodes"]), 3)
        status, res = A.post_import(ctx, {"parent": os.path.dirname(self.shows),
                                          "series": self.series, "scripts": []})
        self.assertIn(status, (400, 403))


if __name__ == "__main__":
    unittest.main()
