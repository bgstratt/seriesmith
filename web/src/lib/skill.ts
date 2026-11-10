// The script-writing skill: where to get it. It isn't in a ComfyUI-Manager install (the Registry
// package leaves its zip out), so every place that tells you to use it says where it is.

/** The skill's zip, as committed on main: uploaded in Claude (Settings → Skills), or unzipped
 * into .claude/skills for Claude Code. */
export const SKILL_URL = "https://github.com/bgstratt/seriesmith/raw/main/prompts/seriesmith-episode-script.zip";

/** The page that walks through installing it and using it on a screenplay. */
export const SKILL_GUIDE_URL = "https://docs.seriesmith.com/tutorials/screenplay-to-episode";

export const SKILL_HOW = "The seriesmith-episode-script skill: upload the zip in Claude (Settings → Skills), "
  + "or unzip it into .claude/skills for Claude Code.";
