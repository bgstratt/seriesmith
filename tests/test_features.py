"""
The Features window's catalog (seriesmith/features.py) and its installer
(seriesmith/installer.py): what each feature is made of, whether it's there,
what an install asks for, and the installing itself, against a stand-in
download server, git and pip (nothing real is fetched or installed).
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import features as FT  # noqa: E402
from seriesmith import installer as INS  # noqa: E402


class FileServer:
    """Serves `files` ({path: bytes}); Range requests; a path under /gated/
    answers 401 without `Authorization: Bearer good`."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.seen: list[dict] = []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                srv.seen.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                 "range": self.headers.get("Range")})
                if self.path.startswith("/gated/") and self.headers.get("Authorization") != "Bearer good":
                    self.send_response(401)
                    self.end_headers()
                    return
                data = srv.files.get(self.path.split("?")[0])
                if data is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                rng = self.headers.get("Range")
                if rng:
                    start = int(rng.split("=")[1].rstrip("-"))
                    if start >= len(data):
                        self.send_response(416)
                        self.end_headers()
                        return
                    body = data[start:]
                    self.send_response(206)
                else:
                    body = data
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        # stand in for huggingface.co: the token goes to URLs naming it
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.cat = FT.catalog()

    def test_every_feature_has_items_and_every_file_a_recorded_download(self):
        ids = [f.id for f in self.cat]
        self.assertEqual(len(ids), len(set(ids)))
        groups = {g for g, _, _ in FT.GROUPS}
        for f in self.cat:
            with self.subTest(feature=f.id):
                self.assertIn(f.group, groups)
                self.assertTrue(f.items)
                for i in f.items:
                    if i.kind == "model":
                        self.assertTrue(i.url.startswith("https://"), i.name)
                        self.assertTrue(i.folder, i.name)
                    if i.kind == "pack":
                        self.assertTrue(i.url.startswith("https://github.com/"), i.name)
                        self.assertTrue(i.classes)

    def test_a_target_feature_is_what_its_passes_load(self):
        by = {f.id: f for f in self.cat}
        h3 = {i.name for i in by["video.h3"].items}
        self.assertIn("minimax_h3_ref2va_pruned_int8_convrot.safetensors", h3)
        self.assertIn("minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors", h3)
        # a pass's slower `base` stand-in and the optional extras are left out
        ltx = {i.name for i in by["video.ltx2"].items}
        self.assertNotIn("ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors", ltx)
        self.assertNotIn("ltx-2.5-duration-head-bf16.safetensors", ltx)

    def test_the_gated_files_say_so(self):
        by = {f.id: f for f in self.cat}
        self.assertTrue(any(i.gated for i in by["video.ltx2"].items))
        self.assertTrue(any(i.gated for i in by["pictures.flux2_klein"].items))
        self.assertFalse(any(i.gated for i in by["video.h3"].items))
        j = next(i for i in by["video.ltx2"].items if i.gated).to_json()
        self.assertTrue(j["licence"].startswith("https://huggingface.co/Lightricks/"))

    def test_a_file_installed_under_its_own_name_saved_as_ours(self):
        # the H3 latent upscaler is published under another name: saved as the one we load
        up = next(f for f in self.cat if f.id == "upscale.h3_latent")
        model = next(i for i in up.items if i.kind == "model")
        self.assertEqual(model.name, "minimax_h3_latent_upscaler_3d_fp16.safetensors")
        self.assertIn("conv_v1", model.url)


class StatusTest(unittest.TestCase):
    def feature(self):
        return FT.Feature("x", "tools", "X", "", [
            FT.Item("model", "a.safetensors", folder="loras", url="https://h/a"),
            FT.Item("pack", "SomePack", url="https://github.com/x/y", classes=("SomeNode",)),
            FT.Item("pip", "demucs", module="demucs")])

    def test_each_kind(self):
        env = FT.Env(model_exists=lambda folder, name: name == "a.safetensors",
                     node_classes={"SomeNode"}, pack_dirs=set(),
                     python_has=lambda where, m: True)
        self.assertEqual(FT.status([self.feature()], env)[0]["status"], "installed")
        env.python_has = lambda where, m: False
        self.assertEqual(FT.status([self.feature()], env)[0]["status"], "partial")

    def test_a_pack_or_package_missing_says_how_you_put_it_in(self):
        env = FT.Env(model_exists=lambda f, n: True, node_classes=set(), pack_dirs=set(),
                     python_has=lambda w, m: False, python_for=lambda w: "/comfy/python")
        items = FT.status([self.feature()], env)[0]["items"]
        self.assertNotIn("how", items[0])
        self.assertTrue(items[1]["manual"])
        self.assertIn("ComfyUI-Manager", items[1]["how"])
        self.assertIn("https://github.com/x/y", items[1]["how"])
        self.assertIn("isn't listed there, clone", items[1]["how"])   # not every pack is
        self.assertIn("/comfy/python -m pip install demucs", items[2]["how"])

    def test_a_pack_cloned_but_not_loaded_wants_a_restart(self):
        env = FT.Env(model_exists=lambda f, n: True, node_classes=set(), pack_dirs={"somepack"},
                     python_has=lambda w, m: True)
        got = FT.status([self.feature()], env)[0]
        self.assertEqual(got["status"], "restart")
        self.assertEqual(got["items"][1]["status"], "restart")

    def test_readiness_counts_a_substitute_for_a_targets_file(self):
        item = FT.Item("model", "want.safetensors", folder="vae", url="https://h/w", target="t1")
        env = FT.Env(model_exists=lambda f, n: False, readiness={"t1": {"status": "ready", "missing": []}})
        self.assertEqual(FT.item_status(item, env), "installed")
        env.readiness = {"t1": {"status": "not_ready", "missing": [{"want": "want.safetensors"}]}}
        self.assertEqual(FT.item_status(item, env), "missing")


