import { describe, expect, it } from "vitest";

import type { ServerMsg, UserInfo } from "../protocol.ts";
import { chatReducer, initialChatState, type ChatState } from "./state.ts";

const user: UserInfo = {
  name: "Pedro",
  native_lang: "pt-BR",
  target_lang: "pl-PL",
  level: "A1",
  recast_pronunciation: true,
};

function apply(state: ChatState, ...msgs: ServerMsg[]): ChatState {
  return msgs.reduce((s, msg) => chatReducer(s, { type: "server", msg }), state);
}

describe("chatReducer", () => {
  it("becomes ready with the user", () => {
    const s = apply(initialChatState, { type: "ready", user, session_id: "s1" });
    expect(s.status).toBe("ready");
    expect(s.user?.name).toBe("Pedro");
  });

  it("streams an AI reply and finishes it", () => {
    let s = chatReducer(initialChatState, { type: "sent" });
    expect(s.awaitingReply).toBe(true);
    s = apply(
      s,
      { type: "transcript", message_id: "u1", text: "Cześć" },
      { type: "ai_text_delta", message_id: "a1", delta: "Hej" },
      { type: "ai_text_delta", message_id: "a1", delta: "!" },
    );
    expect(s.messages).toEqual([
      { id: "u1", role: "user", text: "Cześć", streaming: false },
      { id: "a1", role: "ai", text: "Hej!", streaming: true },
    ]);
    expect(s.awaitingReply).toBe(true);

    s = apply(s, { type: "ai_text_done", message_id: "a1", text: "Hej! Co słychać?" });
    expect(s.messages[1]).toEqual({
      id: "a1",
      role: "ai",
      text: "Hej! Co słychać?",
      streaming: false,
    });
    expect(s.awaitingReply).toBe(false);
  });

  it("shows errors and stops waiting / streaming", () => {
    let s = apply(
      chatReducer(initialChatState, { type: "sent" }),
      { type: "transcript", message_id: "u1", text: "Oi" },
      { type: "ai_text_delta", message_id: "a1", delta: "Ol" },
      { type: "error", code: "provider_unavailable", message: "IA indisponível" },
    );
    expect(s.error).toBe("IA indisponível");
    expect(s.awaitingReply).toBe(false);
    expect(s.messages.every((m) => !m.streaming)).toBe(true);
    s = chatReducer(s, { type: "dismiss_error" });
    expect(s.error).toBeNull();
  });

  it("maps close codes to reasons", () => {
    expect(chatReducer(initialChatState, { type: "closed", code: 4401 }).closeReason).toBe(
      "unauthorized",
    );
    expect(chatReducer(initialChatState, { type: "closed", code: 4403 }).closeReason).toBe(
      "origin",
    );
    expect(chatReducer(initialChatState, { type: "closed", code: 1006 }).closeReason).toBe(
      "network",
    );
  });

  it("updates level and usage", () => {
    const s = apply(
      initialChatState,
      { type: "ready", user, session_id: "s1" },
      { type: "user_updated", user: { ...user, level: "B2" } },
      {
        type: "usage",
        month_usd_est: 1.5,
        budget_usd: 15,
        tts_chars_month: 0,
        tts_chars_allowance: 1_000_000,
        tts_provider_active: "google",
      },
    );
    expect(s.user?.level).toBe("B2");
    expect(s.usage).toEqual({ monthUsdEst: 1.5, budgetUsd: 15 });
  });
});
