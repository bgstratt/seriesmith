"""
What bounds seriesmith (SECURITY.md), one test per guard the 2026-11-14 audit added
(docs/SECURITY_AUDIT.md): what a target may have downloaded and where, a network path never
looked at, who counts as this PC, where the Comfy API key goes, a job's output names, the
addresses fetched for a provider, the title's settings in ffmpeg's filter graph, and ids
that become folder names.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import backends as B  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import features as FT  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import inspector as IN  # noqa: E402
from seriesmith import installer as INS  # noqa: E402
from seriesmith import net as NET  # noqa: E402
from seriesmith import proc as PROC  # noqa: E402
from seriesmith import publish as PUB  # noqa: E402
from seriesmith import settings as S  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends.native import ComfyUIBackend  # noqa: E402
from seriesmith.core import downloads as DL  # noqa: E402
from seriesmith.core import paths as P  # noqa: E402
from seriesmith.server import guard as G  # noqa: E402

BS = chr(92)
UNC = BS * 2 + "evil.example" + BS + "share" + BS + "x.png"
HF = "https://huggingface.co/a/b/resolve/main/x.safetensors"


class DownloadsTest(unittest.TestCase):
    """A target's `downloads` and `fetches` are data from anywhere: only a model file, from
    Hugging Face or Civitai, into a models folder."""

    def test_a_model_from_the_hub_into_a_models_folder(self):
        self.assertIsNone(DL.download_problem("x.safetensors", {"folder": "vae", "url": HF}))
        self.assertIsNone(DL.download_problem("x.gguf", {"folder": "ultralytics/bbox", "url": HF}))
        self.assertIsNone(DL.download_problem("x.py", {"folder": "../custom_nodes", "url": None}))

    def test_what_isnt_downloaded(self):
        ok = {"folder": "vae", "url": HF}
        for name, rec in (
                ("__init__.py", ok), ("x.pt", ok), ("x.safetensors.py", ok), ("..", ok),
                ("x.safetensors", {**ok, "folder": "custom_nodes"}),
                ("x.safetensors", {**ok, "folder": "custom_nodes/pack"}),
                ("x.safetensors", {**ok, "folder": "../custom_nodes"}),
                ("x.safetensors", {**ok, "folder": "C:/Users/u/Startup"}),
                ("x.safetensors", {**ok, "folder": "/etc"}),
                ("x.safetensors", {**ok, "folder": BS * 2 + "host" + BS + "share"}),
                ("x.safetensors", {**ok, "folder": ""}),
                ("x.safetensors", {**ok, "url": "http://huggingface.co/a/b/x.safetensors"}),
                ("x.safetensors", {**ok, "url": "https://evil.example/x.safetensors"}),
                ("x.safetensors", {**ok, "url": "https://huggingface.co.evil.example/x.safetensors"}),
                ("x.safetensors", {**ok, "url": "https://huggingface.co@evil.example/x.safetensors"}),
                ("x.safetensors", {**ok, "url": "https://evil.example/huggingface.co/x.safetensors"}),
                ("x.safetensors", {**ok, "url": "file:///C:/x.safetensors"})):
            self.assertTrue(DL.download_problem(name, rec), (name, rec))

    def test_a_target_drops_the_url_and_folder_of_a_record_that_isnt(self):
        spec = {"id": "x", "downloads": {
            "good.safetensors": {"folder": "vae", "url": HF},
            "evil.py": {"folder": "../custom_nodes/x", "url": "https://evil.example/x.py"}}}
        t = TG.Target.__new__(TG.Target)
        t.spec = spec
        got = t.downloads
        self.assertEqual(got["good.safetensors"]["url"], HF)
        self.assertIsNone(got["evil.py"]["url"])
        self.assertEqual(got["evil.py"]["folder"], "")
        self.assertTrue(any("downloads: evil.py" in p for p in DL.spec_problems(spec)))

    def test_a_workflows_own_records_are_listed_never_downloaded(self):
        ui = {"nodes": [{"properties": {"models": [
            {"name": "__init__.py", "directory": "../custom_nodes/x", "url": "https://evil.example/x.py"},
            {"name": "m.safetensors", "directory": "vae", "url": HF}]}}]}
        got = IN.detect_downloads(ui)
        self.assertIsNone(got["__init__.py"]["url"])
        self.assertEqual(got["m.safetensors"], {"folder": "vae", "url": HF,
                                                "source": "the workflow's own properties.models"})

    def test_fetches(self):
        self.assertIsNone(DL.fetch_problem("owner/repo", {"into": "hf", "files": ["*.bin", "a/b.json"]}))
        for repo, rec in (("../x", {"into": "hf"}), ("owner/repo/more", {"into": "hf"}),
                          ("owner/repo", {"into": "custom_nodes"}),
                          ("owner/repo", {"into": "hf", "files": ["../../x"]}),
                          ("owner/repo", {"into": "hf", "files": ["C:/x"]}),
                          ("owner/repo", {"into": "vae", "dir": "../.."})):
            self.assertTrue(DL.fetch_problem(repo, rec), (repo, rec))
        self.assertFalse(DL.repo_file_ok("../x"))
        self.assertFalse(DL.repo_file_ok("/x"))
        self.assertTrue(DL.repo_file_ok("a/b.bin"))
        self.assertFalse(DL.commit_ok("../../x"))

    def test_the_installer_refuses_a_folder_that_isnt_a_models_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            cn = os.path.join(tmp, "custom_nodes")
            os.makedirs(cn)
            place = INS.Place({"custom_nodes": [cn], "vae": [os.path.join(tmp, "models", "vae")]}, cn)
            self.assertIsNone(place.models_dir("custom_nodes"))
            self.assertIsNone(place.models_dir("../custom_nodes"))
            self.assertIsNone(place.models_dir(tmp))
            self.assertTrue(place.models_dir("vae"))
            ins = INS.Installer.__new__(INS.Installer)
            for folder in ("custom_nodes", "../custom_nodes", tmp):
                with self.assertRaises(INS.InstallError):
                    ins._model(FT.Item("model", "x.py", folder=folder, url="https://evil.example/x.py"), place)
            self.assertEqual(os.listdir(cn), [])

    def test_every_shipped_target_passes(self):
        for t in TG.list_targets():
            self.assertEqual(DL.spec_problems(t.spec), [], t.id)


@unittest.skipUnless(os.name == "nt", "network paths are Windows'")
class NetworkPathTest(unittest.TestCase):
    """A path on a network share is refused by its text: looking at it would sign Windows in
    to that host."""

    def setUp(self):
        self.addCleanup(P.set_project_roots, [])
        P.set_project_roots([])

    def touched(self):
        return mock.patch.object(os.path, "realpath", side_effect=AssertionError("looked at"))

    def test_it_is_refused_without_being_looked_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            ep = os.path.join(tmp, "Show", "ep01")
            os.makedirs(ep)
            real = os.path.realpath
            seen = []

            def spy(p, *a, **kw):
                seen.append(str(p))
                return real(p, *a, **kw)
            with mock.patch.object(os.path, "realpath", spy):
                for bad in (UNC, UNC.replace(BS, "/"), BS * 2 + "?" + BS + "C:" + BS + "Windows" + BS + "win.ini"):
                    with self.assertRaises(P.OutsideShow):
                        P.show_file(ep, bad)
                    self.assertFalse(P.inside(bad, [tmp]))
            self.assertFalse([s for s in seen if s.startswith(BS * 2)], seen)

    def test_a_project_folder_on_a_share_is_the_users_own(self):
        share = BS * 2 + "nas" + BS + "projects"
        P.set_project_roots([share])
        self.assertTrue(P.is_network(share))
        with mock.patch.object(os.path, "realpath", lambda p, *a, **kw: p):
            self.assertTrue(P.inside(share + BS + "Show" + BS + "x.png", [share]))
            self.assertEqual(P.real(UNC), os.path.normcase(UNC))

    def test_an_id_is_never_a_folders_name_for_itself(self):
        self.assertEqual(P.safe_id("..", "x"), "x")
        self.assertEqual(P.safe_id(".", "x"), "x")
        self.assertEqual(P.safe_id("a.b"), "a.b")


class ThisPCTest(unittest.TestCase):
    """This PC is its address and the name it was asked by: a page re-pointed at 127.0.0.1
    (DNS rebinding) comes from this PC's address under its own name."""

    def test_who_is_this_pc(self):
        for remote, host, want in (
                ("127.0.0.1", "127.0.0.1:8190", True), ("::1", "[::1]:8190", True),
                ("127.0.0.1", "localhost:8188", True), ("127.0.0.1", "LOCALHOST", True),
                ("127.0.0.1", "evil.example:8188", False), ("127.0.0.1", "127.0.0.1.nip.io", False),
                ("127.0.0.1", "desktop.tail1234.ts.net", False), ("127.0.0.1", "", False),
                ("127.0.0.1", None, False), ("192.168.1.20", "127.0.0.1:8190", False),
                (None, "localhost", False)):
            self.assertEqual(G.from_this_pc(remote, host), want, (remote, host))

    def test_another_programs_page_on_this_pc_isnt_ours(self):
        self.assertTrue(G.refused("GET", "127.0.0.1:8190", None, "same-site", True))
        self.assertIsNone(G.refused("GET", "127.0.0.1:8190", None, "same-origin", True))
        self.assertIsNone(G.refused("GET", "127.0.0.1:8190", None, "none", True))
        self.assertIsNone(G.refused("GET", "127.0.0.1:8190", None, None, True))


