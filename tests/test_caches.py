"""
The caches that keep the episode status fast: takes.file_sha1 (a ref's sha1,
kept while its size and mtime hold) and targets._folders (the target listing,
kept for a couple of seconds); and ComfyUI's /object_info, kept per address
for the dialogs (api.comfy_object_info). Each must give the answer an uncached
call would.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seriesmith import api as A  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402


def sha1_of(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


class FileSha1CacheTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "ref.png")
        T._SHA1_CACHE.clear()

    def tearDown(self):
        T._SHA1_CACHE.clear()
        self._tmp.cleanup()

    def write(self, data: bytes, age: float) -> None:
        with open(self.path, "wb") as fh:
            fh.write(data)
        t = time.time() - age
        os.utime(self.path, (t, t))

    def test_missing_file(self):
        self.assertIsNone(T.file_sha1(self.path))

    def test_unchanged_file_is_not_read_again(self):
        self.write(b"aaaa", age=60)
        self.assertEqual(T.file_sha1(self.path), sha1_of(b"aaaa"))
        st = os.stat(self.path)
        key = os.path.normcase(os.path.abspath(self.path))
        # poison the entry: a hit must come from the cache, not the file
        T._SHA1_CACHE[key] = (st.st_size, st.st_mtime_ns, "cached")
        self.assertEqual(T.file_sha1(self.path), "cached")

    def test_changed_mtime_is_hashed_again(self):
        self.write(b"aaaa", age=60)
        T.file_sha1(self.path)
        self.write(b"bbbb", age=30)               # same size, new mtime
        self.assertEqual(T.file_sha1(self.path), sha1_of(b"bbbb"))

    def test_changed_size_is_hashed_again(self):
        self.write(b"aaaa", age=60)
        T.file_sha1(self.path)
        self.write(b"aaaaaa", age=60)              # same mtime, new size
        self.assertEqual(T.file_sha1(self.path), sha1_of(b"aaaaaa"))

    def test_a_fresh_write_is_never_cached(self):
        # two writes inside the timer's resolution can share an mtime
        self.write(b"aaaa", age=0)
        T.file_sha1(self.path)
        self.assertEqual(T._SHA1_CACHE, {})

    def test_deleted_file(self):
        self.write(b"aaaa", age=60)
        T.file_sha1(self.path)
        os.remove(self.path)
        self.assertIsNone(T.file_sha1(self.path))


class FoldersCacheTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.show = self._tmp.name
        with open(os.path.join(self.show, "series.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")
        TG.clear_thread_roots()
        TG.forget_targets()

    def tearDown(self):
        TG.clear_thread_roots()
        TG.forget_targets()
        self._tmp.cleanup()

    def add_custom(self, tid: str) -> None:
        d = os.path.join(self.show, TG.CUSTOM_DIR, tid)
        os.makedirs(d)
        with open(os.path.join(d, "target.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": tid, "kind": "video"}, fh)

    def ids(self) -> set[str]:
        return {n for _, n, _ in TG._folders(self.show)}

    def test_listing_is_reused_and_forget_clears_it(self):
        self.assertNotIn("mine_x", self.ids())
        self.add_custom("mine_x")
        self.assertNotIn("mine_x", self.ids())      # cached
        TG.forget_targets()
        self.assertIn("mine_x", self.ids())

    def test_listing_expires(self):
        self.ids()
        self.add_custom("mine_y")
        key = (self.show, TG.thread_roots())
        stamp, folders = TG._FOLDERS[key]
        TG._FOLDERS[key] = (stamp - TG.FOLDERS_TTL - 1, folders)
        self.assertIn("mine_y", self.ids())

    def test_thread_roots_are_part_of_the_key(self):
        self.add_custom("mine_z")
        self.assertNotIn("mine_z", {n for _, n, _ in TG._folders(None)})
        TG.add_thread_root(self.show)               # a new key: scanned, not reused
        self.assertIn("mine_z", {n for _, n, _ in TG._folders(None)})
        TG.clear_thread_roots()
        self.assertNotIn("mine_z", {n for _, n, _ in TG._folders(None)})

    def test_callers_cannot_change_the_cached_listing(self):
        first = TG._folders(self.show)
        first.clear()
        self.assertTrue(TG._folders(self.show))


if __name__ == "__main__":
    unittest.main()


class _InfoFixture:
    """A ComfyUI whose /object_info is `self.answer` (None: away), each ask
    counted in `self.asked`."""

    def setUp(self):
        from unittest import mock
        self.asked = []
        self.answer = {"KSampler": {}}

        def object_info(comfy):
            self.asked.append(comfy.base)
            if self.answer is None:
                raise RuntimeError("ComfyUI away")
            return dict(self.answer)
        patch = mock.patch.object(J.Comfy, "object_info", object_info)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(A.forget_comfy)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def ctx(self, url="http://127.0.0.1:8188"):
        return A.Context(self._tmp.name, url, env={}, model_resolve=None)


class ObjectInfoCacheTest(_InfoFixture, unittest.TestCase):
    """/object_info is a second and megabytes: asked once per ComfyUI for
    READY_TTL, again when told (fresh, forget_comfy), never kept when it fails."""

    def test_asked_once_per_comfyui_while_fresh(self):
        a = A.comfy_object_info(self.ctx())
        b = A.comfy_object_info(self.ctx())                  # a new request, its own client
        self.assertIs(a, b)
        A.comfy_object_info(self.ctx("http://127.0.0.1:8189"))
        self.assertEqual(self.asked, ["http://127.0.0.1:8188", "http://127.0.0.1:8189"])

    def test_fresh_forget_and_age_ask_again(self):
        A.comfy_object_info(self.ctx())
        A.comfy_object_info(self.ctx(), fresh=True)
        A.forget_comfy()
        A.comfy_object_info(self.ctx())
        old = A._INFO["http://127.0.0.1:8188"]
        A._INFO["http://127.0.0.1:8188"] = (old[0] - A.READY_TTL - 1, old[1])
        A.comfy_object_info(self.ctx())
        self.assertEqual(len(self.asked), 4)

    def test_a_failure_is_not_kept(self):
        self.answer = None
        with self.assertRaises(RuntimeError):
            A.comfy_object_info(self.ctx())
        self.answer = {"KSampler": {}}
        self.assertEqual(A.comfy_object_info(self.ctx()), {"KSampler": {}})
        self.assertEqual(len(self.asked), 2)

    def test_a_fake_client_is_always_asked(self):
        class Fake:
            def object_info(self):
                return {"Fake": {}}
        ctx = A.Context(self._tmp.name, "http://127.0.0.1:8188", comfy=Fake(), env={},
                        model_resolve=None)
        self.assertEqual(A.comfy_object_info(ctx), {"Fake": {}})
        self.assertNotIn("http://127.0.0.1:8188", A._INFO)

    def test_missing_is_asked_again_before_it_is_believed(self):
        A.comfy_object_info(self.ctx())                       # kept: no SeedVR2 yet
        self.answer = {"KSampler": {}, "SeedVR2": {}}         # then it went in
        missing = A.missing_on_comfy(self.ctx(), lambda info: [] if "SeedVR2" in info
                                     else ["SeedVR2"])
        self.assertEqual(missing, [])
        self.assertEqual(len(self.asked), 2)


class KeptJsonTest(unittest.TestCase):
    """takes.read_json_kept: a file read over and over (a shotlist) is parsed
    once while its size and mtime hold, and the parse is shared."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(T.forget_kept)
        self.path = os.path.join(self._tmp.name, "shotlist.json")

    def write(self, data, age=10.0):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        t = time.time() - age
        os.utime(self.path, (t, t))

    def test_parsed_once_and_shared(self):
        self.write({"fps": 24})
        a = T.read_json_kept(self.path)
        self.assertIs(T.read_json_kept(self.path), a)

    def test_a_rewrite_of_the_same_size_is_read(self):
        self.write({"fps": 24})
        T.read_json_kept(self.path)
        self.write({"fps": 12}, age=5.0)                     # same size, another mtime
        self.assertEqual(T.read_json_kept(self.path), {"fps": 12})

    def test_a_file_just_written_is_not_kept(self):
        self.write({"fps": 24}, age=0.0)
        a = T.read_json_kept(self.path)
        self.assertIsNot(T.read_json_kept(self.path), a)     # parsed again: it may change yet

    def test_gone_or_broken_is_raised_not_kept(self):
        with self.assertRaises(FileNotFoundError):
            T.read_json_kept(self.path)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write('{"fps": 2')
        with self.assertRaises(ValueError):
            T.read_json_kept(self.path)
        self.write({"fps": 24})
        self.assertEqual(T.read_json_kept(self.path), {"fps": 24})

    def test_a_copy_to_change_is_its_own(self):
        self.write({"shots": {"sh010": {"seed": 1}}})
        mine = T.read_json_copy(self.path)
        mine["shots"]["sh010"]["seed"] = 2
        self.assertEqual(T.read_json_kept(self.path)["shots"]["sh010"]["seed"], 1)
        self.assertEqual(T.read_json_copy(os.path.join(self._tmp.name, "none.json"), {}), {})

    def test_read_picks_never_changes_the_shared_parse(self):
        from seriesmith import refs as R
        p = os.path.join(self._tmp.name, R.PICKS_FILE)
        os.makedirs(os.path.dirname(p))
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"refs": {"subject:ada": {"take": 2}}}, fh)        # no "version"
        os.utime(p, (time.time() - 10, time.time() - 10))
        got = R.read_picks(self._tmp.name)
        self.assertEqual(got["version"], 1)
        self.assertNotIn("version", T.read_json_kept(p))
        self.assertEqual(R.read_picks(os.path.join(self._tmp.name, "nowhere")),
                         {"version": 1, "refs": {}})


