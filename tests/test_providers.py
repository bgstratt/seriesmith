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
            do_GET = do_POST = do_DELETE = do_PUT = answer

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
        # as Atlas really answered, 2026-11-04 (its docs say a top-level `url`)
        f.routes[("POST", "/api/v1/model/uploadMedia")] = {
            "code": 200, "message": "success",
            "data": {"type": "image", "download_url": "https://files.example/pic.png", "filename": "pic.png", "size": 12}}
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


class WhoIsAsking(WithFake):
    def test_not_as_python(self):
        """Python's default User-Agent gets a 403 from a provider behind Cloudflare."""
        self.fake.routes[("GET", "/a")] = {}
        self.atlas().send("GET", self.fake.url + "/a")
        self.assertEqual(self.fake.calls[-1]["headers"]["User-Agent"], "seriesmith")


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

    def test_everything_shipped_is_good_and_says_it_is_untested_until_proved(self):
        defs = PR.definitions()
        for name in ("atlas", "elevenlabs", "openai"):
            self.assertEqual(PR.problems(defs[name]), [], name)
        for name in ("elevenlabs", "openai"):
            self.assertTrue(defs[name]["untested"], name)
        self.assertFalse(defs["atlas"].get("untested"))     # a real take came back

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
                self.propose(text, model="not/on-its-list")
        with self.assertRaisesRegex(AS.SpecError, "no provider"):
            AS.propose("nope", "m", "{}")


class HowPicturesAreNamed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(TG.forget_targets)
        self.root = self.tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        self.spec = AS.propose("atlas", "m/n", json.dumps(ATLAS_EXAMPLE),
                               base=TG.load_target("seedance_2_5", "video").spec)["proposal"]

    def sent(self, **references):
        spec = json.loads(json.dumps(self.spec))
        spec["api"]["inputs"]["references"].update(references)
        return PV.preview(self.root, spec["id"], shot="sh010", spec=spec)["sent"]

    def test_a_provider_writes_the_number_its_own_way(self):
        got = self.sent(define=True, define_as="@Image{n}")
        self.assertIn("@Image1", got)
        self.assertNotIn("@Image 1", got)

    def test_the_default_is_as_it_was(self):
        self.assertIn("@Image 1", self.sent(define=True))

    def test_not_defined_unless_asked(self):
        self.assertNotIn("@Image", self.sent())

    def test_what_an_example_has_and_nothing_takes_is_said(self):
        got = AS.propose("atlas", "m/n", json.dumps(ATLAS_EXAMPLE), base=TG.load_target("seedance_2_5", "video").spec)
        self.assertTrue(any("resolution" in w for w in got["warnings"]))


