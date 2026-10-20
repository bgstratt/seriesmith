#!/usr/bin/env python3
"""
The presets' sample pictures (seriesmith/presets/img/), made with seriesmith
itself on a scratch episode (the starter series, built into --work):

- look/<id>.jpg: one scene, the same for every look, drawn in that look
  (look.json's text), on the image target (--look-target, default krea2);
- relight/<id>-place.jpg: a base plate (BASE_PLACE, in BASE_LOOK) relit by the
  preset's `place` wording, on the edit target (--edit-target);
- base/place.jpg and base/subject.jpg: those two bases, whole (presets.BASE), which a
  relight of yours is rendered on (seriesmith/preset_pictures.py);
- relight/<id>-subject.jpg: a base figure (BASE_FIGURE: Ada's three-quarter
  view, standing on the sample street in plain daylight) relit by its `subject`
  wording, the street behind her asked into the same light (SUBJECT_SCENE);
- look_builder/<row>-<option>.jpg: the look presets' scene in a plain live-action
  base with only that option set (compose_look), so each tile shows its own part;
- framing/<id>.jpg: the same woman and street (FRAMING_SCENE) at each size, on
  the image target;
- camera/<id>.mp4: a short silent loop of each camera move: a scratch episode
  of one shot per move (`camera: <move>`, the base plate, the woman written
  into the action) rendered by `seriesmith render` on the series' video model
  (--video-target, default its own: MiniMax H3), each take made small.

Each take goes through seriesmith's queue on --backend (default: each
target's own, usually this machine's ComfyUI), as `seriesmith refs` does, and
is kept in the work folder; the sample is the picture made small (SIZE wide,
JPEG). A sample already made is skipped unless --redo.

    python tools/make_preset_samples.py --work C:/tmp/presets
    python tools/make_preset_samples.py --work C:/tmp/presets --only look
    python tools/make_preset_samples.py --work C:/tmp/presets --only relight --edit-target flux_kontext
    python tools/make_preset_samples.py --work C:/tmp/presets --only neon,rain --redo
    python tools/make_preset_samples.py --work C:/tmp/presets --only night:subject --redo --edit-target flux2_klein_edit

Writes seriesmith/presets/img/{look,relight}/*.jpg (commit them).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import presets as PR  # noqa: E402
from seriesmith import refs as R  # noqa: E402

STARTER = os.path.join(ROOT, "examples", "starter")
IMG = os.path.join(PR.HERE, "img")
SIZE = 480
PLATE, FIGURE, FIGURE_VIEW = "location:porch", "subject:ada", "01_threequarter"

# the scene every look is drawn in: a figure in a place, so a look shows on both
LOOK_SCENE = PR.LOOK_SCENE
# what the relights start from: plain, even light, so each preset's change shows
BASE_LOOK = "prestige_35mm"
BASE_PLACE = ("A quiet city street corner: a cafe front with a striped awning and a glass door, a "
              "streetlamp, a wooden bench, a bicycle leaning on a brick wall, wet cobbles, no people, "
              "in soft even late-morning daylight")
# every framing draws her; the size sentence goes first, so it leads
FRAMING_SCENE = ("She is a woman in her thirties with short dark hair and a red wool coat, waiting at a "
                 "tram stop on a city street at dusk, a lit cafe window behind her; she is the only one "
                 "in red")
# every camera move's shot: the base plate, with her written in
MOVE_ACTION = ("A woman in a red wool coat stands by the bench outside the cafe, waiting, and looks "
               "down the street.")
MOVE_SECONDS = 3
# a sample shows the move, so it is made large (the tile still hands over the plain move);
# these say their size themselves, or have none
MOVE_AS_SAID = {"static", "shake_slight", "shake_strong"}
CLIP_WIDTH = 360
BASE_FIGURE = ("A full-body three-quarter view of a woman in her thirties with short dark hair and a "
               "red wool coat, standing relaxed on the pavement of a quiet city street corner, a cafe "
               "front with a striped awning and a streetlamp behind her, a brick wall, wet cobbles, in "
               "soft even late-morning daylight, no other people")
# a figure's wording relights the figure; in a sample the street behind her is
# asked into the same light, or she'd stand lit by neon in a daylit street
SUBJECT_SCENE = PR.SUBJECT_SCENE


def keep_base(src: str, dest: str) -> None:
    """A relight sample's base picture, whole, as the presets ship it."""
    from PIL import Image
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with Image.open(src) as im:
        im.convert("RGB").save(dest, quality=90)


