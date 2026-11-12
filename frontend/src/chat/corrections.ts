/** Pure helpers for the corrections panel. */
import type { ChatMessage, Feedback } from "./state.ts";

export interface CorrectionEntry {
  message: ChatMessage;
  feedback: Feedback;
}

/** The learner's messages that have feedback, newest first. */
export function correctionEntries(
  messages: readonly ChatMessage[],
  feedback: Readonly<Record<string, Feedback>>,
): CorrectionEntry[] {
  const out: CorrectionEntry[] = [];
  for (const message of messages) {
    const entry = feedback[message.id];
    if (message.role === "user" && entry) out.push({ message, feedback: entry });
  }
  return out.reverse();
}

/** Split a grammar card front "a «b» c" into parts so the marked mistake can be highlighted. */
export function splitMarked(front: string): { text: string; marked: boolean }[] {
  const parts: { text: string; marked: boolean }[] = [];
  const re = /«([^»]*)»/g;
  let last = 0;
  for (let match = re.exec(front); match; match = re.exec(front)) {
    if (match.index > last) parts.push({ text: front.slice(last, match.index), marked: false });
    parts.push({ text: match[1] ?? "", marked: true });
    last = match.index + match[0].length;
  }
  if (last < front.length) parts.push({ text: front.slice(last), marked: false });
  return parts;
}