class AtlasList(unittest.TestCase):
    """Atlas's documented models, picked rather than pasted (presets/providers/atlas.models.json)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(TG.forget_targets)
        self.root = self.tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        self.base = TG.load_target("seedance_2_5", "video").spec

    def proposed(self, model):
        return AS.propose("atlas", model, "", base=self.base)

    def inputs(self, model):
        return self.proposed(model)["proposal"]["api"]["inputs"]

    def test_every_one_proposes_and_previews_with_its_own_fields_placed(self):
        from seriesmith import inspector as IN
        for m in PR.catalog("atlas"):
            with self.subTest(m["id"]):
                got = self.proposed(m["id"])
                spec = got["proposal"]
                self.assertEqual(IN.validate_spec(spec), [])
                self.assertEqual(got["form"], "catalog")
                self.assertEqual(got["unplaced"], [])
                self.assertEqual(spec["kind"], m["kind"])
                view = PV.preview(self.root, spec["id"], shot="sh010", spec=spec) if m["kind"] == "video" \
                    else PV.preview(self.root, spec["id"], spec=spec)
                self.assertTrue(view["ok"], view.get("why"))

    def test_the_last_frame_on_any_name(self):
        self.assertEqual(self.inputs("google/veo3.1/image-to-video")["last"]["field"], "last_image")
        self.assertEqual(self.inputs("alibaba/wan-3.0/image-to-video")["last"]["field"], "last_image")
        self.assertEqual(self.inputs("kwaivgi/kling-v3.0-pro/image-to-video")["last"]["field"], "end_image")

    def test_what_the_sound_is_called(self):
        self.assertEqual(self.inputs("alibaba/wan-3.0/image-to-video")["audio"]["name"], "audio")
        self.assertEqual(self.inputs("kwaivgi/kling-v3.0-pro/image-to-video")["audio"]["name"], "sound")

    def test_a_size_as_the_api_writes_it(self):
        from seriesmith.targets.generic.request_map import nearest_size
        size = self.inputs("bytedance/seedream-v5.0-pro/text-to-image")["size"]
        self.assertEqual(nearest_size(1024, 1024, size["values"]), "1024*1024")
        self.assertEqual(nearest_size(1920, 1080, size["values"]), "2048*1152")
        self.assertEqual(self.inputs("black-forest-labs/flux-2-pro/text-to-image")["size"]["format"], "{w}_{h}")
        self.assertEqual(self.inputs("qwen-image-3.0/edit")["size"]["format"], "{w}_{h}")
        self.assertIn("1536x1024", self.inputs("openai/gpt-image-2/text-to-image")["size"]["values"])

    def test_an_edit_models_pictures(self):
        self.assertIn("images", self.inputs("qwen-image-3.0/edit"))

    def test_a_first_frame_model_says_it_needs_one(self):
        spec = self.proposed("minimax/hailuo-2.3/i2v-pro")["proposal"]
        self.assertIn("first", spec["recipe"].get("keyframe_required") or {})

    def test_it_comes_from_the_docs_and_says_so(self):
        got = self.proposed("bytedance/seedance-2.5/reference-to-video")
        self.assertTrue(any("not yet proved" in w for w in got["warnings"]))
        self.assertTrue(any("tiers" in w for w in got["warnings"]))

    def test_seedance_goes_to_the_id_for_what_is_sent(self):
        from seriesmith.targets.generic.router_video import model_for
        spec = self.proposed("bytedance/seedance-2.5/reference-to-video")["proposal"]
        block = spec["api"]
        self.assertEqual(model_for(block, "references", ["pic"]), "bytedance/seedance-2.5/reference-to-video")
        self.assertEqual(model_for(block, "frames", ["pic"]), "bytedance/seedance-2.5/image-to-video")
        self.assertNotIn("keyframe_required", spec["recipe"])
        self.assertEqual(model_for({"model": "one"}, "frames", ["pic"]), "one")
        self.assertEqual(model_for({"model": "m", "models": {"text": "t"}}, "references", []), "t")

    def test_a_first_frame_sends_the_frame_and_goes_to_its_id(self):
        spec = self.proposed("bytedance/seedance-2.5/reference-to-video")["proposal"]
        path = os.path.join(self.root, spec["recipe"]["keyframe_path"].format(shot="sh010", end="first"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG")
        view = PV.preview(self.root, spec["id"], shot="sh010", spec=spec)
        self.assertEqual(view["model"], "bytedance/seedance-2.5/image-to-video")
        self.assertIn("image", view["arguments"])
        self.assertNotIn("reference_images", view["arguments"])

    def test_an_answer_flat_or_wrapped(self):
        defs = PR.definitions()["atlas"]
        self.assertEqual(PR.problems(defs), [])
        from seriesmith.backends.http import pick
        until = defs["steps"][1]["until"]
        self.assertEqual(pick({"status": "completed"}, until["status"]), "completed")
        self.assertEqual(pick({"data": {"status": "failed"}}, until["status"]), "failed")
        self.assertEqual(pick({"outputs": ["u"]}, defs["result"]["files"]), ["u"])

    def test_a_listing_says_what_is_on_it(self):
        row = next(r for r in PR.listing(S.Settings(), {}) if r["id"] == "atlas")
        self.assertIn("qwen-image-3.0/edit", {m["id"] for m in row["catalog"]})


class HiggsfieldList(AtlasList):
    """Higgsfield's documented models (presets/providers/higgsfield.models.json, read 2026-11-05)."""

    def proposed(self, model):
        return AS.propose("higgsfield", model, "", base=self.base)

    def view(self, model):
        spec = self.proposed(model)["proposal"]
        return spec, PV.preview(self.root, spec["id"], shot="sh010", spec=spec)

    def test_every_one_proposes_and_previews_with_its_own_fields_placed(self):
        from seriesmith import inspector as IN
        for m in PR.catalog("higgsfield"):
            with self.subTest(m["id"]):
                got = self.proposed(m["id"])
                spec = got["proposal"]
                self.assertEqual(IN.validate_spec(spec), [])
                self.assertEqual(got["form"], "catalog")
                self.assertEqual(got["unplaced"], [])
                self.assertEqual(spec["kind"], m["kind"])
                view = PV.preview(self.root, spec["id"], shot="sh010", spec=spec) if m["kind"] == "video" \
                    else PV.preview(self.root, spec["id"], spec=spec)
                self.assertTrue(view["ok"], view.get("why"))

    def test_only_what_a_model_has_is_sent(self):
        # their schemas refuse anything else (additionalProperties: false), and have no seed
        for m in PR.catalog("higgsfield"):
            if m["kind"] != "video":
                continue
            with self.subTest(m["id"]):
                _, view = self.view(m["id"])
                self.assertTrue(view["ok"], view.get("why"))
                self.assertLessEqual(set(view["arguments"]), set(m["fields"]))

    def test_each_goes_to_the_id_for_what_is_sent(self):
        from seriesmith.targets.generic.router_video import model_for
        block = self.proposed("minimax/h3/reference-to-video")["proposal"]["api"]
        self.assertEqual(model_for(block, "references", ["pic"]), "minimax/h3/reference-to-video")
        self.assertEqual(model_for(block, "frames", ["pic"]), "minimax/h3/image-to-video")
        self.assertEqual(model_for(block, "references", []), "minimax/h3/text-to-video")

    def test_sound_as_kling_writes_it(self):
        spec = self.proposed("kling-video/v3.0/pro/image-to-video")["proposal"]
        self.assertEqual(spec["api"]["inputs"]["audio"], {"name": "sound", "on": "on", "off": "off"})

    def test_a_first_frame_sends_the_frame_and_goes_to_its_id(self):
        spec = self.proposed("bytedance/seedance-2.5/reference-to-video")["proposal"]
        path = os.path.join(self.root, spec["recipe"]["keyframe_path"].format(shot="sh010", end="first"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG")
        view = PV.preview(self.root, spec["id"], shot="sh010", spec=spec)
        self.assertEqual(view["model"], "bytedance/seedance-2.5/image-to-video")
        self.assertIn("image_url", view["arguments"])
        self.assertNotIn("image_urls", view["arguments"])
        self.assertNotIn("aspect_ratio", view["arguments"])

    def test_a_listing_says_what_is_on_it(self):
        row = next(r for r in PR.listing(S.Settings(), {}) if r["id"] == "higgsfield")
        self.assertIn("minimax/h3/reference-to-video", {m["id"] for m in row["catalog"]})
        self.assertTrue(row["untested"])
        self.assertIn("as copied", row["key_hint"])

    # what's only Atlas's
    test_the_last_frame_on_any_name = None
    test_what_the_sound_is_called = None
    test_a_size_as_the_api_writes_it = None
    test_an_edit_models_pictures = None
    test_a_first_frame_model_says_it_needs_one = None
    test_it_comes_from_the_docs_and_says_so = None
    test_seedance_goes_to_the_id_for_what_is_sent = None
    test_an_answer_flat_or_wrapped = None


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


class FromScratch(ScratchSettings):
    """A provider never seen before, from what its docs show, to a finished take."""

    CURL = ("curl -X POST https://api.newco.ai/v2/videos/create "
            f"-H 'Authorization: Bearer {KEY}' -H 'Content-Type: application/json' "
            "-d '{\"model_name\": \"newco-1\", \"text\": \"a cat\", \"prompt\": \"a cat\", \"image_url\": \"https://x/a.png\", "
            "\"seconds\": 5, \"seed\": 1}'")

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)

    def test_a_curl_alone(self):
        from seriesmith import providerdraft as PD
        got = PD.draft(self.CURL)
        f = got["form"]
        self.assertEqual((f["id"], f["base_url"], f["url"], f["auth_type"], f["model_field"]),
                         ("newco", "https://api.newco.ai", "/v2/videos/create", "bearer", "model_name"))
        self.assertEqual(got["model"], "newco-1")
        self.assertNotIn(KEY, json.dumps(got))
        self.assertTrue(PD.form_problems(f))         # how it answers is still to say

    def test_its_answers_fill_in_how_it_comes_back(self):
        from seriesmith import providerdraft as PD
        got = PD.draft(self.CURL, answer='{"result": {"job_id": "abc", "state": "queued"}}',
                       poll=f"curl https://api.newco.ai/v2/videos/abc -H 'Authorization: Bearer {KEY}'",
                       poll_answer='{"result": {"state": "ready", "error": "", "files": ["https://cdn.newco.ai/a.mp4"]}}')
        f = got["form"]
        self.assertEqual((f["id_path"], f["poll_url"], f["status_path"], f["files_path"]),
                         ("result.job_id", "/v2/videos/{task}", "result.state", "result.files"))
        self.assertIn("ready", f["done"])
        self.assertEqual(PD.form_problems(f), [])
        d = PD.definition(f)
        self.assertEqual(PR.problems(d), [])
        self.assertEqual(d["steps"][0]["json"], {"model_name": "$model", "...": "$args"})
        self.assertEqual(d["steps"][0]["take"], {"task": "result.job_id"})
        self.assertNotIn(KEY, json.dumps(d))

    def test_other_ways_of_sending_the_key(self):
        from seriesmith import providerdraft as PD
        f = PD.draft(f"curl -X POST 'https://a.example/go?key={KEY}&x=1' -d '{{\"prompt\":\"a\"}}'")["form"]
        self.assertEqual((f["auth_type"], f["auth_name"]), ("query", "key"))
        self.assertNotIn(KEY, json.dumps(f))
        f = PD.draft(f"curl https://a.example/go -H 'xi-api-key: {KEY}' -d '{{\"text\":\"a\"}}'")["form"]
        self.assertEqual((f["auth_type"], f["auth_name"]), ("header", "xi-api-key"))
        f = PD.draft(f"curl https://a.example/go -H 'Authorization: Key {KEY}' -d '{{\"prompt\":\"a\"}}'")["form"]
        self.assertEqual((f["auth_type"], f["auth_name"], f["auth_prefix"]), ("header", "Authorization", "Key "))

    def test_a_model_in_the_address_as_fal_puts_it(self):
        from seriesmith import providerdraft as PD
        got = PD.draft(f"curl -X POST https://queue.fal.run/fal-ai/kling/v3 -H 'Authorization: Key {KEY}' -d '{{\"prompt\":\"a\"}}'",
                       answer='{"request_id": "r1", "status_url": "https://queue.fal.run/fal-ai/kling/requests/r1/status", '
                              '"response_url": "https://queue.fal.run/fal-ai/kling/requests/r1"}',
                       poll_answer='{"status": "COMPLETED"}')
        f = got["form"]
        self.assertEqual(got["model"], "fal-ai/kling/v3")
        self.assertEqual(f["url"], "/{model}")
        self.assertEqual((f["poll_url"], f["fetch_url"]), ("$status_url", "$response_url"))
        f["files_path"] = "video.url"
        d = PD.definition(f)
        self.assertEqual(d["steps"][0]["take"], {"task": "request_id", "status_url": "status_url", "response_url": "response_url"})
        self.assertEqual(d["steps"][2]["url"], "$response_url")
        self.assertEqual(PR.problems(d), [])

    def test_an_answer_that_is_the_file_or_links(self):
        from seriesmith import providerdraft as PD
        f = PD.draft(self.CURL, answer='{"images": ["https://cdn.x/a.png"]}')["form"]
        self.assertEqual((f["answer"], f["files_path"]), ("links", "images"))
        self.assertEqual(PD.definition(f)["result"], {"files": "images"})
        f = {**PD.draft(self.CURL)["form"], "answer": "file"}
        self.assertEqual(PD.form_problems(f), [])
        d = PD.definition(f)
        self.assertEqual(d["steps"][0]["response"], "bytes")
        self.assertEqual(PR.problems(d), [])

    def test_an_openapi_document(self):
        from seriesmith import providerdraft as PD
        doc = AS.doc_from_example(ATLAS_EXAMPLE)
        doc.update(openapi="3.0.0", servers=[{"url": "https://api.newco.ai/v1"}],
                   components={"securitySchemes": {"k": {"type": "apiKey", "in": "header", "name": "X-Key"}}})
        f = PD.draft(json.dumps(doc))["form"]
        self.assertEqual((f["base_url"], f["url"], f["auth_type"], f["auth_name"], f["model_field"]),
                         ("https://api.newco.ai/v1", "/generate", "header", "X-Key", "model"))

    def test_what_it_can_not_read_says_what_to_do(self):
        from seriesmith import providerdraft as PD
        for text, says in (("", "paste"), ('{"prompt": "a"}', "cURL")):
            with self.assertRaisesRegex(AS.SpecError, says):
                PD.draft(text)
        with self.assertRaisesRegex(AS.SpecError, "isn't JSON"):
            PD.draft(self.CURL, answer="not json")

    def provider(self, **form):
        from seriesmith import api as A
        got = self.ok(A.post_provider_draft(self.ctx, {
            "text": self.CURL, "answer": '{"result": {"job_id": "abc", "state": "queued"}}',
            "poll": "curl https://api.newco.ai/v2/videos/abc", "poll_answer": '{"result": {"state": "ready", "files": ["https://c/a.mp4"]}}'}))
        f = {**got["form"], "base_url": self.fake.url, **form}
        got = self.ok(A.post_provider_draft(self.ctx, {"form": f}))
        self.assertEqual(got["problems"], [])
        return got["definition"]

    def test_the_check_is_one_read_that_starts_nothing(self):
        from seriesmith import api as A
        self.fake.routes[("GET", "/v2/videos/seriesmith-check-does-not-exist")] = (404, {"message": "no such job"}, {})
        got = self.ok(A.post_provider_check(self.ctx, {"definition": self.provider(), "key": KEY}))
        self.assertEqual((got["reached"], got["key_ok"], got["status"]), (True, True, 404))
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.fake.calls[0]["method"], "GET")
        self.assertEqual(self.fake.calls[0]["headers"]["Authorization"], f"Bearer {KEY}")
        self.fake.routes[("GET", "/v2/videos/seriesmith-check-does-not-exist")] = (401, {"message": "bad key"}, {})
        self.assertFalse(self.ok(A.post_provider_check(self.ctx, {"definition": self.provider(), "key": "bad"}))["key_ok"])
        self.assertFalse(os.path.exists(PR.user_dir()) and os.listdir(PR.user_dir()))

    def test_an_openapi_documents_address(self):
        from seriesmith import api as A
        doc = AS.doc_from_example(ATLAS_EXAMPLE)
        doc.update(openapi="3.0.0", servers=[{"url": "https://api.newco.ai/v1"}])
        self.fake.routes[("GET", "/openapi.json")] = doc
        got = self.ok(A.post_provider_draft(self.ctx, {"text": self.fake.url + "/openapi.json"}))
        self.assertEqual(got["form"]["base_url"], "https://api.newco.ai/v1")
        self.assertEqual(self.fake.calls[0]["headers"]["User-Agent"], "seriesmith")

    def test_a_docs_page_at_that_address_says_what_to_do(self):
        from seriesmith import api as A
        self.fake.routes[("GET", "/docs")] = b"<html>docs</html>"
        code, data = A.post_provider_draft(self.ctx, {"text": self.fake.url + "/docs"})
        self.assertEqual(code, 400)
        self.assertIn("example cURL", data["error"])

    def test_no_key_nothing_to_check(self):
        from seriesmith import api as A
        self.err(A.post_provider_check(self.ctx, {"definition": self.provider()}), 400)

    def test_from_a_curl_to_a_finished_take(self):
        from seriesmith import api as A
        from seriesmith import takes as T
        from test_router_render import tiny_mp4
        d = self.provider(id="newco", every=0.01)
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        self.ok(A.put_provider_key(self.ctx, {"id": "newco", "key": KEY}))
        got = self.ok(A.post_provider_read_spec(self.ctx, {"service": "newco", "model": "newco-1", "text": self.CURL}))
        spec = {**got["proposal"], "draft": False}
        self.assertNotIn("model_name", {f["path"] for f in spec["api"]["schema"]["fields"]})
        self.assertNotIn(KEY, json.dumps(got))
        view = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "target": spec, "shot": "sh010"}))
        calls = view["calls"]
        self.assertEqual([c["what"] for c in calls], ["generate", "wait", "download"])
        self.assertEqual(calls[0]["url"], self.fake.url + "/v2/videos/create")
        self.assertEqual(calls[0]["sends"]["model_name"], "newco-1")
        self.assertIn("(your key)", calls[0]["key"])
        self.assertNotIn(KEY, json.dumps(view))
        self.assertEqual(self.fake.calls, [])        # nothing has gone anywhere yet
        tid = self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": spec, "scope": "show"}))["id"]
        f = self.fake
        f.routes[("POST", "/v2/videos/create")] = {"result": {"job_id": "abc", "state": "queued"}}
        f.routes[("GET", "/v2/videos/abc")] = {"result": {"state": "ready", "files": [f.url + "/a.mp4"]}}
        f.routes[("GET", "/a.mp4")] = tiny_mp4()
        self.ok(A.post_render(self.ctx, {"ep": self.ep, "pass": "proxy", "shots": ["sh010"], "target": tid,
                                         "allow_missing_refs": True, "redo": True}))
        self.settle()
        sc = T.list_takes(self.ep, "proxy", "sh010")[-1].sidecar
        self.assertEqual(sc["status"], "ok", sc.get("save_notes"))
        self.assertEqual(sc["backend"], "api:newco")
        sent = json.loads(next(c for c in f.calls if c["method"] == "POST")["body"])
        self.assertEqual(sent["model_name"], "newco-1")


class AContentList(ScratchSettings):
    """BytePlus's shape, from its docs' cURL and the answers its published schema gives
    (tests/fixtures/router_schemas/byteplus__*): a prompt and pictures as typed items of one list,
    a job with a status, the video in `content`."""

    CURL = ("curl -X POST https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks "
            "-H 'Content-Type: application/json' -H 'Authorization: Bearer $ARK_API_KEY' -d '"
            + json.dumps({"model": "dreamina-seedance-2-5-260628", "content": [
                {"type": "text", "text": "One continuous shot (refer to Image 1)."},
                {"type": "image_url", "role": "reference_image", "image_url": {"url": "asset://asset-1"}},
                {"type": "image_url", "role": "reference_image", "image_url": {"url": "https://x/2.png"}}],
                "generate_audio": True, "ratio": "16:9", "duration": 30, "watermark": True}) + "'")
    ANSWER = {"id": "cgt-1", "status": "succeeded", "error": None, "seed": 1,
              "content": {"video_url": "https://x/v.mp4", "last_frame_url": "https://x/f.png"}}

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)

    def draft(self):
        from seriesmith import providerdraft as PD
        return PD.draft(self.CURL, answer='{"id": "cgt-1"}',
                        poll="curl https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks/cgt-1",
                        poll_answer=json.dumps(self.ANSWER))

    def test_the_form(self):
        got = self.draft()
        f = got["form"]
        self.assertEqual(got["model"], "dreamina-seedance-2-5-260628")
        self.assertEqual((f["auth_type"], f["model_field"], f["id_path"], f["status_path"], f["files_path"]),
                         ("bearer", "model", "id", "status", "content.video_url"))
        self.assertEqual(f["poll_url"], "/api/v3/contents/generations/tasks/{task}")
        self.assertNotIn("ARK_API_KEY", json.dumps(got))

    def test_every_item_of_a_list_counts(self):
        from seriesmith import api as A
        d = PD_definition(self.draft()["form"], id="byteplus", base_url=self.fake.url)
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        got = self.ok(A.post_provider_read_spec(self.ctx, {"service": "byteplus", "model": "dreamina-seedance-2-5-260628",
                                                           "text": self.CURL}))
        inp = got["proposal"]["api"]["inputs"]
        self.assertEqual(inp["prompt"], {"list": "content", "item": {"type": "text", "text": "$prompt"}})
        self.assertEqual(inp["references"], {"list": "content", "item": {
            "type": "image_url", "image_url": {"url": "$url"}, "role": "reference_image"}})
        self.assertNotIn("via", inp)                 # Comfy's way in: not this provider's

    def test_a_size_with_no_values_says_so(self):
        from seriesmith import api as A
        d = PD_definition(self.draft()["form"], id="byteplus", base_url=self.fake.url)
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        spec = self.ok(A.post_provider_read_spec(self.ctx, {"service": "byteplus", "model": "dreamina-seedance-2-5-260628",
                                                            "text": self.CURL}))["proposal"]
        spec["api"]["inputs"]["resolution"] = {"name": "resolution"}
        code, data = A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "target": {**spec, "draft": False}, "shot": "sh010"})
        self.assertIn("values", json.dumps(data))
        self.assertNotIn("KeyError", json.dumps(data))
        self.assertEqual(self.fake.calls, [])

    def test_to_a_finished_take(self):
        from seriesmith import api as A
        from seriesmith import takes as T
        from test_router_render import tiny_mp4
        f = self.fake
        path = "/api/v3/contents/generations/tasks"
        d = PD_definition(self.draft()["form"], id="byteplus", base_url=f.url, every=0.01)
        self.assertEqual(d["files"], {"via": "datauri"})       # its schema's "Base64": data:image/<format>;base64
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        self.ok(A.put_provider_key(self.ctx, {"id": "byteplus", "key": KEY}))
        spec = self.ok(A.post_provider_read_spec(self.ctx, {"service": "byteplus", "model": "dreamina-seedance-2-5-260628",
                                                            "text": self.CURL}))["proposal"]
        tid = self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": {**spec, "draft": False}, "scope": "show"}))["id"]
        f.routes[("POST", path)] = {"id": "cgt-1"}
        f.routes[("GET", path + "/cgt-1")] = {**self.ANSWER, "content": {"video_url": f.url + "/v.mp4", "last_frame_url": f.url + "/f.png"}}
        f.routes[("GET", "/v.mp4")] = tiny_mp4()
        self.ok(A.post_render(self.ctx, {"ep": self.ep, "pass": "proxy", "shots": ["sh010"], "target": tid,
                                         "allow_missing_refs": True, "redo": True}))
        self.settle()
        sc = T.list_takes(self.ep, "proxy", "sh010")[-1].sidecar
        self.assertEqual(sc["status"], "ok", sc.get("save_notes"))
        sent = json.loads(next(c for c in f.calls if c["method"] == "POST")["body"])
        self.assertEqual(sent["model"], "dreamina-seedance-2-5-260628")
        self.assertEqual(sent["content"][0]["type"], "text")
        self.assertTrue(sent["content"][0]["text"])


