import { afterEach, describe, expect, it, vi } from "vitest";

import { AudioPlayer, clampVolume } from "./player.ts";

describe("clampVolume", () => {
  it("keeps 0–200 % in 5 % steps and repairs bad values", () => {
    expect(clampVolume(1)).toBe(1);
    expect(clampVolume(1.5)).toBe(1.5);
    expect(clampVolume(1.52)).toBe(1.5);
    expect(clampVolume(-1)).toBe(0);
    expect(clampVolume(9)).toBe(2);
    expect(clampVolume(Number.NaN)).toBe(1);
  });
});

class FakeAudio {
  volume = 1;
  src = "";
  playbackRate = 1;
  preload = "";
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  setAttribute() {}
  play() {
    return Promise.resolve();
  }
  pause() {}
}

function stubBrowser(withWebAudio: boolean) {
  const gain = { gain: { value: 1 }, connect: vi.fn() };
  class FakeContext {
    state = "running";
    destination = {};
    createGain() {
      return gain;
    }
    createMediaElementSource() {
      return { connect: vi.fn() };
    }
    resume() {
      return Promise.resolve();
    }
  }
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("window", withWebAudio ? { AudioContext: FakeContext } : {});
  vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: () => undefined });
  return gain;
}

const clip = (messageId: string) =>
  ({ kind: "audio", messageId, sentence: 0, blob: new Blob(["x"]) }) as const;

describe("AudioPlayer volume", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("boosts the AI voice through the gain node, but not the learner's own recording", () => {
    const gain = stubBrowser(true);
    const player = new AudioPlayer(() => undefined);
    player.unlock();
    player.setVolume(1.6);
    player.enqueue(clip("ai-1"));
    expect(gain.gain.value).toBe(1.6);
    player.stop();
    player.addClip("own:u1", new Blob(["y"]));
    player.replay("own:u1");
    expect(gain.gain.value).toBe(1);
  });

  it("without Web Audio it falls back to <audio>.volume, capped at 100 %", () => {
    stubBrowser(false);
    const player = new AudioPlayer(() => undefined);
    const el = (player as unknown as { el: FakeAudio }).el;
    player.unlock();
    player.setVolume(0.4);
    player.enqueue(clip("ai-1"));
    expect(el.volume).toBe(0.4);
    player.setVolume(2);
    expect(el.volume).toBe(1);
  });
});
