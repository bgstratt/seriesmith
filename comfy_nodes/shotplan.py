"""
What SeriesmithShotLoader decides for one shot, without torch: its size and
length, which panel of each sheet it sends, which voice sample or slice of the
recording goes in which audio slot, the prompt, the seed and the steps.

Two things turn the plan into a shot's inputs: the loader node (shot.py), into
tensors inside ComfyUI, and seriesmith (seriesmith/cloud.py), into picture and
sound files a ComfyUI without this node pack loads with its own LoadImage and
LoadAudio (Comfy Cloud). One plan for both, so a shot is cut the same way
wherever it renders.

Standard library only: seriesmith loads this file by its path.
"""
from __future__ import annotations

import math
import os
import re

GRID_STEP, GRID_BASE, GRID_MAX = 17, 5, 3592

AUDIO_POLICIES = ["generate", "dub", "dub_keep_foley", "clone"]
PANEL_MODES = ["auto", "full", "pair", "face", "body"]

# An unused subject socket's picture (H3's smallest canvas): it holds the
# socket's number so the plate stays <Picture 4> (see plan_shot).
PLACEHOLDER_SIZE = 32


def snap_up(frames: int) -> int:
    """Round up onto H3's 17k+5 frame grid."""
    if frames <= GRID_BASE:
        return GRID_BASE
    value = GRID_STEP * math.ceil((frames - GRID_BASE) / GRID_STEP) + GRID_BASE
    if value > GRID_MAX:
        raise ValueError(
            f"{frames} frames exceeds H3's maximum of {GRID_MAX} "
            f"({GRID_MAX / 24:.2f}s at 24fps). Split this shot."
        )
    return value


def panels_for(mode: str, cast_n: int, shot_size: str) -> tuple[str, list[int]]:
    """Decide which panels of a 4-panel strip (3/4, side, back, face) to keep.

    Reference cost scales with strip width, so crowded shots drop to the
    two panels that actually carry identity.
    """
    if mode == "full":
        return "full", [0, 1, 2, 3]
    if mode == "pair":
        return "pair", [0, 3]
    if mode == "face":
        return "face", [3]
    if mode == "body":
        return "body", [0]
    # auto -- one panel, so the reference never contains a second figure
    # for H3 to duplicate into frame.
    if cast_n <= 1 and shot_size in ("close", "cu"):
        return "face", [3]
    return "body", [0]


def crop_box(width: int, panels: int, keep: list[int]) -> list[tuple[int, int]]:
    """The column ranges [(x0, x1), ...] a horizontal `panels`-panel strip
    `width` wide keeps of `keep`, left to right; [(0, width)] for the whole
    picture. The strip's short side is the vertical one, which is what H3
    scales to 2048 in `max` mode -- so dropping panels narrows the image
    without costing per-panel resolution."""
    if panels <= 1 or not keep:
        return [(0, width)]
    pw = width // panels
    keep = [i for i in keep if 0 <= i < panels]
    if not keep:
        return [(0, width)]
    return [(i * pw, (i + 1) * pw) for i in sorted(keep)]


