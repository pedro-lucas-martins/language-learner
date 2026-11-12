import { useState } from "react";

import type { CorrectionEntry } from "../chat/corrections.ts";
import { t } from "../i18n.ts";
import { CorrectionItem } from "./CorrectionItem.tsx";
import { FlashcardReview } from "./FlashcardReview.tsx";
import { CloseIcon } from "./icons.tsx";
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
    `min-h-11 border-b-2 px-1 text-sm font-medium transition-colors ${
      active
        ? "border-accent-600 text-zinc-900 dark:text-white"
        : "border-transparent text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
    }`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 pt-3">
        <div role="tablist" className="flex flex-1 gap-5">
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
            className="icon-btn"
          >
            <CloseIcon />
          </button>
        )}
      </div>
      <div className="hairline mx-5 border-b" />
      <div className="flex-1 overflow-y-auto px-5 py-4" role="tabpanel">
        {tab === "corrections" ? (
          entries.length === 0 ? (
            <p className="muted mx-auto max-w-xs pt-10 text-center text-sm leading-relaxed">
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
