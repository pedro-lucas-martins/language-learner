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
