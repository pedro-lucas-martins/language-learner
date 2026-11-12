import type { CorrectionEntry } from "../chat/corrections.ts";
import { t } from "../i18n.ts";
import { CheckIcon } from "./icons.tsx";
import type { Practice } from "./practice.ts";
import { WordPractice } from "./WordPractice.tsx";

interface Props {
  entry: CorrectionEntry;
  practice: Practice;
}

/** One learner message and its grammar and pronunciation feedback. */
export function CorrectionItem({ entry, practice }: Props) {
  const { message, feedback } = entry;
  const { lang, targetLang } = practice;
  return (
    <li className="card space-y-3">
      <div>
        <p className="muted text-[11px] font-medium uppercase tracking-wider">{t(lang, "youSaid")}</p>
        <p lang={targetLang} className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-300">
          “{message.text}”
        </p>
      </div>

      {feedback.ok && (
        <p className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
          <CheckIcon className="size-4" /> {t(lang, "allGood")}
        </p>
      )}

      {feedback.errs.length > 0 && (
        <ul className="space-y-3">
          {feedback.errs.map((err, i) => (
            <li key={`e${i}`} className="space-y-1 text-sm leading-relaxed">
              <p lang={targetLang} className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-rose-500 line-through decoration-rose-300">{err.e}</span>
                <span className="muted">→</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">{err.c}</span>
              </p>
              <p className="text-zinc-700 dark:text-zinc-200">{err.r}</p>
              {err.p && (
                <p className="muted">
                  <span className="chip mr-1.5">{t(lang, "contrastTip")}</span>
                  {err.p}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {feedback.pron.length > 0 && (
        <div className="hairline space-y-2 border-t pt-3">
          <p className="muted text-[11px] font-medium uppercase tracking-wider">
            {t(lang, "pronunciation")}
          </p>
          <ul className="space-y-4">
            {feedback.pron.map((issue, i) => (
              <li key={`p${i}`} className="text-sm">
                <p>
                  <span lang={targetLang} className="font-semibold">
                    {issue.w}
                  </span>{" "}
                  <span className="muted">
                    ({t(lang, "heard")}: <span lang={targetLang}>“{issue.heard}”</span>) ·{" "}
                    {t(lang, issue.sev === "major" ? "major" : "minor")}
                  </span>
                </p>
                <p className="text-zinc-700 dark:text-zinc-200">{issue.tip}</p>
                <WordPractice word={issue.w} contextId={message.id} practice={practice} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}
