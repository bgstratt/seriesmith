// The shot form (docs/EDITOR.md, "Editing a shot"): one `## shot` block of the
// script as fields, and back. The script stays the source of truth: the form
// reads the shot's lines (the source route's span), and saving rewrites that
// block only — every other line of the script stays as it was — through
// PUT /seriesmith/source (check, history copy, rebuild).
//
// A block written back is in one order: the cast and framing lines, the render
// lines, the action, then extras, on-screen text, camera, the dialogue in its
// order, sound and music. Comments (`//`) stay at the top. A key the form
// doesn't know is kept, after the known ones.

export interface DialogueLine {
  /** the speaker's key, in capitals as written (ADA) */
  speaker: string;
  /** "" on screen, "V.O." voiceover, "O.S." off screen */
  marker: "" | "V.O." | "O.S.";
  /** a delivery direction ("breathless"); never spoken */
  note: string;
  text: string;
}

export interface ShotForm {
  id: string;
  /** known keys, by their canonical name (who, with, size, dur, ...) */
  keys: Record<string, string>;
  /** the action: the prose lines, one paragraph */
  action: string;
  dialogue: DialogueLine[];
  comments: string[];
  /** lines the form doesn't know, kept as they were */
  other: string[];
}

/** key aliases the script accepts */
const ALIASES: Record<string, string> = { cast: "who", props: "with", duration: "dur" };

/** The keys before the action, in the order they are written. */
export const HEAD_KEYS = ["who", "with", "size", "dur", "plate", "pace", "audio", "target", "profile",
  "model", "lora", "steps", "policy", "retention", "first", "last", "continuous", "overlap"];
/** The keys after the action (dialogue goes between camera and sound). */
export const TAIL_KEYS = ["extras", "text", "camera"];
export const END_KEYS = ["sound", "music"];
const KNOWN = new Set([...HEAD_KEYS, ...TAIL_KEYS, ...END_KEYS]);

const KEY_RE = /^([a-z_]+)\s*:\s*(.*)$/;
const DIALOGUE_RE = /^([A-Z][A-Z0-9_]*)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$/;

/** A shot's block (its lines, from `## id` to before the next header) as a form. */
export function parseShot(lines: string[]): ShotForm {
  const head = (lines[0] ?? "").trim();
  const id = head.replace(/^##\s*/, "").split(/\s+/)[0] ?? "";
  const f: ShotForm = { id, keys: {}, action: "", dialogue: [], comments: [], other: [] };
  const action: string[] = [];
  for (const raw of lines.slice(1)) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("//")) {
      f.comments.push(line);
      continue;
    }
    const d = DIALOGUE_RE.exec(line);
    if (d) {
      const parts = (d[2] ?? "").split(",").map((s) => s.trim()).filter(Boolean);
      const mk = parts.find((p) => /^(V\.?O\.?|O\.?S\.?)$/i.test(p));
      const marker = mk ? (mk.toUpperCase().startsWith("V") ? "V.O." : "O.S.") : "";
      f.dialogue.push({ speaker: d[1], marker, note: parts.filter((p) => p !== mk).join(", "), text: d[3].trim() });
      continue;
    }
    const k = KEY_RE.exec(line);
    if (k) {
      const key = ALIASES[k[1]] ?? k[1];
      if (KNOWN.has(key)) {
        f.keys[key] = k[2].trim();
        continue;
      }
      f.other.push(line);
      continue;
    }
    action.push(line);
  }
  f.action = action.join(" ").replace(/\s+/g, " ").trim();
  return f;
}

/** A dialogue line as the script writes it. */
export function dialogueText(d: DialogueLine): string {
  const paren = [d.marker, d.note.trim()].filter(Boolean).join(", ");
  return `${d.speaker.trim().toUpperCase()}${paren ? ` (${paren})` : ""}: ${d.text.trim()}`;
}

/** The form as the shot's block (no trailing blank line). */
export function writeShot(f: ShotForm): string[] {
  const out = [`## ${f.id}`, ...f.comments];
  const key = (k: string) => {
    const v = (f.keys[k] ?? "").trim();
    if (v) out.push(`${k}: ${v}`);
  };
  HEAD_KEYS.forEach(key);
  if (f.action.trim()) out.push(f.action.trim());
  TAIL_KEYS.forEach(key);
  for (const d of f.dialogue) if (d.speaker.trim() && d.text.trim()) out.push(dialogueText(d));
  END_KEYS.forEach(key);
  out.push(...f.other);
  return out;
}

