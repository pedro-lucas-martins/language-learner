import { describe, expect, it } from "vitest";

import { DEFAULT_VAD, rms, VadDetector, type VadEvent } from "./vad.ts";

/** Calibrate in a quiet room, then feed (level, durationMs) segments at 40 ms steps. */
function run(detector: VadDetector, segments: [number, number][]): VadEvent[] {
  const events: VadEvent[] = [];
  let now = 0;
  for (; now < DEFAULT_VAD.calibrateMs; now += 40) detector.update(0.001, now);
  for (const [level, duration] of segments) {
    for (let t = 0; t < duration; t += 40) {
      const event = detector.update(level, now);
      if (event) events.push(event);
      now += 40;
    }
  }
  return events;
}

describe("VadDetector", () => {
  it("starts on loud audio and ends after the silence window", () => {
    const events = run(new VadDetector(), [
      [0.001, 400],
      [0.2, 1200],
      [0.001, 1200],
    ]);
    expect(events).toEqual(["start", "end"]);
  });

  it("does not end during short pauses between words", () => {
    const events = run(new VadDetector(), [
      [0.2, 600],
      [0.001, 400], // shorter than silenceMs
      [0.2, 600],
      [0.001, 1200],
    ]);
    expect(events).toEqual(["start", "end"]);
  });

  it("discards very short noises", () => {
    const events = run(new VadDetector(), [
      [0.2, 80],
      [0.001, 1200],
    ]);
    expect(events).toEqual(["start", "discard"]);
  });

  it("ends long utterances at the maximum length", () => {
    const events = run(new VadDetector({ ...DEFAULT_VAD, maxUtteranceMs: 2000 }), [[0.2, 2600]]);
    expect(events.slice(0, 2)).toEqual(["start", "end"]);
  });

  it("a constant hum from the start is learned during calibration, not heard as speech", () => {
    const detector = new VadDetector();
    const events: VadEvent[] = [];
    for (let now = 0; now < 4000; now += 40) {
      const event = detector.update(0.02, now); // louder than the minimum threshold
      if (event) events.push(event);
    }
    expect(events).toEqual([]);
    expect(detector.threshold).toBeGreaterThan(0.02);
  });

  it("a hum that starts mid-session eventually ends the utterance", () => {
    const events = run(new VadDetector(), [[0.03, 20_000]]);
    expect(events[0]).toBe("start");
    expect(events[1]).toBe("end"); // ended by adaptation, before the 30 s maximum
  });

  it("reset forgets an utterance in progress", () => {
    const detector = new VadDetector();
    expect(run(detector, [[0.2, 200]])).toEqual(["start"]);
    detector.reset();
    expect(detector.isSpeaking).toBe(false);
  });
});

describe("rms", () => {
  it("computes root mean square", () => {
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5);
    expect(rms(new Float32Array([]))).toBe(0);
  });
});