class KeyTest(unittest.TestCase):
    """The Comfy API key rides in a partner node's job, so that job goes to this PC only."""

    def test_a_partner_job_isnt_sent_to_another_machine(self):
        graph = {"1": {"class_type": "X", "inputs": {}, "_meta": {"partner": True}}}
        b = ComfyUIBackend("local", "http://192.168.1.50:8188")
        b.api_key = "comfy-secret"
        sent = []
        client = mock.Mock()
        client._json.side_effect = lambda path, body: sent.append(body) or {"prompt_id": "p"}
        with mock.patch("seriesmith.backends.native._client", return_value=client), \
                mock.patch.object(ComfyUIBackend, "without_missing", return_value=[]):
            with self.assertRaises(B.BackendError) as e:
                b.submit(graph)
        self.assertIn("this machine", str(e.exception))
        self.assertEqual(sent, [])
        self.assertNotIn("comfy-secret", str(e.exception))


class OutputNameTest(unittest.TestCase):
    """Whoever ran the job names its outputs; the name is joined into a take's folder."""

    def test_a_name_is_a_file_name(self):
        for name, want in (("ep01_s1_t01.mp4", "ep01_s1_t01.mp4"),
                           ("C:" + BS + "Users" + BS + "u" + BS + "Startup" + BS + "x.bat", "x.bat"),
                           ("../../x.bat", "x.bat"), (".." + BS + "x.bat", "x.bat"),
                           (UNC, "x.png"), ("/etc/passwd", "passwd"), ("..", "output"),
                           ("", "output"), ("a.txt:stream", "a.txt_stream"), ("x.bat. ", "x.bat")):
            out = B.Output("9", name, "file", lambda path: None)
            self.assertEqual(out.name, want, name)
            self.assertEqual(os.path.dirname(os.path.join("take", out.name)), "take")


