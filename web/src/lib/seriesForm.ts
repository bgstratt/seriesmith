// The series config as a form (docs/EDITOR.md, "Series settings"): what each
// field is, where it lives in series.json, and the edits that keep the file
// as the server writes it. The file stays the source of truth: the form reads
// it, changes only the keys it shows, keeps every other key (notes, blocks it
// doesn't know), and saves through PUT /seriesmith/source like the text window.

export type Raw = Record<string, unknown>;
export type Path = readonly string[];

/** A path's value in the config (undefined when any step is missing). */
export function getPath(raw: Raw, path: Path): unknown {
  let v: unknown = raw;
  for (const k of path) {
    if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
    v = (v as Raw)[k];
  }
  return v;
}

/** Empty: what a cleared field leaves out of the file. */
export function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || (typeof v === "string" && v.trim() === "")
    || (typeof v === "number" && Number.isNaN(v));
}

/**
 * The config with `path` set to `value` (a copy; the original is untouched).
 * An empty value removes the key, and a block left empty by that goes too, so
 * clearing a field never leaves `"proxy": {}` behind. Key order is kept: a key
 * already there stays where it is, a new one goes at the end of its block.
 */
export function setPath(raw: Raw, path: Path, value: unknown): Raw {
  if (!path.length) return raw;
  const [k, ...rest] = path;
  const out: Raw = { ...raw };
  if (!rest.length) {
    if (isEmpty(value)) delete out[k];
    else out[k] = value;
    return out;
  }
  const child = out[k];
  const base = child && typeof child === "object" && !Array.isArray(child) ? (child as Raw) : {};
  const next = setPath(base, rest, value);
  if (Object.keys(next).length) out[k] = next;
  else delete out[k];
  return out;
}

/** The text the server would write for `raw` (source.dump_series: 2-space
 * indent, key order and non-ASCII kept, a final newline if the file had one). */
export function serialize(raw: Raw, like: string): string {
  return JSON.stringify(raw, null, 2) + (like.endsWith("\n") ? "\n" : "");
}

/** A series id from its title: lower case, words joined by underscores. */
export function slug(title: string): string {
  return title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
}

// ---------------------------------------------------------------------------
// sizes
// ---------------------------------------------------------------------------

/** The final sizes offered (H3's 32 grid; 1344x768 is its native canvas). */
export const FINAL_SIZES = ["1344x768", "1280x704", "1024x576", "960x544"];
/** The proxy sizes offered: 480p and up — smaller is too small to judge a shot by. */
export const PROXY_SIZES = ["864x480", "896x512", "960x544", "640x352", "448x256"];
export const DEFAULT_PROXY = "864x480";

/** A note when the proxy is another shape from the final (more than 1% off):
 * a proxy take standing in for a final shot in a cut is scaled to fit. */
export function shapeNote(finalSize: string, proxySize: string): string | null {
  const a = /^(\d+)x(\d+)$/.exec(finalSize), b = /^(\d+)x(\d+)$/.exec(proxySize);
  if (!a || !b) return null;
  const fa = Number(a[1]) / Number(a[2]), pa = Number(b[1]) / Number(b[2]);
  if (Math.abs(fa - pa) / fa <= 0.01) return null;
  return `A different shape from the final (${pa.toFixed(2)} against ${fa.toFixed(2)}): a proxy take standing in for a final shot in a cut is scaled to fit.`;
}

export function sizeOf(raw: Raw, block: "series" | "proxy"): string {
  const w = getPath(raw, [block, "width"]);
  const h = getPath(raw, [block, "height"]);
  return typeof w === "number" && typeof h === "number" ? `${w}x${h}` : "";
}

/** The config with a block's width and height set from "WxH" ("" clears both). */
export function setSize(raw: Raw, block: "series" | "proxy", size: string): Raw {
  const m = /^\s*(\d+)\s*[xX×]\s*(\d+)\s*$/.exec(size);
  const w = m ? Number(m[1]) : undefined;
  const h = m ? Number(m[2]) : undefined;
  return setPath(setPath(raw, [block, "width"], w), [block, "height"], h);
}

// ---------------------------------------------------------------------------
// the fields
// ---------------------------------------------------------------------------

export interface Choice {
  value: string;
  label: string;
}

