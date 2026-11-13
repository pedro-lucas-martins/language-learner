/**
 * WebSocket protocol (SPEC §7). Mirrors backend/app/protocol.py — change both together.
 * Slice 2 adds voice: audio in, audio out (binary frames after `audio_meta`), barge-in, metrics.
 */

export type Lang = "pt-BR" | "pl-PL";
export type Level = "A1" | "A2" | "B1" | "B2" | "C1";
export const LEVELS: readonly Level[] = ["A1", "A2", "B1", "B2", "C1"];
export type ErrorCode = "quota_exceeded" | "provider_unavailable" | "stt_failed" | "bad_request";

export const MAX_USER_TEXT = 1000;
export const MAX_MIME = 100;

/** WebSocket close codes used by the server. */
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_FORBIDDEN_ORIGIN = 4403;

// --- client → server ---------------------------------------------------------

export type ClientMsg =
  | { type: "auth"; token: string }
  | { type: "user_text"; text: string }
  | { type: "set_level"; level: Level }
  | { type: "regrade"; message_id: string; text: string }
  | { type: "set_recast"; enabled: boolean }
  | { type: "speak_word"; word: string }
  | { type: "set_ui_lang"; ui_lang: Lang }
  | { type: "set_correction"; enabled: boolean }
  | { type: "suggest_topic" }
  | { type: "set_theme"; theme: string }
  | { type: "set_facts"; text: string }
  | {
      type: "start_of_speech";
      mime: string;
      purpose: "utterance" | "pron_retry";
      target_word?: string;
      message_id?: string;
    }
  | { type: "end_of_speech" }
  | { type: "user_started_speaking" };

// --- server → client ---------------------------------------------------------

export interface UserInfo {
  name: string;
  native_lang: Lang;
  target_lang: Lang;
  /** Interface and explanation language (defaults to native_lang on the server). */
  ui_lang: Lang;
  level: Level;
  recast_pronunciation: boolean;
  /** Correction in the conversation (SPEC §4.1). */
  correct_in_chat: boolean;
  /** What the AI remembers about the learner (SPEC §4.3), ≤100 words. */
  user_facts: string;
}

/** One grammar mistake (SPEC §5); explanations are in the learner's native language. */
export interface GrammarError {
  /** The wrong substring, as written/said. */
  e: string;
  /** Corrected form. */
  c: string;
  /** Short rule. */
  r: string;
  /** PT⇄PL contrast tip (may be empty). */
  p: string;
}

export interface PronIssue {
  w: string;
  heard: string;
  tip: string;
  sev: "major" | "minor";
}

export type ServerMsg =
  | { type: "ready"; user: UserInfo; session_id: string }
  | { type: "user_updated"; user: UserInfo }
  | { type: "transcript"; message_id: string; text: string }
  /** A suggested topic: an AI message picked from a list, no LLM call (SPEC §8). */
  | { type: "topic"; message_id: string; text: string }
  | { type: "ai_text_delta"; message_id: string; delta: string }
  | { type: "ai_text_done"; message_id: string; text: string }
  | {
      /** Precedes every binary audio frame; `final` marks the last chunk of a sentence. */
      type: "audio_meta";
      message_id: string;
      seq: number;
      sentence: number;
      mime: string;
      final: boolean;
    }
  | { type: "tts_fallback"; message_id: string; sentence: number; text: string; lang: Lang }
  | { type: "interrupted"; message_id: string }
  | {
      type: "metrics";
      message_id: string;
      stt_ms: number | null;
      llm_first_token_ms: number | null;
      first_audio_ms: number | null;
      total_ms: number;
    }
  | {
      type: "usage";
      month_usd_est: number;
      budget_usd: number;
      tts_chars_month: number;
      tts_chars_allowance: number;
      /** The provider that will actually speak (active, backup or a fallback). */
      tts_provider_active: string;
      /** Today vs the daily caps (0 = no cap). */
      llm_calls_today: number;
      llm_calls_cap: number;
      stt_seconds_today: number;
      stt_seconds_cap: number;
      tts_chars_today: number;
      tts_chars_cap: number;
    }
  | {
      type: "feedback";
      message_id: string;
      source: "audio" | "text";
      ok: boolean;
      errs: GrammarError[];
      pron: PronIssue[];
    }
  | { type: "pron_result"; message_id: string; word: string; better: boolean; tip: string }
  | { type: "error"; code: ErrorCode; message: string };

const SERVER_TYPES = new Set<ServerMsg["type"]>([
  "ready",
  "user_updated",
  "transcript",
  "topic",
  "ai_text_delta",
  "ai_text_done",
  "audio_meta",
  "tts_fallback",
  "interrupted",
  "metrics",
  "feedback",
  "pron_result",
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
