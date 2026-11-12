"""Speech-to-text with Gemini (SPEC §2, §5), kept apart from the chat logic.

LLM-based STT tends to "fix" a learner's grammar. The prompt asks for a verbatim
transcript (errors, hesitations and wrong endings kept) at temperature 0.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.services.llm import LlmError, LlmProvider, LlmUsage
from app.services.prompts import LANG_NAMES

log = logging.getLogger(__name__)

STT_MAX_OUTPUT_TOKENS = 600
AUDIO_TOKENS_PER_SECOND = 32  # Gemini's documented rate for audio input
RETRY_DELAY_S = 0.6

SttErrorCode = Literal["empty", "failed", "not_configured"]

# (model, usage, audio seconds) — writes the usage rows.
RecordStt = Callable[[str, LlmUsage, float], Awaitable[None]]


class SttError(Exception):
    def __init__(self, code: SttErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class SttResult:
    text: str
    seconds: float


def stt_system_prompt(target_lang: str, native_lang: str) -> str:
    target, native = LANG_NAMES[target_lang], LANG_NAMES[native_lang]
    return (
        f"You are a verbatim speech-to-text engine. The speaker is learning {target}; "
        f"their native language is {native}. They mostly speak {target} and may switch to "
        f"{native} for a word or a sentence.\n"
        "Rules:\n"
        "- Write exactly what was said, word for word, in the language it was said in.\n"
        "- Keep every grammatical mistake, wrong word ending, wrong gender or case, and "
        "unusual word order. Never correct, complete or improve the speaker.\n"
        "- Keep hesitations and repetitions that are words (e.g. 'eee', 'yyy', 'é...').\n"
        "- If a word is unclear, write your best guess of what was actually pronounced.\n"
        "- Use normal punctuation and capitalization.\n"
        "- Output only the transcript: no quotes, labels, translations or comments.\n"
        "- If there is no speech, output nothing."
    )


STT_INSTRUCTION = "Transcribe this recording verbatim."


def gemini_mime(mime: str) -> str:
    """Browsers send e.g. 'audio/webm;codecs=opus'; the API wants the bare type."""
    return mime.split(";")[0].strip().lower() or "audio/webm"


def estimate_seconds(num_bytes: int, mime: str) -> float:
    """Rough duration from size, used for the daily cap before calling the API."""
    base = gemini_mime(mime)
    bytes_per_second = 4000 if ("webm" in base or "ogg" in base) else 8000  # ~32 / ~64 kbps
    return num_bytes / bytes_per_second


async def transcribe(
    llm: LlmProvider,
    settings: Settings,
    *,
    audio: bytes,
    mime: str,
    target_lang: str,
    native_lang: str,
    record: RecordStt,
) -> SttResult:
    model = settings.gemini_stt_model
    if not model:
        raise SttError("not_configured", "GEMINI_STT_MODEL is empty")
    system = stt_system_prompt(target_lang, native_lang)
    last: LlmError | None = None
    for attempt in range(2):
        try:
            text, used = await llm.transcribe(
                model=model,
                system=system,
                instruction=STT_INSTRUCTION,
                audio=audio,
                mime=gemini_mime(mime),
                max_output_tokens=STT_MAX_OUTPUT_TOKENS,
            )
        except LlmError as exc:
            last = exc
            log.warning("STT attempt %d failed: %s", attempt + 1, exc)
            if exc.code in ("bad_request", "not_configured") or attempt == 1:
                break
            await asyncio.sleep(RETRY_DELAY_S)
            continue
        seconds = (
            used.audio_tokens / AUDIO_TOKENS_PER_SECOND
            if used.audio_tokens
            else estimate_seconds(len(audio), mime)
        )
        await record(model, used, round(seconds, 2))
        text = text.strip().strip('"').strip()
        if not text:
            raise SttError("empty")
        return SttResult(text=text, seconds=seconds)
    assert last is not None
    raise SttError("not_configured" if last.code == "not_configured" else "failed", str(last))