def PD_definition(form: dict, **more) -> dict:
    from seriesmith import providerdraft as PD
    return PD.definition({**form, **more})


class ADocsPage(ScratchSettings):
    """fal's model page: the cURLs in its HTML, a link to the model's OpenAPI document (the document as
    read 2026-11-05), the video in the answer the status's response_url gives."""

    MODEL = "blackforestlabs/flux-3-max/image-to-video"

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "provider_docs", "fal_flux3max_i2v.json"), encoding="utf-8") as fh:
            self.doc = json.load(fh)
        q = "https://queue.fal.run/blackforestlabs/flux-3-max"
        page = f"""<html><a href="/api/openapi.json?endpoint_id=x">schema</a><pre><code>response=$(curl --request POST \\
  --url https://queue.fal.run/{self.MODEL} \\
  --header &quot;Authorization: Key $FAL_KEY&quot; \\
  --header &quot;Content-Type: application/json&quot; \\
  --data &#x27;{{"prompt": "a \\"quoted\\" (b)", "image_url": "https://x/a.jpg"}}&#x27;)
REQUEST_ID=$(echo &quot;$response&quot; | grep -o &#x27;&quot;request_id&quot;: *&quot;[^&quot;]*&quot;&#x27;)</code></pre>
  <pre><code>curl --request GET \\
  --url {q}/requests/$REQUEST_ID/status \\
  --header &quot;Authorization: Key $FAL_KEY&quot;</code></pre>
  <pre><code>curl --request GET \\
  --url {q}/requests/$REQUEST_ID \\
  --header &quot;Authorization: Key $FAL_KEY&quot;</code></pre></html>"""
        self.fake.routes[("GET", "/models/flux/api")] = page.encode()
        self.fake.routes[("GET", "/api/openapi.json")] = self.doc
        self.page = self.fake.url + "/models/flux/api"

    def read(self):
        from seriesmith import api as A
        return self.ok(A.post_provider_draft(self.ctx, {"text": self.page}))

    def test_the_page_alone_fills_the_form(self):
        got = self.read()
        f = got["form"]
        self.assertEqual(got["model"], self.MODEL)
        self.assertEqual((f["base_url"], f["url"], f["auth_type"], f["auth_name"], f["auth_prefix"]),
                         ("https://queue.fal.run", "/{model}", "header", "Authorization", "Key "))
        self.assertEqual((f["id_path"], f["poll_url"], f["fetch_url"], f["status_path"], f["files_path"]),
                         ("request_id", "$status_url", "$response_url", "status", "video.url"))
        self.assertEqual(f["check_url"], "/blackforestlabs/flux-3-max/requests/{task}/status")
        self.assertEqual(f["error_path"], "error")
        self.assertEqual(got["problems"], [])
        self.assertNotIn("IN_QUEUE", f["done"].upper())

    def test_a_curl_inside_a_script(self):
        for text, url in (("response=$(curl -X POST https://a.example/go -d '{\"a\": \"(b) | c\"}')\nID=$(echo x | grep y)", "https://a.example/go"),
                          ("curl https://a.example/go \\\n  -d '{\"a\": 1}' | jq .", "https://a.example/go"),
                          ("curl https://a.example/go\n  -H 'Authorization: Bearer x'\n  -d '{\"a\": 1}'\n\necho done", "https://a.example/go")):
            with self.subTest(text=text):
                got = AS.parse_curl(text)
                self.assertEqual(got["url"], url)
                self.assertTrue(got["body"])
        self.assertIsNone(AS.curl_in('{"description": "use curl -X POST to start"}'))
        self.assertIsNone(AS.curl_in("not one"))

    def test_the_document_alone_says_what_it_can(self):
        from seriesmith import providerdraft as PD
        got = PD.draft(json.dumps(self.doc))
        f = got["form"]
        self.assertEqual((got["model"], f["url"], f["files_path"], f["poll_url"]),
                         (self.MODEL, "/{model}", "video.url", "$status_url"))
        self.assertEqual(f["auth_prefix"], "")       # it doesn't say: told, not guessed
        self.assertTrue(any("before the key" in n for n in got["notes"]))
        self.assertEqual(PD.form_problems(f), [])

    def test_a_page_with_nothing_on_it(self):
        from seriesmith import api as A
        self.fake.routes[("GET", "/shell")] = b"<html><div id='root'></div></html>"
        code, data = A.post_provider_draft(self.ctx, {"text": self.fake.url + "/shell"})
        self.assertEqual(code, 400)
        self.assertIn("example cURL", data["error"])

    def test_the_model_from_the_same_address(self):
        from seriesmith import api as A
        d = {**self.read()["definition"], "base_url": self.fake.url}
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        got = self.ok(A.post_provider_read_spec(self.ctx, {"service": "fal", "model": self.MODEL, "text": self.page}))
        inp = got["proposal"]["api"]["inputs"]
        self.assertEqual(inp["first"], {"field": "image_url"})
        self.assertEqual(inp["last"], {"field": "end_image_url"})
        self.assertEqual(inp["resolution"]["values"], ["720p", "1080p"])
        self.assertEqual(inp["duration"]["values"], list(range(5, 21)))
        self.assertIn("first", got["proposal"]["recipe"]["keyframe_required"])

    def backend(self):
        d = {**self.read()["definition"], "base_url": self.fake.url}
        next(s for s in d["steps"] if s.get("until"))["until"]["every"] = 0.01
        return d, HttpBackend(d, KEY)

    def answers(self, status_doc=None):
        f = self.fake
        q = f.url + "/blackforestlabs/flux-3-max/requests/r1"
        f.routes[("POST", "/" + self.MODEL)] = {"request_id": "r1", "status": "IN_QUEUE", "status_url": q + "/status",
                                                "response_url": q, "cancel_url": q + "/cancel"}
        f.routes[("GET", "/blackforestlabs/flux-3-max/requests/r1/status")] = status_doc or {"status": "COMPLETED", "request_id": "r1"}
        f.routes[("GET", "/blackforestlabs/flux-3-max/requests/r1")] = {"video": {"url": f.url + "/v.mp4"}, "seed": 1}
        f.routes[("GET", "/v.mp4")] = b"video bytes"

    def test_a_picture_goes_inline_and_the_video_comes_back(self):
        _, b = self.backend()
        self.answers()
        pic = os.path.join(self.tmp, "pic.png")
        with open(pic, "wb") as fh:
            fh.write(b"\x89PNG picture")
        run = b.call(self.MODEL, {"prompt": "a", "image_url": File(pic)})
        self.assertEqual(run.watch(), "succeeded")
        sent = next(c for c in self.fake.calls if c["method"] == "POST")
        self.assertEqual(sent["path"], "/" + self.MODEL)     # the slashes kept
        self.assertEqual(sent["headers"]["Authorization"], f"Key {KEY}")
        body = json.loads(sent["body"])
        self.assertTrue(body["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("model", body)
        (out,) = run.outputs()
        self.assertTrue(out.save(os.path.join(self.tmp, "v.mp4")))
        video = next(c for c in self.fake.calls if c["path"] == "/v.mp4")
        self.assertIsNone(video["headers"].get("Authorization"))

    def test_done_with_an_error_beside_it_is_a_failure(self):
        _, b = self.backend()
        self.answers({"status": "COMPLETED", "request_id": "r1", "error": "the model refused it"})
        run = b.call(self.MODEL, {"prompt": "a"})
        self.assertEqual(run.watch(), "failed")
        self.assertFalse(any(c["path"] == "/v.mp4" for c in self.fake.calls))

    def test_the_check_asks_the_address_the_page_showed(self):
        from seriesmith.backends.http import check_key
        d, _ = self.backend()
        path = "/blackforestlabs/flux-3-max/requests/seriesmith-check-does-not-exist/status"
        self.fake.routes[("GET", path)] = (401, {"detail": "bad key"}, {})
        got = check_key(d, "bad")
        self.assertEqual((got["key_ok"], got["proves_key"]), (False, True))

    def test_a_check_with_no_address_says_it_proves_nothing(self):
        from seriesmith.backends.http import check_key
        d, _ = self.backend()
        del d["check"]
        self.assertFalse(check_key(d, KEY)["proves_key"])


class Higgsfield(WithFake):
    """Its definition as it ships, on answers as its docs show them (read 2026-11-05): a file goes to
    an address its answer gives, with the headers its answer gives, and that storage gets no key."""

    MODEL = "minimax/h3/reference-to-video"
    KEY = "id-1:secret-2"

    def setUp(self):
        super().setUp()
        self.storage = Fake()
        self.addCleanup(self.storage.close)
        self.d = json.loads(json.dumps(PR.definitions()["higgsfield"]))
        self.d["base_url"] = self.fake.url
        self.d["steps"][1]["until"]["every"] = 0.01
        self.b = HttpBackend(self.d, self.KEY)
        f, s = self.fake, self.storage
        f.routes[("POST", "/files/generate-upload-url")] = lambda c: {
            "public_url": s.url + "/input/pic.png", "upload_url": s.url + "/put/pic.png?sig=a%2Bb&x=1",
            "content_type": json.loads(c["body"])["content_type"],
            "upload_headers": {"Content-Type": json.loads(c["body"])["content_type"], "x-amz-tagging": "retention=temporary"}}
        s.routes[("PUT", "/put/pic.png")] = b""
        s.routes[("GET", "/out/v.mp4")] = b"video bytes"
        f.routes[("POST", "/" + self.MODEL)] = {
            "status": "queued", "request_id": "r1", "status_url": f.url + "/requests/r1/status",
            "cancel_url": f.url + "/requests/r1/cancel", "expires_after": 604800}
        self.finished({"status": "completed", "request_id": "r1", "video": {"url": s.url + "/out/v.mp4"}, "error": None})

    def finished(self, answer):
        self.fake.routes[("GET", "/requests/r1/status")] = answer

    def go(self, pics=None):
        return self.b.call(self.MODEL, {"prompt": "a", "image_urls": [File(self.pic)] if pics is None else pics})

    def test_a_picture_goes_in_two_steps_and_a_take_comes_back(self):
        run = self.go()
        self.assertEqual(run.watch(), "succeeded")
        [ask, job, *_] = self.fake.calls
        self.assertEqual(ask["path"], "/files/generate-upload-url")
        self.assertEqual(json.loads(ask["body"]), {"content_type": "image/png"})
        self.assertEqual(ask["headers"]["Authorization"], "Key " + self.KEY)
        put = self.storage.calls[0]
        self.assertEqual((put["method"], put["path"]), ("PUT", "/put/pic.png?sig=a%2Bb&x=1"))
        self.assertEqual(put["body"], b"\x89PNG picture")
        self.assertEqual(put["headers"]["Content-Type"], "image/png")
        self.assertEqual(put["headers"]["x-amz-tagging"], "retention=temporary")
        # the model is in the address, and what's sent is the model's own fields
        self.assertEqual(json.loads(job["body"]), {"prompt": "a", "image_urls": [self.storage.url + "/input/pic.png"]})
        (out,) = run.outputs()
        self.assertEqual(out.type, "video")
        path = out.save(os.path.join(self.tmp.name, "v.mp4"))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"video bytes")

    def test_storage_and_links_never_get_the_key(self):
        self.assertEqual(self.go().watch(), "succeeded")
        for c in self.storage.calls:
            self.assertNotIn("Authorization", c["headers"])
            self.assertNotIn(self.KEY, c["path"])

    def test_no_key_where_a_step_says_so_on_its_own_host_too(self):
        f = self.fake
        f.routes[("POST", "/files/generate-upload-url")] = {
            "public_url": "https://cdn.example/p.png", "upload_url": f.url + "/put", "upload_headers": {"x-a": "b"}}
        f.routes[("PUT", "/put")] = b"<ok/>"              # an answer that isn't JSON is fine here
        self.assertEqual(self.go().watch(), "succeeded")
        put = next(c for c in f.calls if c["method"] == "PUT")
        self.assertNotIn("Authorization", put["headers"])

    def test_a_signed_address_stays_out_of_a_message(self):
        self.fake.routes[("POST", "/files/generate-upload-url")] = {"upload_url": "https://s.example/a?sig=secret", "upload_headers": {}}
        with self.assertRaises(Exception) as e:
            self.go()
        self.assertIn("public_url", str(e.exception))
        self.assertNotIn("sig=secret", str(e.exception))

    def test_a_webp_is_declared_as_one(self):
        pic = os.path.join(self.tmp.name, "pic.webp")
        with open(pic, "wb") as fh:
            fh.write(b"RIFF")
        self.go([File(pic)])
        self.assertEqual(json.loads(self.fake.calls[0]["body"]), {"content_type": "image/webp"})
        self.assertEqual(self.storage.calls[0]["headers"]["Content-Type"], "image/webp")

    def test_one_picture_twice_goes_once(self):
        self.go([File(self.pic), File(self.pic)])
        self.assertEqual(len(self.storage.calls), 1)

    def test_a_picture_or_answer_it_refuses_fails_and_says_so(self):
        for status, said in (("failed", "it broke"), ("nsfw", "the provider says nsfw"), ("canceled", "the provider says canceled")):
            with self.subTest(status):
                self.finished({"status": status, "request_id": "r1", "error": "it broke" if status == "failed" else None})
                run = self.go()
                self.assertEqual(run.watch(), "failed")
                self.assertEqual(run.error, said)

    def test_a_run_followed_after_a_restart_has_no_key_in_it(self):
        run = self.go()
        self.assertNotIn(self.KEY, run.id)
        again = self.b.attach(run.id)
        self.assertEqual(again.watch(), "succeeded")
        self.assertEqual(len([c for c in self.fake.calls if c["path"] == "/" + self.MODEL]), 1)

    def test_cancel_asks_it_to(self):
        self.fake.routes[("POST", "/requests/r1/cancel")] = (202, b"", {})
        self.go().cancel()
        self.assertTrue(any(c["path"] == "/requests/r1/cancel" for c in self.fake.calls))

    def test_check_it_proves_the_key(self):
        from seriesmith.backends.http import check_key
        self.fake.routes[("GET", "/requests/00000000-0000-0000-0000-000000000000/status")] = lambda c: (
            (404, {"detail": "no"}, {}) if c["headers"].get("Authorization") == "Key " + self.KEY
            else (401, {"detail": "Invalid credentials"}, {}))
        good = check_key(self.d, self.KEY)
        self.assertTrue(good["key_ok"] and good["proves_key"])
        self.assertFalse(check_key(self.d, "x:y")["key_ok"])

    def test_the_panel_shows_both_steps_with_nothing_sent(self):
        from seriesmith.backends.http import planned_calls
        calls = planned_calls(self.d, self.MODEL, {"prompt": "a", "image_urls": [File(self.pic)]})
        self.assertEqual([c["method"] for c in calls[:3]], ["POST", "PUT", "POST"])
        self.assertEqual(calls[0]["sends"], {"content_type": "(its type)"})
        self.assertEqual(calls[1]["sends"], {"body": "(the file)"})
        self.assertEqual(calls[1]["key"], "no key")
        self.assertEqual(self.fake.calls, [])


class Runway(WithFake):
    """Its definition as it ships, on answers shaped as its OpenAPI document says (read 2026-11-05):
    a version every request needs, a form for storage, a text-only shot at another address."""

    def setUp(self):
        super().setUp()
        self.storage = Fake()
        self.addCleanup(self.storage.close)
        self.d = json.loads(json.dumps(PR.definitions()["runwayml"]))
        self.d["base_url"] = self.fake.url
        self.d["steps"][1]["until"]["every"] = 0.01
        self.b = HttpBackend(self.d, KEY)
        f, s = self.fake, self.storage
        f.routes[("POST", "/v1/uploads")] = {
            "uploadUrl": s.url + "/bucket", "fields": {"key": "k/1", "policy": "p"}, "runwayUri": "runway://abc"}
        s.routes[("POST", "/bucket")] = (204, b"", {})
        f.routes[("POST", "/v1/image_to_video")] = {"id": "t1", "estimatedCost": {"credits": 60}}
        f.routes[("POST", "/v1/text_to_video")] = {"id": "t1", "estimatedCost": {"credits": 60}}
        s.routes[("GET", "/out/v.mp4")] = b"video bytes"
        self.finished({"id": "t1", "status": "SUCCEEDED", "output": [s.url + "/out/v.mp4"], "cost": {"credits": 60}})

    def finished(self, answer):
        self.fake.routes[("GET", "/v1/tasks/t1")] = answer

    def go(self, args=None, endpoint="image_to_video"):
        return self.b.call("gen4.5", {"promptText": "a", "promptImage": File(self.pic), "ratio": "1280:720", **(args or {}),
                                      ROUTING: {"values": {"endpoint": endpoint}}})

    def test_a_take_from_upload_to_download(self):
        run = self.go()
        self.assertEqual(run.watch(), "succeeded")
        ask, job, *_ = self.fake.calls
        self.assertEqual(json.loads(ask["body"]), {"filename": "pic.png", "type": "ephemeral"})
        self.assertEqual(ask["path"], "/v1/uploads")
        self.assertEqual(json.loads(job["body"]), {"model": "gen4.5", "promptText": "a", "promptImage": "runway://abc", "ratio": "1280:720"})
        self.assertEqual(job["path"], "/v1/image_to_video")
        form = self.storage.calls[0]
        self.assertEqual(form["method"], "POST")
        self.assertTrue(form["headers"]["Content-Type"].startswith("multipart/form-data"))
        # its fields, then the file last, as storage wants
        self.assertLess(form["body"].index(b'name="key"'), form["body"].index(b'name="file"'))
        self.assertIn(b"k/1", form["body"])
        self.assertIn(b"\x89PNG picture", form["body"])
        (out,) = run.outputs()
        path = out.save(os.path.join(self.tmp.name, "v.mp4"))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"video bytes")

    def test_every_request_of_its_own_has_the_version_and_the_key(self):
        self.go().watch()
        for c in self.fake.calls:
            self.assertEqual(c["headers"]["X-Runway-Version"], "2024-11-06", c["path"])
            self.assertEqual(c["headers"]["Authorization"], "Bearer " + KEY)
        for c in self.storage.calls:
            self.assertNotIn("Authorization", c["headers"])
            self.assertNotIn("X-Runway-Version", c["headers"])

    def test_storage_answering_in_xml_is_fine(self):
        self.storage.routes[("POST", "/bucket")] = (201, b"<PostResponse/>", {})
        self.assertEqual(self.go().watch(), "succeeded")

    def test_failed_and_cancelled_say_so(self):
        for status, want in (("FAILED", "the picture was refused"), ("CANCELLED", "the provider says cancelled")):
            with self.subTest(status):
                self.finished({"id": "t1", "status": status, "failure": "the picture was refused" if status == "FAILED" else None})
                run = self.go()
                self.assertEqual(run.watch(), "failed")
                self.assertEqual(run.error, want)
        self.finished({"id": "t1", "status": "FAILED", "failureCode": "INPUT.BAD"})
        run = self.go()
        run.watch()
        self.assertEqual(run.error, "INPUT.BAD")

    def test_waiting_through_its_states(self):
        states = iter(["PENDING", "THROTTLED", "RUNNING", "SUCCEEDED"])
        self.fake.routes[("GET", "/v1/tasks/t1")] = lambda c: {"id": "t1", "status": next(states), "output": [self.storage.url + "/out/v.mp4"]}
        self.assertEqual(self.go().watch(), "succeeded")

    def test_cancel_deletes_the_task(self):
        self.fake.routes[("DELETE", "/v1/tasks/t1")] = (204, b"", {})
        self.go().cancel()
        self.assertTrue(any(c["method"] == "DELETE" and c["path"] == "/v1/tasks/t1" for c in self.fake.calls))

    def test_check_it_is_a_real_read(self):
        from seriesmith.backends.http import check_key
        self.fake.routes[("GET", "/v1/organization")] = lambda c: (
            (200, {"creditBalance": 100}, {}) if c["headers"].get("X-Runway-Version") and c["headers"].get("Authorization") == "Bearer " + KEY
            else (401, {"error": "bad"}, {}))
        got = check_key(self.d, KEY)
        self.assertTrue(got["key_ok"] and got["proves_key"])
        self.assertFalse(check_key(self.d, "other")["key_ok"])

    def test_the_panel_shows_the_version_and_the_form(self):
        from seriesmith.backends.http import planned_calls
        calls = planned_calls(self.d, "gen4.5", {"promptText": "a", "promptImage": File(self.pic), ROUTING: {"values": {"endpoint": "image_to_video"}}})
        self.assertIn("X-Runway-Version: 2024-11-06", calls[0]["key"])
        self.assertEqual(calls[1]["key"], "no key")
        self.assertEqual(calls[1]["sends"], {"(the fields its answer gives)": "...", "file": "(the file)"})
        self.assertEqual(calls[2]["url"], self.fake.url + "/v1/image_to_video")


