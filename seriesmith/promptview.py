"""
promptview -- what the Prompt & mapping panel shows: for one model and one shot, the parts a
template has to work with, the shotlist entry, and the prompt and request as they would go, with
the templates being edited in place of the saved ones (docs/DESIGN.md, section 9).

It goes the way a render goes (targets.trying, jobs.retarget, jobs.plan_job, the model's own
router_call), so what it shows is what is sent, not a second idea of it. Nothing is uploaded,
written or paid for. Stdlib only.
"""
from __future__ import annotations

import copy
import os

from seriesmith import jobs as J
from seriesmith import takes as T
from seriesmith import targets as TG
from seriesmith.core import paths as P
from seriesmith.targets import prompt_template as TP

IMAGE_BASE = "nano_banana_pro"            # plans a ref as a hosted edit model does
TEMPLATE = "recipe.prompt_template"
REQUEST = "recipe.prompt_request"


class PreviewError(ValueError):
    """Nothing to show: no build, no such shot."""


def plain(v):
    """A request as JSON: each picture as its local path, nothing uploaded."""
    from seriesmith.backends import File
    if isinstance(v, File):
        return {"file": v.path, **({"via": v.via} if v.via else {})}
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def editable(t: "TG.Target") -> bool:
    """Whether a model's prompt goes through a template: its writer gives parts. One with a
    writer of its own (H3's fields, the reference-sheet LTX-2s) is shown, not edited."""
    return t.supports("prompt_parts")


def _templates(t: "TG.Target") -> dict:
    """The templates in force on `t`: its own, else the ones its prompts get by default."""
    return {"template": TP.shot_template(t) or (TP.profile("prose")["template"] if editable(t) else ""),
            "request": TP.request_template(t)}


def _own(t: "TG.Target") -> dict:
    """What `t` goes back to: for a model it's shipped or added with, as it stands without the
    show's changes; a show's own model has them in its target.json, so its profile's templates
    and its mapping as it stands."""
    before = t.before_overrides or t
    block = TG.hosted_block(before.spec)
    mapping = {"inputs": block.get("inputs") or {}, "arguments": block.get("arguments") or {}}
    if TG.scope_of(t.folder) != "show":
        return {**_templates(before), **mapping}
    bare = copy.copy(t)
    bare.recipe = {k: v for k, v in t.recipe.items() if k not in ("prompt_template", "prompt_request")}
    return {**_templates(bare), **mapping}


def _pick_shot(root: str, pass_: str, want: str | None) -> tuple[dict, int]:
    try:
        doc = J.load_shotlist(root, pass_)
    except FileNotFoundError:
        raise PreviewError("this episode has no build yet") from None
    if want:
        try:
            return J.find_shot(root, pass_, want)
        except (KeyError, ValueError, FileNotFoundError):
            raise PreviewError(f"no shot {want} in this episode") from None
    shots = doc.get("shots") or []
    if not shots:
        raise PreviewError("this episode has no shots")
    # a shot with someone in it shows the most
    return doc, next((i for i, s in enumerate(shots) if s.get("subjects")), 0)


def _shot_ir(root: str, shot_id: str):
    """(shot, its sequence, the series config) from the build's own story."""
    story, cfg = J.episode_story(root)
    for sq in story.sequences:
        for s in sq.shots:
            if s.id == shot_id:
                return s, sq, cfg
    raise PreviewError(f"{shot_id} is not in shots.json (rebuild the episode)")


def _described(known: dict, values: dict) -> list[dict]:
    return [{"name": n, "about": about, "value": str(values.get(n) or "")} for n, about in known.items()]


def takes_on(root: str, target_id: str) -> int:
    """How many of this episode's takes were made on the model: what a change to its prompt
    would mark stale."""
    n = 0
    for pass_ in T.PASSES:
        try:
            docs = J.load_shotlists(root, pass_)
        except FileNotFoundError:
            continue
        for doc in docs:
            built = doc.get("target")
            for s in doc.get("shots") or []:
                n += sum(1 for k in T.list_takes(root, pass_, s["id"])
                         if k.usable and ((k.sidecar or {}).get("target") or built) == target_id)
    return n


