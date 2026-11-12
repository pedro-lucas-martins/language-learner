interface Props {
  label: string;
  /** "user" while the learner's voice is transcribed, "ai" while the reply is prepared. */
  side: "user" | "ai";
}

/** Animated dots with a short label, so the learner knows the app is working. */
export function ThinkingBubble({ label, side }: Props) {
  return (
    <div className={side === "user" ? "flex justify-end" : "flex justify-start"}>
      <div
        role="status"
        aria-live="polite"
        className={`inline-flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm ${
          side === "user"
            ? "rounded-br-md bg-accent-50 text-accent-700 dark:bg-accent-700/20 dark:text-accent-100"
            : "rounded-bl-md border border-zinc-200/80 bg-white text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
        }`}
      >
        <span className="flex items-center gap-1" aria-hidden>
          <span className="ll-dot size-1.5 rounded-full bg-current" />
          <span className="ll-dot size-1.5 rounded-full bg-current" />
          <span className="ll-dot size-1.5 rounded-full bg-current" />
        </span>
        <span>{label}…</span>
      </div>
    </div>
  );
}