class FetchTest(unittest.TestCase):
    """An address from outside is fetched only over https from a public host."""

    def resolve(self, *ips):
        return lambda host, port, **kw: [(2, 1, 6, "", (ip, port)) for ip in ips]

    def test_which_addresses(self):
        pub = self.resolve("93.184.216.34")
        self.assertIsNone(NET.address_problem("https://docs.example.com/api", resolve=pub))
        for url in ("http://docs.example.com/api", "file:///C:/Windows/win.ini", "ftp://x/y",
                    "https://user:pw@docs.example.com/", "https://", "//x", ""):
            self.assertTrue(NET.address_problem(url, resolve=pub), url)
        for url in ("https://127.0.0.1:8188/queue", "http://localhost:8188/queue", "https://[::1]/",
                    "https://x.localhost/"):
            self.assertTrue(NET.address_problem(url, resolve=pub), url)
            self.assertIsNone(NET.address_problem(url, local=True, resolve=pub), url)
        for ip in ("10.0.0.5", "192.168.1.1", "169.254.169.254", "127.0.0.1", "::1", "fe80::1",
                   "::ffff:10.0.0.5", "100.64.0.1", "0.0.0.0"):
            self.assertTrue(NET.address_problem("https://rebound.example/", resolve=self.resolve(ip)), ip)
            # `local` lets this PC in by its own name only, never a name that resolves to it
            self.assertTrue(NET.address_problem("https://rebound.example/", local=True,
                                                resolve=self.resolve(ip)), ip)
        # one private address among several is enough
        self.assertTrue(NET.address_problem("https://x.example/", resolve=self.resolve("93.184.216.34", "10.0.0.5")))

    def test_the_opener_speaks_http_only(self):
        o = NET.opener()
        for url in ("file:///C:/Windows/win.ini", "ftp://example.com/x", "data:text/plain,hi"):
            with self.assertRaises(Exception):
                o.open(url, timeout=1)

    def test_a_redirect_is_checked_before_its_followed(self):
        h = NET._CheckedRedirects(False)
        req = mock.Mock(full_url="https://docs.example.com/")
        for to in ("file:///C:/Windows/win.ini", "http://127.0.0.1:8188/history",
                   "http://169.254.169.254/latest/meta-data/"):
            with self.assertRaises(NET.Refused):
                h.redirect_request(req, None, 302, "Found", {}, to)


