import { useCallback, useEffect, useReducer, useRef, useState, type RefObject } from "react";

import { WS_URL } from "../config.ts";
import {
  CLOSE_FORBIDDEN_ORIGIN,
  CLOSE_UNAUTHORIZED,
  MAX_MIME,
  MAX_USER_TEXT,
  parseServerMsg,
  type ClientMsg,
  type Lang,
  type Level,
  type ServerMsg,
} from "../protocol.ts";
import { OwnRecordings } from "./ownRecordings.ts";
import { chatReducer, initialChatState } from "./state.ts";

/** Audio-related frames, handed to the voice layer (player) as they arrive. */
export type AudioEvent =
  | { kind: "meta"; meta: Extract<ServerMsg, { type: "audio_meta" }> }
  | { kind: "binary"; data: ArrayBuffer }
  | { kind: "fallback"; msg: Extract<ServerMsg, { type: "tts_fallback" }> }
  | { kind: "interrupted"; messageId: string }
  /** The learner's own recording, now linked to its transcript message. */
  | { kind: "own"; messageId: string; blob: Blob }
  | { kind: "reset" };

export type AudioHandler = (event: AudioEvent) => void;

/** After this long without "ready", tell the learner the server is probably waking up. */
export const WAKING_AFTER_MS = 3000;
/** Automatic reconnects after a network close (a sleeping server can take ~1 min to wake). */
export const MAX_AUTO_RETRIES = 10;

/** Backoff for the n-th automatic retry (0-based): 1 s, 2 s, 4 s … capped at 10 s. */
export function retryDelayMs(n: number): number {
  return Math.min(1000 * 2 ** n, 10_000);
}

/**
 * Owns one WebSocket for the given token: authenticates, feeds server messages
 * into the reducer, hands audio frames to `audioRef` and exposes the client commands.
 */