def look_text(pid: str) -> str:
    return next(p["text"] for p in PR._load("look") if p["id"] == pid)


def episode(work: str) -> str:
    """The scratch episode (the starter series), built once."""
    ep = os.path.join(work, "ep01")
    if not os.path.isfile(os.path.join(ep, "shotlist", "shotlist.json")):
        os.makedirs(work, exist_ok=True)
        subprocess.run([sys.executable, "-m", "seriesmith", "build",
                        os.path.join(STARTER, "series.json"), os.path.join(STARTER, "ep01.md"),
                        "-o", ep], check=True, cwd=ROOT)
    if not os.path.isfile(os.path.join(ep, "series.json")):
        # the series config beside the episode, as the starter keeps it
        import shutil
        shutil.copyfile(os.path.join(STARTER, "series.json"), os.path.join(ep, "series.json"))
    return ep


def moves_episode(work: str, presets: list[dict]) -> tuple[str, dict]:
    """The scratch episode of camera moves: one plate-only shot per move, built.
    (its folder, {preset id: shot id})."""
    ep = os.path.join(work, "moves")
    shots = {p["id"]: f"sh{(i + 1) * 10:03d}" for i, p in enumerate(presets)}
    lines = ["= ep02  Camera moves", "", "# sq01  porch", ""]
    for p in presets:
        # the preset's own sample line (camera.json `sample`), else the move made large
        sm = p.get("sample") or {}
        move = sm.get("camera") or (p["move"] if p["id"] in MOVE_AS_SAID else p["move"] + " with large amplitude")
        size = sm.get("size", "wide")       # None: no size line (a POV shot says so in its action)
        lines += [f"## {shots[p['id']]}", *([f"size: {size}"] if size else []),
                  *([f"plate: {sm['location']}"] if sm.get("location") else []), f"dur: {sm.get('dur', MOVE_SECONDS)}",
                  sm.get("action", MOVE_ACTION), f"camera: {move}",
                  "sound: a quiet city street, distant traffic", ""]
    os.makedirs(ep, exist_ok=True)
    # the starter's series in the base look (it is a cartoon), as the plate is drawn
    import json
    with open(os.path.join(STARTER, "series.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("style", {})["look"] = look_text(BASE_LOOK)
    # what the plate shows, with room for the woman the action brings in
    cfg["locations"]["porch"]["description"] = BASE_PLACE.replace(", no people", "")
    # a sample's own place (camera.json `location`): its plate drawn from `plate` (moves_plates)
    for p in presets:
        sm = p.get("sample") or {}
        if sm.get("location"):
            cfg["locations"][sm["location"]] = {"description": sm["plate"],
                                                "plate": f"../refs/_bg/{sm['location']}.png"}
    series = json.dumps(cfg, indent=2)
    script = os.path.join(work, "moves.md")
    text = "\n".join(lines)
    fresh = all(os.path.isfile(f) and open(f, encoding="utf-8").read() == t
                for f, t in ((script, text), (os.path.join(ep, "series.json"), series)))
    if not fresh:
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(os.path.join(ep, "series.json"), "w", encoding="utf-8") as fh:
            fh.write(series)
        subprocess.run([sys.executable, "-m", "seriesmith", "build", os.path.join(ep, "series.json"),
                        script, "-o", ep], check=True, cwd=ROOT)
    return ep, shots


def latest_take(ep: str, shot: str) -> str | None:
    """A shot's newest finished take's mp4."""
    from seriesmith import takes as T
    good = [t for t in T.list_takes(ep, "final", shot) if t.status == "ok" and os.path.isfile(t.paths.mp4)]
    return good[-1].paths.mp4 if good else None


def clip(src: str, dst: str) -> None:
    """A take made a small silent loop: CLIP_WIDTH wide, H.264, no sound."""
    from seriesmith import ff as FF
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, "-an",
                    "-vf", f"scale={CLIP_WIDTH}:-2:flags=lanczos,fps=24,format=yuv420p",
                    "-c:v", "libx264", "-crf", "28", "-preset", "slow", "-movflags", "+faststart", dst],
                   check=True)