def plan_shot(doc: dict, index: int, panel_mode: str, fps: float,
              resolution_override: str, resolve) -> dict:
    """One shot of a shotlist (`doc`, parsed) planned: everything the loader
    emits except the pictures and sounds themselves, which are described.

    `resolve(path)` is where a path the shotlist names is on this machine
    ("" when it isn't there). Each of `refs` (three, the subject slots) and
    `bg` is {"path", "panels", "keep", "label", "how"} (a picture to read and
    cut: crop_box) or {"neutral": [h, w], "note"} (flat grey); each of `audio`
    (three) is {"path", "start", "end"} (start/end None: the whole file) or
    None. Raises as the loader does for a shot that can't render."""
    shots = doc.get("shots", [])
    if not shots:
        raise ValueError("the shotlist contains no shots")
    shot = shots[index % len(shots)]

    defaults = doc.get("defaults", {})
    book = doc.get("subjects", doc.get("cast", {}))

    # ---- geometry --------------------------------------------------------
    if resolution_override.strip():
        m = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", resolution_override)
        if not m:
            raise ValueError(
                f"resolution_override must look like 1344x768, got {resolution_override!r}"
            )
        width, height = int(m.group(1)), int(m.group(2))
    else:
        width = int(shot.get("width", defaults.get("width", 1344)))
        height = int(shot.get("height", defaults.get("height", 768)))
    for name, v in (("width", width), ("height", height)):
        if v % 32:
            raise ValueError(
                f"{name}={v} is not a multiple of 32. H3 rejects it. "
                f"Nearest legal: {v // 32 * 32} or {(v // 32 + 1) * 32}."
            )

    # ---- duration --------------------------------------------------------
    if "audio_in" in shot and "audio_out" in shot:
        duration = float(shot["audio_out"]) - float(shot["audio_in"])
        if duration <= 0:
            raise ValueError(f"shot {shot.get('id')}: audio_out must follow audio_in")
    else:
        duration = float(shot.get("duration", defaults.get("duration", 3.04)))
    # continuous: latent (docs/CONTINUOUS.md): `hold` more frames, the
    # previous take's last ones held at the head (H3ChainLatent) and
    # trimmed off after decoding (H3ChainTrim)
    hold = int(shot.get("hold") or 0)
    length = snap_up(max(1, round(duration * fps)) + hold)

    # ---- references ------------------------------------------------------
    # Slots 1-3 are the shot's subjects (characters first, then props and
    # vehicles). Slot 4 is ALWAYS the location plate. (A target with more
    # subject sockets says how many, `defaults.subject_slots`: FastH3 Omni's
    # eight, its plate <Picture 9>; the rest of this reads 3 and 4.) There is no style
    # reference: the style is already carried by every sheet and plate,
    # which are all drawn in it, and by the text prefix. Spending slot 4 on
    # the background instead buys concrete layout, palette, lighting
    # direction and depth for this specific shot -- and keeps the same
    # location looking like the same place across every cut in a sequence.
    subject_ids = shot.get("subjects") or shot.get("cast") or []
    size = (shot.get("size") or "medium").lower()
    panels_total = int(defaults.get("sheet_panels", 4))
    n_slots = int(defaults.get("subject_slots", 3))
    plate = f"Picture {n_slots + 1}"

    # `missing_refs: blank` (set by jobs when a render is asked for anyway)
    # turns a missing picture into flat grey and a missing audio reference
    # into none, instead of failing the shot.
    render_anyway = shot.get("missing_refs") == "blank"
    blanked: list[str] = []

    # Background first: it is also what fills any unused subject socket.
    bg_path = resolve(shot.get("background", ""))
    if not bg_path or not os.path.isfile(bg_path):
        if not render_anyway:
            raise FileNotFoundError(
                f"shot {shot.get('id')}: background plate not found at "
                f"{bg_path or '<unset>'}. Every shot needs one -- it is <{plate}>."
            )
        bg = {"neutral": [height, width]}
        blanked.append(plate)
    else:
        bg = {"path": bg_path, "panels": 1, "keep": []}

    # Characters get the panel-crop cost lever; props are single images.
    declared = shot.get("panels")
    if panel_mode != "auto":
        mode_used, keep = panels_for(panel_mode, 99, size)
    elif declared:
        d = int(declared)
        if d == 1:
            view = shot.get("panel_view", "body")
            keep = [3] if view == "face" else [0]
            mode_used = view
        elif d == 4:
            keep, mode_used = [0, 1, 2, 3], "full"
        else:
            keep, mode_used = [0, 3], "pair"
    else:
        mode_used, keep = panels_for("auto", len(subject_ids), size)

    refs: list[dict] = []
    for sid in subject_ids[:n_slots]:
        entry = book.get(sid, {})
        kind = entry.get("kind", "character")
        path = resolve(entry.get("sheet", ""))
        if not path or not os.path.isfile(path):
            if not render_anyway:
                raise FileNotFoundError(
                    f"shot {shot.get('id')}: reference for '{sid}' not found at "
                    f"{path or '<unset>'}"
                )
            refs.append({"neutral": [1024, 1024],
                         "note": f"{sid} ({kind}) MISSING -> flat grey"})
            blanked.append(f"Picture {len(refs)}")
            continue
        label = f"{sid} ({kind}) {os.path.basename(path)}"
        if kind == "character":
            # `sheet_panels: 1` in the series config: a single picture, sent whole
            n_panels = int(entry.get("sheet_panels") or panels_total)
            how = "whole" if n_panels <= 1 else f"{mode_used} of {n_panels} panels"
            refs.append({"path": path, "panels": n_panels, "keep": list(keep),
                         "label": label, "how": how})
        else:
            refs.append({"path": path, "panels": 1, "keep": [], "label": label, "how": "whole"})

    if len(subject_ids) > n_slots:
        raise ValueError(
            f"shot {shot.get('id')}: {len(subject_ids)} subjects but only {n_slots} slots "
            f"-- slot {n_slots + 1} is the background. Drop {len(subject_ids) - n_slots}."
        )

    # A shot with fewer than three subjects fills those sockets with a 32x32
    # grey placeholder, so the plate stays <Picture 4> as the prompt says.
    # MiniMaxH3ReferenceToVideo skips a None socket and the text encoder
    # numbers only the pictures it is given (comfy/text_encoders/minimax.py),
    # so empty sockets (2026-09-22 to 2026-10-05) sent a one-subject shot's
    # plate as <Picture 2> under a prompt naming <Picture 4>. 32x32 is the
    # node's smallest canvas and it never enlarges a reference, so each
    # placeholder costs a 2x2 latent and a few vision tokens, not the plate's
    # thousands (padding with the plate itself, before 2026-09-22, did).
    n_sub = len(refs)
    while len(refs) < n_slots:
        refs.append({"neutral": [PLACEHOLDER_SIZE, PLACEHOLDER_SIZE], "placeholder": True})
    bg_note = (f"background {os.path.basename(bg_path or '') or '(none)'}"
               f"{' MISSING -> flat grey' if plate in blanked else ''} -> <{plate}>"
               + (f" (slots {n_sub + 1}-{n_slots} placeholders)" if n_sub < n_slots else ""))

    # ---- audio -----------------------------------------------------------
    policy = (shot.get("audio_policy") or defaults.get("audio_policy") or "generate")
    if policy not in AUDIO_POLICIES:
        raise ValueError(
            f"shot {shot.get('id')}: audio_policy {policy!r} not one of {AUDIO_POLICIES}"
        )

    audio_note = "none"
    audio: list[dict | None] = [None, None, None]

    if policy == "generate":
        # Deliberately None, not silence. ref_audio is a *reference* socket:
        # handing it a silent clip tells H3 "match this audio", which biases
        # it toward generating silence.
        audio_note = "generate (no audio reference)"

    elif policy == "clone":
        # One timbre sample PER SPEAKER. A two-hander needs two, or the
        # second character gets voiced from the first one's sample.
        vrefs = shot.get("voice_refs") or []
        if not vrefs and shot.get("voice_subject"):
            vrefs = [{"subject": shot["voice_subject"],
                      "sample": book.get(shot["voice_subject"], {}).get("voice_sample", "")}]
        if len(vrefs) > 3:
            raise ValueError(
                f"shot {shot.get('id')}: {len(vrefs)} voice references but H3 takes "
                f"at most 3. Split the shot."
            )
        names = []
        for i, r in enumerate(vrefs[:3]):
            p = resolve(r.get("sample", ""))
            if (not p or not os.path.isfile(p)) and render_anyway:
                blanked.append(f"Audio {i + 1}")
                names.append(f"<Audio {i + 1}>={r.get('subject')} MISSING (none)")
                continue
            if not p or not os.path.isfile(p):
                raise FileNotFoundError(
                    f"shot {shot.get('id')}: voice sample for '{r.get('subject')}' "
                    f"not found at {p or '<unset>'}. clone mode needs one per speaker."
                )
            audio[i] = {"path": p, "start": None, "end": None}
            names.append(f"<Audio {i + 1}>={r.get('subject')}")
        audio_note = "clone <- " + ", ".join(names) if names else "clone (no refs)"

    else:  # dub / dub_keep_foley
        # ONE clip: the slice of the recorded mix, which already contains
        # every voice in the shot.
        src = shot.get("audio_file") or defaults.get("master_track", "")
        src = resolve(src)
        if (not src or not os.path.isfile(src)) and render_anyway:
            blanked.append("Audio 1")
            src = ""
        elif not src or not os.path.isfile(src):
            raise FileNotFoundError(
                f"shot {shot.get('id')}: audio_policy '{policy}' needs the recorded "
                f"mix; looked for {src or '<unset>'}"
            )
        if not src:
            audio_note = f"{policy} <- recording MISSING (no audio reference)"
        elif "audio_in" in shot and not shot.get("audio_file"):
            # a held head starts the window that much earlier on the
            # recording, so the voices land where the shot's own frames are
            a_in = max(0.0, float(shot["audio_in"]) - hold / fps)
            audio[0] = {"path": src, "start": a_in, "end": float(shot["audio_out"])}
            audio_note = (f"{policy} <- {os.path.basename(src)} "
                          f"[{a_in:.2f}..{shot['audio_out']:.2f}]")
        else:
            audio[0] = {"path": src, "start": None, "end": None}
            audio_note = f"{policy} <- {os.path.basename(src)}"

    # ---- prompt / seed ---------------------------------------------------
    prompt = shot.get("prompt", "")
    if isinstance(prompt, list):
        prompt = "\n\n".join(prompt)
    prefix = doc.get("prompt_prefix", "")
    if prefix:
        prompt = f"{prefix}\n\n{prompt}"
    seed = int(shot.get("seed", 0)) & 0x7FFF_FFFF_FFFF_FFFF
    # Sampler steps travel with the shot so the proxy pass actually renders
    # at its own step count instead of inheriting whatever the workflow's
    # scheduler widget happens to say.
    steps = int(shot.get("steps", defaults.get("steps", 4)))

    return {
        "id": str(shot.get("id", f"shot_{index:04d}")), "label": shot.get("id", "?"),
        "prompt": prompt,
        "width": width, "height": height, "length": length, "steps": steps, "seed": seed,
        "policy": policy, "fps": fps, "hold": hold, "duration": duration,
        "pad": length - hold - round(duration * fps),
        "pos": index % len(shots), "count": len(shots),
        "subject_ids": list(subject_ids), "size": size, "voices": list(shot.get("voices", [])),
        "refs": refs, "bg": bg, "bg_note": bg_note, "audio": audio, "audio_note": audio_note,
        "blanked": blanked,
    }