class RunwayList(AtlasList):
    """Runway's models as its OpenAPI document states them (presets/providers/runwayml.models.json)."""

    def proposed(self, model):
        return AS.propose("runwayml", model, "", base=self.base)

    def view(self, model, frame=False):
        spec = self.proposed(model)["proposal"]
        if frame:
            path = os.path.join(self.root, spec["recipe"]["keyframe_path"].format(shot="sh010", end="first"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG")
        return PV.preview(self.root, spec["id"], shot="sh010", spec=spec)

    def test_every_one_proposes_and_previews_with_its_own_fields_placed(self):
        from seriesmith import inspector as IN
        for m in PR.catalog("runwayml"):
            with self.subTest(m["id"]):
                got = self.proposed(m["id"])
                spec = got["proposal"]
                self.assertEqual(IN.validate_spec(spec), [])
                self.assertEqual(got["form"], "catalog")
                self.assertEqual(got["unplaced"], [])
                self.assertEqual(spec["kind"], m["kind"])
                view = PV.preview(self.root, spec["id"], shot="sh010", spec=spec) if m["kind"] == "video" \
                    else PV.preview(self.root, spec["id"], spec=spec)
                self.assertTrue(view["ok"], view.get("why"))
                self.assertEqual(TG.service_of(spec), "runwayml")

    def test_no_id_collides_with_a_shipped_model(self):
        for m in PR.catalog("runwayml"):
            spec = self.proposed(m["id"])["proposal"]
            with self.assertRaises(Exception, msg=spec["id"]):
                TG.load_target(spec["id"], m["kind"])

    def test_only_what_a_model_has_is_sent(self):
        for m in PR.catalog("runwayml"):
            if m["kind"] != "video":
                continue
            with self.subTest(m["id"]):
                view = self.view(m["id"], frame=m["id"] == "gen4_turbo")
                self.assertTrue(view["ok"], view.get("why"))
                self.assertLessEqual(set(view["arguments"]), set(m["fields"]))

    def test_a_text_shot_goes_to_text_to_video(self):
        from seriesmith.targets.generic.router_video import with_routing
        spec = self.proposed("gen4.5")["proposal"]["api"]
        self.assertEqual(spec["values"]["endpoint"], "image_to_video")
        self.assertEqual(with_routing({}, spec, pictures=False)[ROUTING]["values"]["endpoint"], "text_to_video")
        self.assertEqual(with_routing({}, spec, pictures=True)[ROUTING]["values"]["endpoint"], "image_to_video")

    def test_an_image_stays_at_text_to_image(self):
        spec = self.proposed("gen4_image")["proposal"]["api"]
        self.assertEqual(spec["values"]["endpoint"], "text_to_image")
        self.assertNotIn("values_text", spec)

    def test_a_frame_goes_as_its_model_writes_it(self):
        self.assertIsInstance(self.view("gen4.5", frame=True)["arguments"]["promptImage"], (str, dict))
        got = self.view("seedance2_5", frame=True)["arguments"]
        self.assertEqual(got["promptImage"][0]["position"], "first")
        self.assertIn("ratio", got)

    def test_h3_keeps_the_prompt_as_written(self):
        self.assertEqual(self.proposed("h3_max")["proposal"]["api"]["arguments"]["promptExpansionMode"], "disabled")
        self.assertEqual(self.view("h3_max")["arguments"]["promptExpansionMode"], "disabled")

    def test_a_ratio_that_is_also_a_size_goes_by_the_size_asked(self):
        from seriesmith.targets.generic.request_map import ratio_for
        spec = {"values": ["854:480", "480:854", "1280:720", "720:1280", "1920:1080", "1080:1920", "960:960", "640:640"], "by_size": True}
        self.assertEqual(ratio_for(1920, 1080, spec), "1920:1080")
        self.assertEqual(ratio_for(1280, 720, spec), "1280:720")
        self.assertEqual(ratio_for(848, 480, spec), "854:480")
        self.assertEqual(ratio_for(1080, 1920, spec), "1080:1920")
        self.assertEqual(ratio_for(720, 720, spec), "640:640")
        # without it, as ever: the nearest shape, the first of a tie
        self.assertEqual(ratio_for(1920, 1080, {"values": ["1280:720", "1920:1080"]}), "1280:720")

    def test_a_listing_says_what_is_on_it(self):
        row = next(r for r in PR.listing(S.Settings(), {}) if r["id"] == "runwayml")
        self.assertIn("h3_max", {m["id"] for m in row["catalog"]})
        self.assertTrue(row["untested"])

    # what's only Atlas's
    test_the_last_frame_on_any_name = None
    test_what_the_sound_is_called = None
    test_a_size_as_the_api_writes_it = None
    test_an_edit_models_pictures = None
    test_a_first_frame_model_says_it_needs_one = None
    test_it_comes_from_the_docs_and_says_so = None
    test_seedance_goes_to_the_id_for_what_is_sent = None
    test_a_first_frame_sends_the_frame_and_goes_to_its_id = None
    test_an_answer_flat_or_wrapped = None


class AMarkdownPage(ScratchSettings):
    """A Higgsfield model page, as served 2026-11-05: its source in Markdown beside the page, with the
    cURL, the whole schema in a quote, and example answers. Other models' pages are the same."""

    MODEL = "minimax/h3/image-to-video"

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "provider_docs", "higgsfield_h3_i2v.md"), "rb") as fh:
            self.md = fh.read()
        self.fake.routes[("GET", "/docs/h3.md")] = self.md
        # its HTML: an example, and a link to an OpenAPI document without this model
        self.fake.routes[("GET", "/docs/h3")] = (b'<a href="/docs/openapi.json">x</a><pre><code>curl --request POST '
                                                 b'--url https://api.higgsfield.ai/minimax/h3/image-to-video --data \'{"prompt": "a"}\''
                                                 b'</code></pre>')
        self.fake.routes[("GET", "/docs/openapi.json")] = {"openapi": "3.1.0", "paths": {"/other": {}}}

    def test_what_it_reads(self):
        from seriesmith import providerdraft as PD
        got = PD.from_page(self.md.decode("utf-8"), "https://docs.higgsfield.ai/x.md")
        self.assertIn("/minimax/h3/image-to-video", got["post"])
        self.assertEqual(got["schema"]["required"], ["prompt", "image_url"])
        self.assertIn("status_url", got["answer"])
        self.assertIn("video", got["poll_answer"])

    def test_the_address_fills_the_form_with_or_without_md(self):
        from seriesmith import api as A
        for tail in ("/docs/h3.md", "/docs/h3", "/docs/h3?x=1"):
            with self.subTest(tail):
                got = self.ok(A.post_provider_draft(self.ctx, {"text": self.fake.url + tail}))
                f = got["form"]
                self.assertEqual(got["model"], self.MODEL)
                self.assertEqual((f["base_url"], f["url"], f["auth_name"], f["auth_prefix"]),
                                 ("https://api.higgsfield.ai", "/{model}", "Authorization", "Key "))
                self.assertEqual((f["id_path"], f["poll_url"], f["status_path"], f["files_path"]),
                                 ("request_id", "$status_url", "status", "video.url"))
                self.assertEqual(got["problems"], [])

    def test_another_model_on_a_listed_provider_needs_only_its_address(self):
        from seriesmith import api as A
        got = self.ok(A.post_provider_read_spec(self.ctx, {"service": "higgsfield", "model": "", "text": self.fake.url + "/docs/h3"}))
        self.assertEqual(got["model"], self.MODEL)
        self.assertEqual(got["form"], "openapi")
        inputs = got["proposal"]["api"]["inputs"]
        self.assertEqual(inputs["duration"], {"name": "duration", "min": 5, "max": 15})
        self.assertEqual(inputs["first"], {"field": "image_url"})
        self.assertEqual(inputs["last"], {"field": "end_image_url"})

    def test_a_typed_model_stays(self):
        from seriesmith import api as A
        got = self.ok(A.post_provider_read_spec(self.ctx, {"service": "higgsfield", "model": "my/own", "text": self.fake.url + "/docs/h3"}))
        self.assertEqual(got["model"], "my/own")

    def test_a_provider_with_the_model_in_its_body_still_asks_for_it(self):
        from seriesmith import api as A
        got = A.post_provider_read_spec(self.ctx, {"service": "atlas", "model": "", "text": self.fake.url + "/docs/h3"})
        self.assertEqual(got[0], 400)

    def test_a_body_as_a_here_document(self):
        # Higgsfield's sample request, as its site shows it
        sample = """curl --request POST \\
  --url 'https://api.higgsfield.ai/bytedance/seedance-2.5/text-to-video' \\
  --header "Authorization: Key $HF_KEY" \\
  --header "Content-Type: application/json" \\
  --data @- <<'JSON'
{
  "prompt": "A cinematic scene at sunset",
  "duration": 5,
  "generate_audio": true
}
JSON
"""
        for text in (sample, sample.replace("\n", "\r\n")):
            got = AS.parse_curl(text)
            self.assertEqual(got["url"], "https://api.higgsfield.ai/bytedance/seedance-2.5/text-to-video")
            self.assertEqual(got["method"], "POST")
            self.assertEqual(got["auth"], {"type": "header", "name": "Authorization", "prefix": "Key "})
            self.assertEqual(got["body"], {"prompt": "A cinematic scene at sunset", "duration": 5, "generate_audio": True})
        self.assertEqual(AS.read(sample, None)["form"], "curl")
        from seriesmith import providerdraft as PD
        drafted = PD.draft(sample)
        self.assertEqual(drafted["model"], "bytedance/seedance-2.5/text-to-video")
        self.assertEqual(drafted["form"]["url"], "/{model}")

    def test_a_here_document_is_only_for_data_that_asks_for_it(self):
        got = AS.parse_curl("curl https://a.example/go -d '{\"a\": 1}'\ncat <<EOF\nnot it\nEOF\n")
        self.assertEqual(got["body"], {"a": 1})

    def test_a_header_it_asks_for_every_time_but_no_key_or_placeholder(self):
        got = AS.parse_curl("curl https://a.example/go -H 'Authorization: Bearer $K' -H 'X-Runway-Version: 2024-11-06' "
                            "-H 'X-Trace: $TRACE' -H 'X-Secret-Thing: s' -H 'Content-Type: application/json' -d '{}'")
        self.assertEqual(got["headers"], {"X-Runway-Version": "2024-11-06"})
        from seriesmith import providerdraft as PD
        drafted = PD.draft("curl https://a.example/go -H 'X-Runway-Version: 2024-11-06' -d '{\"model\": \"m\"}'")
        self.assertEqual(drafted["form"]["headers"], "X-Runway-Version: 2024-11-06")

    def test_the_key_is_who_is_asking_and_not_the_request(self):
        for text in ("curl https://a.example/go -H 'Authorization: Key x' -H 'Idempotency-Key: y' -d '{\"a\": 1}'",
                     "curl https://a.example/go -H 'Idempotency-Key: y' -H 'Authorization: Key x' -d '{\"a\": 1}'"):
            self.assertEqual(AS.parse_curl(text)["auth"], {"type": "header", "name": "Authorization", "prefix": "Key "})
        self.assertEqual(AS.parse_curl("curl https://a.example/go -H 'Idempotency-Key: y' -d '{}'")["auth"], None)
        self.assertEqual(AS.parse_curl("curl https://a.example/go -H 'x-api-key: y' -d '{}'")["auth"], {"type": "header", "name": "x-api-key"})


