"""
Comfy Cloud (seriesmith/cloud.py): a portable graph made of Cloud's own nodes
(the loader's work done here, the saver as CreateVideo / SaveVideo / SaveAudio,
a node Cloud hasn't spliced out or refused), and the take made from what comes
back. Cloud itself is never asked: its node list is a stand-in.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import cloud as C  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import render  # noqa: E402
from seriesmith import shotnodes as SN  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.backends import File, files_in  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from test_render import build_episode  # noqa: E402
from test_render_take import h3_shot  # noqa: E402

CORE = {"LoadImage", "LoadAudio", "CreateVideo", "SaveVideo", "SaveAudio"}
SEED_NODES = frozenset({"SeriesmithShotLoader", "SeriesmithSaveTake", "SeriesmithChainLatent",
                        "SeriesmithChainTrim", "H3ContinuityFrame"})


def write_png(path: str, size=(512, 128), colours=None) -> None:
    """A picture of `colours` side by side (a 4-panel sheet by default)."""
    from PIL import Image
    colours = colours or [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    w, h = size
    img = Image.new("RGB", size)
    pw = w // len(colours)
    for i, c in enumerate(colours):
        img.paste(Image.new("RGB", (pw, h), c), (i * pw, 0))
    img.save(path, format="PNG")


def write_wav(path: str, seconds: float = 2.0, sr: int = 16000) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(int(seconds * sr) * 2))


def real_refs(root: str) -> None:
    """The fixture's empty reference files made real pictures and sounds."""
    for d, _, names in os.walk(root):
        for n in names:
            p = os.path.join(d, n)
            if os.path.getsize(p):
                continue
            if n.lower().endswith((".png", ".jpg", ".jpeg")):
                write_png(p)
            elif n.lower().endswith(".wav"):
                write_wav(p)


def cloud_info(graph: dict, lacking=()) -> dict:
    """A Cloud node list holding every class `graph` uses but seriesmith's own,
    and the core nodes, less `lacking`."""
    have = ({v["class_type"] for v in graph.values()} - SEED_NODES) | CORE
    return {c: {"input": {}} for c in have - set(lacking)}


def mp4(path: str, frames: int = 12, audio: bool = True) -> bytes:
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=24"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000", "-shortest"]
    subprocess.run([*cmd, "-frames:v", str(frames), "-pix_fmt", "yuv420p", path],
                   check=True, capture_output=True)
    with open(path, "rb") as fh:
        return fh.read()


class Episode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "ep")
        os.makedirs(self.root)
        build_episode(self.root)
        real_refs(self.root)
        self.doc = J.load_shotlist(self.root, "final")
        self.index = h3_shot(self.doc)
        self.shot_id = self.doc["shots"][self.index]["id"]
        self.base, _ = J.resolve_workflow(None, J.WORKFLOW_NAME, None, prefer_repo=True)

    def portable(self):
        job = J.plan_job(self.root, "final", self.doc, self.index,
                         J.RenderRequest(self.shot_id), {})
        take = J.start_job(job)
        return job, take, J.graph_for(self.base, job, take, portable=True)

    def lower(self, lacking=()):
        job, take, g = self.portable()
        lowered, plan = C.lower(g, job, take, cloud_info(g, lacking))
        self.addCleanup(C.done_sending, plan)
        return job, take, g, lowered, plan


