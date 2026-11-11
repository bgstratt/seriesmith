// What a render asks when one of its takes fails its checks (a cut it wasn't asked for, its
// words): new seeds, then the model's first-and-last-frame version from the failed take's
// first frame (seriesmith/retries.py). Kept for the session; local renders only.

import { setRenderRetry } from "../actions";
import { useApp } from "../store";

export function RetryRow() {
  const retry = useApp((s) => s.renderRetry);
  const backends = useApp((s) => s.backends);
  // the retries are steps on seriesmith's own queue: a host without one can't run them
  if (!backends) return null;
  return (
    <div className="h3-target-row" title={"When a take fails its checks (a cut it wasn't asked for, words that don't match its lines), "
      + "render it again: a new seed each time, then once on the model's first-and-last-frame version (H3 Ref2VA to H3 FL2VA), "
      + "from the failed take's first frame as its first keyframe. Never once a take is picked in the cut; local renders only."}>
      <span className="h3-h">If a take fails its checks</span>
      <select className="h3-in" value={retry.tries} onChange={(e) => setRenderRetry({ ...retry, tries: Number(e.target.value) })}>
        <option value={0}>no new seeds</option>
        {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} new seed{n === 1 ? "" : "s"}</option>)}
      </select>
      <label className="h3-check h3-small">
        <input type="checkbox" checked={retry.fallback} onChange={(e) => setRenderRetry({ ...retry, fallback: e.target.checked })} />
        then from its first frame (FL2VA)
      </label>
    </div>
  );
}
