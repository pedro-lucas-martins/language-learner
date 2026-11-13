import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { correctionEntries } from "../chat/corrections.ts";
import { ownKey } from "../chat/ownRecordings.ts";
import type { Metrics } from "../chat/state.ts";
import { useChatSocket, type AudioHandler } from "../chat/useChatSocket.ts";
import { useVoice } from "../chat/useVoice.ts";
import { t } from "../i18n.ts";
import { MAX_USER_TEXT, type Lang } from "../protocol.ts";
import { useTheme } from "../theme.ts";
import { listDueCards } from "../api.ts";
import { FeedbackPanel } from "./FeedbackPanel.tsx";
import { FlashcardReview } from "./FlashcardReview.tsx";
import {
  CheckIcon,
  CloseIcon,
  MenuIcon,
  NotesIcon,
  PencilIcon,
  PlayIcon,
  SendIcon,
  StopIcon,
} from "./icons.tsx";
import { SideNav, type View } from "./SideNav.tsx";
import { MicButton } from "./MicButton.tsx";
import type { Practice } from "./practice.ts";
import { SettingsMenu } from "./SettingsMenu.tsx";
import { ThinkingBubble } from "./ThinkingBubble.tsx";

interface Props {
  token: string;
  fallbackLang: Lang;
  onAuthFailed: (reason: "unauthorized" | "origin") => void;
  onLogout: () => void;
}

const LANG_SHORT: Record<Lang, string> = { "pt-BR": "Português", "pl-PL": "Polski" };

function seconds(ms: number | null): string {
  return ms === null ? "–" : `${(ms / 1000).toFixed(1)} s`;
}

function metricsText(lang: Lang, m: Metrics): string {
  const parts = [`${t(lang, "metricsVoice")} ${seconds(m.firstAudioMs)}`];
  if (m.sttMs !== null) parts.push(`${t(lang, "metricsStt")} ${seconds(m.sttMs)}`);
  parts.push(`${t(lang, "metricsTotal")} ${seconds(m.totalMs)}`);
  return `${t(lang, "metricsLabel")}: ${parts.join(" · ")}`;
}

const WIDE_QUERY = "(min-width: 1024px)";