class ResolveTest(unittest.TestCase):
    def test_files_by_name_only_and_classes_to_their_pack(self):
        items, skipped = FT.resolve(files=["minimax_h3_video_vae_fp16.safetensors", "made_up.bin"],
                                    classes=["H3SLAAttention", "NoSuchNode"], features=FT.catalog())
        names = [i.name for i in items]
        self.assertIn("minimax_h3_video_vae_fp16.safetensors", names)
        # a node pack is never installed by seriesmith: it comes back with how
        self.assertNotIn("ComfyUI-PlagueKind-Nodes", names)
        self.assertEqual(len(skipped), 3)
        self.assertTrue(any("made_up.bin" in s for s in skipped))
        self.assertTrue(any(s.startswith("ComfyUI-PlagueKind-Nodes: Install") for s in skipped))

    def test_packs_and_packages_are_never_queued(self):
        items, skipped = FT.resolve(["sound.demucs", "upscale.h3_latent"], features=FT.catalog())
        self.assertEqual([i.kind for i in items], ["model"])
        self.assertTrue(any("pip install demucs" in s for s in skipped))
        self.assertTrue(any("Comfyui_Minimax_h3_latent_Upscaler" in s for s in skipped))

    def test_what_is_installed_is_left_out_and_each_item_once(self):
        cat = FT.catalog()
        env = FT.Env(model_exists=lambda f, n: n == "seedvr2_ema_vae_fp16.safetensors")
        items, _ = FT.resolve(["upscale.seedvr2_7b", "upscale.seedvr2_3b"], features=cat, env=env)
        self.assertEqual(sorted(i.name for i in items),
                         ["seedvr2_3b_int8_convrot.safetensors", "seedvr2_7b_int8_convrot.safetensors"])


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.data = os.urandom(3 * INS.CHUNK + 123)
        self.srv = FileServer({"/f.bin": self.data, "/gated/g.bin": b"secret"})
        self.addCleanup(self.srv.close)
        self.dir = tempfile.mkdtemp()

    def test_whole_then_resumed(self):
        dest = os.path.join(self.dir, "f.bin")
        seen = []
        INS.download(self.srv.url + "/f.bin", dest, progress=lambda d, t: seen.append((d, t)))
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), self.data)
        self.assertEqual(seen[-1], (len(self.data), len(self.data)))
        # a stopped download left a .part: the rest is asked for, not the whole
        dest2 = os.path.join(self.dir, "g.bin")
        with open(dest2 + ".part", "wb") as fh:
            fh.write(self.data[:1000])
        INS.download(self.srv.url + "/f.bin", dest2)
        with open(dest2, "rb") as fh:
            self.assertEqual(fh.read(), self.data)
        self.assertEqual(self.srv.seen[-1]["range"], "bytes=1000-")

    def test_stopping_keeps_the_part(self):
        dest = os.path.join(self.dir, "s.bin")
        calls = []

        def cancelled():
            calls.append(1)
            return len(calls) > 1
        with self.assertRaises(INS.InstallError):
            INS.download(self.srv.url + "/f.bin", dest, cancelled=cancelled)
        self.assertFalse(os.path.exists(dest))
        self.assertTrue(os.path.getsize(dest + ".part") > 0)

    def test_a_gated_file_asks_for_the_licence_and_a_token(self):
        # the token only goes to Hugging Face: pretend this server is it
        url = self.srv.url + "/gated/g.bin?huggingface.co"
        with self.assertRaises(INS.InstallError) as cm:
            INS.download(url, os.path.join(self.dir, "g"), token=None)
        self.assertIn("Hugging Face token", str(cm.exception))
        INS.download(url, os.path.join(self.dir, "g"), token="good")
        with open(os.path.join(self.dir, "g"), "rb") as fh:
            self.assertEqual(fh.read(), b"secret")
        self.assertEqual(self.srv.seen[-1]["auth"], "Bearer good")


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cn = os.path.join(self.root, "custom_nodes")
        os.makedirs(self.cn)
        self.place = INS.Place({"loras": [os.path.join(self.root, "models", "loras")]}, self.cn,
                               os.path.join(self.root, "python.exe"))
        self.ran = []

    def runner(self, cmd, cwd=None, timeout=0):
        self.ran.append(cmd)
        return ""

    def downloader(self, url, dest, token, progress, cancelled):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"x" * 10)
        progress(10, 10)

    def test_a_file_goes_in_a_pack_or_package_never(self):
        ins = INS.Installer(lambda: self.place, runner=self.runner, downloader=self.downloader)
        items = [FT.Item("pack", "SomePack", url="https://github.com/x/SomePack", classes=("N",)),
                 FT.Item("model", "a.safetensors", folder="loras", url="https://h/a"),
                 FT.Item("pip", "demucs", where="comfyui", module="demucs")]
        st = ins.wait(ins.start(items) and 10)
        self.assertEqual([t["status"] for t in st["tasks"]], ["failed", "done", "failed"], st)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "models", "loras", "a.safetensors")))
        self.assertEqual(self.ran, [])

    def test_a_failure_says_why_and_the_rest_go_on(self):
        def failing(url, dest, token, progress, cancelled):
            if url.endswith("/a"):
                raise INS.InstallError("gated: accept the licence")
            self.downloader(url, dest, token, progress, cancelled)
        ins = INS.Installer(lambda: self.place, runner=self.runner, downloader=failing)
        ins.start([FT.Item("model", "a.safetensors", folder="loras", url="https://h/a"),
                   FT.Item("model", "b.safetensors", folder="loras", url="https://h/b")])
        st = ins.wait(10)
        self.assertEqual([t["status"] for t in st["tasks"]], ["failed", "done"])
        self.assertIn("gated", st["tasks"][0]["error"])

    def test_nowhere_to_put_it(self):
        nowhere = INS.Place(why_not="ComfyUI isn't on this machine")
        ins = INS.Installer(lambda: nowhere, runner=self.runner, downloader=self.downloader)
        ins.start([FT.Item("model", "a.safetensors", folder="loras", url="https://h/a")])
        st = ins.wait(10)
        self.assertEqual(st["tasks"][0]["status"], "failed")
        self.assertIn("isn't on this machine", st["tasks"][0]["error"])