class TitleTest(unittest.TestCase):
    """The title's settings are written into ffmpeg's filter graph: each is what it says."""

    def test_the_defaults_and_colours_pass(self):
        self.assertEqual(PUB.publish_config({})["subtitle"]["color"], "#F4E6D0")
        for c in ("white", "#FFB45A", "#FFB45A@0.8", "0xFFB45A", "red@0.5", "#FFB45AFF", "Gold@1"):
            self.assertEqual(PUB.publish_config({"publish": {"subtitle": {"color": c}}})["subtitle"]["color"], c)

    def test_a_filter_cant_ride_in(self):
        for key, bad in (
                ("color", "white,drawtext=textfile='C" + BS + ":/Users/u/secret.txt'"),
                ("glow", "white:textfile=x"), ("color", "white[x];movie=C" + BS + ":/a.mp4[y]"),
                ("color", ""), ("color", 5), ("glow", "#FFF@0.8:x=1"),
                ("size", "0.05:textfile=x"), ("y", "1,metadata=mode=print:file=x"),
                ("glow_size", True), ("intro_in", [0, "1)',drawtext=text='x"]), ("outro_out", [1]),
                ("font", "font.ttf:textfile=x"), ("font", "x.ttf,movie=a")):
            with self.assertRaises(PUB.PublishError, msg=(key, bad)):
                PUB.publish_config({"publish": {"subtitle": {key: bad}}})


