/**
 * Plays the AI's sentences in order (SPEC §6) and keeps them for replay.
 *
 * One reused <audio> element (unlocked on the first tap, for iOS/Android autoplay
 * rules). Sentences the server could not synthesize are spoken with speechSynthesis.
 * Replay never asks the server again: it uses the audio already received, and 0.8×
 * uses `playbackRate`.
 */
import type { Lang } from "../protocol.ts";

export type PlayItem =
  | { kind: "audio"; messageId: string; sentence: number; blob: Blob }
  | { kind: "speech"; messageId: string; sentence: number; text: string; lang: Lang };

const MAX_KEPT_MESSAGES = 40;

/** A 1-sample silent WAV, played on the first user gesture to unlock audio output. */
function silentWav(): Blob {
  const buffer = new ArrayBuffer(46);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) =>
    [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  write(0, "RIFF");
  view.setUint32(4, 38, true);
  write(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, 2, true);
  return new Blob([buffer], { type: "audio/wav" });
}

export class AudioPlayer {
  private readonly el: HTMLAudioElement;
  private queue: PlayItem[] = [];
  private current: PlayItem | null = null;
  private url: string | null = null;
  private rate = 1;
  private unlocked = false;
  private readonly library = new Map<string, PlayItem[]>();
  private readonly dropped = new Set<string>();

  constructor(private readonly onChange: (playing: boolean) => void) {
    this.el = new Audio();
    this.el.setAttribute("playsinline", "");
    this.el.preload = "auto";
    this.el.onended = () => this.next();
    this.el.onerror = () => this.next(); // undecodable sentence: skip it
  }

  get playing(): boolean {
    return this.current !== null;
  }

  /** Call from a user gesture (tap/click/key) before the first playback. */
  unlock(): void {
    if (this.unlocked) return;
    this.unlocked = true;
    const url = URL.createObjectURL(silentWav());
    this.el.src = url;
    void this.el.play().catch(() => undefined).finally(() => URL.revokeObjectURL(url));
  }

  /** Keep a ready-made clip (e.g. the learner's own recording) for replay under `key`. */
  addClip(key: string, blob: Blob): void {
    this.library.delete(key);
    this.keep({ kind: "audio", messageId: key, sentence: 0, blob });
  }

  has(messageId: string): boolean {
    return this.library.has(messageId);
  }

  enqueue(item: PlayItem): void {
    if (this.dropped.has(item.messageId)) return; // frames that arrive after a barge-in
    this.keep(item);
    this.rate = 1;
    this.queue.push(item);
    if (!this.current) this.next();
  }

  /** Barge-in: silence now, clear the queue and ignore late frames of this message. */
  stop(dropMessageId?: string): void {
    if (dropMessageId) this.dropped.add(dropMessageId);
    this.queue = [];
    this.el.pause();
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    this.finish();
  }

  /** Play a whole reply again from what was received (normal speed or slower). */
  replay(messageId: string, rate = 1): void {
    const items = this.library.get(messageId);
    if (!items) return;
    this.stop();
    this.rate = rate;
    this.queue = [...items].sort((a, b) => a.sentence - b.sentence);
    this.next();
  }

  private keep(item: PlayItem): void {
    const items = this.library.get(item.messageId) ?? [];
    items.push(item);
    this.library.set(item.messageId, items);
    while (this.library.size > MAX_KEPT_MESSAGES) {
      const oldest = this.library.keys().next().value;
      if (oldest === undefined) break;
      this.library.delete(oldest);
    }
  }

  private next(): void {
    this.releaseUrl();
    const item = this.queue.shift() ?? null;
    const wasPlaying = this.current !== null;
    this.current = item;
    if (!item) {
      if (wasPlaying) this.onChange(false);
      return;
    }
    if (!wasPlaying) this.onChange(true);
    if (item.kind === "audio") {
      this.url = URL.createObjectURL(item.blob);
      this.el.src = this.url;
      this.el.playbackRate = this.rate;
      void this.el.play().catch(() => this.next());
    } else {
      this.speak(item.text, item.lang);
    }
  }

  private speak(text: string, lang: Lang): void {
    if (typeof speechSynthesis === "undefined") {
      this.next();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = this.rate;
    utterance.onend = () => this.next();
    utterance.onerror = () => this.next();
    speechSynthesis.speak(utterance);
  }

  private finish(): void {
    this.releaseUrl();
    const wasPlaying = this.current !== null;
    this.current = null;
    if (wasPlaying) this.onChange(false);
  }

  private releaseUrl(): void {
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = null;
  }
}
