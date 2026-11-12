/**
 * Volume-based voice activity detection (SPEC §6). Pure decision logic; the browser
 * side (`MicMonitor`) feeds it one RMS level every few tens of milliseconds.
 *
 * Recording starts as soon as the level crosses the threshold (so the first syllable is
 * kept). The utterance ends after `silenceMs` below the threshold; if it held less than
 * `minSpeechMs` of loud audio it is discarded (a cough, a door).
 */

export interface VadOptions {
  /** Minimum absolute threshold (RMS of samples in [-1, 1]). */
  minThreshold: number;
  /** Threshold = max(minThreshold, noiseFloor × noiseFactor). */
  noiseFactor: number;
  silenceMs: number;
  minSpeechMs: number;
  maxUtteranceMs: number;
  /** At start, only learn the background level for this long (no events). */
  calibrateMs: number;
}

export const DEFAULT_VAD: VadOptions = {
  minThreshold: 0.015,
  noiseFactor: 3,
  silenceMs: 900,
  minSpeechMs: 250,
  maxUtteranceMs: 30_000,
  calibrateMs: 500,
};

export type VadEvent = "start" | "end" | "discard" | null;

export class VadDetector {
  private speaking = false;
  private startedAt = 0;
  private lastLoudAt = 0;
  private loudMs = 0;
  private lastAt: number | null = null;
  private firstAt: number | null = null;
  private noiseFloor = 0.005;

  constructor(private readonly opts: VadOptions = DEFAULT_VAD) {}

  get threshold(): number {
    return Math.max(this.opts.minThreshold, this.noiseFloor * this.opts.noiseFactor);
  }

  get isSpeaking(): boolean {
    return this.speaking;
  }

  update(level: number, now: number): VadEvent {
    const dt = this.lastAt === null ? 0 : Math.max(0, now - this.lastAt);
    this.lastAt = now;
    this.firstAt ??= now;
    if (now - this.firstAt < this.opts.calibrateMs) {
      this.noiseFloor = this.noiseFloor * 0.8 + level * 0.2;
      return null;
    }
    const loud = level >= this.threshold;

    if (!this.speaking) {
      if (!loud) {
        // Slowly follow the background noise while nobody speaks.
        this.noiseFloor = this.noiseFloor * 0.95 + level * 0.05;
        return null;
      }
      this.speaking = true;
      this.startedAt = now;
      this.lastLoudAt = now;
      this.loudMs = 0;
      return "start";
    }

    // Very slow adaptation while recording: speech is unaffected over a few seconds, but a
    // hum that started mid-utterance (a fan) eventually counts as silence and ends it.
    this.noiseFloor = this.noiseFloor * 0.999 + level * 0.001;
    if (loud) {
      this.lastLoudAt = now;
      this.loudMs += dt;
    }
    const tooLong = now - this.startedAt >= this.opts.maxUtteranceMs;
    if (now - this.lastLoudAt >= this.opts.silenceMs || tooLong) {
      this.speaking = false;
      return this.loudMs >= this.opts.minSpeechMs ? "end" : "discard";
    }
    return null;
  }

  /** Forget the current utterance (used when VAD is paused). */
  reset(): void {
    this.speaking = false;
    this.lastAt = null; // the learned noise floor is kept
  }
}

/** Root mean square of a block of samples. */
export function rms(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const s of samples) sum += s * s;
  return Math.sqrt(sum / samples.length);
}

/** Polls the microphone level and feeds a VadDetector. */
export class MicMonitor {
  private ctx: AudioContext | null = null;
  private timer: number | null = null;
  private readonly detector: VadDetector;

  constructor(
    private readonly stream: MediaStream,
    private readonly onEvent: (event: Exclude<VadEvent, null>) => void,
    opts: VadOptions = DEFAULT_VAD,
  ) {
    this.detector = new VadDetector(opts);
  }

  start(): void {
    if (this.timer !== null) return;
    this.ctx = new AudioContext();
    const source = this.ctx.createMediaStreamSource(this.stream);
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const block = new Float32Array(analyser.fftSize);
    this.timer = window.setInterval(() => {
      analyser.getFloatTimeDomainData(block);
      const event = this.detector.update(rms(block), performance.now());
      if (event) this.onEvent(event);
    }, 40);
  }

  /** While paused the level is ignored and any utterance in progress is forgotten. */
  reset(): void {
    this.detector.reset();
  }

  stop(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    void this.ctx?.close();
    this.ctx = null;
    this.detector.reset();
  }
}