class ProgramsTest(unittest.TestCase):
    """Every program is started in one place (seriesmith.proc): an argument list, and an
    environment without the keys."""

    def test_never_a_shell_line(self):
        for bad in ("ffmpeg -i x", b"ffmpeg"):
            with self.assertRaises(ValueError):
                PROC.run(bad)
        with self.assertRaises(ValueError):
            PROC.run([sys.executable, "-c", "pass"], shell=True)
        with self.assertRaises(ValueError):
            PROC.popen("ffmpeg -i x")

    def test_a_program_gets_no_keys(self):
        keys = {"COMFY_API_KEY": "k1", "HF_TOKEN": "k2", "HUGGING_FACE_HUB_TOKEN": "k3",
                "SERIESMITH_KEY_FAL": "k4"}
        code = "import os; print(sorted(k for k in os.environ if os.environ[k] in ('k1','k2','k3','k4','ok')))"
        with mock.patch.dict(os.environ, {**keys, "SERIESMITH_PLAIN": "ok"}):
            self.assertEqual(set(keys) & set(PROC.clean_env()), set())
            r = PROC.run([sys.executable, "-c", code], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "['SERIESMITH_PLAIN']")
            from seriesmith import edit as E          # seriesmith's own tools: the Hub's token only
            self.assertEqual(set(keys) & set(E.tool_env()), {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"})

    def test_nothing_else_starts_one(self):
        """No module of the package but proc (and the helpers, which run in another Python)
        calls subprocess to start a program; the node pack's go through _ff."""
        import re
        starts = re.compile(r"\bsubprocess\.(run|Popen|call|check_call|check_output)\(|\bos\.(system|popen|startfile)\(")
        found = []
        for top, own in (("seriesmith", ("proc.py",)), ("comfy_nodes", ("_ff.py",))):
            for d, _, names in os.walk(os.path.join(ROOT, top)):
                if os.path.basename(d) in ("helpers", "__pycache__", "static"):
                    continue
                for n in names:
                    if n.endswith(".py") and n not in own:
                        with open(os.path.join(d, n), encoding="utf-8") as fh:
                            if starts.search(fh.read()):
                                found.append(os.path.relpath(os.path.join(d, n), ROOT))
        self.assertEqual(found, [])

    def test_a_pip_line_is_text(self):
        from seriesmith import sdk as SDK
        self.assertIsInstance(SDK.command(), str)
        self.assertIsInstance(FT.pip_command(FT.Item("pip", "demucs"), None), str)
        self.assertFalse(hasattr(INS, "run"))


class ImportsTest(unittest.TestCase):
    def test_only_the_runners_import_subprocess(self):
        """seriesmith/proc.py and the node pack's _ff.py are the files that import it; the
        helpers, which run in another Python, are the exception. Everything else takes a
        pipe, a timeout or a failed exit's name from the runner."""
        rx = re.compile(r"^\s*(import subprocess|from subprocess\b)", re.M)
        found = []
        for top in ("seriesmith", "comfy_nodes"):
            for folder, _, names in os.walk(os.path.join(ROOT, top)):
                for name in names:
                    if name.endswith(".py"):
                        path = os.path.join(folder, name)
                        with open(path, encoding="utf-8") as fh:
                            if rx.search(fh.read()):
                                found.append(os.path.relpath(path, ROOT).replace(os.sep, "/"))
        allowed = {"seriesmith/proc.py", "comfy_nodes/_ff.py"}
        self.assertEqual(sorted(f for f in found if f not in allowed and "/helpers/" not in f), [])


class FfmpegInputsTest(unittest.TestCase):
    """ffmpeg and ffprobe read files on this PC that are video, sound or pictures: never an
    address, never a playlist of other files under a media file's name."""

    def test_each_input_is_held(self):
        got = FF.limited(["ffmpeg", "-y", "-i", "a.mp4", "-f", "lavfi", "-i", "anullsrc",
                          "-f", "concat", "-safe", "0", "-i", "list.txt", "-f", "mp4", "o.mp4"])
        self.assertEqual(got.count("-protocol_whitelist"), 3)
        self.assertEqual(got.count("-format_whitelist"), 1)           # the one input with no -f
        self.assertLess(got.index("-format_whitelist"), got.index("a.mp4"))
        self.assertEqual(got[-3:], ["-f", "mp4", "o.mp4"])
        self.assertEqual(FF.limited(got), got)                          # once
        probe = FF.limited([r"C:\x\ffprobe.EXE", "-v", "error", "a.mp4"])
        self.assertEqual(probe[1:3], ["-protocol_whitelist", FF.INPUT_PROTOCOLS])
        self.assertEqual(FF.limited([sys.executable, "x.py", "-i", "a"]), [sys.executable, "x.py", "-i", "a"])
        for bad in ("hls", "concat", "dash", "sdp", "rtsp", "lavfi", "applehttp", "subfile"):
            self.assertNotIn(bad, FF.INPUT_FORMATS.split(","))
        self.assertNotIn("http", FF.INPUT_PROTOCOLS)

    @unittest.skipUnless(FF.have("ffmpeg"), "needs ffmpeg")
    def test_a_list_of_files_under_a_videos_name_isnt_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            real, fake = os.path.join(tmp, "a.mp4"), os.path.join(tmp, "b.mp4")
            made = PROC.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                             "testsrc=d=0.5:s=64x64:r=8", real], capture_output=True)
            self.assertEqual(made.returncode, 0, made.stderr)
            with open(fake, "w", encoding="utf-8") as fh:
                fh.write("ffconcat version 1.0\nfile a.mp4\n")
            read = lambda p: PROC.run([*FF.tool("ffmpeg"), "-v", "error", "-i", p, "-f", "null", "-"],  # noqa: E731
                                      capture_output=True).returncode
            self.assertEqual(read(real), 0)
            self.assertNotEqual(read(fake), 0)
            # and it would have been, left to itself
            bare = subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-i", fake, "-f", "null", "-"],
                                  capture_output=True).returncode
            self.assertEqual(bare, 0)


