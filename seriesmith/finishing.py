"""
Upscales and posts through seriesmith's queue, on any backend.

upscale.py and post.py build their graphs as h3pipe did: nodes that read the
episode folder (H3LoadTakeLatent, H3LoadTakeVideo, H3LoadTakeFrame, the take's
H3ShotListLoader, the upscale's hold of the previous upscale) and H3SaveUpscale,
which writes beside the take and closes its .up.json / .post.json. When the
queue's job starts, `portable` turns that graph into one any backend can run:
each file goes up as an upload, and SeriesmithSaveUpscale (comfy_nodes/upscale.py)
reports what it made; `collect` puts those files where H3SaveUpscale would have
and merges its record into the take's.

Deciding at the start, not at queueing, is what h3pipe's run-time nodes did:
a continuity shot's upscale starts from the previous shot's upscaled last
frame if that upscale has run by then (it is queued ahead), else from the
take's own keyframe; a `continuous: latent` take's upscale holds the previous
upscale's latent if it is there, else nothing; a post stamps the upscale it
was made from as it is when the post starts.
"""
from __future__ import annotations

import copy
import json
import os
import re
import uuid
from dataclasses import dataclass, field

from seriesmith import jobs as J
from seriesmith import takes as T
from seriesmith.backends import File

SAVER = "SeriesmithSaveUpscale"
H3_SAVER = "H3SaveUpscale"
RECORD_SUFFIX = ".record.json"
EVENTS = {"upscale": "h3pipe.upscale", "post": "h3pipe.post"}


@dataclass
class Finish:
    """One upscale or post: its graph as upscale.py / post.py built it, and
    where its files go."""
    kind: str                     # "upscale" | "post"
    root: str
    take: T.Take
    graph: dict
    sidecar: str                  # the .up.json / .post.json it closes
    out_mp4: str
    last: str | None = None       # the last frame kept (an upscale)
    latent: str | None = None     # the re-sampled latent kept (an upscale)
    notes: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.take.shot} t{self.take.take:02d}"


def of_upscale(up, graph: dict) -> Finish:
    """An UpscaleJob (upscale.py) and the graph graph_of built for it."""
    p = up.take.paths
    save = graph.get("up_save", {}).get("inputs", {})
    return Finish("upscale", up.root, up.take, graph, p.up_sidecar, p.up_mp4,
                  last=p.up_last if save.get("last_frame") else None,
                  latent=p.up_latent if save.get("latent_file") else None)


def of_post(job, graph: dict) -> Finish:
    """A PostJob (post.py) and its post_graph."""
    p = job.take.paths
    return Finish("post", job.root, job.take, graph, p.post_sidecar, p.post_mp4)


def _abs(root: str, p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(os.path.normpath(root), p)


def take_input_files(take: T.Take, root: str) -> dict[str, str]:
    """The take's staged inputs ({name in ComfyUI's input folder: local file}):
    each name in its record's `inputs` is <sha1[:20]>.<ext> of a file its
    `refs` list."""
    sc = take.sidecar or {}
    by_sha = {}
    for r in sc.get("refs") or []:
        if r.get("sha1") and r.get("path"):
            by_sha[str(r["sha1"])[:20]] = _abs(root, r["path"])
    out = {}
    for name in (sc.get("inputs") or {}).values():
        if not isinstance(name, str):
            continue
        p = by_sha.get(os.path.splitext(os.path.basename(name))[0])
        if p and os.path.isfile(p):
            out[name] = p
    return out


def run_name(fin: Finish) -> str:
    ep = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(os.path.normpath(fin.root)))
    return f"{ep}_{fin.take.pass_}_{fin.take.paths.stem}_{fin.kind}_{uuid.uuid4().hex[:8]}"


def _relink(g: dict, old: list, new) -> None:
    """Every input linked to `old` takes `new` instead (None: the input goes)."""
    for v in g.values():
        ins = v.get("inputs") or {}
        for k, val in list(ins.items()):
            if val == old:
                if new is None:
                    del ins[k]
                else:
                    ins[k] = new


