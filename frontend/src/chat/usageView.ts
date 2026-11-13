/** Pure helpers for the usage page. */

/** 0–1 share of a limit; 0 when there is no limit. */
export function share(used: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.max(0, Math.min(1, used / limit));
}

/** Bar color: calm until 75%, warning until 95%, alert above. */
export function level(fraction: number): "ok" | "warn" | "alert" {
  if (fraction >= 0.95) return "alert";
  if (fraction >= 0.75) return "warn";
  return "ok";
}

const BRANDS: Record<string, string> = { elevenlabs: "ElevenLabs", google: "Google" };

/** Brand names stay as they are; the free fallbacks are translated by the caller. */
export function providerName(name: string, fallbacks: { edge: string; browser: string }): string {
  if (name === "edge") return fallbacks.edge;
  if (name === "browser") return fallbacks.browser;
  return BRANDS[name] ?? name;
}
