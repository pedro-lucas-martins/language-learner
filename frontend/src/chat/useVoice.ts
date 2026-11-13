/**
 * Voice layer (SPEC §6): microphone (auto-VAD or push-to-talk), barge-in and playback.
 *
 * - Tap the mic: hands-free mode on/off (volume VAD decides when an utterance ends).
 * - Hold the mic: push-to-talk; releasing sends the utterance.
 * - While the AI is speaking, auto-VAD is paused so the app does not hear itself.
 *   Pressing the mic interrupts the AI (barge-in).
 */
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { SentenceAssembler } from "../audio/assembler.ts";
import { AudioPlayer } from "../audio/player.ts";
import { MIC_CONSTRAINTS, micSupported, UtteranceRecorder } from "../audio/recorder.ts";
import { MicMonitor } from "../audio/vad.ts";
import { ownKey } from "./ownRecordings.ts";
import type { AudioHandler } from "./useChatSocket.ts";

/** A press shorter than this is a tap (toggle hands-free), longer is push-to-talk. */
export const TAP_MS = 300;
/** After the AI stops speaking, wait a little before listening again (echo tail). */
const RESUME_AFTER_PLAYBACK_MS = 400;
/** Ignore accidental clicks shorter than this. */
const MIN_UTTERANCE_BYTES = 1500;

export type MicError = "unsupported" | "denied" | null;

interface Options {
  audioRef: RefObject<AudioHandler | null>;
  /** The server is working on a turn (transcribing, thinking or still speaking). */
  busy: boolean;
  /** Id of the latest AI message, dropped from playback on barge-in. */
  lastAiMessageId: string | null;
  sendUtterance: (blob: Blob) => Promise<boolean>;
  interrupt: () => boolean;
}

