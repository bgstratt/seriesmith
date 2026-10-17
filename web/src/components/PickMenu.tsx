// A dropdown that fills a field beside it: it always reads as its label
// ("lengths", "sizes"), so its width never follows what was picked, and
// picking an option hands its value over and goes back to the label.

export function PickMenu(p: {
  label: string;
  options: { value: string; label: string }[];
  onPick: (value: string) => void;
  title?: string;
  width?: number;
}) {
  return (
    <select className="h3-in" style={{ width: p.width ?? 96 }} value="" title={p.title}
      onChange={(e) => { if (e.target.value) p.onPick(e.target.value); }}>
      <option value="" disabled>{p.label}</option>
      {p.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
