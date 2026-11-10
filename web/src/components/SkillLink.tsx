// "Get the skill": the script-writing skill's zip and the page on installing it (lib/skill.ts),
// beside every place the editor says to use it.

import { SKILL_GUIDE_URL, SKILL_HOW, SKILL_URL } from "../lib/skill";

export function SkillLink({ guide = true }: { guide?: boolean }) {
  return (
    <span className="h3-row h3-wrap h3-small" style={{ gap: 8, display: "inline-flex" }}>
      <a className="sm-skill-get" href={SKILL_URL} target="_blank" rel="noreferrer" title={SKILL_HOW}>
        <i className="pi pi-download" /> Get the skill
      </a>
      {guide && <a href={SKILL_GUIDE_URL} target="_blank" rel="noreferrer" title="Installing it, and using it on a screenplay">How to use it</a>}
    </span>
  );
}
