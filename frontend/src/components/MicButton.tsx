import type { KeyboardEvent, PointerEvent } from "react";

import { t } from "../i18n.ts";
import type { Lang } from "../protocol.ts";

interface Props {
  lang: Lang;
  recording: boolean;
  handsFree: boolean;
  disabled: boolean;
  onPress: () => void;
  onRelease: () => void;
}

/** Tap = hands-free on/off; hold = push-to-talk (SPEC §9). */
export function MicButton({ lang, recording, handsFree, disabled, onPress, onRelease }: Props) {
  function down(event: PointerEvent<HTMLButtonElement>) {
    if (disabled || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    onPress();
  }

  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if ((event.key === " " || event.key === "Enter") && !event.repeat && !disabled) {
      event.preventDefault();
      onPress();
    }
  }

  function keyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      onRelease();
    }
  }

  const tone = recording
    ? "bg-red-600 text-white"
    : handsFree
      ? "bg-emerald-600 text-white"
      : "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100";

  return (
    <button
      type="button"
      aria-label={t(lang, "mic")}
      aria-pressed={handsFree}
      title={t(lang, "micHint")}
      disabled={disabled}
      onPointerDown={down}
      onPointerUp={onRelease}
      onPointerCancel={onRelease}
      onKeyDown={keyDown}
      onKeyUp={keyUp}
      onContextMenu={(e) => e.preventDefault()}
      style={{ touchAction: "none" }}
      className={`relative flex size-12 shrink-0 select-none items-center justify-center rounded-full transition-colors disabled:opacity-50 ${tone}`}
    >
      {(recording || handsFree) && (
        <span
          aria-hidden
          className={`absolute inset-0 rounded-full ${recording ? "animate-ping bg-red-500/40" : "animate-pulse bg-emerald-500/30"}`}
        />
      )}
      <svg aria-hidden viewBox="0 0 24 24" className="relative size-6" fill="currentColor">
        <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
      </svg>
    </button>
  );
}
