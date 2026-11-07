"""
The voice models that clone a clip rather than continue it (2026-11-07): Fish Audio
Drama 3 on ComfyUI-Drama3 (`drama3`), Qwen3-TTS on ComfyUI-Qwen-TTS (`qwen3_tts`) and
Drama 3 through Comfy's Fish Audio partner nodes (`fishaudio_drama3`).

Each is sent the words alone; with a voice sample the graph clones it (its clip as
long as the target asks, `capabilities.reference_clip`, with its words when
seriesmith knows them, `reference_text`), and with none the character's voice is
described (Qwen's VoiceDesign) or steered (a Drama 3 direction). The graphs are
checked against tests/fixtures/workflows/object_info_voices.json, trimmed from the
live ComfyUI (0.44.0, ComfyUI-Drama3 and ComfyUI-Qwen-TTS at 2026-11-07), and were
run there: the local two through seriesmith, the partner one not (it's paid).
"""
from __future__ import annotations

import json
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import features as FT  # noqa: E402
from seriesmith import hubcache as HC  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import partner  # noqa: E402
from test_phase85 import Episode  # noqa: E402
from test_phase9c_voice import wav  # noqa: E402

OBJECT_INFO = json.load(open(os.path.join(HERE, "fixtures", "workflows", "object_info_voices.json"),
                             encoding="utf-8"))


class CloneTargetCase(Episode):
    target = ""

    def plan(self, ref="voice:ada"):
        (job,) = R.plan_generate(self.s, R.GenRequest(ref, target=self.target), rng=random.Random(1))
        return job

    def sample(self, seconds=1.0, words=None):
        path = wav(os.path.join(self.s.home, "audio", "voices", "ada_sample.wav"), seconds)
        if words is not None:
            T.write_json(path + ".words.json", [{"word": w, "start": 0.1 * i, "end": 0.1 * i + 0.08}
                                                for i, w in enumerate(words.split())])
        self.s = R.load_series(self.ep)
        return path

    def graph(self, job):
        g = R.graph_for(J.load_graph(job.target.binding.workflow), job, R.start_gen(self.s, job))
        self.assertEqual(J.check_graph(g, OBJECT_INFO), [])
        return g

    @staticmethod
    def nodes(g, cls):
        return [v for v in g.values() if v["class_type"] == cls]

    def words_alone(self, job):
        """The words alone: Ada's lines, no opener, no description."""
        self.assertEqual(job.line_source, "script")
        self.assertFalse(job.line.startswith("Hello, this is"), job.line)
        self.assertEqual(job.prompt, job.line)


