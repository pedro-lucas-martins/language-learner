import { useEffect, useRef, useState } from "react";

import { t } from "../i18n.ts";
import { LEVELS, type Lang, type Level, type UserInfo } from "../protocol.ts";
import type { Theme } from "../theme.ts";
import { SettingsIcon } from "./icons.tsx";

interface Props {
  lang: Lang;
  user: UserInfo | null;
  disabled: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  onLevel: (level: Level) => void;
  onUiLang: (lang: Lang) => void;
  onRecast: (enabled: boolean) => void;
  onLogout: () => void;
}

/** Everything that is not the conversation, out of the way behind one button. */
export function SettingsMenu(props: Props) {
  const { lang, user, disabled, theme } = props;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const row = "flex items-center justify-between gap-3 py-2 text-sm";
  const segment = (active: boolean) =>
    `min-h-9 rounded-full px-3 text-xs font-medium transition-colors ${
      active
        ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
        : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
    }`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        className="icon-btn"
        aria-label={t(lang, "settings")}
        aria-expanded={open}
        title={t(lang, "settings")}
        onClick={() => setOpen((v) => !v)}
      >
        <SettingsIcon />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={t(lang, "settings")}
          className="card absolute right-0 top-12 z-30 w-72 space-y-1 p-3 shadow-xl shadow-zinc-900/5"
        >
          <label className={row}>
            <span>{t(lang, "level")}</span>
            <select
              value={user?.level ?? "A1"}
              disabled={disabled}
              onChange={(e) => props.onLevel(e.target.value as Level)}
              className="field w-auto py-1.5"
            >
              {LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </label>
          <div className={row}>
            <span>{t(lang, "uiLanguage")}</span>
            <div className="flex rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
              {(["pt-BR", "pl-PL"] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  disabled={disabled}
                  aria-pressed={lang === code}
                  className={segment(lang === code)}
                  onClick={() => props.onUiLang(code)}
                >
                  {code === "pt-BR" ? "PT" : "PL"}
                </button>
              ))}
            </div>
          </div>
          <label className={row} title={t(lang, "recastHint")}>
            <span>
              {t(lang, "recast")}
              <span className="muted block text-xs">{t(lang, "recastHint")}</span>
            </span>
            <input
              type="checkbox"
              role="switch"
              disabled={disabled}
              checked={user?.recast_pronunciation ?? false}
              onChange={(e) => props.onRecast(e.target.checked)}
              className="size-5 shrink-0 accent-accent-600"
            />
          </label>
          <div className={row}>
            <span>{t(lang, "theme")}</span>
            <div className="flex rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
              <button
                type="button"
                aria-pressed={theme === "light"}
                className={segment(theme === "light")}
                onClick={() => theme !== "light" && props.onToggleTheme()}
              >
                {t(lang, "themeLight")}
              </button>
              <button
                type="button"
                aria-pressed={theme === "dark"}
                className={segment(theme === "dark")}
                onClick={() => theme !== "dark" && props.onToggleTheme()}
              >
                {t(lang, "themeDark")}
              </button>
            </div>
          </div>
          <div className="hairline mt-1 border-t pt-2">
            <button type="button" onClick={props.onLogout} className="btn-quiet w-full">
              {t(lang, "logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
