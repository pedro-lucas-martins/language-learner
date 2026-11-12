/** REST calls (Bearer token, SPEC §3, §5). The chat itself goes over the WebSocket. */
import { API_URL } from "./config.ts";

export interface Flashcard {
  id: string;
  kind: "grammar" | "pronunciation";
  front: string;
  back: string;
  word: string | null;
  lang: string;
  due_at: string;
  repetitions: number;
  interval_days: number;
}

/** UI buttons → SM-2 grades (backend `sm2.py`). */
export const GRADES = { again: 1, hard: 3, good: 4, easy: 5 } as const;
export type GradeName = keyof typeof GRADES;

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`);
  }
}

async function call<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) throw new ApiError(response.status);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function listDueCards(token: string): Promise<Flashcard[]> {
  return call<Flashcard[]>(token, "/flashcards?due=true&limit=50");
}

export function reviewCard(token: string, id: string, grade: GradeName): Promise<Flashcard> {
  return call<Flashcard>(token, `/flashcards/${encodeURIComponent(id)}/review`, {
    method: "POST",
    body: JSON.stringify({ grade: GRADES[grade] }),
  });
}

export function deleteCard(token: string, id: string): Promise<void> {
  return call<void>(token, `/flashcards/${encodeURIComponent(id)}`, { method: "DELETE" });
}
