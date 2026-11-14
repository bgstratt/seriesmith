"""
The post pass (post.py, docs/POST_PROCESSING.md): an upscale finished by an
enhance step (pixel, SeedVR2, SUPIR; the tiers name them) and motion blur.

What it refuses, when a post is fresh, the graph for each step, readiness,
the recipe; then its nodes (comfy_nodes/finish.py), which need torch and are
skipped without it.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from seriesmith import edit as E  # noqa: E402
from seriesmith import api as A  # noqa: E402
from seriesmith import post as P  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import upscale as U  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_phase13 import UpscaleTest  # noqa: E402


class PostTest(ApiTest):
    final_take = UpscaleTest.final_take

    def upscaled(self, shot="sh010") -> T.Take:
        """A final take with a fresh 1920x1088 upscale."""
        t = self.final_take(shot)
        U.start(U.plan_upscale(self.ep, t))
        with open(t.paths.up_mp4, "wb") as fh:
            fh.write(b"up")
        T.update_sidecar(t.paths.up_sidecar, status="ok", width=1920, height=1088,
                         quality="master")
        return T.get_take(self.ep, "final", shot, 1)

    def by_class(self, g, ctype):
        return [k for k, v in g.items() if v["class_type"] == ctype]

    def finish(self, t: T.Take, job: P.PostJob) -> None:
        """What H3SaveUpscale does when it's done: the upscale stamped as it saves."""
        P.start(job)
        self.assertNotIn("source_sha1", T.read_sidecar(t.paths.post_sidecar))
        self.assertFalse(T.post_of(t)["fresh"])
        with open(t.paths.post_mp4, "wb") as fh:
            fh.write(b"post")
        T.update_sidecar(t.paths.post_sidecar, status="ok", **T.source_stamp(t.paths.up_mp4))

    # -- refusals and freshness -----------------------------------------------

    def test_refusals(self):
        t = self.final_take()
        self.assertIn("no upscale", P.plan_post(self.ep, t, enhance="draft").why)
        t = self.upscaled()
        self.assertIn("nothing to do", P.plan_post(self.ep, t).why)
        self.assertIn("tier", P.plan_post(self.ep, t, enhance={"tier": "ultra"}).why)
        self.assertIn("method", P.plan_post(self.ep, t, enhance="ccsr").why)
        self.assertIn("clean-up", P.plan_post(self.ep, t, enhance={"method": "supir",
                                                                   "strength": 0.8}).why)
        self.assertIn("motion_blur", P.plan_post(self.ep, t, blur=2).why)
        # a stale upscale: the take changed under it
        with open(t.paths.mp4, "ab") as fh:
            fh.write(b"more")
        self.assertIn("stale", P.plan_post(self.ep, t, enhance="draft").why)

    def test_fresh_until_the_upscale_changes(self):
        t = self.upscaled()
        job = P.plan_post(self.ep, t, enhance="production")
        self.assertEqual(job.action, "post")
        self.assertEqual((job.width, job.height), (1920, 1088))
        self.assertEqual(job.quality, "master")              # as its upscale was encoded
        self.assertEqual(P.plan_post(self.ep, t, enhance="production",
                                     quality="review").quality, "review")
        self.assertIsNone(T.post_of(t))
        self.finish(t, job)
        self.assertTrue(T.post_of(t)["fresh"])
        self.assertEqual(P.plan_post(self.ep, t, enhance="production").action, "skip")
        # other settings, or --redo: post again
        self.assertEqual(P.plan_post(self.ep, t, enhance="cinematic").action, "post")
        self.assertEqual(P.plan_post(self.ep, t, enhance="production", redo=True).action, "post")
        # a new upscale: the post is stale
        with open(t.paths.up_mp4, "ab") as fh:
            fh.write(b"again")
        self.assertFalse(T.post_of(t)["fresh"])
        # and it goes with the take
        self.assertIn(t.paths.post_mp4, T.stem_files(t.paths.dir, t.paths.stem))

    # -- faces ----------------------------------------------------------------

    def faced(self, sheets=("ada",)) -> T.Take:
        """An upscaled take whose frozen shotlist has Ada and Bo in it (Bo's sheet
        only when named in `sheets`) and a location."""
        t = self.upscaled()
        os.makedirs(os.path.join(self.ep, "refs"), exist_ok=True)
        for sid in sheets:
            with open(os.path.join(self.ep, "refs", f"{sid}.png"), "wb") as fh:
                fh.write(b"png")
        doc = {"subjects": {"ada": {"kind": "character", "sheet": "refs/ada.png"},
                            "bo": {"kind": "character", "sheet": "refs/bo.png"},
                            "kitchen": {"kind": "location", "sheet": "refs/kitchen.png"}},
               "shots": [{"id": "sh010", "subjects": ["ada", "bo"], "prompt": [
                   "subject_definitions:\n<Subject 1> is Ada Lind, defined by <Picture 1> — one "
                   "character. Preserve the exact reference styling: a red coat and a grey scarf.\n"
                   "<Subject 2> is Bo, defined by <Picture 2> — one character. Preserve the exact "
                   "reference styling: a yellow hat.\n<Subject 3> is the location, defined by <Picture 3>.",
                   "summary:\n[reference generation] Ada waves to Bo across the kitchen.",
                   "detailed_description:\nA naturalistic drama on 35mm film, soft window light.\n"
                   "[Shot 1] A wide shot of the kitchen."]}]}
        T.write_json(t.paths.shotlist, doc)
        return T.get_take(self.ep, "final", "sh010", 1)

    def test_faces_plan(self):
        t = self.faced()
        job = P.plan_post(self.ep, t, faces=True)
        self.assertEqual(job.action, "post")
        self.assertEqual([p["subject"] for p in job.face_passes], ["ada"])
        self.assertIn("bo has no sheet", " ".join(job.notes))
        p = job.face_passes[0]
        self.assertEqual((p["name"], p["sheet"]), ("Ada Lind", "refs/ada.png"))
        # the shot's own words, told as a close-up of the one face
        self.assertIn("a red coat and a grey scarf.", p["prompt"])
        self.assertIn("as in this moment: Ada waves to Bo across the kitchen.", p["prompt"])
        self.assertIn("A naturalistic drama on 35mm film", p["prompt"])
        self.assertNotIn("A wide shot", p["prompt"])
        self.assertNotIn("[reference generation]", p["prompt"])
        self.assertEqual(P.settings_of(job)["faces"], {"denoise": 0.4, "subjects": ["ada"]})
        self.assertIn("faces (ada, denoise 0.4)", P.describe(job))
        # its settings are its own: another denoise is another post
        self.finish(t, job)
        self.assertEqual(P.plan_post(self.ep, t, faces=True).action, "skip")
        self.assertEqual(P.plan_post(self.ep, t, faces={"denoise": 0.3}).action, "post")
        # named subjects: only them; one not in the shot is said
        job = P.plan_post(self.ep, t, faces={"subjects": ["ada", "cy"]}, redo=True)
        self.assertEqual([p["subject"] for p in job.face_passes], ["ada"])
        self.assertIn("cy isn't in the shot", job.notes)

    def test_a_clip_marked_for_faces(self):
        """Marked in the cut (R): its post is refined unless faces are turned off for it."""
        from seriesmith import edit as E
        t = self.faced()
        self.assertEqual(P.plan_post(self.ep, t).action, "error")        # unmarked: nothing asked
        E.set_cut_entry(self.ep, "final", "sh010", refine_faces=True)
        self.assertEqual(P.face_marks(self.ep, "final"), {"sh010": True})
        self.assertEqual(P.face_marks(self.ep, "proxy"), {})
        job = P.plan_post(self.ep, t)                                     # faces alone
        self.assertEqual((job.action, [p["subject"] for p in job.face_passes]), ("post", ["ada"]))
        self.assertIn("marked for faces in the cut", job.notes)
        job = P.plan_post(self.ep, t, enhance="draft")                   # beside the clean-up
        self.assertTrue(job.enhance and job.face_passes)
        job = P.plan_post(self.ep, t, enhance="draft", faces=False)      # turned off for this post
        self.assertEqual(job.face_passes, [])
        kw = P.recipe_for(self.ep, "sh010", {"enhance": "draft"}, {})     # the recipe leaves it to the mark
        self.assertNotIn("faces", kw)
        self.assertTrue(P.plan_post(self.ep, t, **kw).face_passes)

    def test_every_shot_by_the_series(self):
        """Series settings' "every shot" (post.master.faces) refines a clip nobody marked;
        a shot's own post.faces is over it, and false at either level turns it off."""
        from seriesmith import edit as E
        t = self.faced()
        self.assertEqual(P.faces_of(self.ep, "final", "sh010"), (None, ""))
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={"faces": True}, shots={}),
                         (True, "every shot (series settings)"))
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={"faces": True},
                                    shots={"sh010": {"faces": False}}), (None, ""))
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={}, shots={"sh010": {"faces": True}}),
                         (True, "its own post.faces"))
        # the clip's own mark (R) is the last word, either way
        E.set_cut_entry(self.ep, "final", "sh010", refine_faces=True)
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={"faces": False},
                                    shots={"sh010": {"faces": False}}),
                         (True, "marked for faces in the cut"))
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={"faces": {"denoise": 0.3}}, shots={}),
                         ({"denoise": 0.3}, "marked for faces in the cut"))   # the series' settings
        E.set_cut_entry(self.ep, "final", "sh010", refine_faces=False)
        self.assertEqual(P.faces_of(self.ep, "final", "sh010", recipe={"faces": True},
                                    shots={"sh010": {"faces": True}}), (None, ""))   # kept out
        E.set_cut_entry(self.ep, "final", "sh010", refine_faces=None)
        p = os.path.join(self.ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["post"] = {"master": {"faces": {"denoise": 0.3}}}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        job = P.plan_post(self.ep, t)                                     # unmarked, refined all the same
        self.assertEqual((job.action, job.faces["denoise"]), ("post", 0.3))
        self.assertIn("every shot (series settings)", job.notes)
        self.assertEqual(P.plan_post(self.ep, t, faces=False).action, "error")   # told outright: off

    def test_the_dialogs_answer_beats_the_mark(self):
        """One take's dialog says faces outright, by the series recipe too: off here
        leaves a marked clip's faces alone (the dialog unmarks it beside)."""
        from seriesmith import edit as E
        self.ready_comfy()
        self.faced()
        p = os.path.join(self.ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["post"] = {"master": {"enhance": "draft"}}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        E.set_cut_entry(self.ep, "final", "sh010", refine_faces=True)
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                              "recipe": True, "faces": False}))
        self.assertEqual(len(out["queued"]), 1)
        self.assertNotIn("faces", out["queued"][0]["what"])
        self.err(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                         "recipe": True, "faces": "yes"}), 400)

    def test_faces_with_no_one_to_refine(self):
        t = self.faced(sheets=())
        job = P.plan_post(self.ep, t, faces=True)
        self.assertEqual(job.action, "error")            # master: plays its upscale
        self.assertIn("nothing to do", job.why)
        job = P.plan_post(self.ep, t, faces=True, enhance="draft")
        self.assertEqual(job.action, "post")
        self.assertEqual(job.face_passes, [])
        self.assertIn("faces left out", " ".join(job.notes))
        self.assertNotIn("faces", P.settings_of(job))

    def test_faces_refusals(self):
        t = self.faced()
        self.assertIn("denoise", P.plan_post(self.ep, t, faces={"denoise": 0.9}).why)
        self.assertIn("not a field", P.plan_post(self.ep, t, faces={"strength": 0.3}).why)
        self.assertIn("subject ids", P.plan_post(self.ep, t, faces={"subjects": "ada"}).why)
        self.assertIn("true, false", P.plan_post(self.ep, t, faces=3).why)
        for off in (None, False, "none", {}):
            self.assertIsNone(P.resolve_faces(off))
        self.assertEqual(P.resolve_faces(True), {"denoise": 0.4})

    def test_faces_graph(self):
        t = self.faced()
        if os.path.isfile(t.paths.h3_wav):
            os.remove(t.paths.h3_wav)
        g = P.post_graph(P.plan_post(self.ep, t, faces=True))
        self.assertEqual(g["pp_video"]["inputs"]["audio_file"], "")     # no _h3.wav: nothing to hold
        self.assertEqual(self.by_class(g, "SeriesmithHoldAudio"), [])
        tr = g[self.by_class(g, "H3FaceTrackCrop")[0]]["inputs"]
        self.assertFalse(tr["identity_track"])                          # one face: no identity needed
        self.assertNotIn("identity_reference", tr)
        self.assertEqual(g["pf0_sheet"], {"class_type": "H3LoadImageFile", "inputs": {
            "project_root": self.ep, "image_file": "refs/ada.png"}})
        self.assertEqual(g["pp_save"]["inputs"]["images"], ["pf0_stitch", 0])
        self.assertEqual(g["pf0_sigmas"]["inputs"]["denoise"], 0.4)
        # the take's sound held: the lips follow it
        with open(t.paths.h3_wav, "wb") as fh:
            fh.write(b"wav")
        g = P.post_graph(P.plan_post(self.ep, t, faces=True))
        self.assertTrue(g["pp_video"]["inputs"]["audio_file"].endswith("_h3.wav"))
        self.assertEqual(g["pf_aenc"]["inputs"]["audio"], ["pp_video", 1])
        self.assertEqual(g["pf0_denoise"]["inputs"]["av_latent"], ["pf0_hold", 0])
        # two characters: a pass each, chained, each found by their sheet
        t = self.faced(sheets=("ada", "bo"))
        g = P.post_graph(P.plan_post(self.ep, t, faces=True, enhance="draft", blur=0.3))
        self.assertEqual(len(self.by_class(g, "H3FaceTrackCrop")), 2)
        for i in (0, 1):
            ins = g[f"pf{i}_track"]["inputs"]
            self.assertTrue(ins["identity_track"])
            self.assertEqual(ins["identity_reference"], [f"pf{i}_sheet", 0])
        self.assertEqual(g["pf1_track"]["inputs"]["images"], ["pf0_stitch", 0])
        self.assertEqual(g["pf1_stitch"]["inputs"]["base_images"], ["pf0_stitch", 0])
        self.assertNotEqual(g["pf0_noise"]["inputs"]["noise_seed"], g["pf1_noise"]["inputs"]["noise_seed"])
        # enhance, then faces, then blur
        self.assertEqual(g["pf0_track"]["inputs"]["images"], g["pf0_stitch"]["inputs"]["base_images"])
        self.assertNotEqual(g["pf0_track"]["inputs"]["images"], ["pp_video", 0])
        self.assertEqual(g["pp_blur"]["inputs"]["images"], ["pf1_stitch", 0])

    def test_faces_portable(self):
        from seriesmith import finishing as F
        from seriesmith.backends import File
        t = self.faced()
        job = P.plan_post(self.ep, t, faces=True)
        pg, _ = F.portable(F.of_post(job, P.post_graph(job)))
        self.assertEqual(pg["pf0_sheet"]["class_type"], "LoadImage")
        img = pg["pf0_sheet"]["inputs"]["image"]
        self.assertIsInstance(img, File)
        self.assertEqual(os.path.normpath(img.path), os.path.normpath(os.path.join(self.ep, "refs", "ada.png")))

    def test_faces_not_ready(self):
        t = self.faced()
        job = P.plan_post(self.ep, t, faces=True)
        info = {c: {"input": {"required": {}}} for c in P.BASE_NODES + P.FACES_CORE_NODES}
        missing = P.not_ready([job], info)
        self.assertTrue(any(P.FACES_PACK in m for m in missing))
        info.update({c: {"input": {"required": {}}} for c in P.FACES_NODES})
        for c, f, names in (("UNETLoader", "unet_name", [P.FACES_UNET]),
                            ("LoraLoaderModelOnly", "lora_name", [P.FACES_LORA]),
                            ("CLIPLoader", "clip_name", [P.FACES_CLIP]),
                            ("VAELoader", "vae_name", [P.FACES_VAE, P.FACES_AUDIO_VAE])):
            info[c] = {"input": {"required": {f: [names]}}}
        info["H3FaceTrackCrop"] = {"input": {"required": {
            "detector": [["bbox\\face_yolov8m.pt", "face_yolov8m.pt", "hand_yolov8s.pt"]]},
            "optional": {"fallback_detector": [["none", "segm\\person_yolov8m-seg.pt"]]}}}
        self.assertEqual(P.not_ready([job], info), [])
        self.assertEqual(job.face_detectors, ("face_yolov8m.pt", "segm\\person_yolov8m-seg.pt"))
        g = P.post_graph(job)
        self.assertEqual((g["pf0_track"]["inputs"]["detector"], g["pf0_track"]["inputs"]["fallback_detector"]),
                         ("face_yolov8m.pt", "segm\\person_yolov8m-seg.pt"))
        info["H3FaceTrackCrop"]["input"]["required"]["detector"] = [["hand_yolov8s.pt"]]
        self.assertTrue(any("face_yolov8m.pt in models/ultralytics" in m for m in P.not_ready([job], info)))
        self.assertEqual(P.face_detectors(["face_yolov8m.pt"], ["none"]), ("face_yolov8m.pt", "none"))

    def test_faces_recipe(self):
        self.assertEqual(P.recipe_for(self.ep, "sh010", {"enhance": "draft", "faces": True}, {})["faces"], True)
        self.assertEqual(P.describe_recipe({"faces": True, "blur": 0.3}), "faces, then motion blur 0.3")
        self.assertEqual(P.describe_recipe({"faces": {"subjects": ["ada"]}}), "faces (ada)")
        self.assertTrue(any("denoise" in m for m in P.check_recipe({"faces": {"denoise": 2}})))
        self.assertEqual(P.check_recipe({"enhance": "production", "faces": True}), [])

    # -- the graph ------------------------------------------------------------

    def test_after_an_upscale_not_made_yet(self):
        t = self.final_take()                      # no upscale at all
        job = P.plan_post(self.ep, t, enhance="production", blur=0.3,
                          after_upscale=(2560, 1440), quality="master")
        self.assertEqual(job.action, "post")
        self.assertEqual((job.width, job.height, job.enhance["chunk"]), (2560, 1440, 33))
        self.assertEqual(P.describe_recipe({"enhance": "production", "blur": 0.3}),
                         "SeedVR2 7b, then motion blur 0.3")

    def test_tiers(self):
        self.assertEqual(P.resolve_enhance("draft")["method"], "pixel")
        e = P.resolve_enhance("production")
        self.assertEqual((e["method"], e["seedvr2_model"], e["chunk"], e["overlap"]),
                         ("seedvr2", U.SEEDVR2_MODELS["7b"], "fit", "fit"))
        # "fit": 61 frames at 1080p, fewer as the frame grows
        self.assertEqual(P.fit_chunk(1920, 1080), 61)
        self.assertEqual(P.fit_chunk(1920, 1088), 61)
        self.assertEqual(P.fit_chunk(2560, 1440), 33)
        self.assertEqual(P.fit_chunk(3840, 2160), 13)
        # overlap "fit": 6 of 16 latent frames, kept in proportion as the chunk shrinks
        self.assertEqual([P.fit_overlap(c) for c in (61, 33, 13, 5, 0)], [6, 3, 2, 1, 6])
        for size, want in (((1920, 1080), (61, 6)), ((2560, 1440), (33, 3)), ((3840, 2160), (13, 2))):
            e = P.resolve_enhance("production")
            P.resolve_fit(e, *size)
            self.assertEqual((e["chunk"], e["overlap"]), want)
        e = P.resolve_enhance({"tier": "production", "overlap": 4})   # a number stays
        P.resolve_fit(e, 2560, 1440)
        self.assertEqual((e["chunk"], e["overlap"]), (33, 4))
        with self.assertRaises(P.PostError):
            P.resolve_enhance({"method": "seedvr2", "overlap": "most"})
        e = P.resolve_enhance({"tier": "production", "seedvr2_model": "3b", "chunk": 0})
        self.assertEqual(e["seedvr2_model"], U.SEEDVR2_MODELS["3b"])
        self.assertNotIn("chunk", e)                          # 0: auto
        e = P.resolve_enhance("cinematic")
        self.assertEqual((e["method"], e["strength"]), ("supir", 0.2))
        self.assertIsNone(P.resolve_enhance("none"))

    def test_pixel_graph(self):
        t = self.upscaled()
        g = P.post_graph(P.plan_post(self.ep, t, enhance="draft"))
        load = g[self.by_class(g, "H3LoadTakeVideo")[0]]["inputs"]
        self.assertTrue(load["video_file"].endswith(".up.mp4"))
        px = g[self.by_class(g, "SeriesmithPixelUpscale")[0]]["inputs"]
        self.assertEqual((px["width"], px["height"]), (1920, 1088))      # 1x: a sharpen
        self.assertTrue(px["frequency_split"])
        save = g["pp_save"]["inputs"]
        self.assertTrue(save["stamp_source"])
        self.assertEqual(save["event"], "seriesmith.post")
        self.assertTrue(save["out_mp4"].endswith(".post.mp4"))
        self.assertTrue(save["sidecar"].endswith(".post.json"))
        self.assertTrue(save["source_mp4"].endswith(".up.mp4"))         # the upscale's audio

    def test_seedvr2_graph_is_the_upscales_chain(self):
        t = self.upscaled()
        g = P.post_graph(P.plan_post(self.ep, t, enhance="production"))
        unet = g[self.by_class(g, "UNETLoader")[0]]["inputs"]
        self.assertEqual(unet["unet_name"], U.SEEDVR2_MODELS["7b"])
        scale = g[self.by_class(g, "ImageScale")[0]]["inputs"]
        self.assertEqual((scale["width"], scale["height"]), (1920, 1088))
        self.assertEqual(g["pp_save"]["inputs"]["images"], ["pp_sv_finish", 0])
        self.assertEqual(g["pp_sv_chunk"]["inputs"]["chunking_mode.frames_per_chunk"], 61)
        g = P.post_graph(P.plan_post(self.ep, t, enhance={"tier": "production", "chunk": 0}))
        self.assertEqual(g["pp_sv_chunk"]["inputs"]["chunking_mode"], "auto")
        # fixed chunks, so a redo splits the shot at the same frames
        g = P.post_graph(P.plan_post(self.ep, t, enhance={"tier": "production", "chunk": 49,
                                                          "overlap": 4}))
        ch = g["pp_sv_chunk"]["inputs"]
        self.assertEqual((ch["chunking_mode"], ch["chunking_mode.frames_per_chunk"],
                          ch["temporal_overlap"]), ("manual", 49, 4))
        self.assertIn("4n+1", P.plan_post(self.ep, t, enhance={"tier": "production",
                                                               "chunk": 48}).why)

    def test_supir_graph(self):
        t = self.upscaled()
        g = P.post_graph(P.plan_post(self.ep, t, enhance={"method": "supir", "strength": 0.15}))
        ks = g["pp_ks"]["inputs"]
        self.assertEqual(ks["denoise"], 0.15)
        self.assertEqual(ks["model"], ["pp_supir", 0])
        # one batch at a time, then joined and given the source's colour back
        self.assertEqual(g["pp_split"]["class_type"], "RebatchImages")
        self.assertEqual(g["pp_join"]["inputs"]["images"], ["pp_dec", 0])
        self.assertEqual(g["pp_finish"]["inputs"]["source"], ["pp_video", 0])
        self.assertEqual(g["pp_patch"]["inputs"]["name"], P.SUPIR_MODEL)

    def test_blur_after_enhance(self):
        t = self.upscaled()
        g = P.post_graph(P.plan_post(self.ep, t, enhance="draft", blur=0.3))
        self.assertEqual(g["pp_blur"]["inputs"]["images"], ["pp_pixels", 0])
        self.assertEqual(g["pp_blur"]["inputs"]["amount"], 0.3)
        self.assertEqual(g["pp_save"]["inputs"]["images"], ["pp_blur", 0])
        g = P.post_graph(P.plan_post(self.ep, t, blur=0.3))               # blur alone
        self.assertEqual(g["pp_blur"]["inputs"]["images"], ["pp_video", 0])

    def test_not_ready(self):
        t = self.upscaled()
        jobs = [P.plan_post(self.ep, t, enhance="cinematic", blur=0.25)]
        info = {c: {"input": {"required": {}}} for c in
                P.BASE_NODES + P.SUPIR_NODES + P.BLUR_NODES}
        info["ModelPatchLoader"] = {"input": {"required": {"name": [["other.safetensors"]]}}}
        info["OpticalFlowLoader"] = {"input": {"required": {"model_name": [[]]}}}
        missing = P.not_ready(jobs, info)
        self.assertTrue(any(P.SUPIR_MODEL in m for m in missing))
        self.assertTrue(any(P.RAFT_FILE in m and P.RAFT_URL in m for m in missing))
        del info["SeriesmithMotionBlur"]
        self.assertTrue(any("SeriesmithMotionBlur" in m for m in P.not_ready(jobs, info)))

    # -- the routes -----------------------------------------------------------

    def ready_comfy(self):
        self.comfy.nodes |= set(P.BASE_NODES) | set(U.PIXEL_NODES) | set(P.BLUR_NODES)
        self.comfy.info["UpscaleModelLoader"] = {"input": {"required": {
            "model_name": [["RealESRGAN_x2.pth"], {}]}}}
        self.comfy.info["OpticalFlowLoader"] = {"input": {"required": {
            "model_name": [[P.RAFT_FILE], {}]}}}

    def set_post(self, recipe):
        p = os.path.join(self.ep, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg["post"] = {"master": recipe}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

    def test_post_route(self):
        self.ready_comfy()
        t = self.upscaled()
        # no recipe and nothing asked: 409
        self.err(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}]}), 409)
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                              "enhance": "draft", "blur": 0.3}))
        self.assertEqual([q["shot"] for q in out["queued"]], ["sh010"])
        self.assertIn(("seriesmith.post", {"ep": self.ep, "shot": "sh010", "take": 1,
                                       "status": "queued"}), self.events)
        self.assertTrue(T.post_of(t)["fresh"])               # the fake saver stamped it
        # the take's view says so
        view = E.post_summary(self.ep, T.get_take(self.ep, "final", "sh010", 1))
        self.assertEqual((view["status"], view["fresh"]), ("ok", True))
        self.assertEqual(view["recipe"]["motion_blur"], 0.3)
        # the same again is skipped; the recipe is used when nothing is asked
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                              "enhance": "draft", "blur": 0.3}))
        self.assertEqual(out["queued"], [])
        self.set_post({"enhance": "draft"})
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}]}))
        self.assertEqual(len(out["queued"]), 1)
        # bad input
        self.err(A.queue_post(self.ctx, {"ep": self.ep, "shots": "sh010"}), 400)
        self.err(A.queue_post(self.ctx, {"ep": self.ep, "shots": ["sh010"], "blur": "x"}), 400)
        # options: the tiers and the recipe
        opts = self.ok(A.get_post_options(self.ctx, {"ep": self.ep}))
        self.assertEqual([x["id"] for x in opts["tiers"]], list(P.TIERS))
        self.assertEqual(opts["tiers"][0]["readiness"]["status"], "ready")    # draft: pixel
        self.assertEqual(opts["blur"]["readiness"]["status"], "ready")
        self.assertEqual(opts["recipe"]["text"], "pixel")
        # delete
        self.ok(A.delete_post(self.ctx, {"ep": self.ep, "shot": "sh010", "take": "1"}))
        self.assertIsNone(T.post_of(t))
        self.err(A.delete_post(self.ctx, {"ep": self.ep, "shot": "sh010", "take": "1"}), 404)

    # -- the recipe -----------------------------------------------------------

    def test_recipe_and_shot_override(self):
        recipe = {"enhance": "production", "motion_blur": 0}
        shots = {"sh010": {"motion_blur": 0.3, "enhance": "none"}}
        self.assertEqual(P.recipe_for(self.ep, "sh020", recipe, shots),
                         {"enhance": "production", "blur": 0})
        self.assertEqual(P.recipe_for(self.ep, "sh010", recipe, shots),
                         {"enhance": "none", "blur": 0.3})
        self.assertEqual(P.check_recipe(recipe), [])
        bad = P.check_recipe({"enhance": "ultra", "motion_blur": 3, "sharpen": True})
        self.assertEqual(len(bad), 3, bad)


