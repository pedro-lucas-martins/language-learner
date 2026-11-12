import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, deleteCard, listDueCards, reviewCard } from "./api.ts";
import { API_URL } from "./config.ts";

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("flashcards API", () => {
  it("lists due cards with the bearer token", async () => {
    const fetchMock = mockFetch(200, []);
    await expect(listDueCards("tok")).resolves.toEqual([]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_URL}/flashcards?due=true&limit=50`);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("maps grade names to SM-2 grades", async () => {
    const fetchMock = mockFetch(200, { id: "c1" });
    await reviewCard("tok", "c1", "good");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_URL}/flashcards/c1/review`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ grade: 4 });
  });

  it("handles 204 on delete and throws on errors", async () => {
    mockFetch(204);
    await expect(deleteCard("tok", "c1")).resolves.toBeUndefined();
    mockFetch(404);
    await expect(deleteCard("tok", "c1")).rejects.toBeInstanceOf(ApiError);
  });
});
