// Pairing another device: the form a device that isn't paired yet sees in place of the
// editor, and Settings' "Other devices" card on the PC (a code to pair with, the paired
// devices, Remove).
import { useEffect, useState } from "react";
import { deviceName, listDevices, makeCode, pairDevice, pairStatus, removeDevice, type Device, type PairCode } from "../lib/pairing";

/** The editor on a device that isn't paired: the code from the PC, then the page again.
 * `inline`: in ComfyUI's sidebar, not over the whole page (ComfyUI's own page is ComfyUI's). */
export function PairScreen({ inline = false }: { inline?: boolean }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await pairDevice(code, deviceName());
      location.reload();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className={inline ? "h3-root h3-pair-inline" : "h3-root h3-pair"}>
      <form className="h3-card h3-pair-card" onSubmit={(e) => void submit(e)}>
        <div className="h3-card-head">
          <span className="h3-card-title h3-grow">Pair this device with seriesmith</span>
        </div>
        <span className="h3-small">
          On the PC running seriesmith, open <b>Settings → Other devices</b> and click <b>Pair a device</b>. Enter the
          code it shows. This device stays paired until it's removed there.
        </span>
        <div className="h3-row" style={{ gap: 6 }}>
          <input className="h3-in h3-mono h3-grow" inputMode="numeric" autoComplete="one-time-code" maxLength={7}
            aria-label="The code" placeholder="123456" autoFocus value={code}
            onChange={(e) => setCode(e.target.value)} />
          <button className="h3-btn h3-primary" type="submit" disabled={busy || code.replace(/\D/g, "").length !== 6}>
            {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-link" />} Pair
          </button>
        </div>
        {error && <div className="h3-small h3-err">{error}</div>}
      </form>
    </div>
  );
}

function when(seconds: number): string {
  return seconds ? new Date(seconds * 1000).toLocaleString() : "";
}

/** Settings on the PC: a code for a new device, and the paired ones. Nothing on another device. */
export function DevicesCard() {
  const [local, setLocal] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [offer, setOffer] = useState<PairCode | null>(null);
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void pairStatus().then((s) => {
      setLocal(s.local);
      if (s.local) listDevices().then(setDevices).catch((e) => setError((e as Error).message));
    });
  }, []);

  // the code's countdown; when it's used, the new device shows up in the list
  useEffect(() => {
    if (!offer) return;
    const tick = () => {
      const s = Math.max(0, Math.round(offer.expires - Date.now() / 1000));
      setLeft(s);
      if (!s) setOffer(null);
    };
    tick();
    const t = setInterval(tick, 1000);
    const poll = setInterval(() => {
      listDevices().then((d) => {
        setDevices((was) => {
          if (d.length > was.length) setOffer(null);
          return d;
        });
      }).catch(() => undefined);
    }, 3000);
    return () => {
      clearInterval(t);
      clearInterval(poll);
    };
  }, [offer]);

  if (!local) return null;
  return (
    <section className="h3-card" id="sm-set-devices">
      <div className="h3-card-head">
        <span className="h3-card-title h3-grow">Other devices</span>
        <button className="h3-btn" onClick={() => makeCode().then(setOffer).catch((e) => setError((e as Error).message))}>
          <i className="pi pi-link" /> Pair a device
        </button>
      </div>
      {offer && (
        <div className="h3-row" style={{ gap: 10, alignItems: "baseline" }}>
          <span className="h3-mono" style={{ fontSize: 26, letterSpacing: 4 }}>{offer.code.slice(0, 3)} {offer.code.slice(3)}</span>
          <span className="h3-small h3-muted">
            enter it on the device · {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} left
          </span>
        </div>
      )}
      {devices.map((d) => (
        <div key={d.id} className="h3-row" style={{ gap: 6 }}>
          <span className="h3-grow">
            {d.name} <span className="h3-small h3-muted">{d.address} · paired {when(d.added)}{d.seen ? ` · last ${when(d.seen)}` : ""}</span>
          </span>
          <button className="h3-btn h3-icon" title="Remove: it has to pair again"
            onClick={() => removeDevice(d.id).then(setDevices).catch((e) => setError((e as Error).message))}>
            <i className="pi pi-times" />
          </button>
        </div>
      ))}
      <span className="h3-small h3-muted">
        A laptop or phone on your network (run_seriesmith_ext, or Tailscale) asks for a code the first time it opens the
        editor. {devices.length ? "" : "None is paired yet."}
      </span>
      {error && <div className="h3-small h3-err">{error}</div>}
    </section>
  );
}