class TrustedComfyUITest(unittest.TestCase):
    """The one ComfyUI on another machine that Settings (on the PC) trusts with the key."""

    def test_which_addresses_can_be_trusted(self):
        for ok in ("https://comfy.example.com", "http://192.168.1.50:8188", "http://10.0.0.5:8188",
                   "http://100.101.102.103:8188", "http://desktop:8188", "http://desktop.local:8188",
                   "http://desktop.tail1234.ts.net:8188"):
            self.assertIsNone(S.key_comfyui_problem(ok), ok)
        for bad in ("http://comfy.example.com:8188", "http://8.8.8.8:8188", "ftp://x", "desktop:8188", ""):
            self.assertTrue(S.key_comfyui_problem(bad), bad)

    def test_the_key_goes_only_to_the_address_named(self):
        lan = "http://192.168.1.50:8188"
        s = S.Settings(comfyui_url=lan)
        self.assertFalse(S.key_goes_to(lan, s))
        s.comfyui_key_url = lan
        self.assertTrue(S.key_goes_to(lan, s))
        self.assertTrue(S.key_goes_to(lan + "/", s))
        self.assertFalse(S.key_goes_to("http://192.168.1.51:8188", s))      # the address changed: untrusted
        self.assertTrue(S.key_goes_to("http://127.0.0.1:8188", S.Settings()))
        s.comfyui_key_url = "http://comfy.example.com:8188"                 # in the clear across the internet
        self.assertFalse(S.key_goes_to("http://comfy.example.com:8188", s))

    def test_it_is_saved_checked_and_is_the_pcs_alone(self):
        from seriesmith.server import queue_views as QV
        self.assertIn("comfyui_key_url", QV.PC_ONLY)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with self.assertRaises(ValueError):
                S.save_settings({"comfyui_key_url": "http://comfy.example.com:8188"}, path)
            S.save_settings({"comfyui_key_url": "http://192.168.1.50:8188/"}, path)
            self.assertEqual(S.load_settings(path, env={}).comfyui_key_url, "http://192.168.1.50:8188")

    def test_a_trusted_comfyui_gets_the_partner_job(self):
        graph = {"1": {"class_type": "X", "inputs": {}, "_meta": {"partner": True}}}
        b = ComfyUIBackend("local", "http://192.168.1.50:8188")
        b.api_key, b.key_ok = "comfy-secret", True
        sent = []
        client = mock.Mock()
        client._json.side_effect = lambda path, body: sent.append(body) or {"prompt_id": "p"}
        with mock.patch("seriesmith.backends.native._client", return_value=client), \
                mock.patch.object(ComfyUIBackend, "without_missing", return_value=[]):
            b.submit(graph)
        self.assertEqual(sent[0]["extra_data"], {"api_key_comfy_org": "comfy-secret"})


