/**
 * Joins binary audio frames into complete sentences (SPEC §6, §7). Pure logic.
 *
 * Every binary frame is preceded by exactly one `audio_meta`; the chunk whose meta has
 * `final: true` closes its sentence, which is then ready to play.
 */
import type { ServerMsg } from "../protocol.ts";

export type AudioMeta = Extract<ServerMsg, { type: "audio_meta" }>;

export interface SentenceAudio {
  messageId: string;
  sentence: number;
  mime: string;
  parts: ArrayBuffer[];
}

export class SentenceAssembler {
  private pending: AudioMeta | null = null;
  private buffers = new Map<string, ArrayBuffer[]>();

  meta(meta: AudioMeta): void {
    this.pending = meta;
  }

  /** Returns the sentence when this chunk completes it, else null. */
  chunk(data: ArrayBuffer): SentenceAudio | null {
    const meta = this.pending;
    this.pending = null;
    if (!meta) return null; // a binary frame without audio_meta is ignored
    const key = `${meta.message_id}#${meta.sentence}`;
    const parts = this.buffers.get(key) ?? [];
    parts.push(data);
    if (!meta.final) {
      this.buffers.set(key, parts);
      return null;
    }
    this.buffers.delete(key);
    return { messageId: meta.message_id, sentence: meta.sentence, mime: meta.mime, parts };
  }

  /** Drop everything (barge-in or reconnect). */
  reset(): void {
    this.pending = null;
    this.buffers.clear();
  }
}
