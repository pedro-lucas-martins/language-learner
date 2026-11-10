import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { useChatSocket } from "../chat/useChatSocket.ts";
import { t } from "../i18n.ts";
import { LEVELS, MAX_USER_TEXT, type Lang, type Level } from "../protocol.ts";

interface Props {
  token: string;
  fallbackLang: Lang;
  onAuthFailed: (reason: "unauthorized" | "origin") => void;
  onLogout: () => void;
}

/** Slice 1: text-only conversation. Voice, feedback panel and layouts come later. */
export function ChatScreen({ token, fallbackLang, onAuthFailed, onLogout }: Props) {
  const { state, sendText, setLevel, reconnect, dismissError } = useChatSocket(token);
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const lang: Lang = state.user?.native_lang ?? fallbackLang;

  useEffect(() => {
    if (state.closeReason === "unauthorized" || state.closeReason === "origin") {
      onAuthFailed(state.closeReason);
    }
  }, [state.closeReason, onAuthFailed]);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [state.messages]);

  const canSend = state.status === "ready" && !state.awaitingReply && draft.trim().length > 0;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend && sendText(draft)) setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const lastMessage = state.messages[state.messages.length - 1];
  const showTyping = state.awaitingReply && lastMessage?.role !== "ai";

  return (
    <div className="mx-auto flex h-[100dvh] max-w-2xl flex-col">
      <header className="flex items-center gap-2 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-semibold">{t(lang, "appTitle")}</h1>
          {state.user && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {state.user.native_lang} → {state.user.target_lang}
            </p>
          )}
        </div>
        <label className="flex items-center gap-1 text-sm">
          <span className="sr-only sm:not-sr-only">{t(lang, "level")}</span>
          <select
            value={state.user?.level ?? "A1"}
            disabled={state.status !== "ready"}
            onChange={(e) => setLevel(e.target.value as Level)}
            className="min-h-10 rounded-lg border border-slate-300 bg-transparent px-2 dark:border-slate-700"
          >
            {LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={onLogout}
          className="min-h-10 rounded-lg px-3 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {t(lang, "logout")}
        </button>
      </header>

      {state.status === "connecting" && (
        <p className="px-4 py-2 text-center text-sm text-slate-500">{t(lang, "connecting")}</p>
      )}
      {state.status === "closed" && state.closeReason === "network" && (
        <div className="flex items-center justify-center gap-3 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          <span>{t(lang, "disconnected")}</span>
          <button type="button" onClick={reconnect} className="min-h-10 font-medium underline">
            {t(lang, "reconnect")}
          </button>
        </div>
      )}

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
        {state.messages.length === 0 && state.status === "ready" && (
          <p className="pt-10 text-center text-slate-500 dark:text-slate-400">
            {t(lang, "emptyChat")}
          </p>
        )}
        {state.messages.map((message) => (
          <div
            key={message.id}
            className={message.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <p
              lang={message.role === "ai" ? state.user?.target_lang : undefined}
              className={
                message.role === "user"
                  ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-sky-600 px-4 py-2 text-white"
                  : "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-white px-4 py-2 shadow-sm dark:bg-slate-800"
              }
            >
              {message.text}
              {message.streaming && <span className="ml-0.5 animate-pulse">▍</span>}
            </p>
          </div>
        ))}
        {showTyping && (
          <p className="text-sm italic text-slate-500 dark:text-slate-400">{t(lang, "thinking")}</p>
        )}
      </div>

      {state.error && (
        <div
          role="alert"
          className="mx-4 mb-2 flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
        >
          <span className="flex-1">{state.error}</span>
          <button type="button" onClick={dismissError} aria-label="OK" className="font-medium">
            ✕
          </button>
        </div>
      )}

      <form
        onSubmit={submit}
        className="flex items-end gap-2 border-t border-slate-200 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800"
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={MAX_USER_TEXT}
          lang={state.user?.target_lang}
          placeholder={t(lang, "inputPlaceholder")}
          className="max-h-40 min-h-12 flex-1 resize-none rounded-xl border border-slate-300 bg-transparent px-3 py-3 outline-none focus:border-sky-500 dark:border-slate-700"
        />
        <button
          type="submit"
          disabled={!canSend}
          className="min-h-12 rounded-xl bg-sky-600 px-4 font-medium text-white disabled:opacity-50"
        >
          {t(lang, "send")}
        </button>
      </form>

      {state.usage && (
        <p className="pb-2 text-center text-[11px] text-slate-400">
          {t(lang, "usageMonth")}: US$ {state.usage.monthUsdEst.toFixed(2)} /{" "}
          {state.usage.budgetUsd.toFixed(0)}
        </p>
      )}
    </div>
  );
}
