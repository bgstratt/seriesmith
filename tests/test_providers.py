"""
Providers of the user's own, run from their definitions (seriesmith/providers.py,
backends/http.py), and a model's API reference read into a target (seriesmith/apispec.py;
docs/PLAN.md step 15.4). Against a local server answering as each API's docs say; nothing paid.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import apispec as AS  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import promptview as PV  # noqa: E402
from seriesmith import providers as PR  # noqa: E402
from seriesmith import settings as S  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File, available  # noqa: E402
from seriesmith.backends.http import HttpBackend, fill, pick  # noqa: E402
from seriesmith.backends.router import ROUTING  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402

KEY = "sk-secret-key"
ATLAS_EXAMPLE = {"model": "bytedance/seedance-2.5/reference-to-video", "prompt": "a cat",
                 "reference_images": ["https://x/a.png"], "duration": 5, "resolution": "720p",
                 "ratio": "16:9", "generate_audio": True, "seed": 1}


class Fake:
    """A provider: answers each (method, path) from `routes`, remembers what it was asked."""

    def __init__(self):
        self.calls, self.routes = [], {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                path = self.path
                fake.calls.append({"method": self.command, "path": path, "headers": self.headers, "body": body})
                got = fake.routes.get((self.command, path.split("?")[0]))
                got = got(fake.calls[-1]) if callable(got) else got
                if got is None:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'{"message":"no"}')
                    return
                status, data, headers = got if isinstance(got, tuple) else (200, got, {})
                raw = data if isinstance(data, bytes) else json.dumps(data).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            do_GET = do_POST = do_DELETE = answer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class WithFake(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pic = os.path.join(self.tmp.name, "pic.png")
        with open(self.pic, "wb") as fh:
            fh.write(b"\x89PNG picture")

    def atlas(self, **over):
        with open(os.path.join(os.path.dirname(PR.__file__), "presets", "providers", "atlas.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        d["base_url"] = self.fake.url + "/api/v1"
        d["steps"][1]["until"]["every"] = 0.01
        d.update(over)
        return HttpBackend(d, KEY)

    def answers_for_atlas(self, status="completed", error=None, outputs=None):
        f = self.fake
        f.routes[("POST", "/api/v1/model/uploadMedia")] = {"url": "https://files.example/pic.png"}
        f.routes[("POST", "/api/v1/model/generateVideo")] = {"code": 0, "data": {"id": "p1"}}
        f.routes[("GET", "/api/v1/model/prediction/p1")] = {
            "data": {"id": "p1", "status": status, "error": error,
                     "outputs": [f.url + "/out/v.mp4"] if outputs is None else outputs}}
        f.routes[("GET", "/out/v.mp4")] = b"video bytes"


class AtlasSeedance(WithFake):
    """Upload first, then generate, then poll, then a link with no key."""

    def run_it(self):
        b = self.atlas()
        args = {"prompt": "a cat", "reference_images": [File(self.pic)],
                ROUTING: {"values": {"endpoint": "generateVideo", "type": "video"}}}
        run = b.call("bytedance/seedance-2.5/reference-to-video", args)
        return run, run.watch()

    def test_the_whole_way(self):
        self.answers_for_atlas()
        run, status = self.run_it()
        self.assertEqual(status, "succeeded")
        sent = next(c for c in self.fake.calls if c["path"].endswith("generateVideo"))
        body = json.loads(sent["body"])
        self.assertEqual(body["model"], "bytedance/seedance-2.5/reference-to-video")
        self.assertEqual(body["reference_images"], ["https://files.example/pic.png"])
        self.assertNotIn(ROUTING, body)
        (out,) = run.outputs()
        self.assertEqual(out.type, "video")
        path = out.save(os.path.join(self.tmp.name, "v.mp4"))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"video bytes")

    def test_the_upload_goes_as_a_form_with_the_key(self):
        self.answers_for_atlas()
        self.run_it()
        up = self.fake.calls[0]
        self.assertTrue(up["path"].endswith("uploadMedia"))
        self.assertIn("multipart/form-data", up["headers"]["Content-Type"])
        self.assertIn(b'name="file"; filename="pic.png"', up["body"])
        self.assertIn(b"\x89PNG picture", up["body"])
        self.assertEqual(up["headers"]["Authorization"], f"Bearer {KEY}")

    def test_the_id_where_either_page_puts_it(self):
        self.answers_for_atlas()
        self.fake.routes[("POST", "/api/v1/model/generateVideo")] = {"id": "p1", "status": "x"}
        self.assertEqual(self.run_it()[1], "succeeded")

    def test_the_providers_failure_is_the_error(self):
        self.answers_for_atlas(status="failed", error="Invalid parameter: resolution", outputs=[])
        run, status = self.run_it()
        self.assertEqual(status, "failed")
        self.assertIn("Invalid parameter", run.error)
        self.assertEqual(run.outputs(), [])

    def test_a_run_is_followed_after_a_restart_from_its_id_alone(self):
        self.answers_for_atlas()
        run = self.atlas().call("m", {"prompt": "x", ROUTING: {"values": {"endpoint": "generateVideo"}}})
        self.assertNotIn(KEY, run.id)
        self.assertNotIn('"prompt"', run.id)
        again = self.atlas().attach(run.id)
        self.assertEqual(again.watch(), "succeeded")
        self.assertEqual(len(again.outputs()), 1)
        made = [c for c in self.fake.calls if c["path"].endswith("generateVideo")]
        self.assertEqual(len(made), 1)


class TheKey(WithFake):
    def test_a_link_gets_no_key(self):
        self.answers_for_atlas()
        run = self.atlas().call("m", {"prompt": "x", ROUTING: {"values": {"endpoint": "generateVideo"}}})
        run.watch()
        run.outputs()[0].save(os.path.join(self.tmp.name, "o.mp4"))
        got = next(c for c in self.fake.calls if c["path"] == "/out/v.mp4")
        self.assertNotIn("Authorization", got["headers"])

    def test_a_redirect_to_another_host_drops_it(self):
        other = Fake()
        self.addCleanup(other.close)
        other.routes[("GET", "/elsewhere")] = {"ok": True}
        self.fake.routes[("GET", "/hop")] = (302, b"", {"Location": other.url + "/elsewhere"})
        self.atlas().send("GET", self.fake.url + "/hop")
        self.assertEqual(self.fake.calls[0]["headers"]["Authorization"], f"Bearer {KEY}")
        self.assertNotIn("Authorization", other.calls[0]["headers"])

    def test_a_url_a_provider_answers_with_on_another_host_gets_none(self):
        other = Fake()
        self.addCleanup(other.close)
        other.routes[("GET", "/status")] = {"ok": True}
        self.atlas().send("GET", other.url + "/status")
        self.assertNotIn("Authorization", other.calls[0]["headers"])

    def test_an_echoed_key_is_taken_out_of_the_error(self):
        self.fake.routes[("POST", "/api/v1/model/generateVideo")] = (401, f"bad key {KEY}".encode(), {})
        with self.assertRaises(Exception) as caught:
            self.atlas().call("m", {"prompt": "x", ROUTING: {"values": {"endpoint": "generateVideo"}}})
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIn("401", str(caught.exception))

    def test_the_other_ways_of_sending_it(self):
        self.fake.routes[("GET", "/a")] = {}
        def d(auth):
            return {"id": "x", "base_url": self.fake.url, "auth": auth, "steps": [{"url": "/a"}]}
        HttpBackend(d({"type": "header", "name": "xi-api-key"}), KEY).send("GET", "/a")
        self.assertEqual(self.fake.calls[-1]["headers"]["xi-api-key"], KEY)
        HttpBackend(d({"type": "header", "name": "Authorization", "prefix": "Key "}), KEY).send("GET", "/a")
        self.assertEqual(self.fake.calls[-1]["headers"]["Authorization"], f"Key {KEY}")
        HttpBackend(d({"type": "query", "name": "key"}), KEY).send("GET", "/a")
        self.assertIn(f"key={KEY}", self.fake.calls[-1]["path"])


class NoBlindRetry(WithFake):
    def test_a_submit_with_no_answer_is_not_sent_again_and_says_so(self):
        b = self.atlas()
        self.fake.close()
        self.addCleanup(lambda: None)
        with self.assertRaises(Exception) as caught:
            b.call("m", {"prompt": "x", ROUTING: {"values": {"endpoint": "generateVideo"}}})
        self.assertIn("charged", str(caught.exception))
        self.fake = Fake()

    def test_a_poll_is_asked_again_through_a_hiccup(self):
        self.answers_for_atlas()
        seen = {"n": 0}
        good = self.fake.routes[("GET", "/api/v1/model/prediction/p1")]

        def flaky(_):
            seen["n"] += 1
            return (503, b"busy", {}) if seen["n"] == 1 else good
        self.fake.routes[("GET", "/api/v1/model/prediction/p1")] = flaky
        from unittest import mock
        with mock.patch("seriesmith.backends.time.sleep"):
            run = self.atlas().call("m", {"prompt": "x", ROUTING: {"values": {"endpoint": "generateVideo"}}})
            self.assertEqual(run.watch(), "succeeded")
        self.assertEqual(seen["n"], 2)


class OtherShapes(WithFake):
    def shipped(self, name):
        with open(os.path.join(os.path.dirname(PR.__file__), "presets", "providers", f"{name}.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        d["base_url"] = self.fake.url
        return d

    def test_elevenlabs_the_answer_is_the_file(self):
        self.fake.routes[("POST", "/v1/text-to-speech/voice1")] = (200, b"mp3 bytes", {"Content-Type": "audio/mpeg"})
        b = HttpBackend(self.shipped("elevenlabs"), KEY)
        run = b.call("eleven_v3", {"text": "Hello.", ROUTING: {"values": {"voice": "voice1"}}})
        self.assertEqual(run.watch(), "succeeded")
        (out,) = run.outputs()
        self.assertEqual(out.type, "audio")
        path = out.save(os.path.join(self.tmp.name, "a" + os.path.splitext(out.name)[1]))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"mp3 bytes")
        call = self.fake.calls[0]
        self.assertEqual(call["headers"]["xi-api-key"], KEY)
        self.assertEqual(json.loads(call["body"]), {"model_id": "eleven_v3", "text": "Hello."})

    def test_openai_multipart_in_and_the_download_takes_the_key(self):
        d = self.shipped("openai")
        d["steps"][1]["until"]["every"] = 0.01
        self.fake.routes[("POST", "/videos")] = {"id": "v1", "status": "queued"}
        self.fake.routes[("GET", "/videos/v1")] = {"id": "v1", "status": "completed"}
        self.fake.routes[("GET", "/videos/v1/content")] = b"mp4 bytes"
        run = HttpBackend(d, KEY).call("sora-2", {"prompt": "a cat", "input_reference": File(self.pic)})
        self.assertEqual(run.watch(), "succeeded")
        form = self.fake.calls[0]
        self.assertIn(b'name="model"', form["body"])
        self.assertIn(b'filename="pic.png"', form["body"])
        (out,) = run.outputs()
        out.save(os.path.join(self.tmp.name, "o.mp4"))
        got = self.fake.calls[-1]
        self.assertEqual(got["path"], "/videos/v1/content")
        self.assertEqual(got["headers"]["Authorization"], f"Bearer {KEY}")

    def test_done_can_still_be_a_failure(self):
        """fal: COMPLETED with an error in the result."""
        d = {"id": "fal", "base_url": self.fake.url, "auth": {"type": "header", "name": "Authorization", "prefix": "Key "},
             "steps": [{"method": "POST", "url": "/go", "json": "$args", "take": {"task": "request_id"}},
                       {"url": "/s/{task}", "until": {"status": "status", "done": ["COMPLETED"], "every": 0.01}},
                       {"url": "/r/{task}"}],
             "result": {"files": "video.url", "error": "detail"}}
        self.fake.routes[("POST", "/go")] = {"request_id": "r1"}
        self.fake.routes[("GET", "/s/r1")] = {"status": "COMPLETED"}
        self.fake.routes[("GET", "/r/r1")] = {"detail": "the content filter refused it"}
        run = HttpBackend(d, KEY).call("m", {"prompt": "x"})
        self.assertEqual(run.watch(), "failed")
        self.assertIn("content filter", run.error)


class Pieces(unittest.TestCase):
    def test_fill(self):
        self.assertEqual(fill({"model": "$m", "...": "$a", "u": "x/{m}"}, {"m": "M", "a": {"b": 1}}),
                         {"model": "M", "b": 1, "u": "x/M"})
        self.assertEqual(fill("/v/{a}", {"a": "x y/z"}, quote=True), "/v/x%20y/z")
        self.assertEqual(fill("{unknown}", {}), "{unknown}")

    def test_pick(self):
        doc = {"data": {"outputs": ["a"], "id": ""}, "id": "top"}
        self.assertEqual(pick(doc, "data.outputs.0"), "a")
        self.assertEqual(pick(doc, ["data.id", "id"]), "top")
        self.assertIsNone(pick(doc, "nope.x"))


class Definitions(unittest.TestCase):
    GOOD = {"id": "mine", "base_url": "https://a.example", "auth": {"type": "bearer"},
            "steps": [{"url": "/go", "response": "bytes"}]}

    def test_a_good_one(self):
        self.assertEqual(PR.problems(self.GOOD), [])

    def test_everything_shipped_is_good_and_says_it_is_untested(self):
        defs = PR.definitions()
        for name in ("atlas", "elevenlabs", "openai"):
            self.assertEqual(PR.problems(defs[name]), [], name)
            self.assertTrue(defs[name]["untested"], name)

    def test_what_is_refused(self):
        for bad, says in (({"id": "A B"}, "id"), ({"base_url": "http://a.example"}, "https"),
                          ({"auth": {"type": "oauth"}}, "auth"), ({"steps": []}, "steps"),
                          ({"auth": {"type": "header"}}, "auth.name"),
                          ({"steps": [{"url": "/x", "webhook": "y", "response": "bytes"}]}, "webhook")):
            self.assertIn(says, " ".join(PR.problems({**self.GOOD, **bad})), bad)

    def test_a_key_never_leaves_a_listing_and_the_environment_wins(self):
        env = {PR.env_name("atlas"): "from-env"}
        settings = S.Settings(provider_keys={"openai": KEY, "atlas": "saved"})
        rows = {r["id"]: r for r in PR.listing(settings, env)}
        self.assertNotIn(KEY, json.dumps(list(rows.values())))
        self.assertNotIn(KEY, json.dumps(settings.describe()))
        self.assertEqual(settings.describe()["provider_keys"], ["atlas", "openai"])
        self.assertTrue(rows["openai"]["has_key"])
        self.assertFalse(rows["elevenlabs"]["has_key"])
        self.assertEqual(PR.key_of("atlas", settings, env), "from-env")

    def test_only_a_provider_with_a_key_is_a_backend(self):
        settings = S.Settings(provider_keys={"atlas": KEY})
        made = available(settings)
        self.assertIn("api:atlas", made)
        self.assertNotIn("api:openai", made)
        self.assertTrue(made["api:atlas"].paid)
        self.assertEqual(made["api:atlas"].parallel, 3)


class ReadingAReference(unittest.TestCase):
    def propose(self, text, kind="video", path=None, model="bytedance/seedance-2.5/reference-to-video"):
        base = TG.load_target("seedance_2_5", "video").spec
        return AS.propose("atlas", model, text, kind, path, base=base)

    def test_an_example_request(self):
        got = self.propose(json.dumps(ATLAS_EXAMPLE))
        self.assertEqual(got["form"], "example")
        spec = got["proposal"]
        self.assertTrue(TG.is_hosted(spec))
        self.assertNotIn("router", spec)
        block = spec["api"]
        self.assertEqual(block["service"], "atlas")
        self.assertEqual(block["model"], "bytedance/seedance-2.5/reference-to-video")
        self.assertEqual(block["values"]["endpoint"], "generateVideo")
        self.assertEqual(spec["capabilities"]["backends"], ["api"])
        self.assertEqual(block["inputs"]["prompt"], "prompt")
        self.assertEqual(block["inputs"]["references"].get("list"), "reference_images")
        self.assertEqual(block["inputs"]["seed"]["name"], "seed")
        self.assertTrue(any("example" in w for w in got["warnings"]))
        self.assertNotIn("model", {f["path"] for f in block["schema"]["fields"]})

    def test_a_curl_keeps_how_it_authenticates_and_never_the_key(self):
        curl = ("curl -X POST https://api.atlascloud.ai/api/v1/model/generateVideo \\\n"
                f" -H 'Authorization: Bearer {KEY}' -H 'Content-Type: application/json' \\\n"
                f" -d '{json.dumps(ATLAS_EXAMPLE)}'")
        got = self.propose(curl)
        self.assertEqual(got["form"], "curl")
        self.assertEqual(got["auth"], {"type": "bearer"})
        self.assertNotIn(KEY, json.dumps(got))
        self.assertEqual(got["proposal"]["api"]["inputs"]["prompt"], "prompt")

    def test_other_headers_are_read_as_how_too(self):
        got = AS.parse_curl(f"curl https://a.example/x -H 'xi-api-key: {KEY}' -d '{{\"text\":\"hi\"}}'")
        self.assertEqual(got["auth"], {"type": "header", "name": "xi-api-key"})
        self.assertNotIn(KEY, json.dumps(got))
        got = AS.parse_curl(f"curl https://a.example/x -H 'Authorization: Key {KEY}' -F prompt=hi -F file=@a.png")
        self.assertEqual(got["auth"], {"type": "header", "name": "Authorization", "prefix": "Key "})
        self.assertEqual(got["body"], {"prompt": "hi", "file": ""})
        self.assertEqual(got["method"], "POST")

    def test_an_openapi_document_says_what_is_required(self):
        doc = AS.doc_from_example(ATLAS_EXAMPLE)
        body = doc["paths"]["/generate"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        body["required"] = ["model", "prompt", "watermark_id"]
        body["properties"]["watermark_id"] = {"type": "string"}
        doc["openapi"] = "3.0.0"
        got = self.propose(json.dumps(doc))
        self.assertEqual(got["form"], "openapi")
        self.assertIn("watermark_id", got["unplaced"])
        self.assertNotIn("model", got["unplaced"])
        self.assertEqual(sorted(got["proposal"]["api"]["schema"]["required"]), ["prompt", "watermark_id"])

    def test_several_requests_are_a_choice(self):
        one = AS.doc_from_example(ATLAS_EXAMPLE)["paths"]["/generate"]
        doc = {"openapi": "3.0.0", "paths": {"/a": one, "/b": one, "/list": {"get": {}}}}
        got = self.propose(json.dumps(doc))
        self.assertIsNone(got["proposal"])
        self.assertEqual(got["paths"], ["/a", "/b"])
        self.assertTrue(self.propose(json.dumps(doc), path="/b")["proposal"])

    def test_an_image_model(self):
        got = self.propose(json.dumps({"model": "x", "prompt": "a", "seed": 1, "image_urls": ["u"]}), kind="image",
                           model="bytedance/seedream")
        self.assertEqual(got["proposal"]["kind"], "image")
        self.assertEqual(got["proposal"]["api"]["values"]["endpoint"], "generateImage")

    def test_what_cannot_be_read_says_what_to_do(self):
        for text, says in (("", "paste"), ("openapi: 3.0.0\npaths: {}", "YAML"), ("[1]", "object"),
                           ("curl https://a.example/x", "no body"), ("curl -d 'a=$b' https://a.example/x", "JSON")):
            with self.assertRaisesRegex(AS.SpecError, says):
                self.propose(text)
        with self.assertRaisesRegex(AS.SpecError, "no provider"):
            AS.propose("nope", "m", "{}")


class AModelOnAProvider(unittest.TestCase):
    """From the pasted example to the request, the way a render makes it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(TG.forget_targets)
        self.root = self.tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        base = TG.load_target("seedance_2_5", "video").spec
        self.spec = AS.propose("atlas", "bytedance/seedance-2.5/reference-to-video",
                               json.dumps(ATLAS_EXAMPLE), base=base)["proposal"]

    def save(self):
        spec = {**self.spec, "draft": False}
        folder = os.path.join(self.root, "targets", spec["id"])
        os.makedirs(folder, exist_ok=True)
        F.write_json(os.path.join(folder, "target.json"), spec)
        TG.forget_targets()
        return spec["id"]

    def test_its_preview(self):
        got = PV.preview(self.root, self.spec["id"], shot="sh010", spec=self.spec)
        self.assertTrue(got["ok"], got.get("why"))
        self.assertTrue(got["editable"])
        self.assertEqual(got["model"], "bytedance/seedance-2.5/reference-to-video")
        self.assertIn(got["prompt"], got["sent"])
        self.assertEqual(got["arguments"]["prompt"], got["sent"])
        self.assertTrue(got["schema"]["fields"])
        self.assertEqual(got["routing"]["values"]["endpoint"], "generateVideo")

    def test_it_is_valid_to_save(self):
        from seriesmith import inspector as IN
        self.assertEqual(IN.validate_spec(self.spec), [])
        self.assertTrue(IN.validate_spec({**self.spec, "api": {**self.spec["api"], "service": "nope"}}))

    def test_a_shot_on_it_runs_on_that_provider(self):
        tid = self.save()
        with TG.use_roots(self.root):
            t = TG.load_target(tid, "video")
            self.assertEqual(J.backend_choice({}, "sh010", t)[0], "api:atlas")
            self.assertEqual(J.backend_choice({}, "sh010", t, "api:atlas")[0], "api:atlas")
            with self.assertRaises(ValueError):
                J.backend_choice({}, "sh010", t, "api:openai")
            self.assertTrue(t.moderated)
            doc, i = J.find_shot(self.root, "final", "sh010")
            job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=tid), {})
            self.assertEqual(job.error, "")
            model, args = t.module.router_call(t, job)
        self.assertEqual(model, "bytedance/seedance-2.5/reference-to-video")
        self.assertEqual(args[ROUTING]["values"]["endpoint"], "generateVideo")

    def test_a_shows_mapping_reaches_it_and_can_not_change_its_provider(self):
        tid = self.save()
        TG.save_show_overrides(self.root, "seedance_2_5", {})
        path = TG.overrides_path(self.root)
        F.write_json(path, {tid: {"router.inputs.seed": None, "api.service": "evil", "router.service": "evil"}})
        TG.forget_targets()
        t = TG.load_target(tid, "video", root=self.root)
        self.assertEqual(TG.service_of(t.spec), "atlas")