VIDEO_ROLES = {
    "prompt": "The prompt", "negative": "What to avoid", "duration": "The length",
    "resolution": "The size", "ratio": "The shape", "seed": "The seed", "audio": "The sound",
    "references": "The reference pictures", "first": "The first frame", "last": "The last frame",
    "voices": "The voices", "mode": "Which kind of call", "storyboard": "A multishot's storyboard",
}
IMAGE_ROLES = {
    "prompt": "The prompt", "negative": "What to avoid", "images": "The pictures",
    "ratio": "The shape", "resolution": "The size (1K, 2K)", "size": "The size (WxH)",
    "width": "The width", "height": "The height", "seed": "The seed",
}
NOT_A_FIELD = ("via",)                    # how pictures go in: no field of the request


def where(spec) -> str:
    """The request field a value goes in, from where its target.json says."""
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, dict):
        return ""
    if spec.get("fields"):
        return ", ".join(spec["fields"])
    return str(spec.get("list") or spec.get("name") or spec.get("field") or spec.get("switch") or "")


def _at(args, path: str):
    """What the request has at a dotted path (None: nothing)."""
    at = args
    for name in path.split("."):
        if isinstance(at, list) and name.isdigit() and int(name) < len(at):
            at = at[int(name)]
        elif isinstance(at, dict) and name in at:
            at = at[name]
        else:
            return None
    return at


def rows(t: "TG.Target", args: dict | None) -> list[dict]:
    """One per value a hosted model can take: what it is, where it goes, what it comes to here."""
    inputs = TG.hosted_block(t.spec).get("inputs") or {}
    known = IMAGE_ROLES if t.kind == "image" else VIDEO_ROLES
    out = []
    for role in list(known) + [k for k in inputs if k not in known and k not in NOT_A_FIELD]:
        spec = inputs.get(role)
        field = where(spec)
        now = None
        if field and args is not None:
            now = _at(args, field.split(", ")[0])
        out.append({"role": role, "what": known.get(role, role), "spec": spec, "field": field, "now": now})
    return out


def unfilled(t: "TG.Target", required) -> list[str]:
    """What the model's schema requires that nothing goes in: no value is mapped to it, and it
    isn't one of the arguments sent as they are."""
    block = TG.hosted_block(t.spec)
    placed = [p.strip() for spec in (block.get("inputs") or {}).values() for p in where(spec).split(",") if p.strip()]
    placed += list(block.get("arguments") or {})
    return sorted(f for f in (required or [])
                  if not any(p == f or p.startswith(f + ".") for p in placed))


def unfilled_after(t: "TG.Target", fields: dict, required) -> list[str]:
    """unfilled, once `fields` are saved."""
    if not required:
        return []
    return unfilled(TG._with_fields(t.before_overrides or t, {k: v for k, v in fields.items() if k.startswith("router.")}), required)


def _first_frame_on_disk(root: str, t: "TG.Target", shot_id: str) -> bool:
    path = (t.recipe or {}).get("keyframe_path")
    if not path:
        return False
    return os.path.isfile(os.path.join(root, path.format(shot=P.safe_id(shot_id), end="first")))


def samples(root: str, t: "TG.Target", doc: dict) -> dict:
    """A shot of each kind to try a model on, the first of each: what a mapping tends to get
    wrong shows on one of these."""
    built = {s["id"] for s in doc.get("shots") or []}
    story, _ = J.episode_story(root)
    out: dict[str, str] = {}
    for s in story.shots():
        if s.id not in built:
            continue
        kinds = []
        lines = list(s.dialogue)
        if any(not d.mode for d in lines):
            kinds.append("dialogue")
        if any(d.mode for d in lines):
            kinds.append("voiceover")
        if not lines:
            kinds.append("silent")
        if len(s.cast) + len([p for p in s.props if p not in s.cast]) > 1:
            kinds.append("several")
        kinds.append("first_frame" if _first_frame_on_disk(root, t, s.id) else "no_first_frame")
        for k in kinds:
            out.setdefault(k, s.id)
    return out


