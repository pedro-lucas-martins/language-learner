/**
 * WebSocket protocol (SPEC §7). Mirrors backend/app/protocol.py — change both together.
 * Slice 1 implements the text subset.
 */

export type Lang = "pt-BR" | "pl-PL";
export type Level = "A1" | "A2" | "B1" | "B2" | "C1";
export const LEVELS: readonly Level[] = ["A1", "A2", "B1", "B2", "C1"];
export type ErrorCode = "quota_exceeded" | "provider_unavailable" | "stt_failed" | "bad_request";

export const MAX_USER_TEXT = 1000;

/** WebSocket close codes used by the server. */
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_FORBIDDEN_ORIGIN = 4403;

// --- client → server ---------------------------------------------------------

export type ClientMsg =
  | { type: "auth"; token: string }
  | { type: "user_text"; text: string }
  | { type: "set_level"; level: Level };

// --- server → client ---------------------------------------------------------

export interface UserInfo {
  name: string;
  native_lang: Lang;
  target_lang: Lang;
  level: Level;
  recast_pronunciation: boolean;
}

export type ServerMsg =
  | { type: "ready"; user: UserInfo; session_id: string }
  | { type: "user_updated"; user: UserInfo }
  | { type: "transcript"; message_id: string; text: string }
  | { type: "ai_text_delta"; message_id: string; delta: string }
  | { type: "ai_text_done"; message_id: string; text: string }
  | {
      type: "usage";
      month_usd_est: number;
      budget_usd: number;
      tts_chars_month: number;
      tts_chars_allowance: number;
      tts_provider_active: string;
    }
  | { type: "error"; code: ErrorCode; message: string };

const SERVER_TYPES = new Set<ServerMsg["type"]>([
  "ready",
  "user_updated",
  "transcript",
  "ai_text_delta",
  "ai_text_done",
  "usage",
  "error",
]);

/** Parse a server frame; returns null for anything that is not a known message. */
export function parseServerMsg(raw: string): ServerMsg | null {
  try {
    const data: unknown = JSON.parse(raw);
    if (typeof data === "object" && data !== null && "type" in data) {
      const type = (data as { type: unknown }).type;
      if (typeof type === "string" && SERVER_TYPES.has(type as ServerMsg["type"])) {
        return data as ServerMsg;
      }
    }
  } catch {
    // fall through
  }
  return null;
}