class DataTest(unittest.TestCase):
    """What a target.json, a provider's definition and a route's answer may name."""

    def target(self, binding):
        with tempfile.TemporaryDirectory() as tmp:
            return TG.Target(tmp, {"id": "x_model", "kind": "video", "binding": binding}).binding, tmp

    def test_a_targets_workflow_is_a_file_in_its_own_folder(self):
        b, folder = self.target({"workflow": "graph.json", "env": "SERIESMITH_X_WORKFLOW"})
        self.assertEqual((b.workflow, b.env), (os.path.join(folder, "graph.json"), "SERIESMITH_X_WORKFLOW"))
        for bad in ("../../other/graph.json", "C:/Users/u/graph.json", UNC, "sub/graph.json", ".."):
            b, _ = self.target({"workflow": bad})
            self.assertEqual(b.workflow, "", bad)
        for bad in ("COMFY_API_KEY", "HF_TOKEN", "PATH", "workflow", "SERIESMITH_KEY_FAL"):
            b, _ = self.target({"workflow": "graph.json", "env": bad})
            self.assertEqual(b.env, "", bad)

    def test_a_providers_links_open_web_pages(self):
        from seriesmith import providers as PR
        self.assertTrue(any("docs" in p for p in PR.problems({"docs": "javascript:alert(1)"})))
        self.assertTrue(any("key_url" in p for p in PR.problems({"key_url": "http://x.example/keys"})))
        self.assertTrue(any("voices.browse" in p for p in PR.problems({"voices": {"browse": "data:text/html,x"}})))
        self.assertFalse(any("docs" in p or "key_url" in p for p in
                             PR.problems({"docs": "https://x.example/docs", "key_url": "https://x.example/keys"})))

    def test_a_route_sends_only_a_file_it_checked(self):
        from seriesmith import api as A
        self.assertIsInstance(A.served("x.mp4", "video/mp4"), A.Served)
        self.assertNotIsInstance({"path": "C:/Windows/win.ini", "content_type": "text/plain"}, A.Served)
        from seriesmith.server import views as V
        self.assertEqual(V.PAGE_HEADERS["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'self'", V.PAGE_HEADERS["Content-Security-Policy"])

    def test_the_page_runs_only_its_own_scripts(self):
        import base64
        import hashlib
        from seriesmith.server import views as V
        html = '<head><script>\n  go();\n</script><script type="module" src="/assets/a.js"></script></head>'
        want = "'sha256-" + base64.b64encode(hashlib.sha256(b"\n  go();\n").digest()).decode() + "'"
        self.assertEqual(V.inline_script_hashes(html), (want,))
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "standalone.html")
            with open(page, "w", encoding="utf-8", newline="") as fh:
                fh.write(html)
            policy = V.page_policy(page, "192.168.1.20:8190")
        self.assertIn(f"script-src 'self' {want};", policy)
        self.assertIn("connect-src 'self' ws://192.168.1.20:8190 wss://192.168.1.20:8190;", policy)
        self.assertIn("default-src 'self'", policy)
        for never in ("unsafe-eval", "script-src 'self' 'unsafe-inline'", "http:", "https:", " *"):
            self.assertNotIn(never, policy)
        # a Host that isn't a name and a port names no socket
        self.assertIn("connect-src 'self';", V.page_policy(None, "x.example; script-src *"))
        # the page seriesmith ships: every inline script it has is one the policy names
        built = os.path.join(os.path.dirname(V.__file__), "static", "standalone.html")
        if os.path.isfile(built):
            with open(built, encoding="utf-8", newline="") as fh:
                for h in V.inline_script_hashes(fh.read()):
                    self.assertIn(h, V.page_policy(built, "127.0.0.1:8190"))

    def test_the_mcp_server_says_who_it_is(self):
        from seriesmith import mcp as M
        from seriesmith.server import views as V
        seen = []

        class Answer:
            headers = {}
            def read(self): return b"{}"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch("urllib.request.urlopen", lambda req, timeout=0: seen.append(req) or Answer()):
            M.Client("http://127.0.0.1:8190").call("GET", "/seriesmith/config")
        self.assertEqual(seen[0].get_header(V.CLIENT_HEADER.capitalize()), "mcp")

    def test_the_mcp_server_imports_media_from_anywhere_on_the_pc(self):
        from seriesmith import api as A
        with tempfile.TemporaryDirectory() as tmp:
            ctx = A.Context(tmp, "http://127.0.0.1:0", lambda *a: None, env={"SERIESMITH_ROOTS": ""})
            ctx.local, ctx.mcp = False, True
            pic = os.path.join(tmp, "elsewhere", "face.PNG")
            self.assertEqual(A.check_source(ctx, pic), pic)
            self.assertEqual(A.check_source(ctx, os.path.join(tmp, "edit.xml"), "path"),
                             os.path.join(tmp, "edit.xml"))
            for bad in (os.path.join(tmp, ".ssh", "id_rsa"), os.path.join(tmp, "settings.json"),
                        os.path.join(tmp, "notes.txt"), UNC):
                with self.assertRaises(A.ApiError) as e:
                    A.check_source(ctx, bad)
                self.assertEqual(e.exception.status, 403, bad)
            ctx.mcp = False                                 # a paired device: the project folders
            with self.assertRaises(A.ApiError):
                A.check_source(ctx, pic)

    def test_a_save_that_changes_nothing_of_the_pcs_is_anyones(self):
        from seriesmith.server import queue_views as QV
        s = S.Settings(comfyui_url="http://127.0.0.1:8188", deployments={"t": "https://x.run.comfy.app"},
                       paid_limit=0)
        # what the page sends when Save is pressed with nothing touched
        same = {"comfyui_url": "http://127.0.0.1:8188/", "local_url": s.local_url, "cloud_url": s.cloud_url,
                "deployments": {"t": "https://x.run.comfy.app/"}, "ffmpeg_dir": None, "comfyui_dir": None,
                "comfyui_key_url": None, "paid_limit": 0, "local_via": None, "default_targets": {"video": "x"}}
        self.assertEqual(S.changed(same, s, QV.PC_ONLY), [])
        for k, v in (("local_via", "proxy"), ("paid_limit", None), ("paid_limit", 5), ("deployments", {}),
                     ("comfyui_url", "http://10.0.0.5:8188"), ("api_key", "k"), ("hf_token", "t"),
                     ("comfyui_key_url", "http://10.0.0.5:8188"), ("provider_keys", {"fal": "k"}),
                     ("cloud_url", "")):
            want = [] if (k, v) == ("cloud_url", "") else [k]       # empty: the default it has
            self.assertEqual(S.changed({k: v}, s, QV.PC_ONLY), want, (k, v))

    def test_a_module_of_seriesmiths_is_the_only_python_started(self):
        cmd = PROC.module(None, "helpers.probe", "a=b")
        self.assertEqual(cmd[:3], [sys.executable, PROC.RUNNER, "seriesmith.helpers.probe"])
        for bad in ("", "../x", "helpers/probe.py", "os;rm", "a b"):
            with self.assertRaises(ValueError):
                PROC.module(None, bad)
        r = PROC.run(PROC.module(None, "helpers.probe", "json=json", "nope=no_such_module_here"),
                     capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"nope": null', r.stdout)

    def test_a_download_with_a_hash_is_kept_only_if_it_matches(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            cn = os.path.join(tmp, "custom_nodes")
            os.makedirs(cn)
            place = INS.Place({"vae": [os.path.join(tmp, "models", "vae")]}, cn)

            def downloader(url, dest, token, progress, cancelled):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(b"weights")
            ins = INS.Installer(lambda: place, downloader=downloader)
            good = hashlib.sha256(b"weights").hexdigest()
            dest = os.path.join(tmp, "models", "vae", "a.safetensors")
            with self.assertRaises(INS.InstallError):
                ins._model(FT.Item("model", "a.safetensors", folder="vae", url=HF, sha256="0" * 64), place)
            self.assertEqual(os.listdir(os.path.dirname(dest)), [])
            self.assertIn("checked", ins._model(FT.Item("model", "a.safetensors", folder="vae", url=HF, sha256=good), place))
            self.assertTrue(os.path.isfile(dest))


class IdsTest(unittest.TestCase):
    """An id from a request is an id before it is a folder's name."""

    def test_a_cue(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(CU.cue_dir(tmp, "c01").startswith(tmp))
            for bad in ("..", "../..", "C:" + BS + "x", UNC, "a/b", "", None):
                with self.assertRaises(FileNotFoundError):
                    CU.cue_dir(tmp, bad)

    def test_a_target_to_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = os.path.join(tmp, "other")
            os.makedirs(other)
            path = os.path.join(other, "target.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{}")
            show = os.path.join(tmp, "Show", "ep01")
            os.makedirs(show)
            for bad in (other, "../../other", "..", ""):
                self.assertFalse(IN.delete_spec(show, bad), bad)
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
