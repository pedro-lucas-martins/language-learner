import { describe, expect, it } from "vitest";

import { deriveWsUrl } from "./config.ts";

describe("deriveWsUrl", () => {
  it("maps http to ws", () => {
    expect(deriveWsUrl("http://localhost:8000")).toBe("ws://localhost:8000");
  });

  it("maps https to wss", () => {
    expect(deriveWsUrl("https://api.example.com")).toBe("wss://api.example.com");
  });

  it("drops trailing slashes", () => {
    expect(deriveWsUrl("https://api.example.com/")).toBe("wss://api.example.com");
  });
});