export type FieldKind =
  | "text"            // one line
  | "long"            // a paragraph
  | "number"
  | "select"          // `choices`; "" leaves the key out (the default)
  | "video_target" | "image_target" | "audio_target"
  | "backend"
  | "lora"            // one LoRA (name[:strength] | none), from what the video model loads
  | "model"           // a model file the video model can load
  | "picture";        // a picture's path, typed or browsed for

export interface Field {
  path: Path;
  label: string;
  kind: FieldKind;
  help: string;
  choices?: Choice[];
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  /** shown only when this is true of the config */
  when?: (raw: Raw) => boolean;
  /** shown under "More" */
  more?: boolean;
}

export interface Section {
  id: string;
  title: string;
  help: string;
  fields: Field[];
}

const AUDIO_MODES: Choice[] = [
  { value: "", label: "recorded track (the default)" },
  { value: "generate", label: "generate: the model invents each voice" },
  { value: "source_track", label: "recorded track: shots dub to your mix" },
  { value: "clone", label: "clone: the written lines in each sampled voice" },
];

export const SECTIONS: Section[] = [
  {
    id: "series",
    title: "Series",
    help: "The show's name and how every episode renders by default.",
    fields: [
      { path: ["series", "title"], label: "Title", kind: "text", placeholder: "First Light",
        help: "The series title, written on the intro and outro of every master." },
      { path: ["series", "id"], label: "Id", kind: "text", placeholder: "first_light",
        help: "A short name with no spaces. Seeds come from it, with the episode and shot ids: change it and every shot renders differently." },
      { path: ["series", "fps"], label: "Frames per second", kind: "number", min: 1, max: 60, step: 1, placeholder: "24",
        help: "24 unless a target needs otherwise; a target that renders at another rate (Wan 14B: 16) is converted when the cut is assembled." },
      { path: ["series", "steps"], label: "Steps (final)", kind: "number", min: 1, max: 100, step: 1, more: true,
        help: "Sampler steps for the final pass. Leave empty for the target's own preset (H3: 8 with its turbo LoRA)." },
      { path: ["series", "lora"], label: "LoRA (final)", kind: "lora", more: true,
        help: "A LoRA every final-pass shot loads, and its strength; none for none. Empty: the video model's preset." },
      { path: ["series", "model"], label: "Model file (final)", kind: "model", more: true,
        help: "A model file other than the target's preset, for every final-pass shot." },
      { path: ["proxy", "steps"], label: "Steps (proxy)", kind: "number", min: 1, max: 100, step: 1, more: true,
        help: "Sampler steps for the animatic (H3: 4 with its proxy turbo LoRA)." },
      { path: ["proxy", "lora"], label: "LoRA (proxy)", kind: "lora", more: true,
        help: "As LoRA (final), for the animatic." },
    ],
  },
  {
    id: "look",
    title: "Look and sound",
    help: "Written once, said in every shot's prompt.",
    fields: [
      { path: ["style", "look"], label: "Look", kind: "long",
        placeholder: "a 2D hand-drawn cartoon animation with clean black line art, flat solid colors and cel shading",
        help: "One sentence for the photography of the whole series. Every shot's prompt opens with it (\"The target video is …\"), and every reference picture is drawn in it. Say the medium, the lens or line, the colour and the light; not the story." },
      { path: ["speech", "pace"], label: "Speech pace", kind: "select",
        choices: [{ value: "", label: "normal (the default)" }, { value: "slow", label: "slow: 3.6 syllables a second" },
          { value: "normal", label: "normal: 4.4 syllables a second" }, { value: "fast", label: "fast: 5.4 syllables a second" }],
        help: "How fast lines are spoken: `dur: auto` shots are timed by it, and `check` warns when a line won't fit its shot at it." },
      { path: ["audio", "mode"], label: "Dialogue", kind: "select", choices: AUDIO_MODES,
        help: "How dialogue shots sound. Generate needs nothing recorded; a recorded track lip-syncs H3 to your own mix (Recording window); clone speaks the written lines in each character's voice sample." },
      { path: ["audio", "track"], label: "Recorded track", kind: "text", placeholder: "audio/ep01_dialogue.wav",
        when: (r) => (getPath(r, ["audio", "mode"]) ?? "source_track") === "source_track",
        help: "The episode's dialogue mix, relative to the episode. The Recording window attaches one and times the script to it." },
      { path: ["proxy", "audio_mode"], label: "Dialogue (proxy)", kind: "select",
        choices: [{ value: "", label: "as the final" }, ...AUDIO_MODES.slice(1)],
        help: "The animatic can generate voices while the final pass dubs to the recording: the usual set-up before the recording exists." },
      { path: ["negative"], label: "Negative prompt", kind: "long", more: true,
        help: "What models that take one should avoid (LTX-2, Wan, the image models; not H3). An episode's negative.txt beats it." },
    ],
  },
  {
    id: "models",
    title: "Models",
    help: "Which model makes what. Empty: the default, and the editor can still choose per episode, shot or ref.",
    fields: [
      { path: ["series", "target"], label: "Video model", kind: "video_target",
        help: "What the shots render on. MiniMax H3 Ref2VA (the default) keeps characters and places from their reference pictures and lip-syncs; a shot or a sequence can name another." },
      { path: ["series", "backend"], label: "Render on", kind: "backend", more: true,
        help: "Where jobs run unless a request, shot or episode says otherwise: local (your ComfyUI), cloud, a deployment, router. Empty: each model's own." },
      { path: ["refs", "target"], label: "Reference pictures", kind: "image_target",
        help: "The image model that draws character sheets, props and location plates from their design and description (krea2 by default). Pictures you already have can be supplied instead." },
      { path: ["refs", "keyframe_target"], label: "Keyframes", kind: "image_target",
        help: "The image model for a shot's first and last frames — the pictures a keyframe-driven model (H3 FL2VA, LTX-2, Wan) starts or ends on. An edit model (FLUX.2 Klein edit, the default when installed) draws them from your sheets and plate, so the people and the place match." },
      { path: ["refs", "voice_target"], label: "Voices", kind: "audio_target",
        help: "The model that makes a character's voice sample from their voice line (ltx2_voice by default), for clone mode or to keep a voice the same across episodes." },
    ],
  },
  {
    id: "finishing",
    title: "Finishing",
    help: "How a locked cut becomes the delivered episode: every shot upscaled the same way (the master), then optionally cleaned up (post).",
    fields: [
      { path: ["upscale", "master", "deliver"], label: "Deliver at", kind: "select",
        choices: [{ value: "", label: "no master recipe yet" }, { value: "1080p", label: "1080p (1920×1080)" },
          { value: "1440p", label: "1440p (2560×1440)" }, { value: "4k", label: "4K (3840×2160)" }],
        help: "The master's one size. How each video model's shots get there is set below, a row per model." },
      { path: ["upscale", "master", "fit"], label: "Fit", kind: "select",
        when: (r) => !isEmpty(getPath(r, ["upscale", "master", "deliver"])),
        choices: [{ value: "", label: "crop (the default)" }, { value: "crop", label: "crop: fill the frame" }, { value: "pad", label: "pad: black bars" }],
        help: "When a shot's shape isn't the delivery's." },
      { path: ["upscale", "master", "quality"], label: "Quality", kind: "select",
        when: (r) => !isEmpty(getPath(r, ["upscale", "master", "deliver"])),
        choices: [{ value: "", label: "review (the default)" }, { value: "review", label: "review: quicker" }, { value: "master", label: "master: x264 CRF 12, for delivery" }],
        help: "The master's encoding." },
      { path: ["upscale", "save_latents"], label: "Keep latents", kind: "select", more: true,
        choices: [{ value: "", label: "final pass (the default)" }, { value: "final", label: "final pass" }, { value: "always", label: "always" }, { value: "never", label: "never" }],
        help: "Which renders keep their latent (a few MB a take) so an upscale can re-sample it; without one an upscale goes through the VAE." },
      { path: ["post", "master", "enhance"], label: "Post: clean-up", kind: "select",
        choices: [{ value: "", label: "no post recipe" }, { value: "none", label: "none (motion blur only)" }, { value: "draft", label: "draft: an upscale model at 1x" },
          { value: "production", label: "production: SeedVR2 7B (slow, the one to use)" }, { value: "cinematic", label: "cinematic: SUPIR (very slow)" }],
        help: "A pass over each upscaled shot at the same size, for what the model leaves behind (blocky edges and shadows). Master's Post-process uses it." },
      { path: ["post", "master", "motion_blur"], label: "Post: motion blur", kind: "number", min: 0, max: 1, step: 0.05,
        when: (r) => !isEmpty(getPath(r, ["post", "master", "enhance"])),
        help: "A fraction of the frame interval: 0.3 smooths blocky motion, 0.5 is a 180° shutter. Still areas are left alone." },
    ],
  },
  {
    id: "publish",
    title: "Intro and outro",
    help: "The show's opening and closing clips, made once for the series; every master and publish puts the episode between them, its title written under the series title.",
    fields: [
      { path: ["publish", "intro"], label: "Intro clip", kind: "text", placeholder: "../_titles/INTRO.mp4",
        help: "Relative to the episode. Empty: the show folder's _titles/INTRO.mp4 when there is one." },
      { path: ["publish", "outro"], label: "Outro clip", kind: "text", placeholder: "../_titles/OUTRO.mp4",
        help: "Relative to the episode. Empty: the show folder's _titles/OUTRO.mp4 when there is one." },
    ],
  },
];

