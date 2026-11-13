import { useEffect } from "react";

import { t, type StringKey } from "../i18n.ts";
import type { Lang } from "../protocol.ts";
import { CardsIcon, ChartIcon, ChatIcon, CloseIcon, UserIcon } from "./icons.tsx";

export type View = "chat" | "flashcards" | "profile" | "usage";

interface Props {
  lang: Lang;
  view: View;
  onView: (view: View) => void;
  /** Cards due now (null while unknown). */
  dueCount: number | null;
  /** Phone drawer state; on desktop the menu is always visible. */
  open: boolean;
  onClose: () => void;
}

const ITEMS: { view: View; label: StringKey; Icon: typeof ChatIcon }[] = [
  { view: "chat", label: "navChat", Icon: ChatIcon },
  { view: "flashcards", label: "navFlashcards", Icon: CardsIcon },
  { view: "profile", label: "navProfile", Icon: UserIcon },
  { view: "usage", label: "navUsage", Icon: ChartIcon },
];

/** Side menu: Conversation and Flashcards (column on desktop, drawer on phones). */
export function SideNav({ lang, view, onView, dueCount, open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const items = (
    <ul className="space-y-1">
      {ITEMS.map(({ view: item, label, Icon }) => {
        const active = item === view;
        return (
          <li key={item}>
            <button
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => {
                onView(item);
                onClose();
              }}
              className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors ${
                active
                  ? "bg-accent-50 text-accent-700 dark:bg-accent-700/20 dark:text-accent-100"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              }`}
            >
              <Icon className="size-5 shrink-0" />
              <span className="flex-1 text-left">{t(lang, label)}</span>
              {item === "flashcards" && dueCount !== null && dueCount > 0 && (
                <span
                  className="rounded-full bg-accent-600 px-2 text-[11px] font-semibold leading-5 text-white"
                  aria-label={`${dueCount} ${t(lang, "cardsDue")}`}
                >
                  {dueCount >= 50 ? "50+" : dueCount}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );

  return (
    <>
      <nav
        aria-label={t(lang, "menu")}
        className="hairline hidden h-full w-56 shrink-0 flex-col border-r px-3 pt-4 lg:flex"
      >
        <p className="mb-4 px-3 text-[15px] font-semibold tracking-tight">{t(lang, "appTitle")}</p>
        {items}
      </nav>

      {open && (
        <div className="fixed inset-0 z-40 bg-zinc-900/30 backdrop-blur-[2px] lg:hidden" onClick={onClose}>
          <nav
            aria-label={t(lang, "menu")}
            onClick={(e) => e.stopPropagation()}
            className="surface flex h-full w-72 max-w-[85%] flex-col px-3 pt-3 shadow-2xl"
          >
            <div className="mb-3 flex items-center justify-between pl-3">
              <p className="text-[15px] font-semibold tracking-tight">{t(lang, "appTitle")}</p>
              <button type="button" onClick={onClose} aria-label={t(lang, "close")} className="icon-btn">
                <CloseIcon />
              </button>
            </div>
            {items}
          </nav>
        </div>
      )}
    </>
  );
}
