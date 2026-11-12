import type { Lang } from "../protocol.ts";

/** What the panel needs to let the learner listen to and retry a word. */
export interface Practice {
  /** UI language (the learner's native language). */
  lang: Lang;
  /** The language being learned (words are spoken in it). */
  targetLang: Lang | undefined;
  recording: boolean;
  listen: (word: string) => void;
  listenSlow: (word: string) => void;
  canListenSlow: (word: string) => boolean;
  startRetry: () => Promise<boolean>;
  finishRetry: (word: string, contextId: string) => Promise<void>;
  result: (contextId: string, word: string) => { better: boolean; tip: string } | undefined;
}