class ScratchSettings(ApiTest):
    """Keys and definitions are written beside the settings: on a scratch file, never conftest's."""

    def setUp(self):
        super().setUp()
        self.addCleanup(TG.forget_targets)
        self.addCleanup(os.environ.__setitem__, "SERIESMITH_SETTINGS", os.environ["SERIESMITH_SETTINGS"])
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(self.tmp, "user", "settings.json")
        os.makedirs(os.path.dirname(os.environ["SERIESMITH_SETTINGS"]), exist_ok=True)


class Routes(ScratchSettings):

    def test_a_key_is_write_only_and_makes_the_backend(self):
        got = self.ok(A_put_key(self.ctx, {"id": "atlas", "key": KEY}))
        self.assertNotIn(KEY, json.dumps(got))
        row = next(r for r in got["providers"] if r["id"] == "atlas")
        self.assertTrue(row["has_key"])
        self.assertIn("api:atlas", self.ctx.runner.backends)
        self.ok(A_put_key(self.ctx, {"id": "atlas", "key": None}))
        self.assertNotIn("api:atlas", self.ctx.runner.backends)

    def test_an_unknown_provider_has_no_key_to_set(self):
        self.err(A_put_key(self.ctx, {"id": "nope", "key": "x"}), 404)

    def test_a_definition_is_checked_then_saved_and_removed(self):
        from seriesmith import api as A
        self.err(A.put_provider(self.ctx, {"definition": {"id": "mine"}}), 400)
        good = {"id": "mine", "base_url": "https://a.example", "auth": {"type": "bearer"},
                "steps": [{"url": "/go", "response": "bytes"}]}
        got = self.ok(A.put_provider(self.ctx, {"definition": good}))
        self.assertIn("mine", {r["id"] for r in got["providers"]})
        got = self.ok(A.delete_provider(self.ctx, {"id": "mine"}))
        self.assertNotIn("mine", {r["id"] for r in got["providers"]})

    def test_reading_a_reference(self):
        from seriesmith import api as A
        got = self.ok(A.post_provider_read_spec(self.ctx, {
            "service": "atlas", "model": "bytedance/seedance-2.5/reference-to-video", "text": json.dumps(ATLAS_EXAMPLE)}))
        self.assertTrue(got["proposal"])
        self.assertIn("limits", got)
        self.err(A.post_provider_read_spec(self.ctx, {"service": "atlas", "model": "m", "text": "nonsense"}), 400)

    def test_the_panel_previews_it_before_it_is_saved(self):
        from seriesmith import api as A
        got = self.ok(A.post_provider_read_spec(self.ctx, {
            "service": "atlas", "model": "bytedance/seedance-2.5/reference-to-video", "text": json.dumps(ATLAS_EXAMPLE)}))
        view = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "target": got["proposal"], "shot": "sh010"}))
        self.assertTrue(view["ok"], view.get("why"))
        self.assertIn("prompt", view["arguments"])

    def test_it_saves_as_an_own_model_and_its_required_fields_are_held(self):
        from seriesmith import api as A
        doc = AS.doc_from_example(ATLAS_EXAMPLE)
        doc["openapi"] = "3.0.0"
        doc["paths"]["/generate"]["post"]["requestBody"]["content"]["application/json"]["schema"]["required"] = ["seed"]
        got = self.ok(A.post_provider_read_spec(self.ctx, {
            "service": "atlas", "model": "bytedance/seedance-2.5/reference-to-video", "text": json.dumps(doc)}))
        saved = self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": got["proposal"], "scope": "show"}))
        tid = saved["id"]
        self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": tid, "inputs": {"seed": None}}), 400)


