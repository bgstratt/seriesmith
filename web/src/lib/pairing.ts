// Pairing another device (server/pairing.py): the PC makes a code in Settings, the device's
// editor asks for it once, and its cookie keeps it paired.
import { api } from "../host";

export interface PairStatus {
  local: boolean;
  paired: boolean;
}

export interface PairCode {
  code: string;
  expires: number;
  seconds: number;
}

export interface Device {
  id: string;
  name: string;
  added: number;
  seen: number;
  address: string;
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await api().fetch(path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${r.status}`);
  return data as T;
}

/** Whether this device may use the editor, or must pair first. An older server, without
 * pairing, answers 404: everything is open there, as it always was. */
export async function pairStatus(): Promise<PairStatus> {
  try {
    return await call<PairStatus>("/seriesmith/pair");
  } catch {
    return { local: false, paired: true };
  }
}

export const pairDevice = (code: string, name: string) => call<{ paired: boolean }>("/seriesmith/pair", { code, name });
export const makeCode = () => call<PairCode>("/seriesmith/pair/code", {});
export const listDevices = () => call<{ devices: Device[] }>("/seriesmith/devices").then((d) => d.devices);
export const removeDevice = (id: string) =>
  call<{ devices: Device[] }>("/seriesmith/devices/remove", { id }).then((d) => d.devices);

/** A name for this device, from its browser: "Chrome on Windows", "Safari on iPhone". */
export function deviceName(ua: string = navigator.userAgent): string {
  const os = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android"
    : /Mac OS X/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "A browser";
  return os ? `${browser} on ${os}` : browser;
}