export function useChatSocket(token: string, audioRef?: RefObject<AudioHandler | null>) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const [attempt, setAttempt] = useState(0);
  const [waking, setWaking] = useState(false);
  const retries = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const own = useRef(new OwnRecordings());

  useEffect(() => {
    let active = true; // ignore events from a socket this effect already discarded
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    dispatch({ type: "connecting" });
    const wakingTimer = setTimeout(() => {
      if (active) setWaking(true);
    }, WAKING_AFTER_MS);
    const socket = new WebSocket(`${WS_URL}/ws`);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;
    audioRef?.current?.({ kind: "reset" });
    own.current.clear();

    socket.onopen = () => {
      if (!active) return;
      const auth: ClientMsg = { type: "auth", token };
      socket.send(JSON.stringify(auth));
    };
    socket.onmessage = (event: MessageEvent) => {
      if (!active) return;
      const audio = audioRef?.current;
      if (event.data instanceof ArrayBuffer) {
        audio?.({ kind: "binary", data: event.data });
        return;
      }
      if (typeof event.data !== "string") return;
      const msg = parseServerMsg(event.data);
      if (!msg) return;
      if (msg.type === "transcript") {
        const recording = own.current.transcript();
        if (recording) audio?.({ kind: "own", messageId: msg.message_id, blob: recording });
      } else if (msg.type === "error") {
        own.current.clear();
      }
      if (msg.type === "ready") {
        retries.current = 0;
        clearTimeout(wakingTimer);
        setWaking(false);
      }
      if (msg.type === "audio_meta") audio?.({ kind: "meta", meta: msg });
      else if (msg.type === "tts_fallback") audio?.({ kind: "fallback", msg });
      else if (msg.type === "interrupted") audio?.({ kind: "interrupted", messageId: msg.message_id });
      dispatch({ type: "server", msg });
    };
    socket.onclose = (event: CloseEvent) => {
      if (!active) return;
      const fatal = event.code === CLOSE_UNAUTHORIZED || event.code === CLOSE_FORBIDDEN_ORIGIN;
      if (!fatal && retries.current < MAX_AUTO_RETRIES) {
        // Most likely the free server is asleep or restarting: keep "connecting" and retry.
        const delay = retryDelayMs(retries.current);
        retries.current += 1;
        dispatch({ type: "closed", code: event.code }); // end the turn in progress, if any
        dispatch({ type: "connecting" });
        retryTimer = setTimeout(() => setAttempt((n) => n + 1), delay);
        return;
      }
      clearTimeout(wakingTimer);
      setWaking(false);
      dispatch({ type: "closed", code: event.code });
    };

    return () => {
      active = false;
      clearTimeout(wakingTimer);
      clearTimeout(retryTimer);
      socketRef.current = null;
      socket.close(1000);
    };
  }, [token, attempt, audioRef]);

  const send = useCallback((msg: ClientMsg): boolean => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(msg));
    return true;
  }, []);

  const sendText = useCallback(
    (text: string): boolean => {
      const trimmed = text.trim().slice(0, MAX_USER_TEXT);
      if (!trimmed) return false;
      const ok = send({ type: "user_text", text: trimmed });
      if (ok) {
        own.current.clear();
        dispatch({ type: "sent" });
      }
      return ok;
    },
    [send],
  );

  /** One utterance = start_of_speech, one binary frame, end_of_speech (SPEC §6). */
  const sendUtterance = useCallback(
    async (blob: Blob): Promise<boolean> => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN || blob.size === 0) return false;
      const data = await blob.arrayBuffer();
      const mime = (blob.type || "audio/webm").slice(0, MAX_MIME);
      if (!send({ type: "start_of_speech", mime, purpose: "utterance" })) return false;
      socket.send(data);
      send({ type: "end_of_speech" });
      own.current.sent(blob);
      dispatch({ type: "sent", voice: true });
      return true;
    },
    [send],
  );

  const interrupt = useCallback(() => send({ type: "user_started_speaking" }), [send]);

  /** 🎙 try again: one recorded word, judged by the server (pron_result). */
  const sendPronRetry = useCallback(
    async (blob: Blob, word: string, messageId: string): Promise<boolean> => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN || blob.size === 0) return false;
      const data = await blob.arrayBuffer();
      const mime = (blob.type || "audio/webm").slice(0, MAX_MIME);
      const start: ClientMsg = {
        type: "start_of_speech",
        mime,
        purpose: "pron_retry",
        target_word: word,
        message_id: messageId,
      };
      if (!send(start)) return false;
      socket.send(data);
      send({ type: "end_of_speech" });
      return true;
    },
    [send],
  );

  const regrade = useCallback(
    (messageId: string, text: string): boolean => {
      const trimmed = text.trim().slice(0, MAX_USER_TEXT);
      if (!trimmed) return false;
      const ok = send({ type: "regrade", message_id: messageId, text: trimmed });
      if (ok) dispatch({ type: "edit_message", id: messageId, text: trimmed });
      return ok;
    },
    [send],
  );

  const setCorrection = useCallback(
    (enabled: boolean) => send({ type: "set_correction", enabled }),
    [send],
  );

  const setRecast = useCallback(
    (enabled: boolean) => send({ type: "set_recast", enabled }),
    [send],
  );
  const speakWord = useCallback((word: string) => send({ type: "speak_word", word }), [send]);
  const suggestTopic = useCallback(() => send({ type: "suggest_topic" }), [send]);
  const setTheme = useCallback((theme: string) => send({ type: "set_theme", theme }), [send]);
  const setFacts = useCallback((text: string) => send({ type: "set_facts", text }), [send]);
  const setUiLang = useCallback((uiLang: Lang) => send({ type: "set_ui_lang", ui_lang: uiLang }), [send]);
  const correctionsSeen = useCallback(() => dispatch({ type: "corrections_seen" }), []);

  const setLevel = useCallback((level: Level) => send({ type: "set_level", level }), [send]);
  const reconnect = useCallback(() => {
    retries.current = 0;
    setAttempt((n) => n + 1);
  }, []);
  const dismissError = useCallback(() => dispatch({ type: "dismiss_error" }), []);

  return {
    state,
    /** Still connecting after WAKING_AFTER_MS: the server is probably waking up. */
    waking,
    sendText,
    sendUtterance,
    sendPronRetry,
    interrupt,
    regrade,
    setRecast,
    setCorrection,
    speakWord,
    suggestTopic,
    setTheme,
    setFacts,
    setUiLang,
    correctionsSeen,
    setLevel,
    reconnect,
    dismissError,
  };
}
