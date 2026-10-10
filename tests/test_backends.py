"""
The backend layer (seriesmith/backends): the job lifecycle every backend
shares, the settings that say where backends are, and a live round trip
through comfy-api-proxy when one is running (skipped otherwise).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import backends as B  # noqa: E402
from seriesmith.backends import smoke  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.backends.router import output_type, urls_in  # noqa: E402
from seriesmith.settings import load_settings  # noqa: E402

try:
    import comfy_sdk
except ImportError:                          # pragma: no cover
    comfy_sdk = None


def temp_file(test: unittest.TestCase, data: bytes = b"x", suffix: str = ".png") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    test.addCleanup(os.remove, path)
    return path


class FilesTest(unittest.TestCase):
    def test_a_missing_input_is_caught_when_it_is_named(self):
        with self.assertRaises(B.BackendError):
            B.File(os.path.join(HERE, "no_such_picture.png"))

    def test_every_file_in_a_graph_or_arguments_is_found(self):
        a, b = B.File(temp_file(self)), B.File(temp_file(self))
        value = {"1": {"inputs": {"image": a}}, "args": {"images": [b, "keep"], "n": 2}}
        found = [f for _, _, f in B.files_in(value)]
        self.assertEqual(found, [a, b])


class FakeRunTest(unittest.TestCase):
    def test_a_run_reports_progress_then_its_outputs(self):
        fb = FakeBackend(outputs={"9": [("sh010.mp4", "video", b"mp4!")]},
                         progress=[0.25, 0.5, 1.0])
        pic = temp_file(self)
        run = fb.submit({"1": {"class_type": "LoadImage", "inputs": {"image": B.File(pic)}}})
        seen, statuses = [], []
        self.assertEqual(run.watch(lambda p: seen.append(p.value), statuses.append), "succeeded")
        self.assertEqual(seen, [0.25, 0.5, 1.0])
        self.assertEqual(statuses, ["running", "succeeded"])
        self.assertEqual(fb.uploaded, [pic])
        (out,) = run.outputs()
        self.assertEqual((out.node, out.name, out.type), ("9", "sh010.mp4", "video"))
        with tempfile.TemporaryDirectory() as d:
            path = out.save(os.path.join(d, "renders", "sh010", "t1.mp4"))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"mp4!")

    def test_a_failed_run_has_no_outputs_and_says_why(self):
        run = FakeBackend(final="failed", error="out of memory").submit({})
        self.assertEqual(run.watch(), "failed")
        self.assertEqual((run.outputs(), run.error), ([], "out of memory"))

    def test_a_workflow_backend_refuses_a_model_call_and_back(self):
        with self.assertRaises(B.BackendError):
            B.Backend().call("fal/seedance", {})
        with self.assertRaises(B.BackendError):
            B.Backend().submit({})


class SettingsTest(unittest.TestCase):
    def test_defaults_without_a_file(self):
        s = load_settings(os.path.join(HERE, "no_such_settings.json"), env={})
        self.assertEqual((s.local_url, s.comfyui_url, s.api_key, s.path),
                         ("http://127.0.0.1:8189", "http://127.0.0.1:8188", None, None))

    def test_the_environment_wins_over_the_file(self):
        path = temp_file(self, json.dumps({
            "local_url": "http://box:8189/", "api_key": "from-file",
            "deployments": {"minimax_h3_ref2va": "https://h3.run.comfy.app/"}}).encode(),
            suffix=".json")
        s = load_settings(path, env={"COMFY_API_KEY": "from-env"})
        self.assertEqual(s.local_url, "http://box:8189")
        self.assertEqual(s.api_key, "from-env")
        self.assertEqual(s.deployments, {"minimax_h3_ref2va": "https://h3.run.comfy.app"})
        self.assertEqual(s.describe()["api_key"], "set")

    def test_backends_follow_the_settings(self):
        s = load_settings(os.path.join(HERE, "none.json"), env={})
        self.assertEqual(list(B.available(s)), ["local"])
        s.api_key, s.deployments = "k", {"wan22_i2v": "https://wan.run.comfy.app"}
        found = B.available(s)
        self.assertEqual(list(found), ["local", "cloud", "router", "deployment:wan22_i2v"])
        self.assertEqual([b.kind for b in found.values()],
                         ["local", "cloud", "router", "deployment"])


@unittest.skipUnless(comfy_sdk, "comfy-sdk not installed")
class SdkClientTest(unittest.TestCase):
    def test_a_client_is_aimed_without_leaving_the_environment_changed(self):
        from seriesmith.backends.comfy import sdk_client
        before = {k: os.environ.get(k) for k in ("COMFY_BASE_URL", "COMFY_API_KEY")}
        os.environ["COMFY_API_KEY"] = "user-cloud-key"
        try:
            c = sdk_client("http://127.0.0.1:8189", None)
            self.assertIn("127.0.0.1:8189", repr(c))
            # the user's cloud key is not handed to a local proxy
            self.assertIn("authenticated=False", repr(c))
            self.assertEqual(os.environ.get("COMFY_API_KEY"), "user-cloud-key")
            self.assertEqual(os.environ.get("COMFY_BASE_URL"), before["COMFY_BASE_URL"])
        finally:
            for k, v in before.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class RouterResultTest(unittest.TestCase):
    def test_every_url_in_a_provider_result_is_an_output(self):
        result = {"video": {"url": "https://cdn.example/out/a.mp4"},
                  "images": [{"url": "https://cdn.example/b.png"}, "https://cdn.example/b.png"],
                  "seed": 7, "note": "not a url"}
        urls = list(urls_in(result))
        self.assertEqual(urls, ["https://cdn.example/out/a.mp4", "https://cdn.example/b.png"])
        self.assertEqual([output_type(u) for u in urls], ["video", "image"])


class SmokeTest(unittest.TestCase):
    def test_the_round_trip_checks_what_comes_back(self):
        fb = FakeBackend(outputs={"3": [("seriesmith_smoke_00001_.png", "image",
                                         smoke.png(48, 32, smoke.SMOKE_OUT))]})
        with tempfile.TemporaryDirectory() as d:
            out = smoke.round_trip(fb, d)
            self.assertTrue(os.path.isfile(out))
        (graph,) = fb.submitted
        self.assertEqual(graph["1"]["class_type"], "LoadImage")
        self.assertIsInstance(graph["1"]["inputs"]["image"], B.File)

    def test_a_wrong_picture_is_a_failure(self):
        for wrong in (smoke.png(8, 8, smoke.SMOKE_OUT), smoke.png(48, 32, smoke.SMOKE_IN)):
            fb = FakeBackend(outputs={"3": [("x.png", "image", wrong)]})
            with tempfile.TemporaryDirectory() as d, self.assertRaises(B.BackendError):
                smoke.round_trip(fb, d)


def _local_backend():
    if comfy_sdk is None:
        return None
    from seriesmith.backends.comfy import ComfyBackend
    b = ComfyBackend("local", "local", load_settings().local_url, None)
    return b if b.ping() is None else None


@unittest.skipUnless(_local_backend(), "no comfy-api-proxy answering (seriesmith backends)")
class LiveLocalTest(unittest.TestCase):
    def test_a_picture_goes_up_through_comfyui_and_back(self):
        with tempfile.TemporaryDirectory() as d:
            out = smoke.round_trip(_local_backend(), d)
            with open(out, "rb") as fh:
                self.assertEqual(smoke.png_size(fh.read()), (48, 32))


if __name__ == "__main__":
    unittest.main()