/** A master recipe's per-model sections (docs/AUTHORING.md, Masters): how each
 * video model's takes are upscaled. A master with a size and none of these makes
 * every shot a gap, so setting Deliver at writes these when there are none. */
export const MASTER_TARGETS = {
  "minimax_h3_*": { method: "latent", scale: "auto" },
  "ltx2*": { method: "latent", scale: 2 },
  "wan22_*": { method: "seedvr2", seedvr2_model: "7b" },
  "*": { method: "pixel", pixel_model: "RealESRGAN_x2.pth" },
};

/** Whether the master recipe has a size but no per-model sections. */
export function masterLacksTargets(raw: Raw): boolean {
  return !isEmpty(getPath(raw, ["upscale", "master", "deliver"])) && isEmpty(getPath(raw, ["upscale", "master", "targets"]));
}

/** The config with the standard per-model sections (and the finish they assume)
 * added to its master recipe, when it has none. */
export function withMasterTargets(raw: Raw): Raw {
  if (!masterLacksTargets(raw)) return raw;
  let r = setPath(raw, ["upscale", "master", "targets"], structuredClone(MASTER_TARGETS));
  if (isEmpty(getPath(r, ["upscale", "master", "finish"]))) r = setPath(r, ["upscale", "master", "finish"], { frequency_split: true });
  return r;
}

