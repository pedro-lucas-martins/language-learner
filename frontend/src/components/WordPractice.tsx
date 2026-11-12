import { useState, type PointerEvent } from "react";

import { t } from "../i18n.ts";
import type { Practice } from "./practice.ts";

interface Props {
  word: string;
  /** Message or card id, echoed back in pron_result. */
  contextId: string;
  practice: Practice;
}

const btn =
  "min-h-12 min-w-12 rounded-lg px-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-700";

/** ▶ listen (1× / 0.8×) and 🎙 hold to try again, with the verdict (SPEC §5). */
export function WordPractice({ word, contextId, practice }: Props) {
  const [holding, setHolding] = useState(false);
  const { lang } = practice;
  const verdict = practice.result(contextId, word);

  async function down(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    if (await practice.startRetry()) setHolding(true);
  }

  async function up() {
    if (!holding) return;
    setHolding(false);
    await practice.finishRetry(word, contextId);
  }

  return (
    <div className="mt-1">
      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          className={btn}
          onClick={() => practice.listen(word)}
          aria-label={`${t(lang, "listen")}: ${word}`}
          title={t(lang, "listen")}
        >
          ▶
        </button>
        <button
          type="button"
          className={btn}
          disabled={!practice.canListenSlow(word)}
          onClick={() => practice.listenSlow(word)}
          aria-label={`${t(lang, "listenSlow")}: ${word}`}
          title={t(lang, "listenSlow")}
        >
          0.8×
        </button>
        <button
          type="button"
          className={`${btn} ${holding ? "bg-red-600 text-white hover:bg-red-600" : ""}`}
          onPointerDown={(e) => void down(e)}
          onPointerUp={() => void up()}
          onPointerCancel={() => void up()}
          onContextMenu={(e) => e.preventDefault()}
          style={{ touchAction: "none" }}
          aria-label={`${t(lang, "holdToTry")}: ${word}`}
          title={t(lang, "holdToTry")}
        >
          🎙
        </button>
        {holding && <span className="text-xs text-red-600">{t(lang, "tryRecording")}</span>}
      </div>
      {verdict && !holding && (
        <p
          role="status"
          className={`mt-1 rounded-lg px-2 py-1 text-sm ${verdict.better ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100" : "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100"}`}
        >
          <strong>{t(lang, verdict.better ? "better" : "notYet")}</strong> {verdict.tip}
        </p>
      )}
    </div>
  );
}