try:
    import torch
except Exception:                                         # noqa: BLE001
    torch = None


@unittest.skipIf(torch is None, "the post nodes need torch")
class PostNodesTest(unittest.TestCase):
    def setUp(self):
        # SeriesmithMotionBlur asks comfy.model_management for the device and to load RAFT
        mm = types.ModuleType("comfy.model_management")
        mm.get_torch_device = lambda: torch.device("cpu")
        mm.load_model_gpu = lambda m: None
        comfy = types.ModuleType("comfy")
        comfy.model_management = mm
        self._mods = {k: sys.modules.get(k) for k in ("comfy", "comfy.model_management")}
        sys.modules.update({"comfy": comfy, "comfy.model_management": mm})
        import importlib
        self.N = importlib.import_module("comfy_nodes.finish")

    def tearDown(self):
        for k, v in self._mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_frames_to_batch(self):
        a, b = torch.zeros(2, 4, 6, 3), torch.ones(1, 4, 6, 3)
        out, = self.N.SeriesmithFramesToBatch().join([a, b])
        self.assertEqual(tuple(out.shape), (3, 4, 6, 3))
        self.assertEqual(float(out[2].mean()), 1.0)

    def frames(self, n=4, h=64, w=128):
        x = torch.zeros(n, h, w, 3)
        for i in range(n):
            x[i, :, 40 + 4 * i:44 + 4 * i] = 1.0          # a bar moving right
        return x

    def test_blur_zero_passes_through(self):
        x = self.frames()
        out, = self.N.SeriesmithMotionBlur().blur(x, None, amount=0.0)
        self.assertIs(out, x)

    def test_blur_spreads_along_the_motion(self):
        x = self.frames()

        # forward flow +4 px, backward -4 px: a steady move right
        def model(a, b):
            n, _, h, w = a.shape
            f = torch.zeros(n, 2, h, w)
            f[:, 0] = 4.0 if model.forward else -4.0
            model.forward = not model.forward
            return [f]
        model.forward = True
        out, = self.N.SeriesmithMotionBlur().blur(x, types.SimpleNamespace(model=model), amount=1.0,
                                          samples=9, flow_width=128, max_motion=0.5)
        row = out[1, 32, :, 0]
        sharp = x[1, 32, :, 0]
        self.assertGreater(int((row > 0.01).sum()), int((sharp > 0.01).sum()))   # wider
        self.assertAlmostEqual(float(row.sum()), float(sharp.sum()), delta=0.5)   # same light
        self.assertEqual(tuple(out.shape), tuple(x.shape))


if __name__ == "__main__":
    unittest.main()