/** "ada, bo" <-> ["ada", "bo"] */
export function listOf(v: string | undefined): string[] {
  return (v ?? "").split(",").map((s) => s.trim()).filter(Boolean);
}

// ---------------------------------------------------------------------------
// the script around it
// ---------------------------------------------------------------------------

export interface Sequence {
  id: string;
  location: string;
  /** 1-based line of its `#` header */
  line: number;
}

/** The script's sequences (`# sqNN  location`), in order. */
export function sequencesOf(text: string): Sequence[] {
  const out: Sequence[] = [];
  text.split("\n").forEach((l, i) => {
    const m = /^#\s+(\S+)(?:\s+(\S+))?/.exec(l);
    if (m && !l.startsWith("##")) out.push({ id: m[1], location: m[2] ?? "", line: i + 1 });
  });
  return out;
}

/** The sequence a script line is in. */
export function sequenceAt(seqs: Sequence[], line: number): Sequence | null {
  let at: Sequence | null = null;
  for (const s of seqs) if (s.line <= line) at = s;
  return at;
}

/** A free shot id between `prev` and `next` (either may be missing), in the
 * script's own numbering: sh010, sh020 -> sh015; after sh020 -> sh030. */
export function shotIdBetween(prev: string | null, next: string | null, taken: Set<string>): string {
  const parse = (id: string | null) => {
    const m = id ? /^(.*?)(\d+)$/.exec(id) : null;
    return m ? { pre: m[1], n: Number(m[2]), w: m[2].length } : null;
  };
  const a = parse(prev), b = parse(next);
  const pre = a?.pre ?? b?.pre ?? "sh";
  const w = Math.max(a?.w ?? 0, b?.w ?? 0, 3);
  const fmt = (n: number) => `${pre}${String(n).padStart(w, "0")}`;
  const lo = a ? a.n : 0;
  const hi = b ? b.n : Infinity;
  const tries = hi === Infinity
    ? [Math.floor(lo / 10) * 10 + 10]
    : [Math.floor((lo + hi) / 2 / 5) * 5, Math.floor((lo + hi) / 2), lo + 1];
  for (const n of tries) {
    if (n > lo && n < hi && !taken.has(fmt(n))) return fmt(n);
  }
  let n = lo + 1;
  while (taken.has(fmt(n))) n += 1;
  return fmt(n);
}

/** The script with lines [start, end] (1-based, inclusive) replaced by `block`
 * (a blank line kept before the next header). */
export function replaceLines(text: string, start: number, end: number, block: string[]): string {
  const lines = text.split("\n");
  const tail = lines.slice(end);
  // the old block's trailing blank lines are the separator: keep one
  const sep = tail.length && tail[0].trim() !== "" ? [""] : [];
  return [...lines.slice(0, start - 1), ...block, ...sep, ...tail].join("\n");
}

/** The script with `block` inserted after line `after` (0: at the top), a
 * blank line on each side. */
export function insertAfter(text: string, after: number, block: string[]): string {
  const lines = text.split("\n");
  let at = after;
  // past the blank lines that end the block before it
  while (at > 0 && lines[at - 1]?.trim() === "") at -= 1;
  const before = lines.slice(0, at);
  const rest = lines.slice(at);
  while (rest.length && rest[0].trim() === "") rest.shift();
  return [...before, "", ...block, ...(rest.length ? ["", ...rest] : [""])].join("\n");
}

// ---------------------------------------------------------------------------
// the choices
// ---------------------------------------------------------------------------

/** Shot sizes, from close to wide (the script's own words), with what each frames. */
export const SIZES: { value: string; label: string }[] = [
  { value: "ecu", label: "extreme close-up — eyes, a detail" },
  { value: "cu", label: "close-up — the face" },
  { value: "mcu", label: "medium close-up — chest up" },
  { value: "medium", label: "medium — waist up" },
  { value: "cowboy", label: "cowboy — mid-thigh up" },
  { value: "mws", label: "medium wide — knees up, some room" },
  { value: "full", label: "full — head to toe" },
  { value: "wide", label: "wide — the people in their place" },
  { value: "ews", label: "extreme wide — the place, people small in it" },
];

