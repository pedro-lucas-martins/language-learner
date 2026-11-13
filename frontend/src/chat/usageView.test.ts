import { describe, expect, it } from "vitest";

import { level, providerName, share } from "./usageView.ts";

describe("usage helpers", () => {
  it("computes a bounded share and ignores missing limits", () => {
    expect(share(50, 100)).toBe(0.5);
    expect(share(150, 100)).toBe(1);
    expect(share(10, 0)).toBe(0);
  });

  it("colors by how close to the limit", () => {
    expect(level(0.5)).toBe("ok");
    expect(level(0.8)).toBe("warn");
    expect(level(0.96)).toBe("alert");
  });

  it("names providers", () => {
    const fallbacks = { edge: "E", browser: "B" };
    expect(providerName("elevenlabs", fallbacks)).toBe("ElevenLabs");
    expect(providerName("edge", fallbacks)).toBe("E");
    expect(providerName("xyz", fallbacks)).toBe("xyz");
  });
});