export function useVoice({ audioRef, busy, lastAiMessageId, sendUtterance, interrupt }: Options) {
  const [handsFree, setHandsFree] = useState(false);
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [micError, setMicError] = useState<MicError>(micSupported() ? null : "unsupported");
  const [audioVersion, setAudioVersion] = useState(0); // re-render when replayable audio arrives

  const playerRef = useRef<AudioPlayer | null>(null);
  const assembler = useRef(new SentenceAssembler());
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<UtteranceRecorder | null>(null);
  const monitorRef = useRef<MicMonitor | null>(null);
  const pressedAt = useRef<number | null>(null);
  const resumeAt = useRef(0);

  // Latest values for callbacks that outlive a render.
  const latest = useRef({ busy, lastAiMessageId, sendUtterance, interrupt, handsFree });
  latest.current = { busy, lastAiMessageId, sendUtterance, interrupt, handsFree };

  if (playerRef.current === null && typeof window !== "undefined") {
    playerRef.current = new AudioPlayer((playing) => {
      setSpeaking(playing);
      if (playing) monitorRef.current?.reset();
      else resumeAt.current = performance.now() + RESUME_AFTER_PLAYBACK_MS;
    });
  }

  // Audio frames from the socket → sentences → player.
  useEffect(() => {
    audioRef.current = (event) => {
      const player = playerRef.current;
      if (!player) return;
      switch (event.kind) {
        case "meta":
          assembler.current.meta(event.meta);
          break;
        case "binary": {
          const sentence = assembler.current.chunk(event.data);
          if (sentence) {
            player.enqueue({
              kind: "audio",
              messageId: sentence.messageId,
              sentence: sentence.sentence,
              blob: new Blob(sentence.parts, { type: sentence.mime }),
            });
            setAudioVersion((n) => n + 1);
          }
          break;
        }
        case "fallback":
          player.enqueue({
            kind: "speech",
            messageId: event.msg.message_id,
            sentence: event.msg.sentence,
            text: event.msg.text,
            lang: event.msg.lang,
          });
          setAudioVersion((n) => n + 1);
          break;
        case "own":
          player.addClip(ownKey(event.messageId), event.blob);
          setAudioVersion((n) => n + 1);
          break;
        case "interrupted":
          player.stop(event.messageId);
          assembler.current.reset();
          break;
        case "reset":
          player.stop();
          assembler.current.reset();
          break;
      }
    };
    return () => {
      audioRef.current = null;
    };
  }, [audioRef]);

  const finishUtterance = useCallback(async () => {
    const recorder = recorderRef.current;
    setRecording(false);
    if (!recorder) return;
    const blob = await recorder.stop();
    if (blob && blob.size >= MIN_UTTERANCE_BYTES) await latest.current.sendUtterance(blob);
  }, []);

  /** Stop the AI before the learner speaks over it. */
  const bargeIn = useCallback(() => {
    const player = playerRef.current;
    const { busy: isBusy, lastAiMessageId: aiId } = latest.current;
    if (player?.playing || isBusy) {
      latest.current.interrupt();
      player?.stop(aiId ?? undefined);
      assembler.current.reset();
    }
  }, []);

  const ensureMic = useCallback(async (): Promise<boolean> => {
    if (streamRef.current) return true;
    if (!micSupported()) {
      setMicError("unsupported");
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
      streamRef.current = stream;
      recorderRef.current = new UtteranceRecorder(stream);
      setMicError(null);
      return true;
    } catch {
      setMicError("denied");
      return false;
    }
  }, []);

  const startHandsFree = useCallback(() => {
    const stream = streamRef.current;
    if (!stream || monitorRef.current) return;
    const monitor = new MicMonitor(stream, (event) => {
      const recorder = recorderRef.current;
      // Paused while the AI speaks, during push-to-talk, and just after playback.
      if (
        !recorder ||
        playerRef.current?.playing ||
        pressedAt.current !== null ||
        performance.now() < resumeAt.current
      ) {
        if (event === "start") monitor.reset();
        return;
      }
      if (event === "start") {
        bargeIn();
        recorder.start();
        setRecording(true);
      } else if (event === "end") {
        void finishUtterance();
      } else {
        recorder.cancel();
        setRecording(false);
      }
    });
    monitor.start();
    monitorRef.current = monitor;
  }, [bargeIn, finishUtterance]);

  const stopHandsFree = useCallback(() => {
    monitorRef.current?.stop();
    monitorRef.current = null;
    if (pressedAt.current === null && recorderRef.current?.recording) {
      recorderRef.current.cancel();
      setRecording(false);
    }
  }, []);

  /** Pointer down on the mic: start recording right away (push-to-talk or a tap). */
  const press = useCallback(async () => {
    playerRef.current?.unlock();
    if (!(await ensureMic())) return;
    const recorder = recorderRef.current;
    if (!recorder) return;
    bargeIn();
    monitorRef.current?.reset();
    if (recorder.recording) recorder.cancel(); // an auto-VAD utterance in progress
    pressedAt.current = performance.now();
    recorder.start();
    setRecording(true);
  }, [bargeIn, ensureMic]);

  /** Pointer up: short press toggles hands-free, long press sends the utterance. */
  const release = useCallback(async () => {
    const started = pressedAt.current;
    pressedAt.current = null;
    if (started === null) return;
    if (performance.now() - started < TAP_MS) {
      recorderRef.current?.cancel();
      setRecording(false);
      const next = !latest.current.handsFree;
      setHandsFree(next);
      if (next) startHandsFree();
      else stopHandsFree();
      return;
    }
    await finishUtterance();
  }, [finishUtterance, startHandsFree, stopHandsFree]);

  /** 🎙 try again: record one word while the button is held (hands-free VAD is paused). */
  const startClip = useCallback(async (): Promise<boolean> => {
    playerRef.current?.unlock();
    if (!(await ensureMic())) return false;
    const recorder = recorderRef.current;
    if (!recorder) return false;
    playerRef.current?.stop();
    monitorRef.current?.reset();
    if (recorder.recording) recorder.cancel();
    pressedAt.current = performance.now();
    recorder.start();
    setRecording(true);
    return true;
  }, [ensureMic]);

  const finishClip = useCallback(async (): Promise<Blob | null> => {
    pressedAt.current = null;
    setRecording(false);
    const blob = (await recorderRef.current?.stop()) ?? null;
    return blob && blob.size >= MIN_UTTERANCE_BYTES / 3 ? blob : null;
  }, []);

  /** ▶ for a word: replay what was received, or null when it has to be fetched first. */
  const playWord = useCallback((word: string, rate = 1): boolean => {
    const player = playerRef.current;
    const key = `word:${word}`;
    if (!player?.has(key)) return false;
    player.unlock();
    player.replay(key, rate);
    return true;
  }, []);

  const unlock = useCallback(() => playerRef.current?.unlock(), []);
  const replay = useCallback((messageId: string, rate = 1) => {
    playerRef.current?.unlock();
    playerRef.current?.replay(messageId, rate);
  }, []);
  const hasAudio = useCallback(
    (messageId: string) => playerRef.current?.has(messageId) ?? false,
    [audioVersion], // new audio arrived: a fresh function makes callers re-check
  );
  const stopSpeaking = useCallback(() => bargeIn(), [bargeIn]);

  // Release the microphone and silence playback when the screen goes away.
  useEffect(
    () => () => {
      monitorRef.current?.stop();
      recorderRef.current?.cancel();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      playerRef.current?.stop();
    },
    [],
  );

  return {
    handsFree,
    recording,
    speaking,
    micError,
    press,
    release,
    unlock,
    replay,
    hasAudio,
    stopSpeaking,
    startClip,
    finishClip,
    playWord,
  };
}