class AWholeTake(ScratchSettings):
    """Pasted example to a finished take, through the queue, as the app does it."""

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)

    def add_model(self):
        from seriesmith import api as A
        with open(os.path.join(os.path.dirname(PR.__file__), "presets", "providers", "atlas.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        d.update(id="local_atlas", base_url=self.fake.url + "/api/v1", untested=False)
        d["steps"][1]["until"]["every"] = 0.01
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        self.ok(A.put_provider_key(self.ctx, {"id": "local_atlas", "key": KEY}))
        got = self.ok(A.post_provider_read_spec(self.ctx, {
            "service": "local_atlas", "model": "bytedance/seedance-2.5/reference-to-video",
            "text": json.dumps(ATLAS_EXAMPLE)}))
        spec = {**got["proposal"], "draft": False}
        return self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": spec, "scope": "show"}))["id"]

    def test_it_comes_back_as_a_take(self):
        from seriesmith import api as A
        from seriesmith import takes as T
        from test_router_render import tiny_mp4
        f = self.fake
        f.routes[("POST", "/api/v1/model/uploadMedia")] = {"url": "https://files.example/pic.png"}
        f.routes[("POST", "/api/v1/model/generateVideo")] = {"code": 0, "data": {"id": "p1"}}
        f.routes[("GET", "/api/v1/model/prediction/p1")] = {
            "data": {"id": "p1", "status": "completed", "error": None, "outputs": [f.url + "/out/v.mp4"]}}
        f.routes[("GET", "/out/v.mp4")] = tiny_mp4()
        tid = self.add_model()
        self.ok(A.post_render(self.ctx, {"ep": self.ep, "pass": "proxy", "shots": ["sh010"], "target": tid,
                                         "backend": "api:local_atlas", "allow_missing_refs": True, "redo": True}))
        self.settle()
        takes = T.list_takes(self.ep, "proxy", "sh010")
        sc = takes[-1].sidecar
        self.assertEqual(sc["status"], "ok", sc.get("save_notes"))
        self.assertEqual(sc["target"], tid)
        self.assertEqual(sc["backend"], "api:local_atlas")
        self.assertTrue(os.path.getsize(takes[-1].paths.mp4) > 0)
        self.assertNotIn(KEY, json.dumps(sc))
        self.assertEqual(self.ctx.runner.queue.paid_count, 1)
        sent = next(c for c in f.calls if c["path"].endswith("generateVideo"))
        self.assertEqual(json.loads(sent["body"])["model"], "bytedance/seedance-2.5/reference-to-video")

    def test_with_no_key_it_says_so_before_anything_is_spent(self):
        from seriesmith import api as A
        tid = self.add_model()
        self.ok(A.put_provider_key(self.ctx, {"id": "local_atlas", "key": None}))
        code, data = A.post_render(self.ctx, {"ep": self.ep, "pass": "proxy", "shots": ["sh010"], "target": tid,
                                              "allow_missing_refs": True, "redo": True})
        self.settle()
        self.assertEqual(self.fake.calls, [])
        self.assertIn("api:local_atlas", json.dumps(data))


def A_put_key(ctx, body):
    from seriesmith import api as A
    return A.put_provider_key(ctx, body)


if __name__ == "__main__":
    unittest.main()
