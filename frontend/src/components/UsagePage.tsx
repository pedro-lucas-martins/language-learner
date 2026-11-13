import type { Metrics, Usage } from "../chat/state.ts";
import { level, providerName, share } from "../chat/usageView.ts";
import { t, type StringKey } from "../i18n.ts";
import type { Lang } from "../protocol.ts";

interface Props {
  lang: Lang;
  usage: Usage | null;
  metrics: Metrics | null;
}

const BAR = {
  ok: "bg-accent-500",
  warn: "bg-amber-500",
  alert: "bg-rose-500",
} as const;

function Meter({ label, used, limit, format }: { label: string; used: number; limit: number; format: (n: number) => string }) {
  const fraction = share(used, limit);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="muted tabular-nums">
          {format(used)}
          {limit > 0 ? ` / ${format(limit)}` : ""}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit || undefined}
        aria-valuenow={used}
      >
        <div className={`h-full rounded-full ${BAR[level(fraction)]}`} style={{ width: `${fraction * 100}%` }} />
      </div>
    </div>
  );
}

const int = (n: number) => Math.round(n).toLocaleString();
const usd = (n: number) => `US$ ${n.toFixed(2)}`;
const secs = (ms: number | null) => (ms === null ? "–" : `${(ms / 1000).toFixed(1)} s`);

/** Usage HUD (SPEC §9): estimates from the configured prices, not a bill. */
export function UsagePage({ lang, usage, metrics }: Props) {
  if (!usage) return <p className="muted text-sm">{t(lang, "connecting")}</p>;
  const timing: [StringKey, number | null][] = metrics
    ? [
        ["metricsStt", metrics.sttMs],
        ["metricsFirstToken", metrics.llmFirstTokenMs],
        ["metricsVoice", metrics.firstAudioMs],
        ["metricsTotal", metrics.totalMs],
      ]
    : [];
  return (
    <div className="space-y-6">
      <p className="muted text-sm leading-relaxed">{t(lang, "usageEstimate")}</p>

      <section className="card space-y-4">
        <h3 className="font-semibold">{t(lang, "usageThisMonth")}</h3>
        <Meter label={t(lang, "usageSpend")} used={usage.monthUsdEst} limit={usage.budgetUsd} format={usd} />
        <Meter
          label={t(lang, "usageVoicePlan")}
          used={usage.ttsCharsMonth}
          limit={usage.ttsCharsAllowance}
          format={int}
        />
        <p className="text-sm">
          {t(lang, "usageVoiceNow")}: <strong>
            {providerName(usage.ttsProvider, {
              edge: t(lang, "voiceEdge"),
              browser: t(lang, "voiceBrowser"),
            })}
          </strong>
        </p>
      </section>

      <section className="card space-y-4">
        <h3 className="font-semibold">{t(lang, "usageToday")}</h3>
        <Meter label={t(lang, "usageCalls")} used={usage.llmCallsToday} limit={usage.llmCallsCap} format={int} />
        <Meter
          label={t(lang, "usageAudioSeconds")}
          used={usage.sttSecondsToday}
          limit={usage.sttSecondsCap}
          format={int}
        />
        <Meter label={t(lang, "usageVoiceChars")} used={usage.ttsCharsToday} limit={usage.ttsCharsCap} format={int} />
      </section>

      <section className="card space-y-3">
        <h3 className="font-semibold">{t(lang, "metricsLabel")}</h3>
        {timing.length === 0 ? (
          <p className="muted text-sm">{t(lang, "usageNoTimings")}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            {timing.map(([key, ms]) => (
              <div key={key} className="contents">
                <dt className="muted">{t(lang, key)}</dt>
                <dd className="text-right tabular-nums">{secs(ms)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
}
