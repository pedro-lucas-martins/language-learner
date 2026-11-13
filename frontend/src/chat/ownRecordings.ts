/**
 * Links each recorded utterance to the transcript the server sends back for it, so the
 * learner can hear what they actually said next to what was transcribed. Pure logic.
 *
 * Utterances are answered in order (one transcript each). A typed message or an error
 * (e.g. the STT failed) means the pending recording will never get a transcript.
 */
export class OwnRecordings {
  private pending: Blob[] = [];

  /** An utterance was sent. */
  sent(blob: Blob): void {
    this.pending.push(blob);
  }

  /** A transcript arrived: the oldest pending recording belongs to it. */
  transcript(): Blob | null {
    return this.pending.shift() ?? null;
  }

  /** A typed message, an error or a reconnect: forget recordings without a transcript. */
  clear(): void {
    this.pending = [];
  }
}

/** Player key for the learner's own recording of a message. */
export const ownKey = (messageId: string) => `own:${messageId}`;
