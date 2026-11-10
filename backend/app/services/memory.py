"""Conversation memory: sliding window + running summary (SPEC §4.2).

Invariant: every turn is either in the window, in the pending buffer (still sent
to the LLM), or already folded into `summary`. Nothing is ever silently dropped.

The class is pure (no I/O): the session orchestrator decides when to call the
summarizer and then reports the result with `apply_summary`.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Turn:
    user: str
    ai: str


@dataclass
class ConversationMemory:
    window_turns: int = 3
    summary_batch_turns: int = 3
    summary: str = ""
    _window: list[Turn] = field(default_factory=list)
    _pending: list[Turn] = field(default_factory=list)
    _summarizing: int = 0  # number of pending turns currently being summarized

    def __post_init__(self) -> None:
        if self.window_turns < 1 or self.summary_batch_turns < 1:
            raise ValueError("window_turns and summary_batch_turns must be >= 1")

    # --- writes -------------------------------------------------------------

    def add_turn(self, user: str, ai: str) -> None:
        self._window.append(Turn(user, ai))
        while len(self._window) > self.window_turns:
            self._pending.append(self._window.pop(0))

    def needs_summary(self) -> bool:
        """True when enough turns left the window and no summary is in flight."""
        return self._summarizing == 0 and len(self._pending) >= self.summary_batch_turns

    def begin_summary(self) -> tuple[str, list[Turn]]:
        """Reserve the current pending turns for summarization.

        Returns (previous summary, turns to merge). Turns that arrive while the
        summary runs stay pending and are handled by the next batch.
        """
        if self._summarizing:
            raise RuntimeError("A summary is already in progress")
        self._summarizing = len(self._pending)
        return self.summary, list(self._pending[: self._summarizing])

    def apply_summary(self, new_summary: str) -> None:
        """Commit a finished summary: the reserved turns now live only in it."""
        if not self._summarizing:
            raise RuntimeError("No summary in progress")
        del self._pending[: self._summarizing]
        self._summarizing = 0
        self.summary = new_summary.strip()

    def abort_summary(self) -> None:
        """Summarization failed: keep the turns pending and retry later."""
        self._summarizing = 0

    # --- reads --------------------------------------------------------------

    def context_turns(self) -> list[Turn]:
        """Turns sent verbatim to the LLM: pending (not yet summarized) + window."""
        return [*self._pending, *self._window]

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def window(self) -> list[Turn]:
        return list(self._window)
