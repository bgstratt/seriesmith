"""
What every Comfy Router video model is sent, pinned byte for byte: the
kitchen_sink episode's shots retargeted to each one (as the editor's "render on"
does), planned and turned into the provider's request (router_call), offline:
nothing is sent anywhere. The request carries everything that model takes
differently: the prompt as its writer words it (a model with no sound acts the
lines out instead of quoting them), cut to its longest prompt (max_chars) with
the pictures' mentions kept, the pictures and how they go (references, frames,
Seedance's virtual library), length, size or ratio, seed and sound, and a
Seedance draft's final.

    python tests/test_router_golden.py --update     # after an intended change

then review the diff of tests/golden/router_calls/ and say why in the commit.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402

GOLDEN = os.path.join(HERE, "golden", "router_calls")
# one subject, generated sound / three, cloned voices / three, dubbed / none
# (a plate) / two, cloned / one with both keyframes on disk (frames mode)
SHOTS = ("sh010", "sh020", "sh110", "sh140", "sh210", "sh150")
KEYFRAMED = "sh150"
# a prompt past every model's max_chars but Wan 2.7's: the cut (router_video.fit)
# drops sentences from the start and keeps what happens, the line and the sound
LONG = ("Style: live-action, warm tungsten light, 35mm film grain. "
        + " ".join(f"The kitchen's detail {i}: a dented copper pot, a chipped blue tile, "
                   f"a calendar from a year nobody remembers on the wall." for i in range(28))
        + " Ada sets the kettle down hard and turns to Bo. ADA says: \"You know that one "
          "whistles.\" The kettle starts to whistle. Sound: the kettle's rising whistle, "
          "rain on the window, no music.")


def router_targets() -> list[str]:
    """Every shipped Router video model, drafts too."""
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "seriesmith", "targets", "video", "*",
                                           "target.json"))):
        with open(f, encoding="utf-8") as fh:
            spec = json.load(fh)
        if spec.get("code") == "builtin:router_video":
            out.append(spec["id"])
    return out


def plain(value, root: str):
    """The request as JSON: a File as its episode path and how it goes."""
    if isinstance(value, File):
        p = os.path.relpath(value.path, root).replace(os.sep, "/")
        return {"file": p, **({"via": value.via} if getattr(value, "via", None) else {})}
    if isinstance(value, dict):
        return {k: plain(v, root) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v, root) for v in value]
    return value


def capture(root: str, tid: str) -> dict:
    """{case: what planning and router_call made of it, or the error said}."""
    target = TG.load_target(tid, "video")
    out = {}
    cases = [(sid, None) for sid in SHOTS]
    cases += [("sh020", "long"), (KEYFRAMED, "long")]
    if (target.spec.get("router") or {}).get("draft"):
        cases.append(("sh010", {"task": "draft-task-1", "take": 2}))
    for sid, extra in cases:
        draft = extra if isinstance(extra, dict) else None
        key = sid + (" from its draft" if draft else " with a long prompt" if extra else "")
        doc, i = J.find_shot(root, "final", sid)
        try:
            kw = {"from_draft": {sid: draft}} if draft else {"prompt": LONG} if extra else {}
            req = J.RenderRequest(sid, target=tid, **kw)
            job = J.plan_job(root, "final", doc, i, req, {})
            t = J.job_target(job)
            model, args = t.module.router_call(t, job)
            out[key] = {"model": model, "arguments": plain(args, root),
                        "frames": job.frames, "size": [job.width, job.height],
                        "notes": list(job.notes or [])}
        except Exception as e:                           # noqa: BLE001  an answer too
            out[key] = {"error": f"{type(e).__name__}: {e}"}
    return out


def capture_all() -> dict[str, str]:
    with tempfile.TemporaryDirectory() as root:
        build_episode(root)
        # a retargeted shot is compiled again from the episode's series config
        shutil.copy(os.path.join(FIXTURE, "series.json"), root)
        for end in ("first", "last"):                    # one shot with its keyframes made
            p = os.path.join(root, "refs", "shots", KEYFRAMED, f"{end}.png")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()
        return {tid: json.dumps(capture(root, tid), indent=1, sort_keys=True,
                                ensure_ascii=False) + "\n"
                for tid in router_targets()}


class RouterGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.got = capture_all()

    def test_every_router_model_is_pinned(self):
        self.assertGreaterEqual(len(self.got), 15)
        for tid in self.got:
            self.assertTrue(os.path.isfile(os.path.join(GOLDEN, tid + ".json")),
                            f"no golden for {tid}: python tests/test_router_golden.py --update")

    def test_each_request_is_as_pinned(self):
        for tid, text in self.got.items():
            with self.subTest(target=tid):
                with open(os.path.join(GOLDEN, tid + ".json"), encoding="utf-8") as fh:
                    self.assertEqual(text, fh.read().replace("\r\n", "\n"))


if __name__ == "__main__":
    if "--update" in sys.argv:
        os.makedirs(GOLDEN, exist_ok=True)
        for tid, text in capture_all().items():
            with open(os.path.join(GOLDEN, tid + ".json"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print("wrote", tid)
    else:
        unittest.main(verbosity=2)
