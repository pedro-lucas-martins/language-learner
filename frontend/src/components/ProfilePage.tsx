import { useEffect, useState } from "react";

import { countWords, FACTS_MAX_WORDS } from "../chat/words.ts";
import { t } from "../i18n.ts";
import type { Lang, UserInfo } from "../protocol.ts";

interface Props {
  lang: Lang;
  user: UserInfo | null;
  disabled: boolean;
  onSave: (text: string) => void;
}

/** "About you": what the AI remembers (SPEC §4.3), editable by the learner. */
export function ProfilePage({ lang, user, disabled, onSave }: Props) {
  const saved = user?.user_facts ?? "";
  const [draft, setDraft] = useState(saved);
  const [pending, setPending] = useState(false);

  // When the server confirms (user_updated) or updates the facts, show the saved text.
  useEffect(() => {
    setDraft(saved);
    setPending(false);
  }, [saved]);

  const words = countWords(draft);
  const tooLong = words > FACTS_MAX_WORDS;
  const changed = draft.trim() !== saved.trim();

  return (
    <div className="space-y-4">
      <div>
        <h3 className="font-semibold">{t(lang, "factsTitle")}</h3>
        <p className="muted mt-1 text-sm leading-relaxed">{t(lang, "factsHelp")}</p>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={7}
        placeholder={t(lang, "factsEmpty")}
        aria-label={t(lang, "factsTitle")}
        className="field resize-y leading-relaxed"
      />
      <div className="flex items-center justify-between gap-3">
        <span className={`text-xs ${tooLong ? "text-rose-600" : "muted"}`}>
          {words}/{FACTS_MAX_WORDS} {t(lang, "words")}
        </span>
        <div className="flex items-center gap-2">
          {!changed && !pending && saved && <span className="muted text-xs">{t(lang, "saved")} ✓</span>}
          <button
            type="button"
            disabled={disabled || !changed || tooLong || pending}
            onClick={() => {
              setPending(true);
              onSave(draft.trim());
            }}
            className="btn-primary"
          >
            {t(lang, "save_")}
          </button>
        </div>
      </div>
    </div>
  );
}
