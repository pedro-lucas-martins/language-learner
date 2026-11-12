import type { CorrectionEntry } from "../chat/corrections.ts";
import { t } from "../i18n.ts";
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
    <li className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-xs text-slate-500 dark:text-slate-400">{t(lang, "youSaid")}</p>
      <p lang={targetLang} className="mb-2 text-sm italic">
        “{message.text}”
      </p>

      {feedback.ok && (
        <p className="text-sm text-emerald-700 dark:text-emerald-300">✓ {t(lang, "allGood")}</p>
      )}

      {feedback.errs.length > 0 && (
        <ul className="space-y-2">
          {feedback.errs.map((err, i) => (
            <li key={`e${i}`} className="text-sm">
              <p lang={targetLang}>
                <span className="text-red-700 line-through decoration-2 dark:text-red-300">
                  {err.e}
                </span>{" "}
                →{" "}
                <span className="font-semibold text-emerald-700 dark:text-emerald-300">{err.c}</span>
              </p>
              <p className="text-slate-700 dark:text-slate-200">{err.r}</p>
              {err.p && (
                <p className="text-slate-500 dark:text-slate-400">
                  <span className="mr-1 rounded bg-slate-100 px-1 text-[11px] font-medium dark:bg-slate-700">
                    {t(lang, "contrastTip")}
                  </span>
                  {err.p}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}

      {feedback.pron.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {t(lang, "pronunciation")}
          </p>
          <ul className="space-y-3">
            {feedback.pron.map((issue, i) => (
              <li key={`p${i}`} className="text-sm">
                <p>
                  <span lang={targetLang} className="font-semibold">
                    {issue.w}
                  </span>{" "}
                  <span className="text-slate-500">
                    ({t(lang, "heard")}: <span lang={targetLang}>“{issue.heard}”</span>) ·{" "}
                    {t(lang, issue.sev === "major" ? "major" : "minor")}
                  </span>
                </p>
                <p className="text-slate-700 dark:text-slate-200">{issue.tip}</p>
                <WordPractice word={issue.w} contextId={message.id} practice={practice} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}
