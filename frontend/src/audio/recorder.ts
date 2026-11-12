/** MediaRecorder wrapper: one blob per utterance (SPEC §6). */

/** Preferred order from SPEC §6. */
export const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/mp4", "audio/aac"] as const;

export function pickMime(isSupported: (mime: string) => boolean): string | null {
  return MIME_CANDIDATES.find((mime) => isSupported(mime)) ?? null;
}

export const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
};

export function micSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined"
  );
}

export class UtteranceRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  readonly mime: string;

  constructor(private readonly stream: MediaStream) {
    this.mime = pickMime((m) => MediaRecorder.isTypeSupported(m)) ?? "";
  }

  get recording(): boolean {
    return this.recorder?.state === "recording";
  }

  start(): void {
    if (this.recording) return;
    this.chunks = [];
    const recorder = this.mime
      ? new MediaRecorder(this.stream, { mimeType: this.mime })
      : new MediaRecorder(this.stream);
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.start(250);
    this.recorder = recorder;
  }

  /** Stop and return the whole utterance (chunks concatenated, one decodable file). */
  stop(): Promise<Blob | null> {
    const recorder = this.recorder;
    this.recorder = null;
    if (!recorder || recorder.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = () => {
        const type = recorder.mimeType || this.mime;
        resolve(this.chunks.length ? new Blob(this.chunks, { type }) : null);
        this.chunks = [];
      };
      recorder.stop();
    });
  }

  /** Stop and throw the audio away. */
  cancel(): void {
    void this.stop();
  }
}
