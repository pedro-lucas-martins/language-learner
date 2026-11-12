"""Split the streamed AI reply into sentences for TTS (SPEC §6). Pure logic.

A sentence ends at `. ! ? …` or a newline once at least `min_chars` are buffered. A dot
does not end a sentence after a number (`3.5`, Polish dates `11.11.`, ordinals `2.`)
or after a common abbreviation. A boundary is only accepted once the next character is
known, so `3.` waiting for `5` is never split early.
"""

import re

MIN_CHARS = 15

# Lower-case, without the trailing dot. Polish and Brazilian Portuguese.
# fmt: off
ABBREVIATIONS = frozenset({
    # Polish
    "np", "itd", "itp", "tzn", "tj", "m.in", "dr", "prof", "mgr", "inż", "ul", "al",
    "godz", "min", "r", "w", "wg", "tys", "mln", "zł", "gr", "nr", "str", "tel",
    "pl", "św", "ds", "jw", "por", "zob", "płn", "płd", "wsch", "zach", "p", "pt",
    # Portuguese
    "sr", "sra", "srta", "dra", "av", "pág", "ex", "etc", "obs", "aprox", "vs",
    "jr", "profª", "drª", "a.c", "d.c", "n", "nº", "km", "kg", "h",
})
# fmt: on

_TERMINATORS = ".!?…"
_CLOSERS = "\"'”’»)]"
_WORD_BEFORE_DOT = re.compile(r"([\wªº.]+)$")


def _is_abbreviation_or_number(before: str) -> bool:
    """`before` is the buffer up to (not including) a dot."""
    match = _WORD_BEFORE_DOT.search(before)
    if not match:
        return False
    word = match.group(1).lower()
    if word.replace(".", "").isdigit():
        return True  # 3.5, 11.11., ordinals like "2."
    return word in ABBREVIATIONS


class SentenceBuffer:
    def __init__(self, min_chars: int = MIN_CHARS) -> None:
        self._buf = ""
        self._min = min_chars

    def push(self, delta: str) -> list[str]:
        """Add streamed text; return the sentences that are now complete."""
        self._buf += delta
        out: list[str] = []
        while True:
            end = self._find_boundary()
            if end is None:
                return out
            sentence = self._buf[:end].strip()
            self._buf = self._buf[end:]
            if sentence:
                out.append(sentence)

    def flush(self) -> str | None:
        """The remaining text at the end of the reply, if any."""
        rest = self._buf.strip()
        self._buf = ""
        return rest or None

    def _find_boundary(self) -> int | None:
        """Index just after the first acceptable sentence end, or None."""
        buf = self._buf
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == "\n":
                if len(buf[:i].strip()) >= self._min:
                    return i + 1
            elif ch in _TERMINATORS:
                # Swallow runs like "?!" or "..." and closing quotes/brackets.
                j = i + 1
                while j < len(buf) and buf[j] in _TERMINATORS:
                    j += 1
                while j < len(buf) and buf[j] in _CLOSERS:
                    j += 1
                if j >= len(buf):
                    return None  # need the next character to decide
                if (
                    buf[j].isspace()
                    and len(buf[:j].strip()) >= self._min
                    and not (ch == "." and j == i + 1 and _is_abbreviation_or_number(buf[:i]))
                ):
                    return j
                i = j
                continue
            i += 1
        return None
