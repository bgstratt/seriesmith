"""
seriesmith mcp (seriesmith/mcp.py): the protocol on stdio (initialize, tools,
resources, notifications, errors), each tool landing on a route the server
really has with the body it was given, the HTTP errors and an unreachable
server said to the model, pictures as images, and --read-only. A stdlib HTTP
server stands in for seriesmith serve.
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import api as A  # noqa: E402
from seriesmith import mcp as M  # noqa: E402
from seriesmith.server import queue_views as QV  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfake"


class Recorder(M.Client):
    """Answers every call with something of the right shape, recording it."""

    def __init__(self, cut=None):
        super().__init__("http://127.0.0.1:0")
        self.calls = []
        self.cut = cut if cut is not None else {"proxy": [{"shot": "sh010"}], "final": []}

    def call(self, method, path, query=None, body=None, raw=False):
        self.calls.append((method, path, query, body))
        if raw:
            return PNG, "image/png"
        return {"/seriesmith/config": {"roots": ["C:/Shows"]},
                "/seriesmith/jobs": {"jobs": [], "paid": {"count": 0}},
                "/seriesmith/file": self.cut,
                "/seriesmith/episode": {"episode": "ep01", "shots": [
                    {"shot": "sh010"}, {"shot": "sh020"}, {"shot": "sh900", "orphan": True}]},
                "/seriesmith/targets": {"targets": [], "default": {}},
                "/seriesmith/issues/export": {"format": "md", "text": "# issues"},
                }.get(path, {"ok": True})


ARGS = {"ep": "C:/Shows/s/ep01", "file": "script", "text": "x", "series": "{}",
        "shot": "sh010", "path": "refs/a.png", "base_hash": "h", "parent": "C:/Shows",
        "name": "ep01", "scripts": [{"name": "ep01.md", "text": "x"}], "ref": "subject:a",
        "take": 1, "source_path": "C:/a.png", "id": "j1", "action": "queue", "keep": True,
        "fields": {"note": "x"}, "items": "all", "hashes": {}, "what": "all", "from_shot": "sh020"}


def rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method,
                          "params": params or {}})


class ToolsTest(unittest.TestCase):
    def test_every_tool_is_a_route_the_server_has(self):
        have = {(m, p) for m, p, _f, _t in A.ROUTES} | set(QV.PATHS)
        for tool in M.TOOLS:
            c = Recorder()
            res = M.Server(c).call_tool(tool.name, dict(ARGS))
            self.assertFalse(res["isError"], (tool.name, res))
            self.assertTrue(c.calls, tool.name)
            for method, path, _q, _b in c.calls:
                self.assertIn((method, path), have, tool.name)

    def test_arguments_become_the_body_and_none_is_left_out(self):
        c = Recorder()
        M.Server(c).call_tool("check_pair", {"series": "{}", "script": "= ep01"})
        self.assertEqual(c.calls[-1][:2], ("POST", "/seriesmith/check"))
        self.assertEqual(c.calls[-1][3], {"series": "{}", "script": "= ep01", "parent": None})
        M.Server(c).call_tool("save_source", {k: ARGS[k] for k in ("ep", "file", "text",
                                                                   "base_hash")})
        self.assertTrue(c.calls[-1][3]["rebuild"])
        M.Server(c).call_tool("episode_status", {"ep": ARGS["ep"], "pass": "final"})
        self.assertEqual(c.calls[-1][2], {"ep": ARGS["ep"], "pass": "final"})

    def test_edit_cut_changes_only_what_it_names(self):
        cut = {"proxy": [{"shot": "sh010", "take": 2, "trim_in": 4, "note": "keep"},
                         {"shot": "sh020", "locked": True, "audio": {"source": "none"}},
                         {"shot": "sh030"}], "final": []}
        c = Recorder(cut)
        res = M.Server(c).call_tool("edit_cut", {
            "ep": "e", "changes": [{"shot": "sh020", "trim_out": 6}, {"shot": "sh030",
                                                                     "out": True}],
            "order": ["sh030", "sh010", "sh020"]})
        self.assertFalse(res["isError"], res)
        self.assertEqual(c.calls[0][:3], ("GET", "/seriesmith/file", {"ep": "e",
                                                                    "path": "cut.json"}))
        self.assertEqual(c.calls[-1][:2], ("PUT", "/seriesmith/cut"))
        self.assertEqual(c.calls[-1][3], {"ep": "e", "pass": "proxy", "entries": [
            {"shot": "sh030", "out": True},
            {"shot": "sh010", "take": 2, "trim_in": 4, "note": "keep"},
            {"shot": "sh020", "locked": True, "audio": {"source": "none"}, "trim_out": 6}]})
        self.assertEqual(cut["proxy"][1], {"shot": "sh020", "locked": True,
                                           "audio": {"source": "none"}})   # not changed in place

    def test_edit_cut_refuses_what_would_lose_shots(self):
        s = M.Server(Recorder({"proxy": [{"shot": "sh010"}, {"shot": "sh020"}]}))
        for args, said in (({"order": ["sh020"]}, "missing sh010"),
                           ({"order": ["sh010", "sh020", "sh099"]}, "not in it sh099"),
                           ({"changes": [{"shot": "sh099"}]}, "isn't in the proxy cut"),
                           ({"changes": [{"shot": "sh010", "trim": 3}]}, "has no trim")):
            res = s.call_tool("edit_cut", dict(args, ep="e"))
            self.assertTrue(res["isError"], args)
            self.assertIn(said, res["content"][0]["text"])

    def test_edit_cut_with_no_cut_yet_starts_from_the_script(self):
        c = Recorder({"proxy": [], "final": []})
        M.Server(c).call_tool("edit_cut", {"ep": "e", "changes": [{"shot": "sh020",
                                                                   "flag": True}]})
        self.assertEqual(c.calls[-1][3]["entries"], [{"shot": "sh010"},
                                                     {"shot": "sh020", "flag": True}])

    def test_master_plan_writes_nothing(self):
        c = Recorder()
        M.Server(c, read_only=True).call_tool("master_plan", {"ep": "e"})
        self.assertEqual(c.calls[-1][3], {"ep": "e", "conform": None, "post": None,
                                          "action": "plan"})

    def test_upscale_passes_every_field_through(self):
        c = Recorder()
        M.Server(c).call_tool("upscale", {"ep": "e", "then_method": "seedvr2", "detail": 1})
        self.assertEqual(c.calls[-1][3], {"ep": "e", "then_method": "seedvr2", "detail": 1})

    def test_a_missing_argument_is_the_models_error(self):
        res = M.Server(Recorder()).call_tool("render", {})
        self.assertTrue(res["isError"])
        self.assertIn("ep", res["content"][0]["text"])

    def test_read_only_leaves_out_writes_and_queues(self):
        names = {t["name"] for t in rpc(M.Server(Recorder(), read_only=True),
                                        "tools/list")["result"]["tools"]}
        self.assertIn("check_pair", names)
        self.assertIn("view_picture", names)
        for gone in ("save_source", "new_episode", "render", "generate_missing_refs",
                     "cancel_job", "edit_cut", "set_override", "promote", "upscale", "post",
                     "master", "delete_upscale"):
            self.assertNotIn(gone, names)
        every = {t.name for t in M.TOOLS}
        self.assertTrue(all(t.writes for t in M.TOOLS if t.queues))
        self.assertEqual(len(every), len(M.TOOLS))

    def test_queueing_tools_say_so(self):
        for t in M.TOOLS:
            if t.queues:
                self.assertIn("QUEUES", t.description, t.name)

    def test_episode_status_is_trimmed(self):
        res = M.episode_brief({"episode": "ep01", "pass": "proxy", "shots": [{
            "shot": "sh010", "seconds": 4.0, "prompt_hash": "x", "cut": {"take": 2,
                                                                      "usable": True,
                                                                      "trim_in": 0},
            "takes": [{"take": 2, "status": "ok", "seed": "1", "thumb": "r/t.jpg",
                       "strip": None, "comfy_prompt_id": "p"}]}]})
        shot = res["shots"][0]
        self.assertEqual(shot["cut"], {"take": 2, "usable": True})
        self.assertEqual(shot["takes"], [{"take": 2, "status": "ok", "thumb": "r/t.jpg"}])
        self.assertNotIn("prompt_hash", shot)

    def test_jobs_of_one_episode(self):
        jobs = {"jobs": [{"id": "a", "status": "running", "info": {"ep": "C:/S/ep01"}, "log": []},
                         {"id": "b", "status": "queued", "info": {"ep": "C:/S/ep02"}},
                         {"id": "c", "status": "failed", "info": {"ep": "C:/S/ep01"},
                          "error": "boom"}]}
        got = M.jobs_brief(jobs, "C:/S/ep01")
        self.assertEqual([j["id"] for j in got["running_or_queued"]], ["a"])
        self.assertEqual(got["finished_recently"][0]["error"], "boom")
        self.assertNotIn("log", got["running_or_queued"][0])

    def test_waiting_on_ref_jobs_settles_the_refs(self):
        class Done(Recorder):
            def call(self, method, path, query=None, body=None, raw=False):
                if path == "/seriesmith/jobs":
                    self.calls.append((method, path, query, body))
                    return {"jobs": [{"id": "r", "kind": "ref", "status": "succeeded",
                                      "info": {"ep": "C:/S/ep01"}},
                                     {"id": "v", "kind": "render", "status": "succeeded",
                                      "info": {"ep": "C:/S/ep02"}}]}
                return super().call(method, path, query, body, raw)
        c = Done()
        M.Server(c).call_tool("wait_for_jobs", {})
        self.assertEqual([q for m, p, q, b in c.calls if p == "/seriesmith/refs"],
                         [{"ep": "C:/S/ep01", "fresh": "1"}])
        M.Server(c).call_tool("list_refs", {"ep": "C:/S/ep02"})
        self.assertEqual(c.calls[-1][2], {"ep": "C:/S/ep02", "fresh": "1"})

    def test_a_picture_is_an_image(self):
        res = M.Server(Recorder()).call_tool("view_picture", {"ep": "e", "path": "a.png"})
        self.assertEqual(res["content"][0]["type"], "image")
        self.assertEqual(res["content"][0]["mimeType"], "image/png")


class ProtocolTest(unittest.TestCase):
    def test_initialize(self):
        s = M.Server(Recorder())
        r = rpc(s, "initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        self.assertEqual(r["serverInfo"]["name"], "seriesmith")
        self.assertIn("tools", r["capabilities"])
        self.assertIn("check_pair", r["instructions"])
        r = rpc(s, "initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(r["protocolVersion"], M.PROTOCOL_VERSIONS[0])

    def test_notifications_get_no_answer_and_unknowns_an_error(self):
        s = M.Server(Recorder())
        self.assertIsNone(s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(rpc(s, "nope")["error"]["code"], -32601)
        self.assertEqual(rpc(s, "tools/call", {"name": "nope"})["error"]["code"], -32602)
        self.assertEqual(rpc(s, "ping")["result"], {})

    def test_the_script_format_is_a_resource(self):
        s = M.Server(Recorder())
        listed = rpc(s, "resources/list")["result"]["resources"]
        self.assertEqual([r["uri"] for r in listed], [M.FORMAT_URI])
        text = rpc(s, "resources/read", {"uri": M.FORMAT_URI})["result"]["contents"][0]["text"]
        self.assertIn("series.json", text)
        self.assertEqual(rpc(s, "resources/read", {"uri": "x://y"})["error"]["code"], -32002)

    def test_stdio_one_message_per_line(self):
        inp = io.BytesIO(b"\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {}}).encode(),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode(),
            b"not json",
            json.dumps([{"jsonrpc": "2.0", "id": 2, "method": "ping"},
                        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}]).encode(),
            "{\"jsonrpc\": \"2.0\", \"id\": 4, \"method\": \"tools/call\", \"params\": "
            "{\"name\": \"check_pair\", \"arguments\": {\"series\": \"é\"}}}".encode(),
        ]) + b"\n")
        out = io.BytesIO()
        M.serve(M.Server(Recorder()), inp, out)
        lines = [json.loads(x) for x in out.getvalue().decode("utf-8").splitlines()]
        self.assertEqual([x["id"] if isinstance(x, dict) else [y["id"] for y in x]
                          for x in lines], [1, None, [2, 3], 4])
        self.assertEqual(lines[1]["error"]["code"], -32700)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def answer(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/seriesmith/thumb"):
            return self.answer(200, PNG, "image/png")
        if self.path.startswith("/seriesmith/source"):
            return self.answer(404, b'{"error": "no episode folder at C:/x"}')
        if self.path.startswith("/seriesmith/jobs"):
            return self.answer(404, b"404: Not Found", "text/plain")
        self.answer(500, b"<html>broken</html>", "text/html")

    def do_PUT(self):
        self.answer(409, b'{"error": "changed on disk", "hash": "abc", "text": "long"}')

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.answer(200, json.dumps({"got": json.loads(body), "path": self.path}).encode())


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.server = M.Server(M.Client(f"http://127.0.0.1:{cls.httpd.server_port}"))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def text(self, res):
        return res["content"][0]["text"]

    def test_a_post_goes_through(self):
        res = self.server.call_tool("check_pair", {"series": "{\"a\": \"é\"}"})
        self.assertFalse(res["isError"])
        self.assertEqual(json.loads(self.text(res)),
                         {"got": {"series": "{\"a\": \"é\"}"}, "path": "/seriesmith/check"})

    def test_errors_are_said_to_the_model(self):
        res = self.server.call_tool("read_source", {"ep": "C:/x", "file": "script"})
        self.assertTrue(res["isError"])
        self.assertEqual(self.text(res), "HTTP 404: no episode folder at C:/x")
        res = self.server.call_tool("save_source", {"ep": "e", "file": "script", "text": "t",
                                                    "base_hash": "old"})
        self.assertEqual(self.text(res), 'HTTP 409: changed on disk {"hash": "abc"}')
        res = self.server.call_tool("list_refs", {"ep": "e"})
        self.assertIn("HTTP 500", self.text(res))
        res = self.server.call_tool("list_jobs", {})          # a route an older server lacks
        self.assertIn("Restart it", self.text(res))

    def test_a_picture(self):
        res = self.server.call_tool("view_picture", {"ep": "e", "path": "a.png"})
        self.assertEqual(res["content"][0]["mimeType"], "image/png")

    def test_nothing_answering(self):
        res = M.Server(M.Client("http://127.0.0.1:0")).call_tool("list_episodes", {})
        self.assertTrue(res["isError"])
        self.assertIn("seriesmith serve", self.text(res))


class LiveTest(unittest.TestCase):
    """The tools against seriesmith serve's own app on the kitchen_sink
    episode: what the routes accept from them, end to end (no ComfyUI, so
    nothing renders; dry runs and plans only)."""

    def setUp(self):
        try:
            from aiohttp.test_utils import TestServer  # noqa: F401
        except ImportError as exc:                       # pragma: no cover
            self.skipTest(f"the server needs aiohttp: {exc}")
        import shutil
        import tempfile
        from test_render import FIXTURE, build_episode
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ks01")
        os.makedirs(self.ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ks01.md"))
        build_episode(self.ep)
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(self._tmp.name, "user", "settings.json")
        self.addCleanup(os.environ.pop, "SERIESMITH_SETTINGS", None)

    def run_tools(self, body):
        import asyncio
        from aiohttp.test_utils import TestServer
        from seriesmith.server import standalone
        from seriesmith.settings import Settings

        async def go():
            app = standalone.make_app([self.shows], Settings(comfyui_url="http://127.0.0.1:0"))
            async with TestServer(app) as srv:
                server = M.Server(M.Client(f"http://127.0.0.1:{srv.port}"))

                def tool(tool_name, **args):
                    res = server.call_tool(tool_name, args)
                    text = res["content"][0].get("text", "")
                    try:
                        data = json.loads(text)
                    except ValueError:
                        data = text
                    return res["isError"], data
                # the tools block on urllib: off the loop the server answers on
                return await asyncio.to_thread(body, tool)
        return asyncio.run(go())

    def test_end_to_end(self):
        ep = self.ep

        def body(tool):
            err, got = tool("list_episodes")
            self.assertFalse(err, got)
            self.assertEqual([e["name"] for e in got["episodes"]], ["ks01"])
            err, script = tool("read_source", ep=ep, file="script")
            err, series = tool("read_source", ep=ep, file="series")
            err, pair = tool("check_pair", series=series["text"], script=script["text"])
            self.assertTrue(pair["ok"], pair)
            self.assertEqual(pair["shots"][0]["id"], "sh010")
            err, chk = tool("check_source", ep=ep, file="script", text=script["text"])
            self.assertEqual(chk["shots"], pair["shots"])

            # a new episode from the same pair, then built
            err, made = tool("new_episode", parent=self.shows, name="ks02",
                             series=series["text"], script=script["text"])
            self.assertFalse(err, made)
            self.assertTrue(made["check"]["ok"])
            err, built = tool("build", ep=made["ep"])
            self.assertTrue(built["ok"], built)

            # the cut: a trim and a reorder, the rest kept
            err, st = tool("episode_status", ep=ep)
            shots = [s["shot"] for s in st["shots"]]
            err, cut = tool("edit_cut", ep=ep, changes=[{"shot": shots[0], "trim_in": 3,
                                                         "note": "tighter"}],
                            order=shots[1:2] + shots[:1] + shots[2:])
            self.assertFalse(err, cut)
            err, again = tool("edit_cut", ep=ep, changes=[{"shot": shots[1], "flag": True}])
            entries = again["cut"]["proxy"]
            self.assertEqual([e["shot"] for e in entries][:2], [shots[1], shots[0]])
            self.assertEqual(entries[1], {"shot": shots[0], "trim_in": 3, "note": "tighter"})
            self.assertTrue(entries[0]["flag"])
            err, _ = tool("reset_cut", ep=ep, what="trims")
            self.assertFalse(err)

            # an override, seen by get_shot, then cleared
            err, ov = tool("set_override", ep=ep, shot=shots[0], fields={"note": "calmer"})
            self.assertFalse(err, ov)
            err, plan = tool("promote_plan", ep=ep)
            self.assertFalse(err, plan)
            err, _ = tool("clear_override", ep=ep, shot=shots[0])
            self.assertFalse(err)

            # plans and dry runs: nothing queued
            err, refs = tool("generate_missing_refs", ep=ep, dry_run=True)
            self.assertFalse(err, refs)
            self.assertTrue(all(q["take"] is None for q in refs["queued"]))
            err, plan = tool("master_plan", ep=ep)
            self.assertTrue(err or "plan" in plan, plan)   # 409 without a recipe is fine
            for name in ("list_targets", "list_jobs", "upscale_options", "post_options"):
                err, got = tool(name)
                self.assertFalse(err, (name, got))
            err, got = tool("list_refs", ep=ep)
            self.assertFalse(err, got)
            err, got = tool("get_issues", ep=ep)
            self.assertFalse(err, got)
        self.run_tools(body)


if __name__ == "__main__":
    unittest.main()
