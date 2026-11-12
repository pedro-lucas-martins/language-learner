import { useCallback, useEffect, useReducer, useRef, useState, type RefObject } from "react";

import { WS_URL } from "../config.ts";
import {
  MAX_MIME,
  MAX_USER_TEXT,
  parseServerMsg,
  type ClientMsg,
  type Level,
  type ServerMsg,
} from "../protocol.ts";
import { chatReducer, initialChatState } from "./state.ts";

/** Audio-related frames, handed to the voice layer (player) as they arrive. */
export type AudioEvent =
  | { kind: "meta"; meta: Extract<ServerMsg, { type: "audio_meta" }> }
  | { kind: "binary"; data: ArrayBuffer }
  | { kind: "fallback"; msg: Extract<ServerMsg, { type: "tts_fallback" }> }
  | { kind: "interrupted"; messageId: string }
  | { kind: "reset" };

export type AudioHandler = (event: AudioEvent) => void;

/**
 * Owns one WebSocket for the given token: authenticates, feeds server messages
 * into the reducer, hands audio frames to `audioRef` and exposes the client commands.
 */
export function useChatSocket(token: string, audioRef?: RefObject<AudioHandler | null>) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let active = true; // ignore events from a socket this effect already discarded
    dispatch({ type: "connecting" });
    const socket = new WebSocket(`${WS_URL}/ws`);
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;
    audioRef?.current?.({ kind: "reset" });

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
      if (msg.type === "audio_meta") audio?.({ kind: "meta", meta: msg });
      else if (msg.type === "tts_fallback") audio?.({ kind: "fallback", msg });
      else if (msg.type === "interrupted") audio?.({ kind: "interrupted", messageId: msg.message_id });
      dispatch({ type: "server", msg });
    };
    socket.onclose = (event: CloseEvent) => {
      if (!active) return;
      dispatch({ type: "closed", code: event.code });
    };

    return () => {
      active = false;
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
      if (ok) dispatch({ type: "sent" });
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
      dispatch({ type: "sent" });
      return true;
    },
    [send],
  );

  const interrupt = useCallback(() => send({ type: "user_started_speaking" }), [send]);

  const setLevel = useCallback((level: Level) => send({ type: "set_level", level }), [send]);
  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);
  const dismissError = useCallback(() => dispatch({ type: "dismiss_error" }), []);

  return { state, sendText, sendUtterance, interrupt, setLevel, reconnect, dismissError };
}
