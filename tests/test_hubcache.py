"""
What a package would fetch by itself the first time a job runs (seriesmith/hubcache.py,
features kind "hub"): found where that package looks (a fake Hugging Face cache, torch's
hub folder, a models folder: never this machine's), downloaded there by the installer
(against a stand-in Hub), and every job that needs one held back until it's there:
readiness, a foley or ambience job, align, the node pack's vocal strip and vocal stem.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import edit as E  # noqa: E402
from seriesmith import features as FT  # noqa: E402
from seriesmith import hubcache as HC  # noqa: E402
from seriesmith import installer as INS  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith import track as K  # noqa: E402

NODES_HUB = FT.nodes_hub()                     # comfy_nodes/_hub.py, stdlib only


def write(path: str, data: bytes = b"x") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class Caches(unittest.TestCase):
    """Each test on its own empty caches."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hf = os.path.join(self.tmp, "hf")
        env = mock.patch.dict(os.environ, {"HF_HUB_CACHE": self.hf,
                                           "TORCH_HOME": os.path.join(self.tmp, "torch")})
        env.start()
        self.addCleanup(env.stop)

    def snapshot(self, repo: str, files, sha: str = "abc123", ref: bool = True) -> str:
        d = os.path.join(self.hf, "models--" + repo.replace("/", "--"))
        for f in files:
            write(os.path.join(d, "snapshots", sha, *f.split("/")))
        if ref:
            write(os.path.join(d, "refs", "main"), sha.encode())
        return os.path.join(d, "snapshots", sha)


