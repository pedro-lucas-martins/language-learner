import { describe, expect, it } from "vitest";

import { pickMime } from "./recorder.ts";

describe("pickMime", () => {
  it("prefers webm/opus, then mp4, then aac (SPEC §6)", () => {
    expect(pickMime(() => true)).toBe("audio/webm;codecs=opus");
    expect(pickMime((m) => m !== "audio/webm;codecs=opus")).toBe("audio/mp4");
    expect(pickMime((m) => m === "audio/aac")).toBe("audio/aac");
    expect(pickMime(() => false)).toBeNull();
  });
});
