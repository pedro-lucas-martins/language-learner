import type { KeyboardEvent, PointerEvent } from "react";

import { t } from "../i18n.ts";
import type { Lang } from "../protocol.ts";
import { MicIcon } from "./icons.tsx";

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
    ? "bg-rose-500 text-white"
    : handsFree
      ? "bg-accent-600 text-white"
      : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100";

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
      className={`relative flex size-11 shrink-0 select-none items-center justify-center rounded-full transition-colors disabled:opacity-40 ${tone}`}
    >
      {(recording || handsFree) && (
        <span
          aria-hidden
          className={`absolute inset-0 rounded-full ${recording ? "animate-ping bg-rose-400/40" : "animate-pulse bg-accent-500/25"}`}
        />
      )}
      <MicIcon className="relative size-5" />
    </button>
  );
}
