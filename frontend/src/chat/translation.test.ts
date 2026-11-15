import { describe, expect, it } from "vitest";

import { parseServerMsg } from "../protocol.ts";
import { chatReducer, initialChatState } from "./state.ts";

describe("🌐 translations", () => {
  it("marks a request as pending, then stores the translation", () => {
    let s = chatReducer(initialChatState, { type: "translate_requested", id: "m1" });
    expect(s.translating).toEqual({ m1: true });
    s = chatReducer(s, {
      type: "server",
      msg: { type: "translation", message_id: "m1", text: "Cześć!", lang: "pl-PL" },
    });
    expect(s.translating).toEqual({});
    expect(s.translations.m1).toEqual({ text: "Cześć!", lang: "pl-PL" });
  });

  it("an error or a closed socket drops pending requests but keeps finished ones", () => {
    let s = chatReducer(initialChatState, {
      type: "server",
      msg: { type: "translation", message_id: "m1", text: "Oi", lang: "pt-BR" },
    });
    s = chatReducer(s, { type: "translate_requested", id: "m2" });
    const afterError = chatReducer(s, {
      type: "server",
      msg: { type: "error", code: "quota_exceeded", message: "limit" },
    });
    expect(afterError.translating).toEqual({});
    expect(afterError.translations.m1?.text).toBe("Oi");
    expect(chatReducer(s, { type: "closed", code: 1006 }).translating).toEqual({});
  });

  it("parses the server message", () => {
    const raw = JSON.stringify({ type: "translation", message_id: "m1", text: "x", lang: "pl-PL" });
    expect(parseServerMsg(raw)?.type).toBe("translation");
  });
});