def cut(src: str, box: list[float], dst: str) -> str:
    """A 16:9 piece of a picture: `box` its left, top and width as fractions."""
    from PIL import Image
    with Image.open(src) as im:
        w, h = im.size
        x, y, cw = round(box[0] * w), round(box[1] * h), round(box[2] * w)
        im.crop((x, y, x + cw, y + round(cw * 9 / 16))).save(dst)
    return dst


def shrink(src: str, dst: str) -> None:
    from PIL import Image
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((SIZE, SIZE * 4), Image.LANCZOS)
        im.save(dst, "JPEG", quality=84, optimize=True)


class Maker:
    def __init__(self, args, s):
        self.args, self.s = args, s
        self.comfy = J.Comfy(args.comfy, client_id="preset-samples")
        try:
            self.listing = J.model_lister(self.comfy)
        except Exception:                                 # noqa: BLE001  not reachable: no listing
            self.listing = None

    def run(self, req: R.GenRequest, pick: bool = False) -> str | None:
        """One take, waited for; its picture, or None."""
        try:
            done = R.generate_and_wait(self.s, req, self.comfy, timeout=self.args.timeout,
                                       listing=self.listing, cache=R.TG.modelid.temp_cache(),
                                       pick=pick, backend=self.args.backend or None)
        except (R.RefError, R.UnknownRef, RuntimeError) as e:
            print(f"  !! {req.ref}: {e}")
            return None
        return done[0].paths.image if done else None

    def generate(self, ref: str, view: str | None, prompt: str, target: str, pick: bool = False):
        return self.run(R.GenRequest(ref=ref, view=view, prompt=prompt, target=target,
                                     seed=self.args.seed, note="preset sample"), pick)

    def edit(self, ref: str, view: str | None, instruction: str):
        return self.run(R.GenRequest(ref=ref, view=view, prompt=instruction, target=self.args.edit_target,
                                     seed=self.args.seed, note=instruction[:80],
                                     edit={"take": None, "with": [], "wrap": True}))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True, help="the scratch folder (kept: its takes, a rerun's start)")
    ap.add_argument("--only", default="", help="look, relight, or preset ids, a relight's one wording as id:place or id:subject, one kind's id as kind:id (camera:pov) (comma-separated)")
    ap.add_argument("--redo", action="store_true", help="make samples that are already made again")
    ap.add_argument("--look-target", default="krea2", help="the image model the looks are drawn on")
    ap.add_argument("--edit-target", default="flux_kontext", help="the edit model the relights run on")
    ap.add_argument("--video-target", default="", help="the video model the camera moves render on "
                    "(default: the series' own)")
    ap.add_argument("--backend", default="", help="where the takes run (default: each target's own)")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188", help="this machine's ComfyUI")
    ap.add_argument("--seed", type=int, default=20261019, help="one seed for every sample, so they compare")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    # a kind, an id (every kind that has it), or kind:id (that one alone: camera:pov)
    want = lambda kind, pid: not only or kind in only or pid in only or f"{kind}:{pid}" in only   # noqa: E731

    ep = episode(os.path.abspath(args.work))
    s = R.load_series(ep)
    mk = Maker(args, s)
    made = failed = 0

    def keep(src, name):
        nonlocal made, failed
        if src and os.path.isfile(src):
            shrink(src, os.path.join(IMG, name))
            made += 1
            print(f"  -> img/{name}")
        else:
            failed += 1

    for p in PR._load("look"):
        name = PR.image_name("look", p["id"])
        if not want("look", p["id"]) or (not args.redo and PR.image_path(name)):
            continue
        print(f"look {p['id']}")
        keep(mk.generate(PLATE, None, f"{p['text']}. {p.get('scene') or LOOK_SCENE}", args.look_target), name)

    for row in PR._load("look_builder"):
        for o in row["options"]:
            oid = f"{row['id']}-{o['id']}"
            name = PR.image_name("look_builder", oid)
            if not want("look_builder", oid) or (not args.redo and PR.image_path(name)):
                continue
            parts = {"medium": o["id"]} if row["id"] == "medium" else {"medium": "live_action", row["id"]: o["id"]}
            print(f"look builder {oid}")
            keep(mk.generate(PLATE, None, f"{PR.compose_look(parts)}. {LOOK_SCENE}", args.look_target), name)

    relights = [p for p in PR._load("relight") if want("relight", p["id"])
                or any(o.startswith(p["id"] + ":") for o in only)]
    todo = [(p, w) for p in relights for w in ("place", "subject")
            if p.get(w) and (not only or "relight" in only or p["id"] in only or f"{p['id']}:{w}" in only)
            and (args.redo or not PR.image_path(PR.image_name("relight", p["id"], w)))]
    if todo:
        base = look_text(BASE_LOOK)
        # each base is also kept as presets.BASE: what a relight of yours renders on
        if any(w == "place" for _, w in todo):
            print("base plate")
            got = mk.generate(PLATE, None, f"{base}. {BASE_PLACE}", args.look_target, pick=True)
            if not got:
                return 1
            keep_base(got, PR.BASE["place"])
        if any(w == "subject" for _, w in todo):
            print("base figure")
            got = mk.generate(FIGURE, FIGURE_VIEW, f"{base}. {BASE_FIGURE}", args.look_target, pick=True)
            if not got:
                return 1
            keep_base(got, PR.BASE["subject"])
        for p, w in todo:
            print(f"relight {p['id']} ({w})")
            ref, view = (PLATE, None) if w == "place" else (FIGURE, FIGURE_VIEW)
            text = p[w] if w == "place" else p[w].rstrip(".") + SUBJECT_SCENE
            keep(mk.edit(ref, view, text), PR.image_name("relight", p["id"], w))

    framings = PR._load("framing")
    renders = {}                                  # a framing's render, for one cut from it
    for p in sorted(framings, key=lambda p: "crop" in p):
        name = PR.image_name("framing", p["id"])
        if not want("framing", p["id"]) or (not args.redo and PR.image_path(name)):
            continue
        print(f"framing {p['id']}")
        if "crop" in p:
            # too tight for the image model to frame: cut from another framing's render
            src = renders.get(p["crop"]["of"]) or mk.generate(
                PLATE, None, f"{look_text(BASE_LOOK)}. "
                f"{next(q['prompt'] for q in framings if q['id'] == p['crop']['of'])}. {FRAMING_SCENE}",
                args.look_target)
            keep(cut(src, p["crop"]["box"], os.path.join(os.path.dirname(ep), f"{p['id']}.png")) if src else None,
                 name)
            continue
        # a POV says what she sees, not her (`scene`: false leaves the shared scene out)
        scene = f" {FRAMING_SCENE}" if p.get("scene", True) else ""
        renders[p["id"]] = mk.generate(PLATE, None, f"{look_text(BASE_LOOK)}. {p['prompt']}.{scene}",
                                       args.look_target)
        keep(renders[p["id"]], name)

    moves = [p for p in PR._load("camera") if want("camera", p["id"])
             and (args.redo or not PR.image_path(PR.image_name("camera", p["id"])))]
    if moves:
        if not os.path.isfile(os.path.join(os.path.dirname(ep), "refs", "_bg", "porch.png")):
            print("base plate")
            if not mk.generate(PLATE, None, f"{look_text(BASE_LOOK)}. {BASE_PLACE}", args.look_target, pick=True):
                return 1
        mep, shots = moves_episode(os.path.dirname(ep), PR._load("camera"))
        for p in moves:
            sm = p.get("sample") or {}
            loc = sm.get("location")
            if loc and not os.path.isfile(os.path.join(os.path.dirname(ep), "refs", "_bg", f"{loc}.png")):
                print(f"plate {loc}")
                if not Maker(args, R.load_series(mep)).generate(
                        f"location:{loc}", None, f"{look_text(BASE_LOOK)}. {sm['plate']}", args.look_target, pick=True):
                    return 1
        only_shots = ",".join(shots[p["id"]] for p in moves)
        cmd = [sys.executable, "-m", "seriesmith", "render", mep, "--only", only_shots]
        if args.redo:
            cmd.append("--redo")
        if args.video_target:
            cmd += ["--target", args.video_target]
        if args.backend:
            cmd += ["--backend", args.backend]
        print(f"camera moves: rendering {len(moves)} shot(s)")
        subprocess.run(cmd, cwd=ROOT)
        for p in moves:
            src = latest_take(mep, shots[p["id"]])
            name = PR.image_name("camera", p["id"])
            if src:
                clip(src, os.path.join(IMG, name))
                made += 1
                print(f"  -> img/{name}")
            else:
                failed += 1
                print(f"  !! {p['id']}: no take")

    print(f"\n  {made} sample(s) made{f', {failed} failed' if failed else ''}: {IMG}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