/** The keys the form shows (a key outside these is kept as it is). */
export function shownPaths(): string[] {
  return [...SECTIONS.flatMap((s) => s.fields.map((f) => f.path.join("."))),
    "series.width", "series.height", "proxy.width", "proxy.height"];
}

/** A new series' config: the starter's settings, a 480p proxy. */
export function newSeries(title: string): Raw {
  return {
    series: { id: slug(title) || "my_series", title: title || "My Series", fps: 24, width: 1344, height: 768 },
    proxy: { width: 864, height: 480, audio_mode: "generate" },
    // every prompt opens with it, and the build needs one: a plain default to change
    style: { look: "a cinematic live-action film, natural light" },
    subjects: {},
    locations: {},
    audio: { mode: "generate" },
  };
}

/** Field value as the form shows it: a number or a string ("" for unset). */
export function shown(raw: Raw, f: Field): string {
  const v = getPath(raw, f.path);
  if (v === undefined || v === null) return "";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

/** What typing `text` into field `f` stores: a number for a number field, a
 * string otherwise ("" clears). */
export function parsed(f: Field, text: string): unknown {
  if (f.kind === "number") {
    if (text.trim() === "") return undefined;
    const n = Number(text);
    return Number.isFinite(n) ? n : undefined;
  }
  return text;
}

/** Whether two configs say the same thing (the form's dirty check). */
export function same(a: Raw, b: Raw): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ---------------------------------------------------------------------------
// the cast and places: one card per subject or location
// ---------------------------------------------------------------------------

/** What a card makes. A group is a character with `members`; a voice is a
 * character who is never on screen (a `voice`, no picture). */
export type CardKind = "character" | "group" | "prop" | "vehicle" | "location" | "voice";

export const CARD_KINDS: { kind: CardKind; label: string; add: string }[] = [
  { kind: "character", label: "Character", add: "+ Character" },
  { kind: "group", label: "Group", add: "+ Group" },
  { kind: "prop", label: "Prop", add: "+ Prop" },
  { kind: "vehicle", label: "Vehicle", add: "+ Vehicle" },
  { kind: "location", label: "Location", add: "+ Location" },
  { kind: "voice", label: "Voice only", add: "+ Voice" },
];

export function blockOf(kind: CardKind): "subjects" | "locations" {
  return kind === "location" ? "locations" : "subjects";
}

/** The card kind an existing entry is. */
export function cardKindOf(raw: Raw, block: "subjects" | "locations", id: string): CardKind {
  if (block === "locations") return "location";
  const e = (getPath(raw, ["subjects", id]) ?? {}) as Raw;
  const k = typeof e.kind === "string" ? e.kind : "character";
  if (k === "prop" || k === "vehicle") return k;
  if (typeof e.members === "number") return "group";
  if (!e.sheet && !e.of && e.voice) return "voice";
  return "character";
}

/** "../refs/" or "refs/": how this show's config names its pictures (the
 * prefix most of its sheets and plates use; "../refs/" for a new show, so
 * its episodes share one refs folder). */
export function refsPrefix(raw: Raw): string {
  const paths: string[] = [];
  for (const b of ["subjects", "locations"]) {
    for (const e of Object.values((getPath(raw, [b]) ?? {}) as Record<string, Raw>)) {
      for (const k of ["sheet", "plate"]) if (typeof e?.[k] === "string") paths.push(e[k] as string);
    }
  }
  const up = paths.filter((p) => p.startsWith("../refs/")).length;
  const here = paths.filter((p) => p.startsWith("refs/")).length;
  return here > up ? "refs/" : "../refs/";
}

/** Where a new entry's picture goes, by the show's convention. */
export function picturePath(kind: CardKind, id: string, prefix: string): string | undefined {
  switch (kind) {
    case "character": return `${prefix}${id}/${id}_sheet_4panel.png`;
    case "group": return `${prefix}${id}/${id}.png`;
    case "prop": case "vehicle": return `${prefix}props/${id}.png`;
    case "location": return `${prefix}_bg/${id}.png`;
    default: return undefined;
  }
}

/** Why `id` can't name a new entry ("" when it can). */
export function idProblem(raw: Raw, id: string): string {
  if (!id) return "Give it an id.";
  if (!/^[a-z][a-z0-9_]*$/.test(id)) return "An id is lower case letters, digits and underscores, starting with a letter.";
  if (getPath(raw, ["subjects", id]) !== undefined) return `There is already a subject called ${id}.`;
  if (getPath(raw, ["locations", id]) !== undefined) return `There is already a location called ${id}.`;
  return "";
}

/** The fields of a card, by kind (paths inside the entry). */
export function cardFields(kind: CardKind, raw: Raw, id: string): Field[] {
  const others = (block: "subjects" | "locations", ok: (e: Raw) => boolean): Choice[] =>
    Object.entries((getPath(raw, [block]) ?? {}) as Record<string, Raw>)
      .filter(([k, e]) => k !== id && ok(e ?? {}))
      .map(([k, e]) => ({ value: k, label: typeof e?.name === "string" ? `${e.name} (${k})` : k }));
  const name: Field = { path: ["name"], label: "Name", kind: "text",
    placeholder: kind === "group" ? "the ladies" : kind === "prop" ? "the porch lantern" : kind === "vehicle" ? "the green pickup" : "Ada",
    help: kind === "character" || kind === "voice"
      ? "How the prompt names them, and the name their lines are written under (ADA: ...) in capitals."
      : "How the prompt names it: \"the porch lantern\", \"Riley's backpack\"." };
  const design: Field = { path: ["design"], label: "Design", kind: "long",
    placeholder: kind === "group"
      ? "four young women in Regency ball gowns: one in pale blue with dark curls, one in rose with a feathered headband, ..."
      : kind === "character" ? "a nine-year-old girl with short curly black hair, a green raincoat, and yellow rain boots, drawn with thick confident outlines"
        : "a dented brass hurricane lantern with a smoke-stained glass chimney and a wire handle",
    help: kind === "group"
      ? "Each member, with differences in age, build, hair and colour: four identical gowns read as one person four times. Said in every shot they're in."
      : "What a model-sheet artist could draw: age and build, silhouette, hair, clothes with their colours, one or two distinctive things. Said word for word in every shot it's in, and the picture is drawn from it. Never describe it again in the script." };
  const voice: Field = { path: ["voice"], label: "Voice", kind: "text", placeholder: "bright, quick, a little breathless",
    help: "How they sound, for generated dialogue and their voice sample: pitch, pace, texture, accent." };
  const sheet: Field = { path: ["sheet"], label: "Picture file", kind: "picture", more: true,
    help: kind === "character"
      ? "Where their four-panel sheet lives (three-quarter, side, back, face). Filled in from the show's layout."
      : "Where its picture lives. Filled in from the show's layout." };
  const panels: Field = { path: ["sheet_panels"], label: "Picture layout", kind: "select", more: true,
    choices: [{ value: "", label: "four-panel sheet (the default)" }, { value: "1", label: "one whole picture (a portrait you supply)" }],
    help: "A picture of them that isn't a four-panel sheet needs this, or it's cut into quarters." };
  const sample: Field = { path: ["voice_sample"], label: "Voice sample", kind: "text", more: true, placeholder: "audio/voices/ada_sample.wav",
    help: "A recording of their voice, for clone mode. Generating and picking a voice in the Refs tab fills this in." };
  const variant: Field = { path: ["of"], label: "Variant of", kind: "select", more: true,
    choices: [{ value: "", label: "- (their own person)" },
      ...others("subjects", (e) => !e.of && (typeof e.kind === "string" ? e.kind : "character") === (kind === "group" ? "character" : kind))],
    help: "The same character in other clothes (or a prop in another state): it keeps their name and voice, and its sheet is drawn from theirs. Needs only its own design." };
  switch (kind) {
    case "character": return [name, design, voice, variant, sheet, panels, sample];
    case "group": return [name, design, { path: ["members"], label: "How many people", kind: "number", min: 2, max: 12, step: 1,
      help: "The people in the picture (2 to 12). They take one slot in a shot however many they are, and the prompt counts them." }, sheet];
    case "prop": case "vehicle": return [name, design, variant, sheet];
    case "voice": return [name, voice, sample];
    case "location": return [
      { path: ["description"], label: "Description", kind: "long",
        placeholder: "a wooden front porch at dawn, wet boards, a hanging lamp still lit, mist over the lawn beyond",
        help: "One angle of one place, with its light: time of day, direction, and the things the light comes from (the pendant lamp, the TV's glow). The plate is drawn from it, as a still: say what the camera sees from where it stands, not a move. A walk or a turn through the place is a Tour (chosen under Then when you add it, or under its pictures); the place seen from another side is another location, an angle of this one." },
      { path: ["of"], label: "Angle of", kind: "select",
        choices: [{ value: "", label: "- (a place of its own)" }, ...others("locations", (e) => !e.of)],
        help: "Another camera on the same place: its plate is drawn from that one's (on an edit model), so the walls and light match across a cut. Anchor the description to the same fixed things." },
      { path: ["plate"], label: "Picture file", kind: "picture", more: true,
        help: "Where its plate lives. Filled in from the show's layout." },
    ];
  }
}

/** The entry a card saves: `form` (the fields as edited) over what was there,
 * with `kind` written for a new subject and the picture path filled in. */
export function entryFor(kind: CardKind, before: Raw | undefined, form: Raw, id: string, prefix: string): Raw {
  const e: Raw = { ...(before ?? {}) };
  if (!before && kind !== "location") e.kind = kind === "group" || kind === "voice" ? "character" : kind;
  for (const [k, v] of Object.entries(form)) {
    if (isEmpty(v)) delete e[k];
    else e[k] = k === "sheet_panels" || k === "members" ? Number(v) : v;
  }
  const pic = kind === "location" ? "plate" : "sheet";
  const variant = kind !== "location" && !isEmpty(e.of);
  // a variant's sheet is derived from its base's; anything else gets one by the show's layout
  if (kind !== "voice" && !variant && isEmpty(e[pic])) {
    const p = picturePath(kind, id, prefix);
    if (p) e[pic] = p;
  }
  return e;
}

/** The ref id the Refs tab knows an entry by. */
export function refIdOf(kind: CardKind, id: string): string {
  return kind === "location" ? `location:${id}` : kind === "voice" ? `voice:${id}` : `subject:${id}`;
}
