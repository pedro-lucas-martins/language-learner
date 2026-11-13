import { useCallback, useEffect, useState } from "react";

import { deleteCard, listDueCards, reviewCard, type Flashcard, type GradeName } from "../api.ts";
import { splitMarked } from "../chat/corrections.ts";
import { t, type StringKey } from "../i18n.ts";
import type { Practice } from "./practice.ts";
import { WordPractice } from "./WordPractice.tsx";

interface Props {
  token: string;
  practice: Practice;
  /** Called with the number of cards still due (for the menu badge). */
  onCountChange?: (count: number) => void;
}

const GRADE_BUTTONS: [GradeName, StringKey, string][] = [
  ["again", "gradeAgain", "text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50"],
  ["hard", "gradeHard", "text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/50"],
  ["good", "gradeGood", "text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/50"],
  ["easy", "gradeEasy", "text-accent-600 hover:bg-accent-50 dark:hover:bg-accent-700/20"],
];

/** Review due cards one by one (SM-2 runs on the server). */
export function FlashcardReview({ token, practice, onCountChange }: Props) {
  const { lang, targetLang } = practice;
  const [cards, setCards] = useState<Flashcard[] | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      setCards(await listDueCards(token));
      setFlipped(false);
    } catch {
      setError(true);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (cards) onCountChange?.(cards.length);
  }, [cards, onCountChange]);

  const card = cards?.[0];

  async function act(action: () => Promise<unknown>) {
    if (!card || busy) return;
    setBusy(true);
    try {
      await action();
      setCards((list) => (list ? list.slice(1) : list));
      setFlipped(false);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="muted flex items-center justify-between text-sm">
        <span>{cards ? `${cards.length} ${t(lang, "cardsDue")}` : "…"}</span>
        <button type="button" onClick={() => void load()} className="btn-quiet min-h-9 px-3">
          {t(lang, "refresh")}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {t(lang, "loadError")}
        </p>
      )}
      {cards && !card && !error && (
        <p className="muted mx-auto max-w-xs py-10 text-center text-sm leading-relaxed">
          {t(lang, "noCardsDue")}
        </p>
      )}
      {card && (
        <article className="card p-5">
          <p lang={targetLang} className="text-lg leading-relaxed">
            {card.kind === "grammar"
              ? splitMarked(card.front).map((part, i) =>
                  part.marked ? (
                    <mark key={i} className="rounded-md bg-accent-100 px-1 text-accent-700 dark:bg-accent-700/30 dark:text-accent-100">
                      {part.text}
                    </mark>
                  ) : (
                    <span key={i}>{part.text}</span>
                  ),
                )
              : card.front}
          </p>
          {card.kind === "pronunciation" && card.word && (
            <WordPractice word={card.word} contextId={card.id} practice={practice} />
          )}
          {!flipped ? (
            <button
              type="button"
              onClick={() => setFlipped(true)}
              className="btn mt-5 w-full bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
            >
              {t(lang, "showAnswer")}
            </button>
          ) : (
            <>
              <p className="hairline mt-4 whitespace-pre-line border-t pt-4 text-sm leading-relaxed text-zinc-700 dark:text-zinc-200">
                {card.back}
              </p>
              <div className="mt-5 grid grid-cols-4 gap-1">
                {GRADE_BUTTONS.map(([grade, label, color]) => (
                  <button
                    key={grade}
                    type="button"
                    disabled={busy}
                    onClick={() => void act(() => reviewCard(token, card.id, grade))}
                    className={`btn min-h-11 px-1 ${color}`}
                  >
                    {t(lang, label)}
                  </button>
                ))}
              </div>
            </>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => void act(() => deleteCard(token, card.id))}
            className="muted mt-3 min-h-9 text-xs hover:text-rose-600"
          >
            {t(lang, "deleteCard")}
          </button>
        </article>
      )}
    </div>
  );
}