class Drama3Test(CloneTargetCase):
    target = "drama3"

    def test_no_sample_steers_the_model_voice(self):
        os.remove(os.path.join(self.s.home, "audio", "voices", "ada_sample.wav")) \
            if os.path.isfile(os.path.join(self.s.home, "audio", "voices", "ada_sample.wav")) else None
        job = self.plan()
        self.words_alone(job)
        self.assertEqual(R.stage_voice_reference(self.s, job, None), {})
        g = self.graph(job)
        (gen,) = self.nodes(g, "Drama3Generate")
        self.assertNotIn("voices.voice0", gen["inputs"])
        self.assertEqual(gen["inputs"]["text"], f"[dry, quick and precise] {job.line}")
        self.assertEqual(gen["inputs"]["seed"], job.seed)
        # the clone's branch is pruned: nothing to hear, nothing to encode
        for cls in ("LoadAudio", "Qwen3ASRTranscribe", "Drama3EncodeVoice"):
            self.assertFalse(self.nodes(g, cls), cls)
        (load,) = self.nodes(g, "Drama3Loader")
        self.assertEqual((load["inputs"]["model_name"], load["inputs"]["experts"]),
                         ("drama3_w4a8experts_bf16.safetensors", "in RAM"))
        self.assertTrue(self.nodes(g, "H3SaveRefAudio"))

    def test_a_sample_is_cloned_and_heard(self):
        self.sample(1.0)
        job = self.plan()
        self.words_alone(job)
        inputs = R.stage_voice_reference(self.s, job, None)
        self.assertNotIn("reference_text", inputs)            # the graph hears it itself
        g = self.graph(job)
        (gen,) = self.nodes(g, "Drama3Generate")
        self.assertEqual(gen["inputs"]["text"], job.line)      # no direction: the sample is the voice
        enc = g[gen["inputs"]["voices.voice0"][0]]
        self.assertEqual(enc["class_type"], "Drama3EncodeVoice")
        load = g[enc["inputs"]["audio"][0]]
        self.assertEqual(load["inputs"]["audio"], inputs["reference_audio"])
        heard = g[enc["inputs"]["transcript"][0]]
        self.assertEqual((heard["class_type"], heard["inputs"]["audio"][0]),
                         ("Qwen3ASRTranscribe", enc["inputs"]["audio"][0]))

    def test_experts_in_vram_when_the_file_fits(self):
        """`experts: auto`: in VRAM when the whole file and the headroom fit the GPU ComfyUI
        says it has, else in RAM (where, short of RAM, ComfyUI frees the model after every take)."""
        from types import SimpleNamespace as NS
        from seriesmith.targets.audio.drama3 import target as D
        job = self.plan("voice:rex")
        self.assertEqual(job.values.get("experts"), "auto")

        class Local:
            def __init__(self, vram):
                self.vram, self.asked = vram, 0

            def gpu_memory(self):
                self.asked += 1
                return self.vram

        five090 = Local(34162016256)
        R.stage_gpu_memory(job, five090)
        self.assertEqual((five090.asked, job.inputs["gpu_memory"]), (1, 34162016256))
        (load,) = self.nodes(self.graph(job), "Drama3Loader")
        self.assertEqual(load["inputs"]["experts"], "in VRAM")         # W4A8 on a 32 GB card
        for model, vram, where in (("drama3_w6a8experts_bf16.safetensors", 34162016256, "in RAM"),
                                   ("drama3_int8experts_bf16.safetensors", 51527024640, "in VRAM"),
                                   ("drama3_w4a8experts_bf16.safetensors", 25757220864, "in RAM"),   # 24 GB
                                   ("drama3_w4a8experts_bf16.safetensors", None, "in RAM"),          # can't tell
                                   ("my_drama3_experts.safetensors", 51527024640, "in RAM")):        # size unknown
            self.assertEqual(D.experts_where(model, vram), where, (model, vram))
        # a backend that can't say (Cloud): nothing staged, so in RAM
        job2 = self.plan("voice:rex")
        R.stage_gpu_memory(job2, NS())
        self.assertNotIn("gpu_memory", job2.inputs)
        (load,) = self.nodes(self.graph(job2), "Drama3Loader")
        self.assertEqual(load["inputs"]["experts"], "in RAM")
        # named outright, it's used as it is
        job3 = self.plan("voice:rex")
        job3.values["experts"] = "in RAM"
        R.stage_gpu_memory(job3, five090)
        (load,) = self.nodes(self.graph(job3), "Drama3Loader")
        self.assertEqual(load["inputs"]["experts"], "in RAM")
        # a target that doesn't choose by it never asks
        qwen = R.plan_generate(self.s, R.GenRequest("voice:rex", target="qwen3_tts"), rng=random.Random(1))[0]
        asked = five090.asked
        R.stage_gpu_memory(qwen, five090)
        self.assertEqual((five090.asked, "gpu_memory" in qwen.inputs), (asked, False))

    def test_the_largest_installed_is_used(self):
        t = TG.load_target("drama3", "audio")
        want = "drama3_w4a8experts_bf16.safetensors"
        for installed, using in (([want], want),
                                 ([want, "drama3_w6a8experts_bf16.safetensors"], "drama3_w6a8experts_bf16.safetensors"),
                                 (["drama3_int8experts_bf16.safetensors", "drama3_w6a8experts_bf16.safetensors"],
                                  "drama3_int8experts_bf16.safetensors"),
                                 ([want, "drama3_fp8experts_bf16.safetensors"], "drama3_fp8experts_bf16.safetensors"),
                                 (["other.safetensors"], None)):
            got = TG.resolve_file(t, "model", want, installed)
            self.assertEqual(got and got["using"], using, installed)
        # a target with no `prefer` keeps the wanted file first, as before
        lt = TG.load_target("ltx2_voice", "audio")
        name = lt.presets["final"].model
        self.assertEqual(TG.resolve_file(lt, "model", name, [name, "ltx-2.5-22b-dev-x.safetensors"])["how"], "exact")


