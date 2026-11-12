import { describe, expect, it } from "vitest";

import { SentenceAssembler, type AudioMeta } from "./assembler.ts";

const meta = (sentence: number, seq: number, final: boolean, id = "a1"): AudioMeta => ({
  type: "audio_meta",
  message_id: id,
  seq,
  sentence,
  mime: "audio/ogg;codecs=opus",
  final,
});
const bytes = (...values: number[]) => new Uint8Array(values).buffer;

describe("SentenceAssembler", () => {
  it("joins chunks and releases the sentence on the final chunk", () => {
    const a = new SentenceAssembler();
    a.meta(meta(0, 0, false));
    expect(a.chunk(bytes(1, 2))).toBeNull();
    a.meta(meta(0, 1, true));
    const done = a.chunk(bytes(3));
    expect(done?.sentence).toBe(0);
    expect(done?.mime).toBe("audio/ogg;codecs=opus");
    expect(done?.parts.map((p) => [...new Uint8Array(p)])).toEqual([[1, 2], [3]]);
  });

  it("keeps sentences apart", () => {
    const a = new SentenceAssembler();
    a.meta(meta(0, 0, false));
    a.chunk(bytes(1));
    a.meta(meta(1, 1, true));
    expect(a.chunk(bytes(9))?.sentence).toBe(1);
    a.meta(meta(0, 2, true));
    expect(a.chunk(bytes(2))?.parts).toHaveLength(2);
  });

  it("ignores a binary frame without audio_meta", () => {
    const a = new SentenceAssembler();
    expect(a.chunk(bytes(1))).toBeNull();
    a.meta(meta(0, 0, true));
    a.chunk(bytes(1));
    expect(a.chunk(bytes(2))).toBeNull(); // the meta was consumed by the previous chunk
  });

  it("reset drops partial sentences", () => {
    const a = new SentenceAssembler();
    a.meta(meta(0, 0, false));
    a.chunk(bytes(1));
    a.reset();
    a.meta(meta(0, 1, true));
    expect(a.chunk(bytes(2))?.parts).toHaveLength(1);
  });
});
