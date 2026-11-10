/**
 * Backend URLs. In development they default to the local backend; in production
 * they must be set as Vercel environment variables (VITE_API_URL, VITE_WS_URL).
 */
const DEFAULT_API_URL = "http://localhost:8000";

/** Turn http(s)://host into ws(s)://host, so only VITE_API_URL is strictly required. */
export function deriveWsUrl(apiUrl: string): string {
  return apiUrl.replace(/^http(s?):\/\//, "ws$1://").replace(/\/+$/, "");
}

export const API_URL: string = (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");

export const WS_URL: string = import.meta.env.VITE_WS_URL ?? deriveWsUrl(API_URL);
