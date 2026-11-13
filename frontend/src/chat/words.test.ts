import { describe, expect, it } from "vitest";

import { countWords } from "./words.ts";

describe("countWords", () => {
  it("counts words separated by any whitespace", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   ")).toBe(0);
    expect(countWords("Pracuje jako programator;\n mieszka w Gdańsku")).toBe(6);
  });
});