class LowerTest(Episode):
    def test_nothing_of_seriesmiths_goes(self):
        _, _, g, lowered, plan = self.lower()
        self.assertFalse({v["class_type"] for v in lowered.values()} & SEED_NODES)
        self.assertNotIn(J.node_of(g, J.PORTABLE_LOADER), lowered)
        json.dumps(plan)                                 # the queue's journal keeps it

    def test_the_loaders_values_are_written_into_the_nodes_that_read_them(self):
        job, _, g, lowered, _ = self.lower()
        sp = SN.shotplan()
        li = g[J.node_of(g, J.PORTABLE_LOADER)]["inputs"]
        where = {r: li[SN.file_input(i)].path for i, r in enumerate(json.loads(li["files"]))}
        plan = sp.plan_shot(json.loads(li["shotlist"]), 0, "auto", float(li["fps"]), "",
                            lambda p: where.get(p, ""))
        cond = lowered[J.node_of(lowered, "MiniMaxH3ReferenceToVideo")]["inputs"]
        self.assertEqual((cond["prompt"], cond["width"], cond["height"], cond["length"]),
                         (plan["prompt"], plan["width"], plan["height"], plan["length"]))
        self.assertEqual((cond["width"], cond["height"], cond["length"]),
                         (job.width, job.height, job.frames))
        # a generate shot has no audio reference: the inputs are left out
        self.assertFalse([k for k in cond if k.startswith("ref_audios.")])
        for k in ("ref_images.ref_image_0", "ref_images.ref_image_3"):
            src = lowered[cond[k][0]]
            self.assertEqual(src["class_type"], "LoadImage")
            self.assertIsInstance(src["inputs"]["image"], File)
        noise = next(v for v in lowered.values() if v["class_type"] == "RandomNoise")
        self.assertEqual(noise["inputs"]["noise_seed"], plan["seed"])

    def test_the_saver_is_clouds_own_nodes(self):
        _, take, _, lowered, plan = self.lower()
        save = lowered[C.VIDEO]["inputs"]
        self.assertEqual((save["format"], save["format.codec"], save["format.codec.encoding.crf"]),
                         ("mp4", "h264", float(C.CRF)))
        self.assertIn(take.paths.stem, save["filename_prefix"])
        create = lowered[save["video"][0]]
        self.assertEqual(create["class_type"], "CreateVideo")
        self.assertIn("audio", create["inputs"])                  # generate: H3's sound is the shot's
        self.assertEqual(lowered[C.AUDIO]["inputs"]["audio"], create["inputs"]["audio"])
        self.assertEqual((plan["video"], plan["audio"], plan["policy"]),
                         (C.VIDEO, C.AUDIO, "generate"))
        self.assertTrue(plan["loaded_refs"])

    def test_a_node_the_target_can_do_without_is_spliced_out(self):
        _, _, g, lowered, plan = self.lower(lacking={"H3SLAAttention"})
        self.assertIn("H3SLAAttention", {v["class_type"] for v in g.values()})
        self.assertNotIn("H3SLAAttention", {v["class_type"] for v in lowered.values()})
        self.assertIn("H3SLAAttention isn't on Comfy Cloud: rendered without it", plan["notes"])

    def test_a_node_cloud_hasnt_refuses_the_job(self):
        with self.assertRaises(J.NotPortable) as cm:
            self.lower(lacking={"MiniMaxH3ReferenceToVideo"})
        self.assertIn("MiniMaxH3ReferenceToVideo", str(cm.exception))

    def test_a_held_shot_stays_local(self):
        job, take, g = self.portable()
        g["99"] = {"class_type": "SeriesmithChainLatent", "inputs": {}}
        with self.assertRaises(J.NotPortable) as cm:
            C.lower(g, job, take, cloud_info(g))
        self.assertIn("render it on local", str(cm.exception))

    def test_the_files_made_go_once_sent(self):
        _, _, _, lowered, plan = self.lower()
        made = [f.path for _, _, f in files_in(lowered) if f.path.startswith(plan["staging"])]
        self.assertTrue(made)
        C.done_sending(plan)
        self.assertFalse(os.path.exists(plan["staging"]))


class PictureAndSoundTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.d = self._tmp.name
        self.sp = SN.shotplan()

    def test_a_sheet_is_cut_to_its_kept_panels(self):
        from PIL import Image
        sheet = os.path.join(self.d, "sheet.png")
        write_png(sheet)
        out = os.path.join(self.d, "cut.png")
        path, size = C.picture(self.sp, {"path": sheet, "panels": 4, "keep": [0, 3]}, out)
        self.assertEqual((path, size), (out, (256, 128)))
        with Image.open(out) as img:
            self.assertEqual((img.getpixel((10, 10)), img.getpixel((200, 10))),
                             ((255, 0, 0), (255, 255, 0)))

    def test_a_whole_picture_goes_as_it_is(self):
        sheet = os.path.join(self.d, "plate.png")
        write_png(sheet)
        self.assertEqual(C.picture(self.sp, {"path": sheet, "panels": 1, "keep": []},
                                   os.path.join(self.d, "x.png")), (sheet, (512, 128)))

    def test_grey_is_grey(self):
        from PIL import Image
        path, size = C.picture(self.sp, {"neutral": [32, 32]}, os.path.join(self.d, "g.png"))
        with Image.open(path) as img:
            self.assertEqual((size, img.getpixel((0, 0))), ((32, 32), (128, 128, 128)))

    def test_a_slice_of_the_recording_is_sample_exact(self):
        src = os.path.join(self.d, "mix.wav")
        write_wav(src, seconds=2.0, sr=16000)
        out = C.sound({"path": src, "start": 0.25, "end": 1.0}, os.path.join(self.d, "s.wav"))
        with wave.open(out, "rb") as w:
            self.assertEqual((w.getnframes(), w.getframerate()), (12000, 16000))
        self.assertEqual(C.sound({"path": src, "start": None, "end": None}, "unused"), src)
        with self.assertRaises(ValueError):
            C.sound({"path": src, "start": 3.0, "end": 4.0}, os.path.join(self.d, "e.wav"))


class CollectTest(Episode):
    def test_the_video_and_sound_make_the_take(self):
        job, take, _, lowered, plan = self.lower()
        clip = mp4(os.path.join(self._tmp.name, "clip.mp4"))
        wav = os.path.join(self._tmp.name, "h3.flac")
        write_wav(wav)
        with open(wav, "rb") as fh:
            sound = fh.read()
        fb = FakeBackend("cloud", "cloud", outputs={
            C.VIDEO: [("sh_00001_.mp4", "video", clip)],
            C.AUDIO: [("sh_h3_00001_.flac", "audio", sound)]})
        run = fb.submit(lowered)
        J.mark_submitted(take, fb.name, run.id)
        self.assertEqual(C.collect(take, run, run.watch(), json.loads(json.dumps(plan))), "ok")
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual((sc["status"], sc["frames"], sc["mp4"], sc["backend"]),
                         ("ok", 12, os.path.basename(take.paths.mp4), "cloud"))
        self.assertIn("mp4 from Comfy Cloud", sc["save_notes"])
        self.assertTrue(sc["loaded_refs"])
        for p in (take.paths.mp4, take.paths.h3_wav, take.paths.thumb, take.paths.strip):
            self.assertTrue(os.path.isfile(p), p)
        self.assertFalse(os.path.exists(plan["staging"]))

    def test_no_video_fails_the_take(self):
        _, take, _, lowered, plan = self.lower()
        fb = FakeBackend("cloud", "cloud", outputs={})
        run = fb.submit(lowered)
        self.assertEqual(C.collect(take, run, run.watch(), plan), "failed")
        self.assertIn("sent no video back", T.read_sidecar(take.paths.sidecar)["save_notes"])


class FakeCloud(FakeBackend):
    """A fake backend that is Comfy Cloud: it has a node list."""
    def __init__(self, *a, info=None, **k):
        super().__init__("cloud", "cloud", *a, **k)
        self.info = info or {}

    def object_info(self):
        return self.info

    def choices(self, ctype, field, strict=False):
        return J.choices_in(self.info, ctype, field, strict)


class RenderOnCloudTest(Episode):
    def test_render_makes_a_take_on_cloud(self):
        _, _, g = self.portable()
        info = cloud_info(g)
        clip = mp4(os.path.join(self._tmp.name, "clip.mp4"), audio=False)
        fb = FakeCloud(info=info, outputs={C.VIDEO: [("v_00001_.mp4", "video", clip)]})
        with mock.patch.object(render, "available", return_value={fb.name: fb}), \
                mock.patch("builtins.print"):
            code = render.main([self.root, "--only", self.shot_id, "--redo", "--backend", "cloud"])
        self.assertEqual(code, 0)
        sent = fb.submitted[-1]
        self.assertFalse({v["class_type"] for v in sent.values()} & SEED_NODES)
        take = T.list_takes(self.root, "final", self.shot_id)[-1]
        self.assertEqual((take.sidecar["status"], take.sidecar["backend"]), ("ok", "cloud"))


if __name__ == "__main__":
    unittest.main()
