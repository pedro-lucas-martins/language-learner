import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { WS_URL } from "../config.ts";
import { MAX_USER_TEXT, parseServerMsg, type ClientMsg, type Level } from "../protocol.ts";
import { chatReducer, initialChatState } from "./state.ts";

/**
 * Owns one WebSocket for the given token: authenticates, feeds server messages
 * into the reducer and exposes the client commands.
 */
export function useChatSocket(token: string) {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let active = true; // ignore events from a socket this effect already discarded
    dispatch({ type: "connecting" });
    const socket = new WebSocket(`${WS_URL}/ws`);
    socketRef.current = socket;

    socket.onopen = () => {
      if (!active) return;
      const auth: ClientMsg = { type: "auth", token };
      socket.send(JSON.stringify(auth));
    };
    socket.onmessage = (event: MessageEvent) => {
      if (!active || typeof event.data !== "string") return;
      const msg = parseServerMsg(event.data);
      if (msg) dispatch({ type: "server", msg });
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
  }, [token, attempt]);

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

  const setLevel = useCallback((level: Level) => send({ type: "set_level", level }), [send]);
  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);
  const dismissError = useCallback(() => dispatch({ type: "dismiss_error" }), []);

  return { state, sendText, setLevel, reconnect, dismissError };
}