def portable(fin: Finish) -> tuple[dict, dict]:
    """The finish's graph for any backend, worked out now (see the module).
    Returns (the graph, fields for the record when it succeeds: a post's
    source stamp). Notes on what was decided go to fin.notes. J.NotPortable
    when something still reads the episode folder."""
    from seriesmith import shotnodes as SN

    g = copy.deepcopy(fin.graph)
    files = take_input_files(fin.take, fin.root)
    extra: dict = {}
    for nid, v in list(g.items()):
        ct, ins = v["class_type"], v.get("inputs") or {}
        root = ins.get("project_root") or fin.root
        if ct == "H3LoadTakeLatent":
            v["class_type"] = "SeriesmithLoadTakeLatent"
            v["inputs"] = {"latent": File(_abs(root, ins["latent_file"]))}
        elif ct == "H3LoadTakeVideo":
            audio = ins.get("audio_file") or ""
            v["class_type"] = "SeriesmithLoadTakeVideo"
            v["inputs"] = {"video": File(_abs(root, ins["video_file"])),
                           "audio": File(_abs(root, audio)) if audio else ""}
        elif ct == "H3LoadTakeFrame":
            path = _abs(root, ins["image_file"])
            if os.path.isfile(path):
                fin.notes.append(f"starts from {os.path.basename(path)}")
            else:
                path = files.get(ins.get("fallback") or "")
                if not path:
                    raise J.NotPortable(f"{ins['image_file']} isn't there, and the take's "
                                        f"keyframe can't be found to start from instead")
                fin.notes.append("the previous upscale's last frame isn't there: starts from "
                                 "the take's keyframe")
            v["class_type"], v["inputs"] = "LoadImage", {"image": File(path)}
        elif ct == "H3ShotListLoader":
            doc = T.read_json(_abs(root, ins["shotlist_file"]))
            shot = doc["shots"][int(ins.get("index") or 0)]
            names = []
            for r in J.ref_slots(doc, shot):
                p = r.get("path")
                if p and p not in names and os.path.isfile(_abs(fin.root, p)):
                    names.append(p)
            if len(names) > SN.MAX_FILES:
                raise J.NotPortable(f"{fin.label} needs {len(names)} files; the loader "
                                    f"takes {SN.MAX_FILES}")
            new = {k: val for k, val in ins.items() if k not in ("project_root", "shotlist_file")}
            new["shotlist"] = json.dumps(doc, ensure_ascii=False)
            new["files"] = json.dumps(names, ensure_ascii=False)
            for i, rel in enumerate(names):
                new[SN.file_input(i)] = File(_abs(fin.root, rel))
            v["class_type"], v["inputs"] = J.PORTABLE_LOADER, new
        elif ct == "H3ChainLatent" and "previous_latent" in ins:
            # the upscale of a continuous: latent take, held on the previous upscale
            prev = _abs(root, ins["previous_latent"])
            if os.path.isfile(prev):
                src = {"shot": None, "pass": ins.get("pass_"), "upscale": True}
                m = re.match(r"(.+)_t(\d+)\.up\.latent\.safetensors$", os.path.basename(prev))
                if m:
                    src.update(shot=m.group(1), take=int(m.group(2)))
                v["class_type"] = "SeriesmithChainLatent"
                v["inputs"] = {"latent": ins["latent"], "overlap": ins["overlap"],
                               "hold_audio": False, "fps": ins.get("fps", 24.0),
                               "previous": File(prev), "previous_video": "",
                               "source": json.dumps(src)}
                fin.notes.append(f"holds {os.path.basename(prev)}")
            else:
                _relink(g, [nid, 0], ins["latent"])
                _relink(g, [nid, 1], None)
                del g[nid]
                fin.notes.append("the previous upscale kept no latent: the head isn't held")
        elif ct == "H3ChainTrim":
            v["class_type"] = "SeriesmithChainTrim"
        elif ct == H3_SAVER:
            source = _abs(root, ins["source_mp4"])
            new = {"images": ins["images"], "source": File(source), "run": run_name(fin),
                   "name": os.path.basename(fin.out_mp4)[:-len(".mp4")],
                   "fps": ins.get("fps", 24.0), "encoder": ins.get("encoder", "auto")}
            for k in ("width", "height", "fit", "quality", "chain_hold"):
                if k in ins:
                    new[k] = ins[k]
            if ins.get("last_frame"):
                new["last_frame"] = True
            if ins.get("latent") is not None and ins.get("latent_file"):
                new["latent"] = ins["latent"]
            if ins.get("stamp_source"):
                extra.update(T.source_stamp(source))
            v["class_type"], v["inputs"] = SAVER, new
    J.files_as_uploads(g, files)
    from seriesmith import render as RD
    left = RD.episode_bound(g)
    if left:
        raise J.NotPortable(f"{fin.label}'s {fin.kind} still reads the episode folder: "
                            + ", ".join(left))
    return g, extra


def mark_failed(fin: Finish, why: str) -> None:
    T.update_sidecar(fin.sidecar, status="failed", finished=T.now(), save_notes=why)


def collect(fin: Finish, run, saver: str, status: str, extra: dict | None = None) -> str:
    """After the run ended with `status`: the saver's files where H3SaveUpscale
    wrote them (the take's .up.mp4, .up_last.png, .up.latent.safetensors, or
    .post.mp4) and its record merged into the .up.json / .post.json. Returns
    the finish's status ("ok", "failed")."""
    if status != "succeeded":
        mark_failed(fin, run.error or f"the job ended {status}")
        return "failed"
    record, got = None, []
    for out in run.outputs():
        if out.node != saver:
            continue
        n = out.name
        if n.endswith(RECORD_SUFFIX):
            tmp = os.path.join(fin.take.paths.dir, f".{n}.part")
            try:
                record = T.read_json(out.save(tmp))
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            continue
        dst = (fin.last if n.endswith("_last.png") else
               fin.latent if n.endswith(".latent.safetensors") else
               fin.out_mp4 if n.endswith(".mp4") else None)
        if not dst:
            continue
        part = dst + ".part"
        out.save(part)
        os.replace(part, dst)
        got.append(n)
    if not isinstance(record, dict):
        mark_failed(fin, "the job finished but its saver reported no record "
                         f"(got {', '.join(got) or 'nothing'})")
        return "failed"
    fields = dict(record)
    ok = fields.get("status") == "ok" and os.path.isfile(fin.out_mp4)
    if fields.get("status") == "ok" and not ok:
        fields.update(status="failed",
                      save_notes=f"{fields.get('save_notes', '')}; the mp4 didn't come back")
    fields["mp4"] = os.path.basename(fin.out_mp4) if ok else None
    if ok and extra:
        fields.update(extra)
    if fin.notes:
        fields["save_notes"] = "; ".join([fields.get("save_notes") or "", *fin.notes]).strip("; ")
    T.update_sidecar(fin.sidecar, **fields)
    return fields["status"]
