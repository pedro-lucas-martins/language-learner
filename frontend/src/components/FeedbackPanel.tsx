import type { CorrectionEntry } from "../chat/corrections.ts";
import { t } from "../i18n.ts";
import { CorrectionItem } from "./CorrectionItem.tsx";
import { CloseIcon } from "./icons.tsx";
import type { Practice } from "./practice.ts";

interface Props {
  entries: CorrectionEntry[];
  practice: Practice;
  onClose?: () => void;
}

/** Corrections of this conversation (SPEC §9): a side column on desktop, a sheet on phones.
 * Flashcards have their own page in the side menu. */
export function FeedbackPanel({ entries, practice, onClose }: Props) {
  const { lang } = practice;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 pt-3">
        <h2 className="min-h-11 flex-1 content-center text-sm font-semibold">{t(lang, "corrections")}</h2>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={t(lang, "close")} className="icon-btn">
            <CloseIcon />
          </button>
        )}
      </div>
      <div className="hairline mx-5 border-b" />
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {entries.length === 0 ? (
          <p className="muted mx-auto max-w-xs pt-10 text-center text-sm leading-relaxed">
            {t(lang, "noCorrections")}
          </p>
        ) : (
          <ul className="space-y-3" aria-live="polite">
            {entries.map((entry) => (
              <CorrectionItem key={entry.message.id} entry={entry} practice={practice} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
