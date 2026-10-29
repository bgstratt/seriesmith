// A clip out of line with the rest of its sequence (the episode status's
// `cut.look_off`: brighter or darker, flatter or punchier, a cast, more or less
// colourful; seriesmith/color.py out_of_line): a small mark on its timeline
// clip, three colour circles in a ring, saying what's off.

export function lookOffTitle(off: string[], shot: string): string {
  return `${shot}'s colour is out of line with the rest of its sequence: ${off.join(", ")}.\n`
    + "Set its colour in the inspector (In the cut), or right-click the clip that looks right: "
    + "Match the sequence's colour to this.";
}

export function LookBadge({ off, shot }: { off: string[]; shot: string }) {
  return (
    <span className="h3-look-off" title={lookOffTitle(off, shot)} aria-label="colour out of line">
      <svg width={13} height={13} viewBox="0 0 26 26" aria-hidden>
        <circle cx={13} cy={13} r={12} fill="none" stroke="currentColor" strokeWidth={2} />
        <g style={{ mixBlendMode: "screen" }}>
          <circle cx={13} cy={9.5} r={5.2} fill="#ff3b3b" />
          <circle cx={9.6} cy={15.4} r={5.2} fill="#3bdc5a" />
          <circle cx={16.4} cy={15.4} r={5.2} fill="#3b7bff" />
        </g>
      </svg>
    </span>
  );
}