class AnUploadAddressInTheForm(unittest.TestCase):
    FORM = {"id": "x", "base_url": "https://a.example", "url": "/{model}", "answer": "links", "files_path": "url",
            "files_via": "presigned", "upload_url": "/ask", "upload_put": "put.to", "upload_link": "public"}

    def test_it_comes_to_two_steps_and_storage_gets_no_key(self):
        from seriesmith import providerdraft as PD
        d = PD.definition(self.FORM)
        self.assertEqual(PR.problems(d), [])
        ask, put = d["files"]["steps"]
        self.assertEqual(d["files"]["via"], "upload")
        self.assertEqual(ask["json"], {"content_type": "$mime"})
        self.assertEqual(ask["take"], {"put_to": "put.to", "link": "public"})
        self.assertEqual(put, {"method": "PUT", "url": "$put_to", "key": False, "body": "$file"})

    def test_headers_only_when_it_gives_them(self):
        from seriesmith import providerdraft as PD
        d = PD.definition({**self.FORM, "upload_headers": "h"})
        ask, put = d["files"]["steps"]
        self.assertEqual(ask["json"], {"content_type": "$mime"})
        self.assertEqual(ask["take"]["put_headers"], "h")
        self.assertEqual(put["headers"], "$put_headers")

    def test_a_form_to_post_where_its_answer_says(self):
        from seriesmith import providerdraft as PD
        d = PD.definition({**self.FORM, "upload_fields": "fields", "upload_body": '{"filename": "$name"}'})
        ask, put = d["files"]["steps"]
        self.assertEqual(ask["json"], {"filename": "$name"})
        self.assertEqual(put["multipart"], {"...": "$put_fields", "file": "$file"})
        self.assertFalse(put["key"])
        self.assertEqual(put["response"], "none")

    def test_it_says_what_is_missing(self):
        from seriesmith import providerdraft as PD
        self.assertEqual(PD.form_problems(self.FORM), [])
        self.assertTrue(PD.form_problems({**self.FORM, "upload_put": ""}))
        self.assertTrue(PD.form_problems({**self.FORM, "upload_body": "not json"}))
        PD.definition({**self.FORM, "upload_body": "not json"})     # still comes to something to show

    def test_headers_every_request_sends(self):
        from seriesmith import providerdraft as PD
        d = PD.definition({**self.FORM, "headers": "X-Version: 2024-11-06\n\nnot one\nX-Other: a:b"})
        self.assertEqual(d["headers"], {"X-Version": "2024-11-06", "X-Other": "a:b"})
        self.assertEqual(PR.problems(d), [])
        self.assertNotIn("headers", PD.definition(self.FORM))