/** Durations free on H3's grid (17k+5 frames at 24 fps), with what each suits. */
export const DURATIONS: { value: string; label: string }[] = [
  { value: "1.62", label: "1.62 s — a single word, a snap" },
  { value: "2.33", label: "2.33 s — a quick reaction, one short line" },
  { value: "3.04", label: "3.04 s — the workhorse shot" },
  { value: "3.75", label: "3.75 s — a beat with a little air" },
  { value: "4.46", label: "4.46 s — two lines of dialogue" },
  { value: "5.17", label: "5.17 s — a long beat, a small piece of business" },
  { value: "5.88", label: "5.88 s" },
  { value: "6.58", label: "6.58 s" },
  { value: "auto", label: "auto — as long as the dialogue needs" },
  { value: "model", label: "model — the video model chooses (LTX-2)" },
];

/** H3's camera vocabulary: motion, then amplitude and speed (both optional). */
export const CAMERA_MOVES = [
  "holds a static shot", "pushes in", "pulls out", "zooms in", "zooms out", "pans left", "pans right",
  "trucks left", "trucks right", "tilts up", "tilts down", "pedestals up", "pedestals down",
  "arcs around", "tracks", "shakes slightly", "shakes strongly", "takes the subject's POV",
  "rolls clockwise", "rolls counterclockwise",
];
export const CAMERA_AMPLITUDE = ["", "with small amplitude", "with large amplitude"];
export const CAMERA_SPEED = ["", "at slow speed", "at fast speed"];

/** A camera line from its parts. */
export function cameraLine(move: string, amplitude: string, speed: string): string {
  return [move, amplitude, speed].filter(Boolean).join(" ");
}

/** A new shot's form. */
export function newShot(id: string): ShotForm {
  return { id, keys: { size: "medium", dur: "3.04" }, action: "", dialogue: [], comments: [], other: [] };
}

// ---------------------------------------------------------------------------
// a `lora:` line (jobs.parse_lora): `name`, `name:0.7`, or none / off / -
// ---------------------------------------------------------------------------

const LORA_OFF = new Set(["none", "off", "-"]);

/** A `lora:` value as the picker shows it: none, or a file and its strength. */
export function parseLoraLine(v: string): { off: boolean; name: string; strength: string } {
  const s = v.trim();
  if (LORA_OFF.has(s.toLowerCase())) return { off: true, name: "", strength: "1" };
  const i = s.lastIndexOf(":");
  if (i > 0 && s.slice(i + 1).trim() !== "" && Number.isFinite(Number(s.slice(i + 1)))) {
    return { off: false, name: s.slice(0, i), strength: s.slice(i + 1).trim() };
  }
  return { off: false, name: s, strength: "1" };
}

/** The `lora:` value for a file and its strength (1 is left unsaid). */
export function loraLine(name: string, strength: string): string {
  if (!name.trim()) return "";
  const n = Number(strength);
  return !strength.trim() || !Number.isFinite(n) || n === 1 ? name.trim() : `${name.trim()}:${strength.trim()}`;
}

/** A `lora:` value as its LoRAs: "" (the default), `none`, or a chain
 * separated by commas ("a:0.6, b"), each a {name, strength}. */
export function parseLoraChain(v: string): { off: boolean; rows: { name: string; strength: string }[] } {
  const s = v.trim();
  if (!s) return { off: false, rows: [] };
  if (LORA_OFF.has(s.toLowerCase())) return { off: true, rows: [] };
  return { off: false, rows: s.split(",").map((x) => x.trim()).filter(Boolean).map((x) => {
    const p = parseLoraLine(x);
    return { name: p.name, strength: p.strength };
  }) };
}

/** The `lora:` value for a chain (rows without a name left out; none: ""). */
export function loraChainLine(rows: { name: string; strength: string }[]): string {
  return rows.map((r) => loraLine(r.name, r.strength)).filter(Boolean).join(", ");
}

/** What a `first:` / `last:` value is: a method, or a picture's path. */
export const KEYFRAME_METHODS = ["generate", "import", "none"];
