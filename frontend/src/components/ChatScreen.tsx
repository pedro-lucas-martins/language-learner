import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import type { Metrics } from "../chat/state.ts";
import { useChatSocket, type AudioHandler } from "../chat/useChatSocket.ts";
import { useVoice } from "../chat/useVoice.ts";
import { t } from "../i18n.ts";
import { LEVELS, MAX_USER_TEXT, type Lang, type Level } from "../protocol.ts";
import { MicButton } from "./MicButton.tsx";

interface Props {
  token: string;
  fallbackLang: Lang;
  onAuthFailed: (reason: "unauthorized" | "origin") => void;
  onLogout: () => void;
}

function seconds(ms: number | null): string {
  return ms === null ? "–" : `${(ms / 1000).toFixed(1)} s`;
}

function metricsText(lang: Lang, m: Metrics): string {
  const parts = [`${t(lang, "metricsVoice")} ${seconds(m.firstAudioMs)}`];
  if (m.sttMs !== null) parts.push(`${t(lang, "metricsStt")} ${seconds(m.sttMs)}`);
  parts.push(`${t(lang, "metricsTotal")} ${seconds(m.totalMs)}`);
  return `${t(lang, "metricsLabel")}: ${parts.join(" · ")}`;
}

/** Slice 2: text and voice conversation. Feedback panel and responsive layouts come later. */
export function ChatScreen({ token, fallbackLang, onAuthFailed, onLogout }: Props) {
  const audioRef = useRef<AudioHandler | null>(null);
  const { state, sendText, sendUtterance, interrupt, setLevel, reconnect, dismissError } =
    useChatSocket(token, audioRef);
  const lastAi = [...state.messages].reverse().find((m) => m.role === "ai");
  const voice = useVoice({
    audioRef,
    busy: state.awaitingReply,
    lastAiMessageId: lastAi?.id ?? null,
    sendUtterance,
    interrupt,
  });
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

  const voiceStatus = voice.recording
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
    <div
      className="mx-auto flex h-[100dvh] max-w-2xl flex-col"
      onPointerDownCapture={voice.unlock}
      onKeyDownCapture={voice.unlock}
    >
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
              {message.role === "ai" && !message.streaming && voice.hasAudio(message.id) && (
                <span className="mt-1 flex gap-1">
                  <button
                    type="button"
                    onClick={() => voice.replay(message.id)}
                    aria-label={t(lang, "replay")}
                    title={t(lang, "replay")}
                    className="min-h-12 min-w-12 rounded-lg text-lg text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    ▶
                  </button>
                  <button
                    type="button"
                    onClick={() => voice.replay(message.id, 0.8)}
                    aria-label={t(lang, "replaySlow")}
                    title={t(lang, "replaySlow")}
                    className="min-h-12 min-w-12 rounded-lg text-sm font-medium text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    0.8×
                  </button>
                </span>
              )}
            </p>
          </div>
        ))}
        {showTyping && (
          <p className="text-sm italic text-slate-500 dark:text-slate-400">{t(lang, "thinking")}</p>
        )}
      </div>

      {(voiceStatus || micProblem) && (
        <div className="flex items-center justify-center gap-3 px-4 pb-1 text-sm text-slate-600 dark:text-slate-300">
          <span role="status">{micProblem ?? voiceStatus}</span>
          {voice.speaking && (
            <button
              type="button"
              onClick={voice.stopSpeaking}
              className="min-h-10 rounded-lg px-2 font-medium underline"
            >
              {t(lang, "stopAudio")}
            </button>
          )}
        </div>
      )}

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
        <MicButton
          lang={lang}
          recording={voice.recording}
          handsFree={voice.handsFree}
          disabled={state.status !== "ready" || voice.micError === "unsupported"}
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

      {(state.usage || state.metrics) && (
        <div className="pb-2 text-center text-[11px] text-slate-400">
          {state.metrics && <p>{metricsText(lang, state.metrics)}</p>}
          {state.usage && (
            <p>
              {t(lang, "usageMonth")}: US$ {state.usage.monthUsdEst.toFixed(2)} /{" "}
              {state.usage.budgetUsd.toFixed(0)}
              {onFallbackVoice && ` · ${t(lang, "fallbackVoice")}`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