/** True on desktop widths, where the corrections panel is always visible. */
function useIsWide(): boolean {
  const [wide, setWide] = useState(() =>
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia(WIDE_QUERY).matches : false,
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const query = window.matchMedia(WIDE_QUERY);
    const onChange = () => setWide(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return wide;
}

/** Text and voice conversation with the corrections / flashcards panel (SPEC §5, §9). */
export function ChatScreen({ token, fallbackLang, onAuthFailed, onLogout }: Props) {
  const audioRef = useRef<AudioHandler | null>(null);
  const {
    state,
    sendText,
    sendUtterance,
    sendPronRetry,
    interrupt,
    regrade,
    setRecast,
    setCorrection,
    speakWord,
    setUiLang,
    correctionsSeen,
    setLevel,
    reconnect,
    dismissError,
  } = useChatSocket(token, audioRef);
  const lastAi = [...state.messages].reverse().find((m) => m.role === "ai");
  const voice = useVoice({
    audioRef,
    busy: state.awaitingReply,
    lastAiMessageId: lastAi?.id ?? null,
    sendUtterance,
    interrupt,
  });
  const [theme, toggleTheme] = useTheme();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [dueCount, setDueCount] = useState<number | null>(null);
  const isWide = useIsWide();

  // Cards due now, for the menu badge: on start, when switching pages and when a new
  // correction with mistakes may have created cards.
  const feedbackCount = Object.keys(state.feedback).length;
  useEffect(() => {
    let alive = true;
    listDueCards(token)
      .then((cards) => alive && setDueCount(cards.length))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [token, view, feedbackCount]);
  const listRef = useRef<HTMLDivElement>(null);
  const lang: Lang = state.user?.ui_lang ?? fallbackLang;
  const ready = state.status === "ready";

  const entries = useMemo(
    () => correctionEntries(state.messages, state.feedback),
    [state.messages, state.feedback],
  );

  const practice: Practice = {
    lang,
    targetLang: state.user?.target_lang,
    recording: voice.recording,
    listen: (word) => {
      if (!voice.playWord(word)) speakWord(word);
    },
    listenSlow: (word) => void voice.playWord(word, 0.8),
    canListenSlow: (word) => voice.hasAudio(`word:${word}`),
    startRetry: voice.startClip,
    finishRetry: async (word, contextId) => {
      const blob = await voice.finishClip();
      if (blob) await sendPronRetry(blob, word, contextId);
    },
    result: (contextId, word) => state.pronResults[`${contextId}|${word}`],
  };

  // The panel is visible on desktop (or open on a phone): its corrections count as seen.
  useEffect(() => {
    if ((isWide || sheetOpen) && state.unseenCorrections > 0) correctionsSeen();
  }, [isWide, sheetOpen, state.unseenCorrections, correctionsSeen]);

  // Escape closes the phone sheet.
  useEffect(() => {
    if (!sheetOpen) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setSheetOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  useEffect(() => {
    if (state.closeReason === "unauthorized" || state.closeReason === "origin") {
      onAuthFailed(state.closeReason);
    }
  }, [state.closeReason, onAuthFailed]);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [state.messages, state.phase]);

  const canSend = ready && !state.awaitingReply && draft.trim().length > 0;
  const lastMessage = state.messages[state.messages.length - 1];

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

  function saveEdit(event?: FormEvent) {
    event?.preventDefault();
    if (editing && regrade(editing.id, editing.text)) setEditing(null);
  }

  const status = voice.recording
    ? t(lang, "recording")
    : voice.speaking
      ? t(lang, "aiSpeaking")
      : voice.handsFree
        ? t(lang, "listening")
        : null;
  const micProblem =
    voice.micError === "denied"
      ? t(lang, "micDenied")
      : voice.micError === "unsupported"
        ? t(lang, "micUnsupported")
        : null;
  const onFallbackVoice =
    state.usage !== null &&
    state.usage.ttsProvider !== "google" &&
    state.usage.ttsProvider !== "elevenlabs";

  return (
    <div className="flex h-[100dvh]" onPointerDownCapture={voice.unlock} onKeyDownCapture={voice.unlock}>
      <SideNav
        lang={lang}
        view={view}
        onView={setView}
        dueCount={dueCount}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />
      <main className="mx-auto flex h-full min-w-0 max-w-2xl flex-1 flex-col">
        <header className="flex items-center gap-2 px-4 pb-2 pt-3 sm:px-6">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label={t(lang, "openMenu")}
            title={t(lang, "openMenu")}
            className="icon-btn relative -ml-2 lg:hidden"
          >
            <MenuIcon />
            {dueCount !== null && dueCount > 0 && view === "chat" && (
              <span aria-hidden className="absolute right-2 top-2 size-2 rounded-full bg-accent-600" />
            )}
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[15px] font-semibold tracking-tight">
              {t(lang, view === "chat" ? "navChat" : "navFlashcards")}
            </h1>
            {state.user && (
              <p className="muted truncate text-xs">
                {t(lang, "direction")}: {LANG_SHORT[state.user.target_lang]} · {state.user.level}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            aria-label={t(lang, "openCorrections")}
            title={t(lang, "openCorrections")}
            className="icon-btn relative lg:hidden"
          >
            <NotesIcon />
            {state.unseenCorrections > 0 && (
              <span className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-accent-600 px-1 text-[10px] font-semibold leading-4 text-white">
                {state.unseenCorrections}
              </span>
            )}
          </button>
          <SettingsMenu
            lang={lang}
            user={state.user}
            disabled={!ready}
            theme={theme}
            onToggleTheme={toggleTheme}
            onLevel={setLevel}
            onUiLang={setUiLang}
            onRecast={setRecast}
            onCorrection={setCorrection}
            onLogout={onLogout}
          />
        </header>

        {state.status === "connecting" && (
          <p className="muted px-4 py-1 text-center text-sm">{t(lang, "connecting")}</p>
        )}
        {state.status === "closed" && state.closeReason === "network" && (
          <div className="mx-4 flex items-center justify-center gap-3 rounded-xl bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-950/60 dark:text-amber-100">
            <span>{t(lang, "disconnected")}</span>
            <button type="button" onClick={reconnect} className="min-h-10 font-medium underline">
              {t(lang, "reconnect")}
            </button>
          </div>
        )}

        {view === "flashcards" && (
          <section className="flex-1 overflow-y-auto px-4 py-6 sm:px-6" aria-label={t(lang, "navFlashcards")}>
            <div className="mx-auto max-w-xl">
              <FlashcardReview token={token} practice={practice} onCountChange={setDueCount} />
            </div>
          </section>
        )}

        {/* The conversation stays mounted (scroll, drafts, audio) while another page is open. */}
        <div className={view === "chat" ? "contents" : "hidden"}>
          <div ref={listRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
            {state.messages.length === 0 && ready && state.phase === "idle" && (
              <p className="muted mx-auto max-w-xs pt-16 text-center text-sm leading-relaxed">
                {t(lang, "emptyChat")}
              </p>
            )}
            {state.messages.map((message) => (
              <div
                key={message.id}
                className={message.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                {message.role === "user" && editing?.id === message.id ? (
                  <form onSubmit={saveEdit} className="flex w-[85%] flex-col gap-2">
                    <textarea
                      value={editing.text}
                      onChange={(e) => setEditing({ id: message.id, text: e.target.value })}
                      maxLength={MAX_USER_TEXT}
                      lang={state.user?.target_lang}
                      rows={2}
                      autoFocus
                      className="field"
                    />
                    <div className="flex justify-end gap-1">
                      <button type="button" onClick={() => setEditing(null)} className="btn-quiet">
                        {t(lang, "cancel")}
                      </button>
                      <button type="submit" disabled={!editing.text.trim()} className="btn-primary">
                        {t(lang, "save")}
                      </button>
                    </div>
                  </form>
                ) : message.role === "user" ? (
                  <div className="flex max-w-[85%] items-end justify-end gap-1">
                    {voice.hasAudio(ownKey(message.id)) && (
                      <button
                        type="button"
                        onClick={() => voice.replay(ownKey(message.id))}
                        aria-label={t(lang, "playMine")}
                        title={t(lang, "playMine")}
                        className="icon-btn size-9 shrink-0"
                      >
                        <PlayIcon className="size-4" />
                      </button>
                    )}
                    <button
                      type="button"
                      lang={state.user?.target_lang}
                      title={t(lang, "editTranscript")}
                      onClick={() => setEditing({ id: message.id, text: message.text })}
                      className="bubble-user group max-w-full transition-colors hover:bg-accent-700"
                    >
                      {message.text}
                      <span aria-hidden className="ml-2 inline-flex translate-y-0.5 opacity-60 group-hover:opacity-100">
                        {state.feedback[message.id]?.ok ? (
                          <CheckIcon className="size-3.5" />
                        ) : (
                          <PencilIcon className="size-3.5" />
                        )}
                      </span>
                    </button>
                  </div>
                ) : (
                  <div lang={state.user?.target_lang} className="bubble-ai">
                    {message.text}
                    {message.streaming && <span className="ml-0.5 animate-pulse text-accent-500">▍</span>}
                    {!message.streaming && voice.hasAudio(message.id) && (
                      <div className="-mb-1 -ml-2 mt-1 flex items-center gap-0.5">
                        <button
                          type="button"
                          onClick={() => voice.replay(message.id)}
                          aria-label={t(lang, "replay")}
                          title={t(lang, "replay")}
                          className="icon-btn size-9"
                        >
                          <PlayIcon className="size-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => voice.replay(message.id, 0.8)}
                          aria-label={t(lang, "replaySlow")}
                          title={t(lang, "replaySlow")}
                          className="icon-btn size-9 text-xs font-semibold"
                        >
                          0.8×
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            {state.phase === "transcribing" && <ThinkingBubble side="user" label={t(lang, "transcribing")} />}
            {/* Shown once the learner's message is on screen (typed text appears when the server echoes it). */}
            {state.phase === "thinking" && lastMessage?.role === "user" && (
              <ThinkingBubble side="ai" label={t(lang, "thinking")} />
            )}
          </div>

          {(status || micProblem) && (
            <div className="flex items-center justify-center gap-2 px-4 pb-2 text-sm">
              <span role="status" className="muted">
                {micProblem ?? status}
              </span>
              {voice.speaking && (
                <button type="button" onClick={voice.stopSpeaking} className="btn-quiet min-h-9 px-3">
                  <StopIcon className="size-3.5" />
                  {t(lang, "stopAudio")}
                </button>
              )}
            </div>
          )}

          {state.error && (
            <div
              role="alert"
              className="mx-4 mb-2 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950/60 dark:text-red-200"
            >
              <span className="flex-1">{state.error}</span>
              <button type="button" onClick={dismissError} aria-label="OK" className="opacity-70 hover:opacity-100">
                <CloseIcon className="size-4" />
              </button>
            </div>
          )}

          <form onSubmit={submit} className="px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5">
            <div className="surface flex items-end gap-1 rounded-[28px] border border-zinc-200/80 p-1.5 shadow-sm transition-shadow focus-within:border-accent-500 focus-within:ring-4 focus-within:ring-accent-100 dark:border-zinc-800 dark:focus-within:ring-accent-700/30">
              <MicButton
                lang={lang}
                recording={voice.recording}
                handsFree={voice.handsFree}
                disabled={!ready || voice.micError === "unsupported"}
                onPress={() => void voice.press()}
                onRelease={() => void voice.release()}
              />
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                maxLength={MAX_USER_TEXT}
                lang={state.user?.target_lang}
                placeholder={t(lang, "inputPlaceholder")}
                className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 outline-none placeholder:text-zinc-400"
              />
              <button
                type="submit"
                disabled={!canSend}
                aria-label={t(lang, "send")}
                title={t(lang, "send")}
                className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-accent-600 text-white transition-colors hover:bg-accent-700 disabled:bg-zinc-200 disabled:text-zinc-400 dark:disabled:bg-zinc-800"
              >
                <SendIcon />
              </button>
            </div>
            <p className="muted mt-2 text-center text-[11px]">{t(lang, "micHint")}</p>
          </form>
        </div>

        {(state.usage || state.metrics) && (
          <div className="pb-2 text-center text-[10px] leading-relaxed text-zinc-400 dark:text-zinc-500">
            {state.metrics && <p>{metricsText(lang, state.metrics)}</p>}
            {state.usage && (
              <p>
                {t(lang, "usageMonth")}: US$ {state.usage.monthUsdEst.toFixed(2)} / {state.usage.budgetUsd.toFixed(0)}
                {onFallbackVoice && ` · ${t(lang, "fallbackVoice")}`}
              </p>
            )}
          </div>
        )}
      </main>

      <aside className="hairline surface hidden h-full w-96 shrink-0 border-l lg:block">
        <FeedbackPanel entries={entries} practice={practice} />
      </aside>

      {sheetOpen && !isWide && (
        <div
          className="fixed inset-0 z-40 flex flex-col justify-end bg-zinc-900/30 backdrop-blur-[2px]"
          onClick={() => setSheetOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t(lang, "corrections")}
            onClick={(e) => e.stopPropagation()}
            className="surface h-[82dvh] rounded-t-3xl pb-[env(safe-area-inset-bottom)] shadow-2xl"
          >
            <div aria-hidden className="mx-auto mt-2 h-1 w-10 rounded-full bg-zinc-300 dark:bg-zinc-700" />
            <FeedbackPanel entries={entries} practice={practice} onClose={() => setSheetOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
