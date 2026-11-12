import { useCallback, useEffect, useState } from "react";

import { deleteCard, listDueCards, reviewCard, type Flashcard, type GradeName } from "../api.ts";
import { splitMarked } from "../chat/corrections.ts";
import { t, type StringKey } from "../i18n.ts";
import type { Practice } from "./practice.ts";
import { WordPractice } from "./WordPractice.tsx";

interface Props {
  token: string;
  practice: Practice;
}

const GRADE_BUTTONS: [GradeName, StringKey, string][] = [
  ["again", "gradeAgain", "bg-red-600"],
  ["hard", "gradeHard", "bg-amber-600"],
  ["good", "gradeGood", "bg-emerald-600"],
  ["easy", "gradeEasy", "bg-sky-600"],
];

/** Review due cards one by one (SM-2 runs on the server). */
export function FlashcardReview({ token, practice }: Props) {
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
      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>{cards ? `${cards.length} ${t(lang, "cardsDue")}` : "…"}</span>
        <button type="button" onClick={() => void load()} className="min-h-10 px-2 underline">
          {t(lang, "refresh")}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {t(lang, "loadError")}
        </p>
      )}
      {cards && !card && !error && (
        <p className="py-6 text-center text-slate-500 dark:text-slate-400">{t(lang, "noCardsDue")}</p>
      )}
      {card && (
        <article className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <p lang={targetLang} className="text-lg">
            {card.kind === "grammar"
              ? splitMarked(card.front).map((part, i) =>
                  part.marked ? (
                    <mark key={i} className="rounded bg-amber-200 px-0.5 dark:bg-amber-700">
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
              className="mt-4 min-h-12 w-full rounded-xl bg-slate-200 font-medium dark:bg-slate-700"
            >
              {t(lang, "showAnswer")}
            </button>
          ) : (
            <>
              <p className="mt-3 whitespace-pre-line border-t border-slate-200 pt-3 text-sm dark:border-slate-700">
                {card.back}
              </p>
              <div className="mt-4 grid grid-cols-4 gap-2">
                {GRADE_BUTTONS.map(([grade, label, color]) => (
                  <button
                    key={grade}
                    type="button"
                    disabled={busy}
                    onClick={() => void act(() => reviewCard(token, card.id, grade))}
                    className={`min-h-12 rounded-xl text-sm font-medium text-white disabled:opacity-50 ${color}`}
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
            className="mt-3 min-h-10 text-xs text-slate-500 underline"
          >
            {t(lang, "deleteCard")}
          </button>
        </article>
      )}
    </div>
  );
}
