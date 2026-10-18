# LAST LIGHT: the demo episode

One screenplay scene taken all the way through seriesmith, for seriesmith.com's video and
its "page to picture" section. Every file here is a real stage's output, kept as it came
out, so the site shows what the pipeline actually did.

| Stage | File | Made by |
|---|---|---|
| 1. The screenplay | `screenplay.fountain` | by hand: spec format, about a page and a half, built to show off (motion, rain, light, faces, a strong prop, three lines of dialogue) |
| 2. The series config | `series.json` | the script-writing skill, converting the screenplay (docs/SCRIPT_CONVERSION.md) |
| 3. The episode script | `ep01.md` | the same conversion |
| 4. The pictures | `refs/` | `seriesmith refs`: Mara's and Voss's sheets, the case, the drone, a plate per rooftop angle |
| 5. The takes | `renders/` | the editor: proxies to judge the cut, then finals |
| 6. The cut | `master/` | the timeline, Master with titles |

While stages 4 to 6 run, record the editor (the Shots board filling with thumbnails, a
sheet arriving on Refs, Play all on the timeline): those recordings are the UI in the video.

Renders and masters are large; keep them out of git (the repo's `.gitignore`), and copy
the picks the site uses into the site repo's `public/` (short clips) or R2 (the full cut).