class Qwen3TTSTest(CloneTargetCase):
    target = "qwen3_tts"

    def test_no_sample_designs_the_voice(self):
        job = self.plan("voice:rex")                           # Rex has no sample
        self.words_alone(job)
        g = self.graph(job)
        (design,) = self.nodes(g, "FB_Qwen3TTSVoiceDesign")
        self.assertEqual(design["inputs"]["text"], job.line)
        self.assertEqual(design["inputs"]["instruct"],
                         "Rex is a scruffy brown terrier with one white ear and a red collar. "
                         "Voice: a gravelly bark of a voice.")
        self.assertEqual(design["inputs"]["seed"], job.seed)
        self.assertFalse(self.nodes(g, "FB_Qwen3TTSVoiceClone"))

    def test_a_sample_is_cloned_with_its_words_when_known(self):
        self.sample(1.0, words="Hello there, this is Ada.")
        job = self.plan()
        inputs = R.stage_voice_reference(self.s, job, None)
        self.assertEqual(inputs["reference_text"], "Hello there, this is Ada.")
        g = self.graph(job)
        self.assertFalse(self.nodes(g, "FB_Qwen3TTSVoiceDesign"))
        (clone,) = self.nodes(g, "FB_Qwen3TTSVoiceClone")
        c = clone["inputs"]
        self.assertEqual((c["target_text"], c["ref_text"], c["x_vector_only"], c["model_choice"], c["seed"]),
                         (job.line, "Hello there, this is Ada.", False, "1.7B", job.seed))
        self.assertEqual(g[c["ref_audio"][0]]["inputs"]["audio"], inputs["reference_audio"])
        # what saves it reads the clone (it took Voice Design's place)
        (saver,) = self.nodes(g, "H3SaveRefAudio")
        self.assertEqual(g[saver["inputs"]["audio"][0]]["class_type"], "FB_Qwen3TTSVoiceClone")

    def test_words_not_known_clone_from_the_voice_alone(self):
        self.sample(1.0)                                       # dropped in by hand: no words
        job = self.plan()
        self.assertEqual(R.stage_voice_reference(self.s, job, None)["reference_text"], "")
        (clone,) = self.nodes(self.graph(job), "FB_Qwen3TTSVoiceClone")
        self.assertEqual((clone["inputs"]["ref_text"], clone["inputs"]["x_vector_only"]), ("", True))

    def test_a_line_continuing_a_take_sends_its_words(self):
        """lines.local_job: a character with no sample continues their first line's take,
        whose words lines.json has."""
        path = wav(os.path.join(self.ep, "audio", "lines", "sh010.1_t01.wav"), 1.0)
        job = self.plan("voice:rex")
        job.held_sample, job.held_text = path, "Woof."
        self.assertEqual(R.stage_voice_reference(self.s, job, None)["reference_text"], "Woof.")

    def test_fetched_where_the_pack_reads_them(self):
        t = TG.load_target("qwen3_tts", "audio")
        items = {i.name: i for i in FT.fetch_items(t)}
        self.assertEqual(set(items), {"Qwen/Qwen3-TTS-12Hz-1.7B-Base", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                                      "Qwen/Qwen3-TTS-Tokenizer-12Hz"})
        base = items["Qwen/Qwen3-TTS-12Hz-1.7B-Base"]
        # models/qwen-tts/<the model's name>, not models/qwen-tts/Qwen/<name>
        self.assertEqual(HC.where_text(base), "models/qwen-tts/Qwen3-TTS-12Hz-1.7B-Base")
        self.assertEqual(HC.path_of(base, lambda f: os.path.join("M", f)),
                         os.path.join("M", "qwen-tts", "Qwen3-TTS-12Hz-1.7B-Base"))
        self.assertTrue(HC.present(base, lambda f: os.path.join(self.ep, "nowhere", f)) is False)


