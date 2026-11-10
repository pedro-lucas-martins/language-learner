import { describe, expect, it } from "vitest";

import { parseServerMsg } from "./protocol.ts";
import { detectLang, STRINGS } from "./i18n.ts";

describe("parseServerMsg", () => {
  it("accepts known messages", () => {
    expect(parseServerMsg('{"type":"transcript","message_id":"1","text":"oi"}')).toEqual({
      type: "transcript",
      message_id: "1",
      text: "oi",
    });
  });

  it("rejects unknown or malformed frames", () => {
    expect(parseServerMsg('{"type":"nope"}')).toBeNull();
    expect(parseServerMsg("not json")).toBeNull();
    expect(parseServerMsg("42")).toBeNull();
  });
});

describe("i18n", () => {
  it("has the same keys in both locales", () => {
    expect(Object.keys(STRINGS["pl-PL"]).sort()).toEqual(Object.keys(STRINGS["pt-BR"]).sort());
  });

  it("detects the browser language", () => {
    expect(detectLang(["pl", "en"])).toBe("pl-PL");
    expect(detectLang(["pt-PT"])).toBe("pt-BR");
    expect(detectLang(["en-US"])).toBe("pt-BR");
  });
});