def _draft_fields(asked: dict, problems: dict, inputs, arguments) -> dict:
    fields = {f: asked[k] for k, f in (("template", TEMPLATE), ("request", REQUEST))
              if asked[k] is not None and not problems[k]}
    for role, spec in (inputs or {}).items():
        fields[TG.SHOW_FIELD_PREFIX + str(role)] = spec
    if arguments is not None:
        fields["router.arguments"] = arguments
    return fields


def preview(root: str, target_id: str, pass_: str = "proxy", shot: str | None = None,
            template: str | None = None, request: str | None = None, spec: dict | None = None,
            count: bool = False, inputs: dict | None = None, arguments: dict | None = None,
            required=None, ref: str | None = None, view: str | None = None) -> dict:
    """The panel's whole view of `target_id` on `shot` (default: the first with someone in it),
    or on `ref` for an image model. `template`, `request`, `inputs` and `arguments`, when given,
    stand in for the saved ones ("" is the default template; an input's null sends none); `spec`
    is a target.json not saved yet (the Add wizard). A wrong template is reported in `problems`,
    and the rest is shown without it."""
    known = {"template": list(TP.PARTS), "request": list(TP.REQUEST_PARTS)}
    asked = {"template": template, "request": request}
    problems = {k: TP.problems(v, known[k]) if v else [] for k, v in asked.items()}
    fields = _draft_fields(asked, problems, inputs, arguments)
    changed = False
    if spec is None:
        # as saved, before the panel's own go over it
        saved = TG.load_target(target_id, root=root)
        changed = bool(TP.signature(saved)) and (TG.scope_of(saved.folder) == "show"
                                                 or bool(saved.show_fields))
    kind = spec.get("kind") if spec else saved.kind
    if kind == "image":
        return _preview_image(root, target_id, fields, spec, problems, changed, ref, view, required)
    if kind != "video":
        raise PreviewError(f"{target_id} is a {kind} model: its prompts aren't templated yet")

    doc, index = _pick_shot(root, pass_, shot)
    built = doc["shots"][index]
    sid = built["id"]
    with TG.trying(target_id, fields, spec):
        t = TG.load_target(target_id, "video", root=root)
        out = {"ok": True, "id": t.id, "kind": t.kind, "label": t.label, "scope": TG.scope_of(t.folder),
               "hosted": TG.is_hosted(t.spec), "shot": sid, "pass": pass_, "editable": editable(t),
               "problems": problems, "changed": changed, "shipped": _own(t), "request_parts": []}
        out.update(_templates(t))
        if count:
            out["takes_on_model"] = takes_on(root, t.id)
            out["samples"] = samples(root, t, doc)
        ir_shot, seq, cfg = _shot_ir(root, sid)
        values = t.module.prompt_parts(t, ir_shot, seq, cfg) if editable(t) else {}
        out["parts"] = _described(TP.PARTS, values) if editable(t) else []
        _mapping(t, out, None, required)
        try:
            fresh, entry = J.retarget(root, pass_, doc, built, t.id)
        except Exception as e:                            # noqa: BLE001  a shot this model can't take
            out.update(ok=False, why=str(e))
            return out
        fresh = {k: v for k, v in fresh.items() if k != J.BEHIND}
        overrides = T.load_overrides(root)
        if t.id != J.shotlist_target(doc).id:
            # as a retarget renders: a prompt written for another model isn't used
            overrides = _without_prompt(overrides, sid)
        job = J.plan_job(root, pass_, fresh, fresh["shots"].index(entry),
                         J.RenderRequest(sid, target=t.id, redo=True), overrides)
        if job.action == "error":
            out.update(ok=False, why=job.error)
            return out
        frozen = J.frozen_shotlist(job)["shots"][0]
        out["entry"] = frozen
        out["prompt"] = J._prompt_text(frozen.get("prompt") or job.prompt)
        out["overridden"] = "prompt" in job.overridden
        out["sent"] = out["prompt"]
        if out["hosted"]:
            _request(t, job, out)
            _mapping(t, out, out.get("arguments"), required)
    return out


