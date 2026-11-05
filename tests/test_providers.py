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
        d = PD.definition({**self.FORM, "upload_headers": "h", "upload_type_field": "kind"})
        ask, put = d["files"]["steps"]
        self.assertEqual(ask["json"], {"kind": "$mime"})
        self.assertEqual(ask["take"]["put_headers"], "h")
        self.assertEqual(put["headers"], "$put_headers")

    def test_it_says_what_is_missing(self):
        from seriesmith import providerdraft as PD
        self.assertEqual(PD.form_problems(self.FORM), [])
        self.assertTrue(PD.form_problems({**self.FORM, "upload_put": ""}))


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
