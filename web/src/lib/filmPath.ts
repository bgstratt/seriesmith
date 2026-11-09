// The guided film path (docs/DESIGN.md, section 10): where an episode has got to, worked out from
// what's on disk, so the guide can be closed and come back with no record of its own.

export const FILM_STEPS = ["Idea", "Story", "Cast and places", "Storyboard", "Film", "Watch"] as const;
export type FilmStep = 1 | 2 | 3 | 4 | 5;

export interface ScriptShot {
  id: string;
  hold: boolean;
}

export interface ScriptFound {
  characters: string[];
  things: string[];
  locations: string[];
}

const uniqueAdd = (list: string[], id: string) => {
  if (id && !list.includes(id)) list.push(id);
};
const idsOf = (value: string) => value.split(",").map((x) => x.trim()).filter(Boolean);

/** The shots a script has, in order, and which have no model yet. */
export function scriptShots(text: string): ScriptShot[] {
  const out: ScriptShot[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const head = /^##\s+(\S+)/.exec(line);
    if (head) out.push({ id: head[1], hold: false });
    else if (out.length && /^target:\s*hold\s*$/.test(line)) out[out.length - 1].hold = true;
  }
  return out;
}

/** The people, things and places a script names, by id, in the order it names them. */
export function scriptNames(text: string): ScriptFound {
  const found: ScriptFound = { characters: [], things: [], locations: [] };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const place = /^#\s+\S+\s+(\S+)/.exec(line);
    if (place) uniqueAdd(found.locations, place[1]);
    const who = /^(?:who|cast):\s*(.+)$/.exec(line);
    if (who) idsOf(who[1]).forEach((id) => uniqueAdd(found.characters, id));
    const things = /^with:\s*(.+)$/.exec(line);
    if (things) idsOf(things[1]).forEach((id) => uniqueAdd(found.things, id));
  }
  return found;
}

/** A name to start a card with, from a script's id: `old_ada` -> `Old Ada`. */
export function nameOfId(id: string): string {
  return id.split("_").filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
}

/** A script pasted in, under this episode's name: its own title stays. */
export function scriptForEpisode(name: string, title: string, text: string): string {
  const body = text.replace(/\r\n/g, "\n").trim();
  const head = /^=[ \t]*\S+([ \t]+.*)?$/m.exec(body);
  if (head && body.slice(0, head.index).trim() === "") {
    return `= ${name}${head[1] ? `  ${head[1].trim()}` : title.trim() ? `  ${title.trim()}` : ""}${body.slice(head.index + head[0].length)}\n`;
  }
  return `= ${name}${title.trim() ? `  ${title.trim()}` : ""}\n\n${body}\n`;
}

export interface FilmFacts {
  shots: number;
  structure: boolean;
  /** pictures of the cast and places that aren't made yet */
  missing: number;
  /** shots with no model yet */
  held: number;
  /** shots on a model with no take in the cut */
  unrendered: number;
}

/** The step to be on: the first thing not done yet. */
export function filmStep(f: FilmFacts): FilmStep {
  if (!f.shots && !f.structure) return 1;
  if (f.missing) return 2;
  if (!f.shots || f.held) return 3;
  if (f.unrendered) return 4;
  return 5;
}

/** What to paste into your own agent to have it write this episode, over seriesmith's MCP tools.
 * The series config goes first: the script is checked against the one on disk. */
export function agentInstructions(ep: string): string {
  return [
    "Use the seriesmith script-writing skill to write this episode. Ask me what it's about if I haven't said.",
    "",
    `The episode folder is: ${ep}`,
    "",
    "With the seriesmith MCP tools, in this order:",
    '1. read_source for file "series" and for file "script". Keep each one\'s hash.',
    "2. Write the script, and add every character, prop, vehicle and location it names to the series config. Keep what's already there.",
    '3. check_source the series config, then save_source it with its hash.',
    '4. check_source the script and fix what it reports, then save_source it with its hash.',
  ].join("\n");
}
