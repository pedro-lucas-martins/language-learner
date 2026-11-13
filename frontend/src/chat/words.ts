/** Word counting for the facts editor (the server truncates at the same limit). */
export const FACTS_MAX_WORDS = 100;

export function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}
