// seriesmith: which picked files make which episode, for Import series.
//
// Files come as {path, text}: `path` is the picked file's path within what was
// picked (a whole folder gives "Season2/s2ep02/s2ep02.md"), else its name.
// A script is a .md (or .txt) whose first line is an episode header
// (`= s2ep02  Title`); any other .md (notes, refs_todo.md, a cast list) is left
// out. A series config is a .json. Each script gets its own config when there
// is one beside it (the only .json in its folder) or named for it
// (`s2ep02.json`, `s2ep02.series.json`); the rest share the one config left
// over. Episodes in Porchlights' layout -- every episode folder with its own
// series.json -- so pair up when the season's folder is picked.

export interface Picked {
  path: string;
  text: string;
}

export interface Pairing {
  /** the config every script without its own uses (null: none) */
  shared: Picked | null;
  scripts: { script: Picked; config: Picked | null }[];
  /** .md files left out: not a script (no episode header) */
  notScripts: string[];
  problems: string[];
}

const HEADER = /^=\s*\S+/;

function dir(path: string): string {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i < 0 ? "" : path.slice(0, i);
}

function base(path: string): string {
  return path.slice(dir(path).length).replace(/^[\\/]/, "");
}

function stem(path: string): string {
  return base(path).replace(/\.[^.]+$/, "");
}

export function isScript(text: string): boolean {
  const first = text.split(/\r?\n/).find((l) => l.trim());
  return !!first && HEADER.test(first.trim());
}

export function pairFiles(files: Picked[]): Pairing {
  const configs = files.filter((f) => /\.json$/i.test(f.path));
  const texts = files.filter((f) => /\.(md|txt)$/i.test(f.path));
  const scripts = texts.filter((f) => isScript(f.text));
  const notScripts = texts.filter((f) => !isScript(f.text)).map((f) => f.path);
  const used = new Set<Picked>();
  const out: Pairing["scripts"] = [];
  for (const s of scripts) {
    const d = dir(s.path);
    const n = stem(s.path).toLowerCase();
    const beside = d ? configs.filter((c) => dir(c.path) === d) : [];
    const named = configs.filter((c) => {
      const cs = stem(c.path).toLowerCase();
      return cs === n || cs === `${n}.series`;
    });
    // a config named for the script wins; else the only one beside it, unless
    // that one sits at the top of what was picked beside every script (shared)
    const own = named[0] ?? (beside.length === 1 && scripts.filter((x) => dir(x.path) === d).length === 1
      ? beside[0] : null);
    if (own) used.add(own);
    out.push({ script: s, config: own });
  }
  const left = configs.filter((c) => !used.has(c));
  const problems: string[] = [];
  let shared: Picked | null = null;
  if (left.length === 1) shared = left[0];
  else if (left.length > 1 && out.some((x) => !x.config)) {
    problems.push(`${left.length} series configs aren't any one episode's (${left.map((c) => c.path).join(", ")}): `
      + "pick just the one the series shares, or put each beside its script");
  }
  const orphans = out.filter((x) => !x.config && !shared).map((x) => x.script.path);
  if (orphans.length && !problems.length) {
    problems.push(`no series config for ${orphans.join(", ")}: pick the series' series.json too`);
  }
  if (!scripts.length) problems.push("no scripts: a script is a .md whose first line is its header, like `= ep01  Title`");
  return { shared, scripts: out, notScripts, problems };
}
