import { describe, expect, it } from "vitest";

import { OwnRecordings, ownKey } from "./ownRecordings.ts";

const blob = (text: string) => new Blob([text], { type: "audio/webm" });

describe("OwnRecordings", () => {
  it("gives each transcript the oldest pending recording", async () => {
    const own = new OwnRecordings();
    own.sent(blob("first"));
    own.sent(blob("second"));
    expect(await own.transcript()?.text()).toBe("first");
    expect(await own.transcript()?.text()).toBe("second");
    expect(own.transcript()).toBeNull();
  });

  it("a typed message's transcript gets nothing after a clear", () => {
    const own = new OwnRecordings();
    own.sent(blob("lost: the STT failed"));
    own.clear();
    expect(own.transcript()).toBeNull();
  });

  it("namespaces the player key", () => {
    expect(ownKey("u1")).toBe("own:u1");
  });
});
