import { useState } from "react";

import type { CorrectionEntry } from "../chat/corrections.ts";
import { t } from "../i18n.ts";
import { CorrectionItem } from "./CorrectionItem.tsx";
import { FlashcardReview } from "./FlashcardReview.tsx";
import type { Practice } from "./practice.ts";

interface Props {
  token: string;
  entries: CorrectionEntry[];
  practice: Practice;
  onClose?: () => void;
}

type Tab = "corrections" | "flashcards";

/** Corrections / Flashcards tabs (SPEC §9): a side column on desktop, a sheet on phones. */
export function FeedbackPanel({ token, entries, practice, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("corrections");
  const { lang } = practice;
  const tabClass = (active: boolean) =>
    `min-h-11 flex-1 rounded-lg text-sm font-medium ${active ? "bg-white shadow-sm dark:bg-slate-700" : "text-slate-500"}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 p-3">
        <div role="tablist" className="flex flex-1 gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "corrections"}
            className={tabClass(tab === "corrections")}
            onClick={() => setTab("corrections")}
          >
            {t(lang, "corrections")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "flashcards"}
            className={tabClass(tab === "flashcards")}
            onClick={() => setTab("flashcards")}
          >
            {t(lang, "flashcards")}
          </button>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={t(lang, "close")}
            className="min-h-11 min-w-11 rounded-lg text-lg hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            ✕
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-4" role="tabpanel">
        {tab === "corrections" ? (
          entries.length === 0 ? (
            <p className="pt-6 text-center text-sm text-slate-500 dark:text-slate-400">
              {t(lang, "noCorrections")}
            </p>
          ) : (
            <ul className="space-y-3" aria-live="polite">
              {entries.map((entry) => (
                <CorrectionItem key={entry.message.id} entry={entry} practice={practice} />
              ))}
            </ul>
          )
        ) : (
          <FlashcardReview token={token} practice={practice} />
        )}
      </div>
    </div>
  );
}
