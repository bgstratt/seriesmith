"""
Caches kept between server runs (seriesmith/diskcache.py): a file's sha1 and
an episode's live files survive a restart (a fresh process reads them from
disk), and a changed file is never answered from them.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import diskcache as DC  # noqa: E402
from seriesmith import takes as T  # noqa: E402


class DiskCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SERIESMITH_CACHE_DIR": os.path.join(self._tmp.name, "cache")})
        self.env.start()
        DC._STORES.clear()
        T._SHA1_CACHE.clear()

    def tearDown(self):
        self.env.stop()
        DC._STORES.clear()
        T._SHA1_CACHE.clear()
        self._tmp.cleanup()

    def file(self, name: str, data: bytes) -> str:
        p = os.path.join(self._tmp.name, name)
        with open(p, "wb") as fh:
            fh.write(data)
        os.utime(p, (1_700_000_000, 1_700_000_000))        # old enough to be kept
        return p

    def restart(self):
        DC.save()
        DC._STORES.clear()                                  # a fresh process: memory empty
        T._SHA1_CACHE.clear()

    def test_a_sha1_survives_a_restart_and_a_change_is_hashed_again(self):
        p = self.file("a.png", b"one")
        first = T.file_sha1(p)
        self.restart()
        with open(os.path.join(self._tmp.name, "cache", "sha1.json"), encoding="utf-8") as fh:
            self.assertIn(os.path.normcase(os.path.abspath(p)), json.load(fh))
        with mock.patch.object(T.hashlib, "sha1", side_effect=AssertionError("hashed again")):
            self.assertEqual(T.file_sha1(p), first)          # from disk, not hashed
        self.restart()
        with open(p, "wb") as fh:
            fh.write(b"two, longer")
        os.utime(p, (1_700_000_100, 1_700_000_100))
        self.assertNotEqual(T.file_sha1(p), first)

    def test_an_unreadable_store_is_an_empty_one(self):
        os.makedirs(os.path.join(self._tmp.name, "cache"))
        with open(os.path.join(self._tmp.name, "cache", "sha1.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(DC.store("sha1"), {})
        self.assertEqual(T.file_sha1(self.file("b.png", b"x")), T.file_sha1(os.path.join(self._tmp.name, "b.png")))


if __name__ == "__main__":
    unittest.main()
