import { describe, expect, it } from "vitest";

import { MAX_AUTO_RETRIES, retryDelayMs } from "./useChatSocket.ts";

describe("automatic reconnect while the server wakes up", () => {
  it("backs off 1 s, 2 s, 4 s and caps at 10 s", () => {
    expect([0, 1, 2, 3, 4, 7].map(retryDelayMs)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });

  it("keeps trying for at least one minute", () => {
    let total = 0;
    for (let n = 0; n < MAX_AUTO_RETRIES; n++) total += retryDelayMs(n);
    expect(total).toBeGreaterThanOrEqual(60_000);
  });
});
