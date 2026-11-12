import { describe, expect, it } from "vitest";

import { correctionEntries, splitMarked } from "./corrections.ts";
import type { ChatMessage, Feedback } from "./state.ts";

const msg = (id: string, role: "user" | "ai", text = id): ChatMessage => ({
  id,
  role,
  text,
  streaming: false,
});
const ok: Feedback = { source: "text", ok: true, errs: [], pron: [] };

describe("correctionEntries", () => {
  it("lists only the learner's messages with feedback, newest first", () => {
    const messages = [msg("u1", "user"), msg("a1", "ai"), msg("u2", "user"), msg("u3", "user")];
    const entries = correctionEntries(messages, { u1: ok, u3: ok, a1: ok });
    expect(entries.map((e) => e.message.id)).toEqual(["u3", "u1"]);
  });
});

describe("splitMarked", () => {
  it("splits a card front around the «marked» mistake", () => {
    expect(splitMarked("Ja mam «dwa kot» w domu.")).toEqual([
      { text: "Ja mam ", marked: false },
      { text: "dwa kot", marked: true },
      { text: " w domu.", marked: false },
    ]);
  });

  it("handles a front that is only the mark or has no mark", () => {
    expect(splitMarked("«de a»")).toEqual([{ text: "de a", marked: true }]);
    expect(splitMarked("pão")).toEqual([{ text: "pão", marked: false }]);
  });
});
