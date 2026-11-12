/**
 * Backend URLs. In development they default to the local backend; in production
 * they must be set as Vercel environment variables (VITE_API_URL, VITE_WS_URL).
 * In "lan" mode (`npm run dev:lan`) the Vite proxy serves the API on the page's own
 * HTTPS origin, so the URLs are derived from `window.location`.
 */
const DEFAULT_API_URL = "http://localhost:8000";

/** Turn http(s)://host into ws(s)://host, so only VITE_API_URL is strictly required. */
export function deriveWsUrl(apiUrl: string): string {
  return apiUrl.replace(/^http(s?):\/\//, "ws$1://").replace(/\/+$/, "");
}

const SAME_ORIGIN = import.meta.env.MODE === "lan" && typeof window !== "undefined";

export const API_URL: string = SAME_ORIGIN
  ? window.location.origin
  : (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");

export const WS_URL: string = SAME_ORIGIN
  ? deriveWsUrl(window.location.origin)
  : (import.meta.env.VITE_WS_URL ?? deriveWsUrl(API_URL));
