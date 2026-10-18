"""
The local backend straight to ComfyUI (seriesmith/backends/native.py), against
a stand-in ComfyUI of a few routes: uploads, queueing, status and outputs as
comfy-api-proxy would report them, a node it hasn't spliced out; and the
models a series naming none renders on (targets.machine_default, found
installed: edit.detect_defaults), stamped into a new series.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import backends as B  # noqa: E402
from seriesmith import edit as E  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import settings as S  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends.native import ComfyUIBackend  # noqa: E402


class FakeComfyUI:
    """Just enough of ComfyUI's API: /system_stats, /upload/image, /prompt,
    /queue, /history/<id>, /view and /object_info/<class>."""

    def __init__(self):
        self.uploads: dict[str, bytes] = {}       # "subfolder/name" -> bytes
        self.prompts: dict[str, dict] = {}        # prompt id -> graph
        self.history: dict[str, dict] = {}        # prompt id -> its history entry
        self.files: dict[tuple, bytes] = {}       # (subfolder, filename) -> bytes
        self.nodes = {"SaveImage", "LoadImage", "UNETLoader", "KSampler"}
        self.finish = None                        # graph -> history entry (None: stays queued)
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                from urllib.parse import parse_qs, urlparse
                u = urlparse(self.path)
                if u.path == "/system_stats":
                    return self._send(200, {"system": {}})
                if u.path == "/queue":
                    pending = [[0, pid] for pid in fake.prompts if pid not in fake.history]
                    return self._send(200, {"queue_running": [], "queue_pending": pending})
                m = re.match(r"^/history/(.+)$", u.path)
                if m:
                    pid = m.group(1)
                    return self._send(200, {pid: fake.history[pid]} if pid in fake.history else {})
                m = re.match(r"^/object_info/(.+)$", u.path)
                if m:
                    c = m.group(1)
                    return self._send(200, {c: {"input": {}}} if c in fake.nodes else {})
                if u.path == "/view":
                    q = {k: v[0] for k, v in parse_qs(u.query).items()}
                    key = (q.get("subfolder", ""), q["filename"])
                    if key in fake.files:
                        return self._send(200, fake.files[key], "application/octet-stream")
                    return self._send(404, {"error": "no such file"})
                self._send(404, {})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                if self.path == "/upload/image":
                    sub = re.search(rb'name="subfolder"\r\n\r\n(.*?)\r\n', body).group(1).decode()
                    m = re.search(rb'filename="([^"]+)"\r\nContent-Type: [^\r]+\r\n\r\n(.*)\r\n--',
                                  body, re.S)
                    fake.uploads[f"{sub}/{m.group(1).decode()}"] = m.group(2)
                    return self._send(200, {"name": m.group(1).decode(), "subfolder": sub,
                                            "type": "input"})
                if self.path == "/prompt":
                    got = json.loads(body)
                    g = got["prompt"]
                    bad = {nid: {"class_type": v["class_type"],
                                 "errors": [{"message": "Node not found", "details": v["class_type"]}]}
                           for nid, v in g.items() if v["class_type"] not in fake.nodes}
                    if bad:
                        return self._send(400, {"error": {"message": "Prompt outputs failed validation"},
                                                "node_errors": bad})
                    pid = f"p{len(fake.prompts) + 1}"
                    fake.prompts[pid] = g
                    if fake.finish:
                        fake.history[pid] = fake.finish(g)
                    return self._send(200, {"prompt_id": pid, "number": 1, "node_errors": {}})
                self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def temp_file(test, data=b"\x89PNG picture", suffix=".png") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    test.addCleanup(os.remove, path)
    return path


def ok_entry(outputs: dict) -> dict:
    return {"status": {"status_str": "success", "completed": True, "messages": []},
            "outputs": outputs}


class NativeBackendTest(unittest.TestCase):
    def setUp(self):
        self.comfy = FakeComfyUI()
        self.addCleanup(self.comfy.close)
        self.backend = ComfyUIBackend("local", self.comfy.url)

    def test_it_answers_and_says_when_it_doesnt(self):
        self.assertIsNone(self.backend.ping())
        self.assertIn("doesn't answer", ComfyUIBackend("local", "http://127.0.0.1:9").ping())

    def test_a_file_goes_up_once_by_its_content_and_the_graph_names_it(self):
        pic = temp_file(self)
        self.comfy.finish = lambda g: ok_entry({})
        graph = {"1": {"class_type": "LoadImage", "inputs": {"image": B.File(pic)}},
                 "2": {"class_type": "LoadImage", "inputs": {"image": B.File(pic)}}}
        run = self.backend.submit(graph)
        self.assertEqual(len(self.comfy.uploads), 1)
        (name, data), = self.comfy.uploads.items()
        self.assertTrue(name.startswith("seriesmith/") and name.endswith(".png"), name)
        self.assertEqual(data, b"\x89PNG picture")
        sent = self.comfy.prompts[run.id]
        self.assertEqual(sent["1"]["inputs"]["image"], name)
        self.assertEqual(sent["2"]["inputs"]["image"], name)
        # the caller's graph is left as it was
        self.assertIsInstance(graph["1"]["inputs"]["image"], B.File)

    def test_a_run_ends_and_its_outputs_come_back_typed(self):
        c = self.comfy
        c.files[("seriesmith/run1", "sh010_t01.mp4")] = b"video bytes"
        c.files[("seriesmith/run1", "sh010_t01.record.json")] = b'{"status": "ok"}'
        c.files[("seriesmith/run1", "sh010_t01.latent.safetensors")] = b"latent"
        item = lambda n: {"filename": n, "subfolder": "seriesmith/run1", "type": "output"}  # noqa: E731
        c.finish = lambda g: ok_entry({"9": {
            "gifs": [dict(item("sh010_t01.mp4"), format="video/h264-mp4")],
            "files": [item("sh010_t01.record.json")],
            "latents": [item("sh010_t01.latent.safetensors")],
            "text": ["not a file"]}})
        run = self.backend.submit({"1": {"class_type": "KSampler", "inputs": {}}})
        seen = []
        self.assertEqual(run.watch(on_status=seen.append), "succeeded")
        self.assertEqual(seen[-1], "succeeded")
        outs = {o.name: o for o in run.outputs()}
        self.assertEqual({n: (o.node, o.type) for n, o in outs.items()},
                         {"sh010_t01.mp4": ("9", "video"),
                          "sh010_t01.record.json": ("9", "file"),
                          "sh010_t01.latent.safetensors": ("9", "latent")})
        with tempfile.TemporaryDirectory() as d:
            p = outs["sh010_t01.mp4"].save(os.path.join(d, "sub", "take.mp4"))
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(), b"video bytes")

    def test_a_failed_run_says_which_node_and_why(self):
        self.comfy.finish = lambda g: {"status": {"status_str": "error", "messages": [
            ["execution_start", {}],
            ["execution_error", {"node_id": "4", "node_type": "KSampler",
                                 "exception_message": "CUDA out of memory"}]]}, "outputs": {}}
        run = self.backend.submit({"4": {"class_type": "KSampler", "inputs": {}}})
        self.assertEqual(run.refresh(), "failed")
        self.assertEqual(run.error, "KSampler (node 4): CUDA out of memory")
        self.assertEqual(run.outputs(), [])

    def test_an_interrupted_run_is_canceled(self):
        self.comfy.finish = lambda g: {"status": {"status_str": "error", "messages": [
            ["execution_interrupted", {}]]}, "outputs": {}}
        run = self.backend.submit({"4": {"class_type": "KSampler", "inputs": {}}})
        self.assertEqual(run.refresh(), "canceled")

    def test_a_queued_run_then_one_comfyui_forgot(self):
        run = self.backend.submit({"4": {"class_type": "KSampler", "inputs": {}}})
        self.assertEqual(run.refresh(), "queued")
        # after a restart: picked up by its id, which ComfyUI no longer knows
        gone = self.backend.attach("p999")
        self.assertEqual(gone.refresh(), "expired")
        self.assertIn("no longer knows", gone.error)

    def test_a_graph_comfyui_refuses_is_a_backend_error_naming_the_node(self):
        with self.assertRaises(B.BackendError) as cm:
            self.backend.submit({"7": {"class_type": "NoSuchNode", "inputs": {}}})
        self.assertIn("NoSuchNode (node 7)", str(cm.exception))

    def test_a_node_it_can_do_without_is_spliced_out_where_it_isnt_installed(self):
        self.comfy.finish = lambda g: ok_entry({})
        graph = {"3": {"class_type": "UNETLoader", "inputs": {}},
                 "4": {"class_type": "H3SLAAttention", "inputs": {"model": ["3", 0],
                                                                  "sparsity_ratio": 0.85}},
                 "5": {"class_type": "KSampler", "inputs": {"model": ["4", 0]}}}
        run = self.backend.submit(graph)
        sent = self.comfy.prompts[run.id]
        self.assertNotIn("4", sent)
        self.assertEqual(sent["5"]["inputs"]["model"], ["3", 0])
        self.assertEqual(len(run.notes), 1)
        self.assertIn("H3SLAAttention", run.notes[0])
        # installed: kept as it is
        self.comfy.nodes.add("H3SLAAttention")
        self.backend._has.clear()
        run = self.backend.submit(graph)
        self.assertEqual(self.comfy.prompts[run.id]["5"]["inputs"]["model"], ["4", 0])
        self.assertEqual(run.notes, [])


class BypassTest(unittest.TestCase):
    def test_the_h3_targets_can_do_without_sparse_attention(self):
        self.assertEqual(TG.bypassable().get("H3SLAAttention"), "model")
        t = TG.load_target("minimax_h3_ref2va", "video")
        self.assertEqual(E.target_nodes(t)["H3SLAAttention"]["tier"], "optional")

    def test_every_consumer_reads_the_passed_through_input(self):
        g = {"1": {"class_type": "A", "inputs": {}},
             "2": {"class_type": "Skip", "inputs": {"model": ["1", 0]}},
             "3": {"class_type": "B", "inputs": {"m": ["2", 0], "n": ["2", 0]}},
             "4": {"class_type": "Skip", "inputs": {"other": 1}}}
        self.assertEqual(J.bypass_nodes(g, {"Skip": "model"}), ["Skip"])
        self.assertEqual(g["3"]["inputs"], {"m": ["1", 0], "n": ["1", 0]})
        self.assertNotIn("2", g)
        self.assertIn("4", g)                 # nothing to pass through: left alone


class LocalBackendSettingsTest(unittest.TestCase):
    def test_local_renders_go_straight_to_comfyui_unless_through_the_proxy(self):
        from seriesmith.backends.comfy import ComfyBackend
        s = S.load_settings(os.path.join(HERE, "none.json"), env={})
        self.assertEqual(s.local_via, "comfyui")
        local = B.available(s)["local"]
        self.assertIsInstance(local, ComfyUIBackend)
        self.assertEqual((local.kind, local.base_url), ("local", "http://127.0.0.1:8188"))
        # inside ComfyUI: that ComfyUI, on whatever port it runs
        s.host_url = "http://127.0.0.1:8000"
        self.assertEqual(B.available(s)["local"].base_url, "http://127.0.0.1:8000")
        s.local_via = "proxy"
        local = B.available(s)["local"]
        self.assertIsInstance(local, ComfyBackend)
        self.assertEqual(local.base_url, "http://127.0.0.1:8189")

    def test_the_new_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            S.save_settings({"local_via": "proxy", "default_targets": {"video": "ltx2"},
                             "detected_targets": {"video": "ltx2", "image": "z_image_turbo"}}, path)
            s = S.load_settings(path, env={})
            self.assertEqual((s.local_via, s.default_targets, s.detected_targets),
                             ("proxy", {"video": "ltx2"},
                              {"video": "ltx2", "image": "z_image_turbo"}))
            self.assertEqual(S.load_settings(path, env={"SERIESMITH_LOCAL_VIA": "comfyui"}).local_via,
                             "comfyui")
            S.save_settings({"local_via": None, "default_targets": {"video": None}}, path)
            s = S.load_settings(path, env={})
            self.assertEqual((s.local_via, s.default_targets), ("comfyui", {}))
            for bad in ({"local_via": "carrier pigeon"}, {"default_targets": {"audio": "x"}},
                        {"detected_targets": ["ltx2"]}):
                with self.assertRaises(ValueError):
                    S.save_settings(bad, path)


class MachineDefaultTest(unittest.TestCase):
    def use_settings(self, data: dict) -> None:
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.environ["SERIESMITH_SETTINGS"] = path      # conftest puts it back
        TG.forget_targets()

    def test_the_built_in_models_without_settings(self):
        self.assertEqual((TG.machine_default("video"), TG.machine_default("image")),
                         ("minimax_h3_ref2va", "krea2"))

    def test_found_installed_then_the_users_choice(self):
        self.use_settings({"detected_targets": {"video": "ltx2", "image": "z_image_turbo"}})
        self.assertEqual(TG.machine_default("video"), "ltx2")
        self.assertEqual(TG.video_target({"series": {}}).id, "ltx2")
        self.assertEqual(TG.image_target({}).id, "z_image_turbo")
        # a series that names one keeps it
        self.assertEqual(TG.video_target({"series": {"target": "minimax_h3_ref2va"}}).id,
                         "minimax_h3_ref2va")
        self.use_settings({"detected_targets": {"video": "ltx2"},
                           "default_targets": {"video": "minimax_h3_fl2va"}})
        self.assertEqual(TG.machine_default("video"), "minimax_h3_fl2va")
        # one that doesn't exist (any more) is passed over
        self.use_settings({"default_targets": {"video": "gone_model"},
                           "detected_targets": {"video": "ltx2"}})
        self.assertEqual(TG.machine_default("video"), "ltx2")

    def test_a_new_series_names_this_machines_models(self):
        from seriesmith import source as SRC
        raw = {"series": {"id": "x"}}
        self.assertEqual(SRC.stamp_machine_defaults(raw), {"series": {"id": "x"}})
        self.use_settings({"detected_targets": {"video": "ltx2", "image": "z_image_turbo"}})
        raw = SRC.stamp_machine_defaults({"series": {"id": "x"}})
        self.assertEqual((raw["series"]["target"], raw["refs"]["target"]), ("ltx2", "z_image_turbo"))
        raw = SRC.stamp_machine_defaults({"series": {"id": "x", "target": "minimax_h3_ref2va"},
                                          "refs": {"target": "krea2"}})
        self.assertEqual((raw["series"]["target"], raw["refs"]["target"]),
                         ("minimax_h3_ref2va", "krea2"))


class DetectDefaultsTest(unittest.TestCase):
    def cands(self):
        return {k: TG.default_candidates(k) for k in ("video", "image")}

    def test_the_candidates_are_local_in_order(self):
        video = [t.id for t in TG.default_candidates("video")]
        self.assertEqual(video[:2], ["minimax_h3_ref2va", "ltx2"])
        self.assertTrue(all(not TG.load_target(i, "video").spec.get("router") for i in video))
        self.assertEqual(TG.default_candidates("image")[0].id, "krea2")

    def test_the_first_ready_then_the_first_degraded_then_none(self):
        ready = {"minimax_h3_ref2va": {"status": "not_ready"}, "ltx2": {"status": "ready"},
                 "krea2": {"status": "not_ready"}, "z_image_turbo": {"status": "degraded"}}
        self.assertEqual(E.detect_defaults(ready, self.cands()),
                         {"video": "ltx2", "image": "z_image_turbo"})
        ready["minimax_h3_ref2va"] = {"status": "ready"}
        self.assertEqual(E.detect_defaults(ready, self.cands())["video"], "minimax_h3_ref2va")
        self.assertEqual(E.detect_defaults({}, self.cands()), {})

    def test_readiness_finds_ltx_when_h3_isnt_installed(self):
        # a ComfyUI with every node class, and only LTX-2's files
        info = _object_info_with(TG.load_target("ltx2", "video"))
        rd = E.readiness(TG.list_targets(), info)
        self.assertNotEqual(rd["minimax_h3_ref2va"]["status"], "ready")
        found = E.detect_defaults(rd, self.cands())
        self.assertEqual(found.get("video"), "ltx2", rd["ltx2"])


def _object_info_with(target) -> dict:
    """/object_info as a ComfyUI would answer with every node class the
    targets use, and in each loader's list exactly the files `target` wants."""
    info: dict = {}
    for t in TG.list_targets():
        for c in E.target_nodes(t):
            info.setdefault(c, {"input": {"required": {}}})
        for spec in t.models.values():
            ct, fld = spec.get("class_type"), spec.get("field")
            if ct and fld:
                info.setdefault(ct, {"input": {"required": {}}})["input"]["required"].setdefault(
                    fld, [[]])
    for pass_ in target.presets:
        for param, want in TG.wanted_files(target, pass_, None).items():
            spec = target.models.get(param) or {}
            ct, fld = spec.get("class_type"), spec.get("field")
            if ct and fld and want:
                for w in (want if isinstance(want, list) else [want]):
                    name = w if isinstance(w, str) else (w or {}).get("want")
                    if name and name not in info[ct]["input"]["required"][fld][0]:
                        info[ct]["input"]["required"][fld][0].append(name)
    return info


if __name__ == "__main__":
    unittest.main()