class RefreshBehindTest(_InfoFixture, unittest.TestCase):
    """On a server (REFRESH_BEHIND), an answer past READY_TTL is given at once
    and asked again behind it; an install (forget_comfy) still waits."""

    def setUp(self):
        super().setUp()
        A.REFRESH_BEHIND = True
        self.addCleanup(setattr, A, "REFRESH_BEHIND", False)

    def age(self, url="http://127.0.0.1:8188"):
        t, info = A._INFO[url]
        A._INFO[url] = (t - A.READY_TTL - 1, info)

    def settle(self):
        for t in [t for t in __import__("threading").enumerate() if t.name == "seriesmith-refresh"]:
            t.join(5)

    def test_an_old_answer_is_given_and_asked_again_behind_it(self):
        first = A.comfy_object_info(self.ctx())
        self.age()
        self.answer = {"KSampler": {}, "SeedVR2": {}}
        self.assertIs(A.comfy_object_info(self.ctx()), first)    # at once: the kept one
        self.settle()
        self.assertEqual(len(self.asked), 2)
        self.assertIn("SeedVR2", A.comfy_object_info(self.ctx()))  # the refreshed one
        self.assertEqual(len(self.asked), 2)

    def test_after_an_install_the_next_answer_waits(self):
        A.comfy_object_info(self.ctx())
        self.age()
        A.forget_comfy()
        self.answer = {"KSampler": {}, "SeedVR2": {}}
        self.assertIn("SeedVR2", A.comfy_object_info(self.ctx()))

    def test_a_refresh_from_before_an_install_is_not_kept(self):
        import threading
        A.comfy_object_info(self.ctx())
        self.age()
        gate, started = threading.Event(), threading.Event()
        real = self.answer

        def slow(comfy):
            started.set()
            gate.wait(5)
            return {"Old": {}}
        from unittest import mock
        with mock.patch.object(J.Comfy, "object_info", slow):
            A.comfy_object_info(self.ctx())                      # starts the refresh
            started.wait(5)
            A.forget_comfy()                                     # an install meanwhile
            gate.set()
            self.settle()
        self.assertNotIn("http://127.0.0.1:8188", A._INFO)       # its old answer dropped
        self.answer = real