class PresentTest(Caches):
    def test_a_repo_in_the_hugging_face_cache(self):
        item = FT.whisper_item("medium.en")
        self.assertEqual(item.name, "Systran/faster-whisper-medium.en")
        self.assertFalse(HC.present(item))
        self.snapshot(item.name, ["config.json", "model.bin", "tokenizer.json"])
        self.assertFalse(HC.present(item))                  # no vocabulary.* yet
        self.snapshot(item.name, ["vocabulary.txt"])
        self.assertTrue(HC.present(item))
        # a snapshot refs/main doesn't name isn't what huggingface_hub reads
        other = FT.whisper_item("large-v3")
        self.snapshot(other.name, ["config.json", "model.bin", "tokenizer.json",
                                   "vocabulary.json"], ref=False)
        self.assertFalse(HC.present(other))

    def test_a_file_in_torchs_hub_folder_and_a_folder_in_a_models_folder(self):
        ht = next(i for f in FT.catalog() if f.id == "sound.demucs" for i in f.items if i.kind == "hub")
        self.assertEqual((ht.folder, ht.name), ("torch", NODES_HUB.HTDEMUCS))
        self.assertFalse(HC.present(ht))
        write(os.path.join(self.tmp, "torch", "hub", "checkpoints", "955717e8-8726e21a.th"))
        self.assertTrue(HC.present(ht))
        big = FT.fetch_items(TG.load_target("mmaudio_ambience"))[0]
        self.assertEqual((big.folder, big.files), ("mmaudio", ("config.json", "bigvgan_generator.pt")))
        models = os.path.join(self.tmp, "models", "mmaudio")
        self.assertIsNone(HC.present(big))                  # no models folder known
        self.assertFalse(HC.present(big, lambda f: models))
        # the pack's own half-done snapshot (only its README) isn't BigVGAN
        write(os.path.join(models, "nvidia", "bigvgan_v2_44khz_128band_512x", "README.md"))
        self.assertFalse(HC.present(big, lambda f: models))
        for f in big.files:
            write(os.path.join(models, "nvidia", "bigvgan_v2_44khz_128band_512x", f))
        self.assertTrue(HC.present(big, lambda f: models))

    def test_status_and_the_window(self):
        item = FT.whisper_item("tiny.en")
        env = FT.Env(hub_has=lambda i: HC.present(i))
        self.assertEqual(FT.item_status(item, env), "missing")
        self.assertEqual(FT.item_status(item, FT.Env()), "unknown")
        self.snapshot(item.name, ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"])
        self.assertEqual(FT.item_status(item, env), "installed")
        j = item.to_json()
        self.assertEqual((j["kind"], j["into"]), ("hub", "the Hugging Face cache"))
        self.assertNotIn("manual", j)                       # seriesmith downloads it
        self.assertNotIn("folder", j)

    def test_the_vocal_stem_counts_torchaudios_own_copy(self):
        vocals = next(f for f in FT.catalog() if f.id == "sound.vocals")
        w = next(i for i in vocals.items if i.kind == "model")
        env = FT.Env(model_exists=lambda f, n: False, hub_has=lambda i: HC.present(i))
        self.assertEqual(FT.item_status(w, env), "missing")
        write(os.path.join(self.tmp, "torch", "hub", "torchaudio", "models", "hdemucs_high_trained.pt"))
        self.assertEqual(FT.item_status(w, env), "installed")


class ListingHub:
    """A stand-in Hub: the listing and the downloads."""

    def __init__(self, files: dict[str, bytes], sha: str = "c0ffee"):
        self.files, self.sha, self.got = files, sha, []

    def listing(self, repo, token=None):
        return self.sha, [(n, len(b)) for n, b in self.files.items()]

    def download(self, url, dest, token, progress, cancelled):
        name = url.split(f"/resolve/{self.sha}/", 1)[1]
        self.got.append(name)
        write(dest, self.files[name])
        if progress:
            progress(len(self.files[name]), len(self.files[name]))


class DownloadTest(Caches):
    def test_a_repo_into_the_hugging_face_cache_as_huggingface_hub_lays_it_out(self):
        item = FT.whisper_item("base.en")
        hub = ListingHub({"README.md": b"r", ".gitattributes": b"g", "config.json": b"{}",
                          "model.bin": b"m" * 50, "tokenizer.json": b"t", "vocabulary.txt": b"v",
                          "preprocessor_config.json": b"p"})
        seen = []
        root = HC.fetch_repo(item, None, hub.download, progress=lambda d, t: seen.append((d, t)),
                             listing=hub.listing)
        self.assertEqual(sorted(hub.got), ["config.json", "model.bin", "preprocessor_config.json",
                                           "tokenizer.json", "vocabulary.txt"])
        self.assertEqual(root, os.path.join(HC.repo_dir(item.name), "snapshots", "c0ffee"))
        with open(os.path.join(HC.repo_dir(item.name), "refs", "main"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "c0ffee")           # no newline: huggingface_hub reads it raw
        self.assertTrue(HC.present(item))
        self.assertEqual(seen[-1], (55, 55))                # across the files
        # again: nothing fetched twice
        hub.got.clear()
        HC.fetch_repo(item, None, hub.download, listing=hub.listing)
        self.assertEqual(hub.got, [])

    def test_a_repo_without_a_file_it_must_have(self):
        item = FT.whisper_item("base.en")
        hub = ListingHub({"config.json": b"{}", "model.bin": b"m"})
        with self.assertRaises(ValueError):
            HC.fetch_repo(item, None, hub.download, listing=hub.listing)
        self.assertFalse(os.path.exists(os.path.join(HC.repo_dir(item.name), "refs", "main")))

    def test_the_installer_puts_each_kind_where_its_package_looks(self):
        root = tempfile.mkdtemp()
        place = INS.Place({"mmaudio": [os.path.join(root, "models", "mmaudio")]},
                          os.path.join(root, "custom_nodes"))
        os.makedirs(place.custom_nodes)
        big = FT.fetch_items(TG.load_target("mmaudio_ambience"))[0]
        hub = ListingHub({"config.json": b"{}", "bigvgan_generator.pt": b"g" * 9,
                          "bigvgan_discriminator_optimizer.pt": b"d" * 99})
        torch_got = []

        def download(url, dest, token, progress, cancelled):
            if "/resolve/" in url:
                return hub.download(url, dest, token, progress, cancelled)
            torch_got.append(url)
            write(dest, b"h")
        ins = INS.Installer(lambda: place, downloader=download, listing=hub.listing)
        ht = FT.Item("hub", NODES_HUB.HTDEMUCS, folder="torch", url=NODES_HUB.HTDEMUCS_URL)
        st = ins.wait(ins.start([big, ht]) and 10)
        self.assertEqual([t["status"] for t in st["tasks"]], ["done", "done"], st)
        folder = os.path.join(root, "models", "mmaudio", "nvidia", "bigvgan_v2_44khz_128band_512x")
        self.assertEqual(sorted(os.listdir(folder)), ["bigvgan_generator.pt", "config.json"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "torch", "hub", "checkpoints",
                                                    "955717e8-8726e21a.th")))
        self.assertEqual(torch_got, [NODES_HUB.HTDEMUCS_URL])
        # nothing that's there is fetched again
        ins.start([big, ht])
        st = ins.wait(10)
        self.assertEqual([t["note"] for t in st["tasks"]], ["already there", "already there"])

    def test_the_whats_missing_window_asks_for_a_repo_by_name(self):
        items, skipped = FT.resolve(files=["laion/larger_clap_general"], features=FT.catalog())
        self.assertEqual([(i.kind, i.name) for i in items], [("hub", "laion/larger_clap_general")])
        self.assertEqual(skipped, [])


class HeldBackTest(Caches):
    """A job that would set a package fetching never goes."""

    class Backend:
        def __init__(self, kind="local", url="http://127.0.0.1:8188"):
            self.kind, self.base_url = kind, url

    def test_readiness_holds_a_target_back_until_its_fetches_are_here(self):
        t = TG.load_target("hunyuan_xl_foley")
        info = {c: {"input": {"required": {}}} for c in E.target_nodes(t)}
        self.assertEqual(E.readiness([t], info)[t.id]["status"], "ready")
        r = E.readiness([t], info, hub_has=lambda i: HC.present(i))[t.id]
        self.assertEqual(r["status"], "not_ready")
        self.assertEqual(sorted(m["want"] for m in r["missing"]),
                         ["google/siglip2-base-patch16-512", "laion/larger_clap_general"])
        m = r["missing"][0]
        self.assertEqual((m["param"], m["tier"], m["folder"]), ("fetches", "required", None))
        self.assertTrue(m["url"].startswith("https://huggingface.co/"))
        self.assertIn("Features", m["source"])
        # what Install asks for comes back as the hub item
        items, _ = FT.resolve(files=[m["want"] for m in r["missing"]], features=FT.catalog())
        self.assertEqual({i.kind for i in items}, {"hub"})
        for i in FT.fetch_items(t):
            self.snapshot(i.name, i.files)
        self.assertEqual(E.readiness([t], info, hub_has=lambda i: HC.present(i))[t.id]["status"],
                         "ready")

    def test_a_job_on_this_machines_comfyui_refuses(self):
        t = TG.load_target("hunyuan_xl_foley")
        with self.assertRaises(RuntimeError) as cm:
            HC.check_target(t, self.Backend())
        self.assertIn("Features window (Effects (HunyuanVideo-Foley XL))", str(cm.exception))
        # elsewhere: its own caches, not this machine's
        HC.check_target(t, self.Backend(url="http://10.0.0.5:8188"))
        HC.check_target(t, self.Backend(kind="cloud"))
        for i in FT.fetch_items(t):
            self.snapshot(i.name, i.files)
        HC.check_target(t, self.Backend())
        # a models folder's: asked where ComfyUI keeps it
        mm = TG.load_target("mmaudio_ambience")
        models = os.path.join(self.tmp, "models", "mmaudio")
        with self.assertRaises(RuntimeError):
            HC.check_target(mm, self.Backend(), models_dir=lambda f: models)
        HC.check_target(TG.load_target("stable_audio3"), self.Backend())   # fetches nothing

    def test_align_needs_its_whisper_model_downloaded(self):
        ready = {"ready": True, "missing": [], "install": "", "python": "py", "ffmpeg": "ffmpeg",
                 "packages": {"numpy": "2", "faster-whisper": "1.2", "openai-whisper": None}}
        with mock.patch.object(K, "align_ready", lambda py=None: ready), \
                mock.patch.object(K, "recording_path", lambda ep, track: None):
            with self.assertRaises(K.TrackError) as cm:
                K.check_align("ep", python="py")
            self.assertEqual(cm.exception.status, 409)
            self.assertIn("Features window (Recorded dialogue)", str(cm.exception))
            self.assertEqual(cm.exception.data["feature"], "sound.align")
            with self.assertRaises(K.TrackError) as cm:
                K.check_align("ep", python="py", model="large-v3")
            self.assertEqual(cm.exception.data["feature"], "sound.whisper.large-v3")
            self.snapshot(K.WHISPER_REPOS["medium.en"], ["config.json", "model.bin",
                                                         "tokenizer.json", "vocabulary.txt"])
            K.check_align("ep", python="py")                # downloaded: it runs
            # a transcript already beside the recording needs no Whisper at all
            with mock.patch.object(K, "recording_path", lambda ep, track: "rec.wav"), \
                    mock.patch.object(E, "has_words", lambda rec: True):
                K.check_align("ep", python="py", model="large-v3")

    def test_align_itself_never_lets_faster_whisper_fetch(self):
        from seriesmith import align as AL
        with self.assertRaises(SystemExit) as cm:
            AL.local_whisper("small.en")
        self.assertIn("Features window", str(cm.exception))
        d = tempfile.mkdtemp()
        self.assertEqual(AL.local_whisper(d), d)            # a model's own folder is used as is


class NodePackTest(Caches):
    """comfy_nodes/_hub.py: what the vocal strip and the vocal stem read."""

    def test_the_vocal_strip_is_skipped_until_htdemucs_is_here(self):
        why = NODES_HUB.strip_blocked()
        self.assertIn("Features window", why)
        self.assertIn("foley bed skipped", why)
        write(os.path.join(self.tmp, "torch", "hub", *NODES_HUB.HTDEMUCS.split("/")))
        self.assertIsNone(NODES_HUB.strip_blocked())
        self.assertEqual(NODES_HUB.demucs_env()["HF_HUB_OFFLINE"], "1")

    def test_demucs_41s_hugging_face_copy_counts(self):
        repo, files = NODES_HUB.HTDEMUCS_HF
        self.snapshot(repo, files)
        self.assertTrue(NODES_HUB.htdemucs_here())

    def test_the_vocal_stem_never_falls_back_to_a_download(self):
        with self.assertRaises(RuntimeError) as cm:
            NODES_HUB.hdemucs_weights(None)
        self.assertIn("Features window (Vocal stem)", str(cm.exception))
        mine = os.path.join(self.tmp, "models", "demucs", "hdemucs_high_trained.pt")
        write(mine)
        self.assertEqual(NODES_HUB.hdemucs_weights(mine), mine)
        cached = os.path.join(self.tmp, "torch", "hub", *NODES_HUB.TORCHAUDIO_HDEMUCS.split("/"))
        write(cached)
        self.assertEqual(NODES_HUB.hdemucs_weights(None), cached)
        with open(os.path.join(os.path.dirname(HERE), "comfy_nodes", "audio.py"), encoding="utf-8") as fh:
            self.assertNotIn("HDEMUCS_HIGH_MUSDB_PLUS.get_model", fh.read())

    def test_the_vocal_stems_weights_are_the_ones_features_downloads(self):
        from seriesmith import vocals as V
        self.assertEqual(NODES_HUB.TORCHAUDIO_HDEMUCS.rsplit("/", 1)[1], V.WEIGHTS_FILE)


if __name__ == "__main__":
    unittest.main()
