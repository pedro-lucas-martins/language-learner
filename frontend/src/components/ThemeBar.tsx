import { useState, type FormEvent } from "react";

import { t } from "../i18n.ts";
import type { Lang } from "../protocol.ts";
import { CloseIcon } from "./icons.tsx";

interface Props {
  lang: Lang;
  theme: string;
  disabled: boolean;
  onChange: (theme: string) => void;
}

const MAX_THEME = 40;

/** Optional steering theme for the conversation (SPEC §8), shown as a small chip. */
export function ThemeBar({ lang, theme, disabled, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(theme);

  function save(event?: FormEvent) {
    event?.preventDefault();
    onChange(draft.trim().slice(0, MAX_THEME));
    setEditing(false);
  }

  if (editing) {
    return (
      <form onSubmit={save} className="mb-2 flex items-center gap-2 px-2">
        <input
          autoFocus
          value={draft}
          maxLength={MAX_THEME}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t(lang, "themePlaceholder")}
          aria-label={t(lang, "theme_")}
          className="field flex-1 py-1.5 text-sm"
        />
        <button type="submit" className="btn-primary min-h-9 px-3">
          {t(lang, "save_")}
        </button>
        <button type="button" onClick={() => setEditing(false)} className="btn-quiet min-h-9 px-3">
          {t(lang, "cancel")}
        </button>
      </form>
    );
  }

  return (
    <div className="mb-2 flex items-center gap-2 px-2 text-xs">
      {theme ? (
        <span className="chip">
          {t(lang, "theme_")}: {theme}
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              setDraft("");
              onChange("");
            }}
            aria-label={t(lang, "clear")}
            className="-mr-1 ml-0.5 rounded-full p-0.5 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          >
            <CloseIcon className="size-3" />
          </button>
        </span>
      ) : null}
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          setDraft(theme);
          setEditing(true);
        }}
        className="muted underline-offset-2 hover:underline disabled:opacity-40"
      >
        {theme ? t(lang, "themeChange") : t(lang, "themeAdd")}
      </button>
    </div>
  );
}
