import {
  CLOSE_FORBIDDEN_ORIGIN,
  CLOSE_UNAUTHORIZED,
  type GrammarError,
  type PronIssue,
  type ServerMsg,
  type UserInfo,
} from "../protocol.ts";

/** Track 2 result for one of the learner's messages (SPEC §5). */
export interface Feedback {
  source: "audio" | "text";
  ok: boolean;
  errs: GrammarError[];
  pron: PronIssue[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "ai";
  text: string;
  /** True while the AI reply is still streaming in. */
  streaming: boolean;
}

export type ConnectionStatus = "connecting" | "ready" | "closed";
/** What the server is doing for the current turn, for the "thinking" indicator. */
export type TurnPhase = "idle" | "transcribing" | "thinking";
export type CloseReason = "unauthorized" | "origin" | "network";

export interface Usage {
  monthUsdEst: number;
  budgetUsd: number;
  ttsProvider: string;
  ttsCharsMonth: number;
  ttsCharsAllowance: number;
  llmCallsToday: number;
  llmCallsCap: number;
  sttSecondsToday: number;
  sttSecondsCap: number;
  ttsCharsToday: number;
  ttsCharsCap: number;
}

/** Last turn's timings in ms (SPEC §6), shown as measured values, never as targets. */
export interface Metrics {
  sttMs: number | null;
  llmFirstTokenMs: number | null;
  firstAudioMs: number | null;
  totalMs: number;
}

export interface ChatState {
  status: ConnectionStatus;
  closeReason: CloseReason | null;
  user: UserInfo | null;
  messages: ChatMessage[];
  /** A message was sent and the turn has not finished yet. */
  awaitingReply: boolean;
  phase: TurnPhase;
  error: string | null;
  usage: Usage | null;
  metrics: Metrics | null;
  /** Feedback by learner message id; a regrade replaces the entry. */
  feedback: Record<string, Feedback>;
  /** Last pron_retry verdict per "messageId|word". */
  pronResults: Record<string, { better: boolean; tip: string }>;
  /** Corrections with mistakes that arrived since the panel was last looked at. */
  unseenCorrections: number;
}

export type ChatAction =
  | { type: "connecting" }
  | { type: "server"; msg: ServerMsg }
  | { type: "closed"; code: number }
  | { type: "sent"; voice?: boolean }
  | { type: "dismiss_error" }
  /** The learner fixed a transcript (a regrade follows). */
  | { type: "edit_message"; id: string; text: string }
  | { type: "corrections_seen" };

export const initialChatState: ChatState = {
  status: "connecting",
  closeReason: null,
  user: null,
  messages: [],
  awaitingReply: false,
  phase: "idle",
  error: null,
  usage: null,
  metrics: null,
  feedback: {},
  pronResults: {},
  unseenCorrections: 0,
};

function finishStreaming(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((m) => (m.streaming ? { ...m, streaming: false } : m));
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "connecting":
      return { ...state, status: "connecting", closeReason: null, error: null };

    case "closed": {
      const closeReason: CloseReason =
        action.code === CLOSE_UNAUTHORIZED
          ? "unauthorized"
          : action.code === CLOSE_FORBIDDEN_ORIGIN
            ? "origin"
            : "network";
      return {
        ...state,
        status: "closed",
        closeReason,
        awaitingReply: false,
        phase: "idle",
        messages: finishStreaming(state.messages),
      };
    }

    case "sent":
      return {
        ...state,
        awaitingReply: true,
        phase: action.voice ? "transcribing" : "thinking",
        error: null,
      };

    case "dismiss_error":
      return { ...state, error: null };

    case "edit_message":
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === action.id ? { ...m, text: action.text } : m)),
      };

    case "corrections_seen":
      return { ...state, unseenCorrections: 0 };

    case "server":
      return applyServerMsg(state, action.msg);
  }
}

function applyServerMsg(state: ChatState, msg: ServerMsg): ChatState {
  switch (msg.type) {
    case "ready":
      return { ...state, status: "ready", closeReason: null, user: msg.user };

    case "user_updated":
      return { ...state, user: msg.user };

    case "transcript":
      return {
        ...state,
        awaitingReply: true,
        phase: "thinking",
        messages: [
          ...state.messages,
          { id: msg.message_id, role: "user", text: msg.text, streaming: false },
        ],
      };

    case "topic":
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: msg.message_id, role: "ai", text: msg.text, streaming: false },
        ],
      };

    case "ai_text_delta": {
      const index = state.messages.findIndex((m) => m.id === msg.message_id);
      if (index === -1) {
        return {
          ...state,
          phase: "idle",
          messages: [
            ...state.messages,
            { id: msg.message_id, role: "ai", text: msg.delta, streaming: true },
          ],
        };
      }
      const messages = state.messages.slice();
      const current = messages[index]!;
      messages[index] = { ...current, text: current.text + msg.delta };
      return { ...state, messages };
    }

    case "ai_text_done": {
      const exists = state.messages.some((m) => m.id === msg.message_id);
      const done: ChatMessage = { id: msg.message_id, role: "ai", text: msg.text, streaming: false };
      return {
        ...state,
        awaitingReply: false,
        phase: "idle",
        messages: exists
          ? state.messages.map((m) => (m.id === msg.message_id ? done : m))
          : [...state.messages, done],
      };
    }

    case "usage":
      return {
        ...state,
        usage: {
          monthUsdEst: msg.month_usd_est,
          budgetUsd: msg.budget_usd,
          ttsProvider: msg.tts_provider_active,
          ttsCharsMonth: msg.tts_chars_month,
          ttsCharsAllowance: msg.tts_chars_allowance,
          llmCallsToday: msg.llm_calls_today ?? 0,
          llmCallsCap: msg.llm_calls_cap ?? 0,
          sttSecondsToday: msg.stt_seconds_today ?? 0,
          sttSecondsCap: msg.stt_seconds_cap ?? 0,
          ttsCharsToday: msg.tts_chars_today ?? 0,
          ttsCharsCap: msg.tts_chars_cap ?? 0,
        },
      };

    case "interrupted":
      return {
        ...state,
        awaitingReply: false,
        phase: "idle",
        messages: finishStreaming(state.messages),
      };

    case "metrics":
      return {
        ...state,
        metrics: {
          sttMs: msg.stt_ms,
          llmFirstTokenMs: msg.llm_first_token_ms,
          firstAudioMs: msg.first_audio_ms,
          totalMs: msg.total_ms,
        },
      };

    case "feedback":
      return {
        ...state,
        unseenCorrections: state.unseenCorrections + (msg.ok ? 0 : 1),
        feedback: {
          ...state.feedback,
          [msg.message_id]: { source: msg.source, ok: msg.ok, errs: msg.errs, pron: msg.pron },
        },
      };

    case "pron_result":
      return {
        ...state,
        pronResults: {
          ...state.pronResults,
          [`${msg.message_id}|${msg.word}`]: { better: msg.better, tip: msg.tip },
        },
      };

    // Audio frames are handled by the voice layer (player), not this reducer.
    case "audio_meta":
    case "tts_fallback":
      return state;

    case "error":
      return {
        ...state,
        awaitingReply: false,
        phase: "idle",
        error: msg.message,
        messages: finishStreaming(state.messages),
      };
  }
}
