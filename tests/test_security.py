"""
What bounds seriesmith (SECURITY.md), one test per guard the 2026-11-14 audit added
(docs/SECURITY_AUDIT.md): what a target may have downloaded and where, a network path never
looked at, who counts as this PC, where the Comfy API key goes, a job's output names, the
addresses fetched for a provider, the title's settings in ffmpeg's filter graph, and ids
that become folder names.
"""
from __future__ import annotations

import os
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
