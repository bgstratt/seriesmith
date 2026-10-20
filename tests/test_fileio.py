"""
seriesmith/core/fileio: files written whole or not at all, and read back. The
one place for it (a dozen near-copies before, some writing CRLF, some sharing
a temp name between threads, some without the Windows retry).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith.core import fileio as F  # noqa: E402


class FileioTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = self._tmp.name

    def p(self, *parts):
        return os.path.join(self.d, *parts)

    def raw(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def leftovers(self, folder=None):
        return [n for n in os.listdir(folder or self.d) if n.startswith(".tmp_")]

    def test_json_is_lf_utf8_with_the_callers_layout(self):
        F.write_json(self.p("a", "b.json"), {"name": "Zoë", "n": [1, 2]})     # folders made
        self.assertEqual(self.raw(self.p("a", "b.json")),
                         '{\n  "name": "Zoë",\n  "n": [\n    1,\n    2\n  ]\n}\n'.encode())
        F.write_json(self.p("c.json"), {"a": 1}, indent=None, end="", ensure_ascii=True)
        self.assertEqual(self.raw(self.p("c.json")), b'{"a": 1}')
        F.write_json(self.p("d.json"), {"t": object()}, indent=1, end="", default=lambda o: "x")
        self.assertEqual(self.raw(self.p("d.json")), b'{\n "t": "x"\n}')
        self.assertEqual(self.leftovers(), [])

    def test_text_and_bytes_and_copy(self):
        F.write_text(self.p("t.md"), "one\ntwo\n")
        self.assertEqual(self.raw(self.p("t.md")), b"one\ntwo\n")              # never CRLF
        F.write_bytes(self.p("b.bin"), b"\x00\x01")
        F.copy(self.p("b.bin"), self.p("sub", "c.bin"))
        self.assertEqual(self.raw(self.p("sub", "c.bin")), b"\x00\x01")
        self.assertEqual(self.leftovers() + self.leftovers(self.p("sub")), [])

    def test_a_failed_write_leaves_the_old_file_and_no_temp(self):
        F.write_json(self.p("x.json"), {"v": 1})
        with self.assertRaises(TypeError):
            F.write_json(self.p("x.json"), {"v": object()})            # not JSON
        with self.assertRaises(FileNotFoundError):
            F.copy(self.p("missing"), self.p("x.json"))
        self.assertEqual(json.loads(self.raw(self.p("x.json"))), {"v": 1})
        self.assertEqual(self.leftovers(), [])

    def test_a_file_in_use_is_waited_out(self):
        real, calls = os.replace, []

        def busy(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("in use")
            return real(a, b)
        with mock.patch.object(os, "replace", busy), mock.patch.object(F, "SHARING_WAIT", 0):
            F.write_json(self.p("y.json"), {"v": 2})
        self.assertEqual((len(calls), F.read_json(self.p("y.json"))), (3, {"v": 2}))

    def test_temp_names_are_each_writers_own(self):
        names = {F.temp_beside(self.p("same.json")) for _ in range(50)}
        self.assertEqual(len(names), 50)
        self.assertTrue(all(n.endswith("_same.json") for n in names))
        self.assertTrue(F.temp_beside(self.p("x.png"), ".jpg").endswith(".jpg"))

        errors = []

        def write(i):
            try:
                for _ in range(20):
                    F.write_json(self.p("busy.json"), {"i": i})
            except Exception as e:                       # noqa: BLE001
                errors.append(e)
        threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertIn(F.read_json(self.p("busy.json"))["i"], range(4))

    def test_reads(self):
        self.assertEqual(F.read_json(self.p("none.json"), {"d": 1}), {"d": 1})
        with open(self.p("bad.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        with self.assertRaises(ValueError):
            F.read_json(self.p("bad.json"))
        self.assertEqual(F.read_json_or(self.p("bad.json"), {}), {})
        self.assertEqual(F.read_json_or(self.p("none.json"), None), None)
        F.write_json(self.p("list.json"), [1])
        self.assertEqual(F.read_json_or(self.p("list.json"), {}, want=dict), {})
        self.assertEqual(F.read_json_or(self.p("list.json"), {}), [1])

    def test_digest_matches_hashlib(self):
        data = os.urandom(3 << 20)                               # more than one chunk
        F.write_bytes(self.p("v.bin"), data)
        self.assertEqual(F.file_digest(self.p("v.bin")), hashlib.sha1(data).hexdigest())
        self.assertEqual(F.file_digest(self.p("v.bin"), "sha256"),
                         hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