def ref_notes(plan: dict, sizes: list[tuple[int, int] | None]) -> list[str]:
    """The loader's reference lines: each subject slot's picture (`sizes`, its
    (width, height) as cut, one per slot; None for a slot with no picture
    read), then the background."""
    out = []
    for ref, wh in zip(plan["refs"], sizes):
        if ref.get("placeholder"):
            continue
        if "neutral" in ref:
            out.append(ref["note"])
        else:
            out.append(f"{ref['label']} [{wh[0]}x{wh[1]}, {ref['how']}]")
    if not any("path" in r or "note" in r for r in plan["refs"]):
        # Plate-only shot: an establishing view with voiceover over it. The
        # prompt makes the location <Subject 1>, sourced from <Picture 4>,
        # and names no other picture — so the subject sockets get placeholders.
        out.append("no subjects — the background is the whole reference")
    out.append(plan["bg_note"])
    return out


def info_text(plan: dict, sizes: list[tuple[int, int] | None]) -> str:
    """The loader's `info` output: what this shot is, and every reference."""
    fps, length, hold = plan["fps"], plan["length"], plan["hold"]
    subject_ids = plan["subject_ids"]
    return "\n".join([
        f"shot {plan['pos'] + 1} of {plan['count']}   —   {plan['label']}",
        f"{plan['width']}x{plan['height']}   {length} frames   {length / fps:.2f}s   "
        f"{plan['steps']} steps   (asked {plan['duration']:.2f}s, pad {plan['pad']}f)"
        + (f"   holding {hold}f of the previous take" if hold else ""),
        f"subjects: {', '.join(subject_ids) if subject_ids else '- (plate only)'}   "
        f"size: {plan['size']}",
        f"voices: {', '.join(plan['voices']) or '-'}",
        f"audio: {plan['audio_note']}",
        *([f"RENDERED WITHOUT: {', '.join(plan['blanked'])} (missing refs)"]
          if plan["blanked"] else []),
        "refs:",
        *[f"  {n}" for n in ref_notes(plan, sizes)],
        f"seed: {plan['seed']}",
    ])
