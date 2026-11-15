import { clampVolume, DEFAULT_VOLUME } from "./audio/player.ts";

/** localStorage can be missing or throw (private mode, blocked storage): never let it crash. */

const TOKEN_KEY = "ll.token";

export function loadToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Not persisted: the user will have to log in again next time.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

const LISTEN_KEY = "ll.listenMode";

/** Listening mode (AI text blurred until tapped) is a per-browser preference. */
export function loadListenMode(): boolean {
  try {
    return window.localStorage.getItem(LISTEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveListenMode(on: boolean): void {
  try {
    window.localStorage.setItem(LISTEN_KEY, on ? "1" : "0");
  } catch {
    // Not persisted: the default (off) comes back next time.
  }
}

const VOLUME_KEY = "ll.voiceVolume";

/** AI voice volume (0–2, 1 = as received), per browser like listening mode. */
export function loadVoiceVolume(): number {
  try {
    const raw = window.localStorage.getItem(VOLUME_KEY);
    return raw === null ? DEFAULT_VOLUME : clampVolume(Number(raw));
  } catch {
    return DEFAULT_VOLUME;
  }
}

export function saveVoiceVolume(value: number): void {
  try {
    window.localStorage.setItem(VOLUME_KEY, String(clampVolume(value)));
  } catch {
    // Not persisted: 100 % comes back next time.
  }
}
