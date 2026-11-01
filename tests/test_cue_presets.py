"""
The cue window's presets (seriesmith/presets/cue.json): each a worked example of a
cue's fields, its sections as shares of the cue. Each one's shape sums to the whole,
its energies and levels are in range, its meter and key read, and a spec made from
it as the editor makes one (lib/cue.ts applyCuePreset: whole bars from the shares,
the orchestra per bar) is one cue.check_spec takes; the route lists them.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import api as A  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import presets as PR  # noqa: E402

# the key picker's (lib/cue.ts KEYS)
NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
KEYS = {f"{n} {m}" for n in NOTES for m in ("major", "minor")}


def bars_of(shares: list[float], bars: int) -> list[int]:
    """Whole bars from the shares, one at least each, summing to `bars` (the editor's presetBars)."""
    raw = [s * bars for s in shares]
    out = [max(1, int(x)) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - int(raw[i]), reverse=True)
    k = 0
    while sum(out) < bars:
        out[order[k % len(order)]] += 1
        k += 1
    while sum(out) > bars:
        i = max(range(len(out)), key=lambda j: out[j])
        out[i] -= 1
    return out


def spec_of(p: dict, bars: int) -> dict:
    f = p["fields"]
    counts = bars_of([s["share"] for s in f["shape"]], bars)
    sections, orchestra, at = [], {}, 0
    for s, n in zip(f["shape"], counts):
        sections.append({k: v for k, v in (("name", s["name"]), ("bars", n), ("words", s.get("words")),
                                           ("from", s["from"]), ("to", s["to"])) if v is not None})
        for fam, lv in (s.get("orchestra") or {}).items():
            row = orchestra.setdefault(fam, [0] * bars)
            row[at:at + n] = [lv] * n
        at += n
    spec = {"id": "m01", "in": {"shot": "sh010", "frame": 0}, "out": {"shot": "sh030", "frame": 100},
            "kind": f["kind"], "style": f["style"], "bpm": f["bpm"], "sections": sections, "orchestra": orchestra}
    for k in ("meter", "key"):
        if f.get(k):
            spec[k] = f[k]
    return spec


class CuePresetsTest(unittest.TestCase):
    def setUp(self):
        self.presets = PR.listing("cue")

    def test_each_is_a_cue_the_server_takes(self):
        self.assertGreaterEqual(len(self.presets), 10)
        self.assertEqual(len({p["id"] for p in self.presets}), len(self.presets))
        for p in self.presets:
            with self.subTest(p["id"]):
                f = p["fields"]
                self.assertTrue(p["label"] and p["hint"])
                self.assertIn(p["group"], ("Score", "Song"))
                self.assertEqual(p["group"].lower(), f["kind"])
                self.assertTrue(f["style"].strip())
                self.assertTrue(30 <= f["bpm"] <= 240)
                CU.parse_meter(f.get("meter", 4))
                if "key" in f:
                    self.assertIn(f["key"], KEYS)
                self.assertAlmostEqual(sum(s["share"] for s in f["shape"]), 1, delta=0.01)
                for s in f["shape"]:
                    self.assertTrue(s["name"].strip() and s["words"].strip())
                    self.assertTrue(s["share"] > 0)
                    for k in ("from", "to"):
                        self.assertTrue(1 <= s[k] <= 5, (s["name"], k))
                    for fam, lv in (s.get("orchestra") or {}).items():
                        self.assertTrue(fam.strip() and isinstance(lv, int) and 0 <= lv <= 3, (s["name"], fam))
                for bars in (16, 3, 40):
                    n = min(bars, len(f["shape"]))
                    spec = spec_of({**p, "fields": {**f, "shape": f["shape"][:n]}}, bars)
                    got = CU.check_spec(spec)
                    self.assertEqual(sum(s["bars"] for s in got["sections"]), bars)
                    self.assertEqual(got.get("kind", "score"), f["kind"])

    def test_the_route_lists_them(self):
        ctx = A.Context(tempfile.mkdtemp(), "http://127.0.0.1:0", env={})
        status, data = A.get_presets(ctx, {"kind": "cue"})
        self.assertEqual((status, set(data)), (200, {"cue"}))
        self.assertEqual([p["id"] for p in data["cue"]], [p["id"] for p in self.presets])
        self.assertNotIn("image", data["cue"][0])


if __name__ == "__main__":
    unittest.main()