class FishAudioPartnerTest(CloneTargetCase):
    target = "fishaudio_drama3"

    def test_paid_and_never_seeded(self):
        t = TG.load_target("fishaudio_drama3", "audio")
        self.assertTrue(TG.runs_partner(t))
        self.assertFalse(TG.runs_partner(TG.load_target("drama3", "audio")))
        self.assertFalse(t.reproducible)
        self.assertTrue(partner(J.load_graph(t.binding.workflow)))

    def test_no_sample(self):
        job = self.plan("voice:rex")
        self.words_alone(job)
        g = self.graph(job)
        (tts,) = self.nodes(g, "FishAudioTextToSpeech")
        self.assertEqual(tts["inputs"]["model"], "drama-3")
        self.assertEqual(tts["inputs"]["text"], f"[a gravelly bark of a voice] {job.line}")
        self.assertNotIn("model.voices.voice0", tts["inputs"])
        self.assertTrue(partner(g))

    def test_a_sample_is_cloned_on_fish(self):
        self.sample(1.0)
        job = self.plan()
        inputs = R.stage_voice_reference(self.s, job, None)
        g = self.graph(job)
        (tts,) = self.nodes(g, "FishAudioTextToSpeech")
        clone = g[tts["inputs"]["model.voices.voice0"][0]]
        self.assertEqual(clone["class_type"], "FishAudioInstantVoiceClone")
        self.assertTrue(clone["_meta"]["partner"])
        self.assertEqual(g[clone["inputs"]["files.audio0"][0]]["inputs"]["audio"], inputs["reference_audio"])
        self.assertEqual(tts["inputs"]["text"], job.line)


class GpuMemoryTest(unittest.TestCase):
    def test_a_comfyui_that_doesnt_answer_cant_tell(self):
        from seriesmith.backends.native import ComfyUIBackend
        self.assertIsNone(ComfyUIBackend("local", "http://127.0.0.1:0").gpu_memory())


class FeaturesTest(unittest.TestCase):
    def test_drama3_sizes_are_offered(self):
        cat = {f.id: f for f in FT.catalog()}
        main = {i.name for i in cat["sound.voice_drama3"].items}
        self.assertEqual(main, {"ComfyUI-Drama3", "drama3_w4a8experts_bf16.safetensors",
                                "drama3_codec.safetensors", "qwen3_asr_0.6b_bf16.safetensors"})
        self.assertEqual([i.name for i in cat["sound.voice_drama3_w6a8"].items],
                         ["drama3_w6a8experts_bf16.safetensors"])
        self.assertEqual([i.name for i in cat["sound.voice_drama3_int8"].items],
                         ["drama3_int8experts_bf16.safetensors"])
        self.assertTrue(all(i.url.startswith("https://huggingface.co/PedroMarinhoDev/")
                            for f in ("sound.voice_drama3_w6a8", "sound.voice_drama3_int8")
                            for i in cat[f].items))
        qwen = {i.kind for i in cat["sound.voice_qwen3"].items}
        self.assertEqual(qwen, {"pack", "hub"})
        self.assertEqual([i.kind for i in cat["sound.voice_fishaudio"].items], ["key"])


if __name__ == "__main__":
    unittest.main()