def _mapping(t: "TG.Target", out: dict, args, required) -> None:
    if not TG.is_hosted(t.spec):
        return
    block = TG.hosted_block(t.spec)
    out.update(rows=rows(t, args), inputs=block.get("inputs") or {},
               fixed_arguments=block.get("arguments") or {},
               **({"schema": {"available": True, **block["schema"]}} if block.get("schema") else {}))
    if required is None and block.get("schema"):
        required = block["schema"].get("required")     # read when it was added
    if required is not None:
        out["unfilled"] = unfilled(t, required)


def _preview_image(root, target_id, fields, spec, problems, changed, ref_id, view, required) -> dict:
    """An image model on one ref: its prompt and, hosted, its request. A ref's words come from the
    series config (targets/image/common.py), so only what's around them is a template here."""
    from seriesmith import refs as R
    s = R.load_series(root)
    all_refs = R.series_refs(s)
    if ref_id:
        try:
            ref = R.find_ref(s, ref_id)
        except Exception:                                 # noqa: BLE001  an unknown id
            raise PreviewError(f"no ref {ref_id} in this episode") from None
    else:
        ref = next((r for r in all_refs if r.kind == "character"), all_refs[0] if all_refs else None)
        if ref is None:
            raise PreviewError("this episode has no refs to try it on")
    with TG.trying(target_id, fields, spec):
        t = TG.load_target(target_id, "image", root=root)
        hosted = TG.is_hosted(t.spec)
        out = {"ok": True, "id": t.id, "kind": "image", "label": t.label, "scope": TG.scope_of(t.folder),
               "hosted": hosted, "shot": ref.id, "pass": "", "editable": False, "problems": problems,
               "changed": changed, "shipped": _own_image(t), "parts": [], "request_parts": [],
               "template": "", "request": TP.request_template(t, "image")}
        _mapping(t, out, None, required)
        # the pictures chosen as a hosted edit model chooses them (the Add wizard's model has no
        # folder to plan from; what differs is its own request)
        base = t.id if spec is None else IMAGE_BASE
        jobs = R.plan_generate(s, R.GenRequest(ref=ref.id, view=view, target=base))
        if not jobs:
            out.update(ok=False, why=f"{ref.id}: nothing to generate")
            return out
        job = jobs[0]
        out["prompt"] = out["sent"] = job.prompt or ""
        if hosted:
            job.target = t
            R.hosted_references(s, job)
            _request(t, job, out)
            _mapping(t, out, out.get("arguments"), required)
    return out


def _own_image(t: "TG.Target") -> dict:
    before = t.before_overrides or t
    block = TG.hosted_block(before.spec)
    return {"template": "", "request": TP.request_template(before, "image"),
            "inputs": block.get("inputs") or {}, "arguments": block.get("arguments") or {}}


def _without_prompt(overrides: dict, sid: str) -> dict:
    """`overrides` with no prompt on this shot."""
    ov = copy.deepcopy(overrides)
    shot = (ov.get("shots") or {}).get(sid)

    def strip(block):
        if isinstance(block, dict):
            block.pop("prompt", None)
            for v in block.values():
                strip(v)
    strip(shot)
    return ov


def _request(t: "TG.Target", job, out: dict) -> None:
    """A hosted model's request for the job, and what its prompt was made of. A mapping being
    edited can be wrong in any way: whatever it breaks is said, not raised."""
    from seriesmith.backends.router import ROUTING
    with TP.watching() as seen:
        try:
            model, args = t.module.router_call(t, job)
        except Exception as e:                            # noqa: BLE001  said in the panel
            out["request_error"] = f"{e}" if isinstance(e, ValueError) else f"{e.__class__.__name__}: {e}"
            out["request_parts"] = _described(TP.REQUEST_PARTS, {"prompt": out["prompt"]})
            return
    service = TG.service_of(t.spec)
    if service:
        from seriesmith import providers as PR
        from seriesmith.backends.http import planned_calls
        d = PR.definitions().get(service)
        if d:
            out["calls"] = planned_calls(d, model, args)
    routing = args.pop(ROUTING, None)
    out.update(model=model, arguments=plain(args), **({"routing": routing} if routing else {}))
    if seen:
        out["sent"] = seen["sent"]
        out["limit"] = seen["limit"]
        out["request_parts"] = _described(TP.REQUEST_PARTS, {**seen["values"], "prompt": seen["text"]})