class AVoiceOnAProvider(ScratchSettings):
    """A character's speaker on ElevenLabs, from its free list to a sample through the queue."""

    def setUp(self):
        super().setUp()
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        d = json.loads(json.dumps(PR.definitions()["elevenlabs"]))
        d.update(id="local_eleven", base_url=self.fake.url, untested=False)
        self.d = d
        from seriesmith import api as A
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        self.ok(A.put_provider_key(self.ctx, {"id": "local_eleven", "key": KEY}))
        self.fake.routes[("GET", "/v2/voices")] = lambda c: {
            "voices": [{"voice_id": "v1", "name": "George", "preview_url": "https://cdn.example/g.mp3",
                        "category": "premade", "labels": {"accent": "british"}, "description": "warm"},
                       {"voice_id": "v2", "name": "Sarah"}] if "next_page_token" not in c["path"] else [{"voice_id": "v3", "name": "Third"}],
            "has_more": "next_page_token" not in c["path"], "next_page_token": None if "next_page_token" in c["path"] else "p2"}
        self.fake.routes[("GET", "/v1/voices")] = {"voices": [{"voice_id": "b1", "name": "Roger", "preview_url": "https://cdn.example/r.mp3",
                                                               "labels": {"accent": "american"}}]}
        self.fake.routes[("GET", "/v1/shared-voices")] = lambda c: {
            "voices": [{"voice_id": "s1", "name": "Mark", "gender": "male", "accent": "american", "preview_url": ""}],
            "has_more": "page=" not in c["path"], "last_sort_id": "x"}

    def speak(self, voice="v1", name="George"):
        from seriesmith import api as A
        return self.ok(A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": "ada", "service": "local_eleven", "id": voice, "name": name}))

    def add_model(self):
        from seriesmith import api as A
        got = AS.propose("elevenlabs", "eleven_v4", "")
        spec = json.loads(json.dumps(got["proposal"]))
        spec["api"]["service"] = "local_eleven"
        spec.update(id="eleven_v4_local", draft=False)
        return self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": spec, "scope": "show"}))["id"]

    def test_its_list_is_free_and_read_in_one_shape(self):
        from seriesmith import api as A
        got = self.ok(A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "yours"}))
        self.assertEqual(got["voices"][0], {"id": "v1", "name": "George", "preview": "https://cdn.example/g.mp3", "about": "warm",
                                            "category": "premade", "labels": {"accent": "british"}})
        self.assertEqual(got["voices"][1]["preview"], "")
        self.assertEqual(got["next"], "p2")
        self.assertEqual(self.fake.calls[0]["headers"]["xi-api-key"], KEY)
        more = self.ok(A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "yours", "after": "p2", "search": "a b"}))
        self.assertEqual([v["id"] for v in more["voices"]], ["v3"])
        self.assertIn("search=a%20b", self.fake.calls[-1]["path"])
        self.assertEqual(more["next"], "")
        self.assertTrue(all(c["method"] == "GET" for c in self.fake.calls))

    def test_its_list_needs_the_key_and_says_what_went_wrong(self):
        from seriesmith import api as A
        self.ok(A.put_provider_key(self.ctx, {"id": "local_eleven", "key": None}))
        self.assertEqual(A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "library"})[0], 400)
        self.ok(A.put_provider_key(self.ctx, {"id": "local_eleven", "key": KEY}))
        self.fake.routes[("GET", "/v2/voices")] = (401, {"detail": {"message": "bad " + KEY}}, {})
        code, data = A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "yours"})
        self.assertEqual(code, 502)
        self.assertNotIn(KEY, data["error"])
        self.assertEqual(A.get_provider_voices(self.ctx, {"service": "nobody"})[0], 404)

    def test_its_own_voices_play_with_no_key_and_none_is_sent(self):
        from seriesmith import api as A
        self.ok(A.put_provider_key(self.ctx, {"id": "local_eleven", "key": None}))
        got = self.ok(A.get_provider_voices(self.ctx, {"service": "local_eleven", "search": "ignored", "after": "2"}))
        self.assertEqual([v["name"] for v in got["voices"]], ["Roger"])
        self.assertEqual(got["voices"][0]["labels"], {"accent": "american"})
        self.assertEqual(self.fake.calls[-1]["path"], "/v1/voices")
        self.assertNotIn("xi-api-key", self.fake.calls[-1]["headers"])

    def test_the_library_with_a_key_pages_and_searches(self):
        from seriesmith import api as A
        got = self.ok(A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "library", "search": "old"}))
        self.assertEqual(got["voices"][0]["labels"], {"gender": "male", "accent": "american"})
        self.assertEqual(got["next"], "1")
        self.assertIn("search=old", self.fake.calls[-1]["path"])
        self.assertEqual(self.fake.calls[-1]["headers"]["xi-api-key"], KEY)
        more = self.ok(A.get_provider_voices(self.ctx, {"service": "local_eleven", "list": "library", "after": "1"}))
        self.assertIn("page=1", self.fake.calls[-1]["path"])
        self.assertEqual(more["next"], "")

    def test_a_listing_says_it_has_voices(self):
        rows = {r["id"]: r for r in PR.listing(S.Settings(), {})}
        self.assertEqual([x["id"] for x in rows["elevenlabs"]["voices"]["lists"]], ["own", "library", "yours"])
        self.assertTrue(rows["elevenlabs"]["voices"]["lists"][0]["free"])
        self.assertFalse(rows["elevenlabs"]["voices"]["lists"][1]["free"])
        self.assertTrue(rows["elevenlabs"]["key_url"])
        self.assertIsNone(rows["atlas"]["voices"])
        self.assertEqual({m["kind"] for m in rows["elevenlabs"]["catalog"]}, {"audio"})

    def test_the_speaker_is_on_the_subject_in_the_series_config(self):
        from seriesmith import api as A
        from seriesmith import refs as R
        self.assertTrue(self.speak()["changed"])
        self.assertFalse(self.speak()["changed"])
        s = R.load_series(self.ep)
        ref = R.find_ref(s, "voice:ada")
        self.assertEqual(ref.entry["voices"], {"local_eleven": {"id": "v1", "name": "George"}})
        self.ok(A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": "ada", "service": "local_eleven", "id": "v1",
                                                     "name": "George", "preview": "https://cdn.example/g.mp3"}))
        self.assertEqual(R.find_ref(R.load_series(self.ep), "voice:ada").entry["voices"]["local_eleven"]["preview"], "https://cdn.example/g.mp3")
        self.ok(A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": "ada", "service": "local_eleven", "id": None}))
        self.assertNotIn("voices", R.find_ref(R.load_series(self.ep), "voice:ada").entry)
        self.assertEqual(A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": "nobody", "service": "x", "id": "v"})[0], 400)

    def test_no_speaker_no_call(self):
        from seriesmith import api as A
        tid = self.add_model()
        got = self.ok(A.post_refs_generate(self.ctx, {"ep": self.ep, "ref": "voice:ada", "target": tid, "backend": "api:local_eleven"}))
        self.assertEqual(got["queued"], [])
        self.assertIn("no voice on ElevenLabs", got["errors"][0]["error"])
        self.assertEqual([c for c in self.fake.calls if c["method"] == "POST"], [])

    def test_the_prompt_panel_shows_the_words_and_the_call(self):
        tid = self.add_model()
        view = PV.preview(self.ep, tid, ref="voice:ada")
        self.assertTrue(view["ok"], view.get("why"))
        self.assertEqual(view["kind"], "audio")
        self.assertEqual(view["model"], "eleven_v4")
        self.assertEqual(view["arguments"]["text"], view["prompt"])
        self.assertNotIn("says:", view["prompt"])
        self.assertIsNone(view["speaker"])
        self.assertIn("VOICE_ID", view["calls"][0]["url"])
        self.speak()
        view = PV.preview(self.ep, tid, ref="voice:ada")
        self.assertEqual(view["speaker"]["name"], "George")
        self.assertIn("/v1/text-to-speech/v1", view["calls"][0]["url"])
        self.assertEqual([c for c in self.fake.calls if c["method"] == "POST"], [])

    def test_its_listing_names_the_provider_and_its_voices(self):
        t = TG.load_target(self.add_model(), "audio", root=self.ep)
        row = next(x for x in TG.list_targets("audio", root=self.ep) if x.id == t.id).describe()
        self.assertEqual(row["service"], "local_eleven")
        self.assertEqual(row["service_label"], "ElevenLabs")
        self.assertTrue(row["service_voices"])

    def test_a_hosted_model_needs_nothing_of_comfyui(self):
        from seriesmith import edit as E
        t = TG.load_target(self.add_model(), "audio", root=self.ep)
        self.assertEqual(E.readiness([t], None)[t.id]["status"], "ready")
        local = TG.load_target("ltx2_voice", "audio")
        self.assertEqual(E.readiness([local], None)[local.id]["status"], "unknown")

    def test_a_sample_is_the_words_alone_in_the_speakers_voice(self):
        from seriesmith import api as A
        from seriesmith import refs as R
        self.fake.routes[("POST", "/v1/text-to-speech/v1")] = (200, b"not really an mp3", {"Content-Type": "audio/mpeg"})
        tid = self.add_model()
        self.speak()
        got = self.ok(A.post_refs_generate(self.ctx, {"ep": self.ep, "ref": "voice:ada", "target": tid, "backend": "api:local_eleven"}))
        self.assertEqual(got["errors"], [])
        self.settle()
        call = next(c for c in self.fake.calls if c["method"] == "POST")
        body = json.loads(call["body"])
        self.assertEqual(body["model_id"], "eleven_v4")
        self.assertEqual(set(body), {"model_id", "text", "seed"})
        self.assertTrue(body["text"])
        for said in ("speaking", "says:", "Voice:", "microphone"):
            self.assertNotIn(said, body["text"])
        self.assertEqual(call["headers"]["xi-api-key"], KEY)
        # and it landed as one of the voice's takes, to play and pick
        made = os.listdir(R.takes_dir(R.find_ref(R.load_series(self.ep), "voice:ada")))
        self.assertTrue(any(n.endswith((".mp3", ".wav")) for n in made), made)


def fake_speech(seconds=1.0):
    """A real little sound, as a provider's bytes: what ffmpeg must be able to read."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x10\x00" * int(44100 * seconds))
    return buf.getvalue()


def timed_answer(text, seconds=1.0):
    """ElevenLabs' with-timestamps: the sound as base64, a time for each character."""
    import base64
    n = max(len(text), 1)
    return {"audio_base64": base64.b64encode(fake_speech(seconds)).decode("ascii"),
            "alignment": {"characters": list(text),
                          "character_start_times_seconds": [round(i * seconds / n, 3) for i in range(len(text))],
                          "character_end_times_seconds": [round((i + 1) * seconds / n, 3) for i in range(len(text))]}}


class Lines(ScratchSettings):
    """An episode's lines: what they'd cost first, a take each, then a recording align can read."""

    def setUp(self):
        super().setUp()
        from seriesmith import api as A
        from seriesmith import lines as LN
        self.A, self.LN = A, LN
        self.fake = Fake()
        self.addCleanup(self.fake.close)
        d = json.loads(json.dumps(PR.definitions()["elevenlabs"]))
        d.update(id="local_eleven", base_url=self.fake.url, untested=False)
        self.ok(A.put_provider(self.ctx, {"definition": d}))
        self.ok(A.put_provider_key(self.ctx, {"id": "local_eleven", "key": KEY}))
        spec = json.loads(json.dumps(AS.propose("elevenlabs", "eleven_v4", "")["proposal"]))
        spec["api"]["service"] = "local_eleven"
        spec.update(id="eleven_v4_local", draft=False)
        self.tid = self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": spec, "scope": "show"}))["id"]
        self.t = TG.load_target(self.tid, "audio", root=self.ep)
        self.fake.routes[("POST", "/v1/text-to-speech/v1/with-timestamps")] = lambda c: timed_answer(json.loads(c["body"])["text"])
        self.fake.routes[("POST", "/v1/text-to-speech/v2/with-timestamps")] = lambda c: timed_answer(json.loads(c["body"])["text"])

    def plan(self):
        return self.ok(self.A.get_lines(self.ctx, {"ep": self.ep, "target": self.tid}))

    def people(self):
        return sorted({r["who"] for r in self.plan()["lines"]})

    def speak_all(self):
        for i, who in enumerate(self.people()):
            base = (json.load(open(self.series_path(), encoding="utf-8"))["subjects"][who]).get("of") or who
            self.A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": base, "service": "local_eleven",
                                                      "id": "v1" if i % 2 == 0 else "v2", "name": f"Voice {i}"})

    def series_path(self):
        from seriesmith.core import paths as P
        return P.episode_files(self.ep)[0]

    def generate(self, **more):
        plan = self.plan()
        return self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "confirm_chars": plan["to_make"]["chars"], "backend": "api:local_eleven", **more})

    def posts(self):
        return [c for c in self.fake.calls if c["method"] == "POST"]

    def test_an_unknown_voice_model_says_so(self):
        got = self.ok(self.A.get_lines(self.ctx, {"ep": self.ep, "target": "nobody"}))
        self.assertFalse(got["available"])
        self.assertIn("no voice model", got["why"])
        self.assertTrue(got["lines"])                    # the lines are still there to bring a file for

    def test_a_local_model_needs_no_speaker_and_says_nothing_is_paid(self):
        got = self.ok(self.A.get_lines(self.ctx, {"ep": self.ep, "target": "ltx2_voice"}))
        self.assertTrue(got["available"])
        self.assertFalse(got["paid"])
        self.assertEqual(got["no_speaker"], [])
        self.assertEqual(got["characters"][0]["to_make"]["lines"], got["characters"][0]["lines"])
        hosted = self.plan()
        self.assertTrue(hosted["paid"])

    def test_one_characters_lines_alone(self):
        self.speak_all()
        mine = self.mine("ada")
        chars = sum(r["chars"] for r in mine)
        got = self.ok(self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "who": "ada", "confirm_chars": chars, "backend": "api:local_eleven"}))
        self.assertEqual(sorted(q["line"] for q in got["queued"]), sorted(r["id"] for r in mine))
        self.settle()
        plan = self.plan()
        char = next(c for c in plan["characters"] if c["who"] == "ada")
        self.assertEqual(char["to_make"], {"lines": 0, "chars": 0})
        self.assertGreater(plan["to_make"]["lines"], 0)   # the others are still to make

    def test_one_characters_lines_on_a_local_model_continue_one_voice(self):
        from seriesmith import refs as R
        self.ctx.model_choices = None
        mine = self.mine("bo")
        s = R.load_series(self.ep)
        ref = R.find_ref(s, "voice:bo")
        had_takes = R.list_takes(ref, None)
        with open(ref.file, "wb") as fh:                  # the fixture's sample, as a real sound
            fh.write(fake_speech(4.0))
        had_config = open(self.series_path(), encoding="utf-8").read()
        chars = sum(r["chars"] for r in mine)
        got = self.ok(self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": "ltx2_voice", "who": "bo", "confirm_chars": chars}))
        self.assertEqual(got["errors"], [])
        self.settle()
        plan = self.ok(self.A.get_lines(self.ctx, {"ep": self.ep, "target": "ltx2_voice"}))
        rows = self.mine("bo", plan)
        failed = [t.get("error") for r in rows for t in r["takes"] if t["status"] == "failed"]
        self.assertEqual(failed, [])
        self.assertEqual({r["status"] for r in rows}, {"ok"})
        for r in rows:
            self.assertEqual(r["takes"][0]["voice"], "model:ltx2_voice")
        self.assertEqual(self.posts(), [])                # nothing went to a provider
        # the character's ref and the series config are left as they were
        self.assertEqual(len(R.list_takes(R.find_ref(R.load_series(self.ep), "voice:bo"), None)), len(had_takes))
        self.assertEqual(open(self.series_path(), encoding="utf-8").read(), had_config)

    def test_a_later_line_continues_the_first_when_there_is_no_sample(self):
        self.ctx.model_choices = None
        t = TG.load_target("ltx2_voice", "audio", root=self.ep)
        mine = self.mine("rex") or self.mine("bo")
        first, second = mine[0], (mine[1] if len(mine) > 1 else mine[0])
        self.assertEqual(self.LN.held_voice(self.ep, first["who"], first["id"]), "")
        n = self.LN.reserve(self.ep, {**first, "speaker": {"id": "model:ltx2_voice"}}, t)
        path = os.path.join(self.LN.folder(self.ep), "first.wav")
        with open(path, "wb") as fh:
            fh.write(fake_speech(1.0))
        record = self.LN.load(self.ep)
        record["lines"][first["id"]]["takes"][0].update(status="ok", file=os.path.relpath(path, self.ep))
        record["lines"][first["id"]]["picked"] = n
        self.LN.save(self.ep, record)
        if second is not first:
            self.assertEqual(os.path.normpath(self.LN.held_voice(self.ep, second["who"], second["id"])), os.path.normpath(path))
        self.assertEqual(self.LN.held_voice(self.ep, first["who"], first["id"]), "")

    def mine(self, who, plan=None):
        """A character's lines, its variants' with them: one character keeps one voice and one file."""
        with open(self.series_path(), encoding="utf-8") as fh:
            book = json.load(fh)["subjects"]
        return [r for r in (plan or self.plan())["lines"] if (book[r["who"]].get("of") or r["who"]) == who]

    def character_file(self, who, skip=(), extra=0.8):
        """A file of one character's lines in script order, with its words beside it, as Whisper would
        leave them: {path, rows}. A second of sound a line, and `extra` of quiet between."""
        import wave
        rows = self.mine(who)
        words, t, pcm = [], 0.2, bytearray(b"\0\0" * int(44100 * 0.2))
        for r in rows:
            if r["id"] in skip:
                continue
            said = r["text"].split()
            for i, w in enumerate(said):
                words.append({"word": w, "start": round(t + i / len(said), 3), "end": round(t + (i + 1) / len(said), 3)})
            pcm.extend(b"\x10\x00" * 44100)
            pcm.extend(b"\0\0" * int(44100 * extra))
            t += 1 + extra
        path = os.path.join(self.tmp, f"{who}_all.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(bytes(pcm))
        with open(path + ".words.json", "w", encoding="utf-8") as fh:
            json.dump(words, fh)
        return path, rows

    def bring(self, who, path):
        got = self.ok(self.A.post_lines_character(self.ctx, {"ep": self.ep, "who": who, "source_path": path}))
        self.settle()
        return got

    def test_a_characters_file_is_cut_into_a_take_per_line(self):
        import wave
        who = "ada"
        path, rows = self.character_file(who)
        self.bring(who, path)
        plan = self.plan()
        mine = self.mine(who, plan)
        self.assertEqual({r["status"] for r in mine}, {"ok"})
        self.assertEqual(self.posts(), [])                # nothing was paid for
        char = next(c for c in plan["characters"] if c["who"] == who)
        self.assertEqual((char["source"]["status"], char["source"]["cut"], char["source"]["unheard"]), ("ok", len(rows), []))
        for r in mine:
            take = next(t for t in r["takes"] if t["take"] == r["picked"])
            self.assertEqual(take["source"], "file")
            self.assertEqual(" ".join(w["word"] for w in take["words"]), r["text"])
            with wave.open(os.path.join(self.ep, take["file"]), "rb") as w:
                seconds = w.getnframes() / w.getframerate()
            self.assertAlmostEqual(seconds, 1.0 + 2 * self.LN.CUT_AIR, delta=0.05)
            self.assertLessEqual(take["words"][0]["start"], self.LN.CUT_AIR + 0.01)
        # the others still want making, and only theirs count
        others = [r for r in plan["lines"] if r not in mine]
        self.assertEqual(plan["to_make"]["chars"], sum(r["chars"] for r in others))
        self.assertNotIn(char["name"], plan["no_speaker"])

    def test_a_line_not_in_the_file_is_said_and_gets_no_take(self):
        who = "ada"
        rows = self.mine(who)
        missing = rows[-1]["id"]
        path, _ = self.character_file(who, skip=(missing,))
        self.bring(who, path)
        plan = self.plan()
        char = next(c for c in plan["characters"] if c["who"] == who)
        self.assertEqual(char["source"]["unheard"], [missing])
        self.assertIn("couldn't hear", " ".join(char["source"]["notes"]))
        row = next(r for r in plan["lines"] if r["id"] == missing)
        self.assertEqual(row["status"], "missing")

    def test_every_characters_file_lays_and_aligns_with_no_whisper_or_key(self):
        import subprocess
        from test_render import ENV
        with open(self.series_path(), encoding="utf-8") as fh:
            book = json.load(fh)["subjects"]
        for who in sorted({book[w].get("of") or w for w in self.people()}):
            path, _ = self.character_file(who)
            self.bring(who, path)
        self.assertTrue(self.plan()["can_lay"])
        got = self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        self.assertTrue(got["timed"])
        ran = subprocess.run([sys.executable, "-m", "seriesmith.align", self.ep, "--dry-run"], capture_output=True, text=True, env=ENV)
        self.assertEqual(ran.returncode, 0, ran.stderr[-600:] + ran.stdout[-600:])
        self.assertEqual(self.posts(), [])

    def test_a_file_for_someone_with_no_lines_is_refused(self):
        path = os.path.join(self.tmp, "x.wav")
        with open(path, "wb") as fh:
            fh.write(fake_speech(0.1))
        self.assertEqual(self.A.post_lines_character(self.ctx, {"ep": self.ep, "who": "nobody", "source_path": path})[0], 400)

    def test_a_redo_on_a_cut_line_is_still_one_line(self):
        self.speak_all()
        who = "ada"
        path, _ = self.character_file(who)
        self.bring(who, path)
        row = self.mine(who)[0]
        self.ok(self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "lines": [row["id"]], "confirm_chars": row["chars"], "backend": "api:local_eleven"}))
        self.settle()
        again = next(r for r in self.plan()["lines"] if r["id"] == row["id"])
        self.assertEqual(len(again["takes"]), 2)
        self.assertEqual(len(self.posts()), 1)

    def test_the_plan_counts_what_it_would_cost_and_sends_nothing(self):
        plan = self.plan()
        self.assertTrue(plan["available"])
        self.assertGreater(plan["to_make"]["lines"], 0)
        self.assertEqual(plan["to_make"]["chars"], sum(len(r["text"]) for r in plan["lines"]))
        self.assertEqual(sum(c["chars"] for c in plan["characters"]), plan["to_make"]["chars"])
        self.assertFalse(plan["can_lay"])
        self.assertEqual(self.fake.calls, [])

    def test_refused_until_every_speaker_is_picked_and_nothing_is_sent(self):
        code, data = self.generate()
        self.assertEqual(code, 400)
        self.assertIn("pick a speaker", data["error"])
        self.assertEqual(self.posts(), [])

    def test_refused_when_the_total_is_not_what_was_shown(self):
        self.speak_all()
        plan = self.plan()
        code, data = self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "confirm_chars": plan["to_make"]["chars"] + 1, "backend": "api:local_eleven"})
        self.assertEqual(code, 409)
        self.assertEqual(self.posts(), [])

    def make_them(self):
        self.speak_all()
        got = self.ok(self.generate())
        self.assertEqual(got["errors"], [])
        self.settle()
        return got

    def test_each_line_is_a_call_with_the_words_alone(self):
        got = self.make_them()
        plan = self.plan()
        self.assertEqual(len(self.posts()), len(plan["lines"]))
        self.assertEqual(len(got["queued"]), len(plan["lines"]))
        sent = sorted(json.loads(c["body"])["text"] for c in self.posts())
        self.assertEqual(sent, sorted(r["text"] for r in plan["lines"]))
        for c in self.posts():
            self.assertEqual(set(json.loads(c["body"])), {"model_id", "text", "seed"})
            self.assertEqual(c["headers"]["xi-api-key"], KEY)
        self.assertEqual({r["status"] for r in plan["lines"]}, {"ok"})
        self.assertEqual(plan["to_make"], {"lines": 0, "chars": 0})
        self.assertTrue(plan["can_lay"])

    def test_they_lay_into_a_recording_with_its_timings_in_script_order(self):
        import wave
        self.make_them()
        rows = self.plan()["lines"]
        got = self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        self.assertTrue(got["timed"])
        self.assertEqual(got["lines"], len(rows))
        path = os.path.join(self.ep, got["path"])
        with wave.open(path, "rb") as w:
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), got["seconds"], places=1)
        with open(path + ".words.json", encoding="utf-8") as fh:
            words = json.load(fh)
        self.assertEqual([w["word"] for w in words], " ".join(r["text"] for r in rows).split())
        starts = [w["start"] for w in words]
        self.assertEqual(starts, sorted(starts))
        self.assertGreaterEqual(starts[0], self.LN.ENDS)
        # attached, and align needs no Whisper: the timings are newer than the recording
        with open(self.series_path(), encoding="utf-8") as fh:
            audio = json.load(fh)["audio"]
        self.assertEqual(audio["mode"], "source_track")
        self.assertEqual(audio["track"], got["path"])
        from seriesmith import edit as E
        self.assertTrue(E.has_words(path))

    def test_a_silent_shot_keeps_its_pause_after_align_takes_its_dur(self):
        self.make_them()
        shots = self.LN.script_shots(self.ep)
        silent = [s for s in shots if not s["lines"]]
        self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        kept = self.LN.load(self.ep)["pauses"]
        self.assertEqual(set(kept), {s["id"] for s in silent})
        for s in silent:
            self.assertEqual(kept[s["id"]], float(s["dur"] or self.LN.SILENT_DEFAULT))

    def test_align_reads_the_recording_with_no_whisper_and_every_word_matches(self):
        import subprocess
        from test_render import ENV
        self.make_them()
        rows = self.plan()["lines"]
        self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        out = os.path.join(self.tmp, "align.json")

        def align(*more):
            got = subprocess.run([sys.executable, "-m", "seriesmith.align", self.ep, "--json", out, *more],
                                 capture_output=True, text=True, env=ENV)
            self.assertEqual(got.returncode, 0, got.stderr[-800:] + got.stdout[-800:])
            with open(out, encoding="utf-8") as fh:
                return json.load(fh)

        dry = align("--dry-run")
        self.assertEqual(dry["words"], sum(len(r["text"].split()) for r in rows))
        self.assertEqual([n for n in dry["notes"] if "couldn't hear" in n or "matched" in n], [])
        real = align()
        self.assertTrue(real["ok"])
        from seriesmith import build as BLD  # noqa: F401
        from seriesmith.core import paths as P
        with open(P.episode_files(self.ep)[1], encoding="utf-8") as fh:
            script = fh.read()
        self.assertIn("audio: ", script)
        # laid again after align took the silent shots' `dur:`: their pauses are still there
        again = self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        self.assertTrue(again["timed"])
        again2 = align("--dry-run")
        self.assertEqual(again2["duration"], real["duration"])

    def staleness_after_a_redo(self):
        """Every shot's take as a real render would record it, a line redone longer, the recording laid
        and aligned again: {shot: why it's stale}, and the redone shot."""
        import subprocess
        from seriesmith import jobs as J
        from test_render import ENV
        self.make_them()
        self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))

        def align_and_build():
            got = subprocess.run([sys.executable, "-m", "seriesmith.align", self.ep], capture_output=True, text=True, env=ENV)
            self.assertEqual(got.returncode, 0, got.stderr[-600:] + got.stdout[-600:])
            built = subprocess.run([sys.executable, "-m", "seriesmith", "build", self.ep], capture_output=True, text=True, env=ENV)
            self.assertEqual(built.returncode, 0, built.stderr[-600:] + built.stdout[-600:])
            return J.load_shotlist(self.ep, "final")

        def sidecar(doc, shot):
            refs = [dict(r, sha1=T.file_sha1(os.path.join(self.ep, r["path"])) if r["path"] else None)
                    for r in J.ref_slots(doc, shot)]
            return {"target": doc.get("target"), "shot_hash": J.story_hash(shot), "refs": refs,
                    "preset_hash": J.preset_hash(doc, shot), **J.laid_fields(self.ep, shot)}
        from seriesmith import takes as T
        doc = align_and_build()
        made = {s["id"]: sidecar(doc, s) for s in doc["shots"]}
        rows = self.plan()["lines"]
        row = rows[len(rows) // 2]
        speaker = row["speaker"]["id"]
        self.fake.routes[("POST", f"/v1/text-to-speech/{speaker}/with-timestamps")] = lambda c: timed_answer(json.loads(c["body"])["text"], 3.0)
        self.ok(self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "lines": [row["id"]], "confirm_chars": row["chars"], "backend": "api:local_eleven"}))
        self.settle()
        self.ok(self.A.post_lines_pick(self.ctx, {"ep": self.ep, "line": row["id"], "take": 2}))
        self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        doc = align_and_build()
        return {s["id"]: J.stale_reasons(self.ep, doc, s, made[s["id"]]) for s in doc["shots"] if s["id"] in made}, row["shot"], [s["id"] for s in doc["shots"]]

    def test_a_redone_line_makes_only_its_own_shot_stale(self):
        stale, redone, order = self.staleness_after_a_redo()
        self.assertTrue(stale[redone], redone)
        self.assertEqual({k: v for k, v in stale.items() if v and k != redone}, {})

    def test_a_recording_replaced_by_hand_still_says_so(self):
        from seriesmith import jobs as J
        from seriesmith import takes as T
        self.make_them()
        self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        path = os.path.join(self.ep, self.LN.DIR, self.LN.RECORDING)
        shot = {"id": "sh020", "audio_in": 1.0, "audio_out": 2.0}
        doc = {"defaults": {}}
        side = {"refs": [{"kind": "audio", "path": os.path.relpath(path, self.ep), "sha1": "other"}]}
        # no lines remembered: a take from before lines, or an actor's recording
        self.assertIn("ref", J.stale_reasons(self.ep, doc, shot, side))
        # remembered, but this shot's lines were laid differently since
        side.update(lines_sound="different", place_free_hash=J.place_free_hash(shot))
        self.assertIn("ref", J.stale_reasons(self.ep, doc, shot, side))
        self.assertTrue(T.file_sha1(path))

    def test_a_line_with_no_timings_is_placed_where_it_was_laid_with_no_whisper(self):
        import wave
        self.make_them()
        record = self.LN.load(self.ep)
        rows = self.plan()["lines"]
        last = rows[-1]["id"]
        take = next(t for t in record["lines"][last]["takes"] if t["take"] == record["lines"][last]["picked"])
        del take["words"]                                # as a local model's take has none
        self.LN.save(self.ep, record)
        got = self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))
        self.assertEqual(got["guessed"], 1)
        path = os.path.join(self.ep, got["path"])
        with open(path + ".words.json", encoding="utf-8") as fh:
            words = json.load(fh)
        said = rows[-1]["text"].split()
        tail = words[-len(said):]
        self.assertEqual([w["word"] for w in tail], said)
        with wave.open(path, "rb") as w:
            seconds = w.getnframes() / w.getframerate()
        # the take is a second of sound, right at the end of the recording before its silence
        self.assertAlmostEqual(tail[-1]["end"] - tail[0]["start"], 1.0, delta=0.05)
        self.assertLess(tail[-1]["end"], seconds)
        from seriesmith import edit as E
        self.assertTrue(E.has_words(path))

    def test_laying_makes_it_what_the_cut_plays_and_exports(self):
        from unittest import mock
        from seriesmith import edit as E
        self.make_them()
        self.assertEqual(self.ok(self.A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))["cut_audio"], "clips")
        self.assertEqual(self.ok(self.A.post_lines_lay(self.ctx, {"ep": self.ep}))["cut_audio"], "recording")
        self.assertEqual(self.ok(self.A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))["cut_audio"], "recording")

        def asked():
            with mock.patch.object(E, "run_tool", return_value=(1, "", "stopped here")) as run:
                E.assemble_episode(self.ep, "proxy", True)
            return run.call_args[0][1]
        self.assertIn("recording", asked())
        self.ok(self.A.post_cut_audio(self.ctx, {"ep": self.ep, "audio": "clips"}))
        self.assertEqual(self.ok(self.A.get_episode(self.ctx, {"ep": self.ep, "pass": "proxy"}))["cut_audio"], "clips")
        self.assertNotIn("recording", asked())
        self.assertEqual(self.A.post_cut_audio(self.ctx, {"ep": self.ep, "audio": "x"})[0], 400)

    def test_laying_refuses_while_a_line_has_no_take(self):
        code, data = self.A.post_lines_lay(self.ctx, {"ep": self.ep})
        self.assertEqual(code, 400)
        self.assertIn("no take yet", data["error"])

    def test_a_line_redone_alone_and_a_take_picked(self):
        self.make_them()
        first = self.plan()["lines"][0]
        before = len(self.posts())
        got = self.ok(self.A.post_lines_generate(self.ctx, {"ep": self.ep, "target": self.tid, "lines": [first["id"]], "confirm_chars": first["chars"], "backend": "api:local_eleven"}))
        self.assertEqual(got["queued"][0]["take"], 2)
        self.settle()
        self.assertEqual(len(self.posts()), before + 1)
        row = self.plan()["lines"][0]
        self.assertEqual(row["picked"], 1)                   # kept: you choose after hearing it
        self.ok(self.A.post_lines_pick(self.ctx, {"ep": self.ep, "line": row["id"], "take": 2}))
        self.assertEqual(self.plan()["lines"][0]["picked"], 2)
        self.assertEqual(self.A.post_lines_pick(self.ctx, {"ep": self.ep, "line": row["id"], "take": 9})[0], 400)

    def test_a_changed_speaker_needs_its_line_again(self):
        self.make_them()
        row = self.plan()["lines"][0]
        base = (json.load(open(self.series_path(), encoding="utf-8"))["subjects"][row["who"]]).get("of") or row["who"]
        self.ok(self.A.put_refs_provider_voice(self.ctx, {"ep": self.ep, "subject": base, "service": "local_eleven", "id": "other"}))
        plan = self.plan()
        self.assertIn("changed", {r["status"] for r in plan["lines"] if r["who"] == row["who"]})
        self.assertGreater(plan["to_make"]["chars"], 0)

    def test_a_failure_is_said_on_its_line_and_the_rest_are_kept(self):
        self.speak_all()
        self.fake.routes[("POST", "/v1/text-to-speech/v1/with-timestamps")] = (402, {"detail": {"code": "insufficient_credits", "message": "no credits"}}, {})
        self.ok(self.generate())
        self.settle()
        plan = self.plan()
        failed = [t for r in plan["lines"] for t in r["takes"] if t["status"] == "failed"]
        self.assertTrue(failed)
        self.assertIn("no credits", failed[0]["error"])
        self.assertNotIn(KEY, json.dumps(plan))
        self.assertFalse(plan["can_lay"])

    def test_words_from_character_timings(self):
        got = self.LN.words_from({"characters": list("Hi, you."), "character_start_times_seconds": [0, .1, .2, .3, .4, .5, .6, .7],
                                  "character_end_times_seconds": [.1, .2, .3, .4, .5, .6, .7, .8]})
        self.assertEqual(got, [{"word": "Hi,", "start": 0.0, "end": 0.3}, {"word": "you.", "start": 0.4, "end": 0.8}])
        self.assertIsNone(self.LN.words_from(None))
        self.assertIsNone(self.LN.words_from({"characters": ["a"], "character_start_times_seconds": [], "character_end_times_seconds": []}))

    def test_the_timed_way_shows_in_the_panel(self):
        from seriesmith.backends.http import planned_calls
        d = PR.definitions()["local_eleven"]
        calls = planned_calls(d, "eleven_v4", {"text": "a", ROUTING: {"values": {"voice": "v1", "use": "timed"}}})
        self.assertTrue(calls[0]["url"].endswith("/v1/text-to-speech/v1/with-timestamps"))
        plain = planned_calls(d, "eleven_v4", {"text": "a", ROUTING: {"values": {"voice": "v1"}}})
        self.assertTrue(plain[0]["url"].endswith("/v1/text-to-speech/v1"))


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
        # as Atlas really answered, 2026-11-04 (its docs say a top-level `url`)
        f.routes[("POST", "/api/v1/model/uploadMedia")] = {
            "code": 200, "message": "success",
            "data": {"type": "image", "download_url": "https://files.example/pic.png", "filename": "pic.png", "size": 12}}
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
