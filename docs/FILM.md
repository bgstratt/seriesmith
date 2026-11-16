# A film: a show's episodes joined as one cut

*Shelved (2026-11-16). A show's episodes are joined outside seriesmith, in an NLE. Planned the same day from One
Horse Open Sleigh (four acts and nine musical numbers, 984 shots), and set aside.*

## Decided (2026-11-16): joining episodes stays outside seriesmith

A long piece is made as episodes: an act of a couple of hundred shots keeps the editor quick, and a musical number
is an episode of its own (MUSICAL_NUMBERS.md). The plan was a `film.json` in the show folder, with the episodes in
order and a join between each: a number's band intro started under the act's last lines (prelap), a score's tail
carried past the cut (overlap), a picture dissolve, the titles and the loudness once for the whole film, and a Film
window in the Shots tab's More menu.

Set aside, because that's an NLE's work done half-way. seriesmith's finishing is a light touch over the renders
(an episode's titles, its four-track mix, its loudness) for those who don't take it further. Anyone joining a
show into one film is finishing it in Resolve or Premiere, which already does all of it better: joins, overlaps,
crossfades, the loudness of the whole, the titles once. The design would have needed each export's loudness
gain undone, join previews, routes, a window: a lot, and still short of an editor.

A number in the middle of an act's script is out for the same reason it was on 2026-11-15
(MUSICAL_NUMBERS.md): two kinds of sound in one episode, and align over part of it. Where a number goes is the
act's `// song:` line; that order is all the NLE needs.

## What seriesmith gives the NLE

- Each episode's export, its stems beside it in `<cut>_stems/`: one per mix track (the four defaults, or up to
  16 of the mix's own `track_list`: a second music track, a walla track), `me.wav` and `mix.wav`.
- Each episode's timeline, `assemble --xml` (FCP7 XML).
- A number's whole song, `audio/song_full.wav`, beside the cut recording, for a prelap: laid under the act's last
  lines in the NLE.

## If it comes back

The small piece worth having is `assemble --xml` writing several episodes in order as one timeline, with a marker
at each. It's an addition to `nle_xml`, not a feature of its own. Not planned.
