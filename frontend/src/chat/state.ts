import {
  CLOSE_FORBIDDEN_ORIGIN,
  CLOSE_UNAUTHORIZED,
  type ServerMsg,
  type UserInfo,
} from "../protocol.ts";

export interface ChatMessage {
  id: string;
  role: "user" | "ai";
  text: string;
  /** True while the AI reply is still streaming in. */
  streaming: boolean;
}

export type ConnectionStatus = "connecting" | "ready" | "closed";
export type CloseReason = "unauthorized" | "origin" | "network";

export interface Usage {
  monthUsdEst: number;
  budgetUsd: number;
}

export interface ChatState {
  status: ConnectionStatus;
  closeReason: CloseReason | null;
  user: UserInfo | null;
  messages: ChatMessage[];
  /** A message was sent and the turn has not finished yet. */
  awaitingReply: boolean;
  error: string | null;
  usage: Usage | null;
}

export type ChatAction =
  | { type: "connecting" }
  | { type: "server"; msg: ServerMsg }
  | { type: "closed"; code: number }
  | { type: "sent" }
  | { type: "dismiss_error" };

export const initialChatState: ChatState = {
  status: "connecting",
  closeReason: null,
  user: null,
  messages: [],
  awaitingReply: false,
  error: null,
  usage: null,
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
        messages: finishStreaming(state.messages),
      };
    }

    case "sent":
      return { ...state, awaitingReply: true, error: null };

    case "dismiss_error":
      return { ...state, error: null };

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
        messages: [
          ...state.messages,
          { id: msg.message_id, role: "user", text: msg.text, streaming: false },
        ],
      };

    case "ai_text_delta": {
      const index = state.messages.findIndex((m) => m.id === msg.message_id);
      if (index === -1) {
        return {
          ...state,
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
        messages: exists
          ? state.messages.map((m) => (m.id === msg.message_id ? done : m))
          : [...state.messages, done],
      };
    }

    case "usage":
      return {
        ...state,
        usage: { monthUsdEst: msg.month_usd_est, budgetUsd: msg.budget_usd },
      };

    case "error":
      return {
        ...state,
        awaitingReply: false,
        error: msg.message,
        messages: finishStreaming(state.messages),
      };
  }
}