class PlaceTest(unittest.TestCase):
    def test_the_folder_named_after_the_kind_wins(self):
        p = INS.Place({"diffusion_models": ["/c/models/unet", "/c/models/diffusion_models"]}, "/c/custom_nodes")
        self.assertEqual(os.path.basename(p.models_dir("diffusion_models")), "diffusion_models")
        # a folder ComfyUI hasn't listed goes under models/
        self.assertEqual(os.path.normpath(p.models_dir("optical_flow")),
                         os.path.normpath("/c/models/optical_flow"))

    def test_comfyuis_python_beside_a_portable_install(self):
        base = tempfile.mkdtemp()
        root = os.path.join(base, "ComfyUI")
        os.makedirs(root)
        os.makedirs(os.path.join(base, "python_embeded"))
        exe = os.path.join(base, "python_embeded", "python.exe" if os.name == "nt" else "python")
        open(exe, "w").close()
        self.assertEqual(INS.comfy_python(root), exe)
        self.assertIsNone(INS.comfy_python(os.path.join(tempfile.mkdtemp(), "ComfyUI")))


class FfmpegExtractTest(unittest.TestCase):
    def test_the_two_tools_out_of_a_build(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ffmpeg-7.1-essentials_build/bin/ffmpeg.exe", b"ff")
            z.writestr("ffmpeg-7.1-essentials_build/bin/ffprobe.exe", b"fp")
            z.writestr("ffmpeg-7.1-essentials_build/doc/readme.txt", b"r")
        d = tempfile.mkdtemp()
        archive = os.path.join(d, "b.zip")
        with open(archive, "wb") as fh:
            fh.write(buf.getvalue())
        into = os.path.join(d, "out")
        INS.extract_ffmpeg(archive, into)
        self.assertEqual(sorted(os.listdir(into)), ["ffmpeg.exe", "ffprobe.exe"])


if __name__ == "__main__":
    unittest.main()
