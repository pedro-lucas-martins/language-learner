import { describe, expect, it } from "vitest";

import type { ServerMsg, UserInfo } from "../protocol.ts";
import { chatReducer, initialChatState, type ChatState } from "./state.ts";

const user: UserInfo = {
  name: "Pedro",
  native_lang: "pt-BR",
  ui_lang: "pt-BR",
  correct_in_chat: true,
  user_facts: "",
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
        llm_calls_today: 12,
        llm_calls_cap: 1200,
        stt_seconds_today: 30.5,
        stt_seconds_cap: 3600,
        tts_chars_today: 900,
        tts_chars_cap: 45000,
      },
    );
    expect(s.user?.level).toBe("B2");
    expect(s.usage).toEqual({
      monthUsdEst: 1.5,
      budgetUsd: 15,
      ttsProvider: "google",
      ttsCharsMonth: 0,
      ttsCharsAllowance: 1_000_000,
      llmCallsToday: 12,
      llmCallsCap: 1200,
      sttSecondsToday: 30.5,
      sttSecondsCap: 3600,
      ttsCharsToday: 900,
      ttsCharsCap: 45000,
    });
  });

  it("stores the last turn's metrics", () => {
    const s = apply(initialChatState, {
      type: "metrics",
      message_id: "a1",
      stt_ms: 1600,
      llm_first_token_ms: 2600,
      first_audio_ms: 3500,
      total_ms: 4600,
    });
    expect(s.metrics).toEqual({
      sttMs: 1600,
      llmFirstTokenMs: 2600,
      firstAudioMs: 3500,
      totalMs: 4600,
    });
  });

  it("interrupted ends streaming and the wait for a reply", () => {
    const s = apply(
      initialChatState,
      { type: "transcript", message_id: "u1", text: "Hej" },
      { type: "ai_text_delta", message_id: "a1", delta: "Cze" },
      { type: "interrupted", message_id: "a1" },
    );
    expect(s.awaitingReply).toBe(false);
    expect(s.messages[1]).toMatchObject({ text: "Cze", streaming: false });
  });

  it("stores feedback per message and a regrade replaces it", () => {
    const first = {
      type: "feedback" as const,
      message_id: "u1",
      source: "audio" as const,
      ok: false,
      errs: [{ e: "dwa kot", c: "dwa koty", r: "plural", p: "" }],
      pron: [],
    };
    let s = apply(initialChatState, first);
    expect(s.feedback.u1?.errs[0]?.c).toBe("dwa koty");
    s = apply(s, { ...first, source: "text", ok: true, errs: [] });
    expect(s.feedback.u1).toEqual({ source: "text", ok: true, errs: [], pron: [] });
  });

  it("counts unseen corrections with mistakes until the panel is seen", () => {
    const base = {
      type: "feedback" as const,
      source: "text" as const,
      errs: [],
      pron: [],
    };
    let s = apply(
      initialChatState,
      { ...base, message_id: "u1", ok: false },
      { ...base, message_id: "u2", ok: true },
      { ...base, message_id: "u3", ok: false },
    );
    expect(s.unseenCorrections).toBe(2);
    s = chatReducer(s, { type: "corrections_seen" });
    expect(s.unseenCorrections).toBe(0);
  });

  it("edits a transcript locally before the regrade", () => {
    let s = apply(initialChatState, { type: "transcript", message_id: "u1", text: "Ja mam dwa kot" });
    s = chatReducer(s, { type: "edit_message", id: "u1", text: "Ja mam dwa koty" });
    expect(s.messages[0]?.text).toBe("Ja mam dwa koty");
  });

  it("keeps the last pron_result per message and word", () => {
    const s = apply(initialChatState, {
      type: "pron_result",
      message_id: "u1",
      word: "łóżko",
      better: true,
      tip: "Bom!",
    });
    expect(s.pronResults["u1|łóżko"]).toEqual({ better: true, tip: "Bom!" });
  });

  it("tracks the turn phase for the thinking indicator", () => {
    let s = chatReducer(initialChatState, { type: "sent", voice: true });
    expect(s.phase).toBe("transcribing");
    s = apply(s, { type: "transcript", message_id: "u1", text: "Oi" });
    expect(s.phase).toBe("thinking");
    s = apply(s, { type: "ai_text_delta", message_id: "a1", delta: "Ol" });
    expect(s.phase).toBe("idle");

    s = chatReducer(s, { type: "sent" });
    expect(s.phase).toBe("thinking");
    s = apply(s, { type: "error", code: "provider_unavailable", message: "x" });
    expect(s.phase).toBe("idle");
  });

  it("adds a suggested topic as an AI message", () => {
    const s = apply(initialChatState, { type: "topic", message_id: "t1", text: "Você gosta de praia?" });
    expect(s.messages).toEqual([{ id: "t1", role: "ai", text: "Você gosta de praia?", streaming: false }]);
    expect(s.awaitingReply).toBe(false);
  });
});

