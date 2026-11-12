"""LLM access (SPEC §2, §4): provider interface, Gemini implementation, retry + model fallback.

Nothing outside this module talks to the Gemini SDK, so tests use `FakeLlm` and the
rest of the app only sees `LlmProvider`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from app.config import Settings

log = logging.getLogger(__name__)

ChatRole = Literal["user", "model"]
LlmErrorCode = Literal["quota", "unavailable", "bad_request", "not_configured"]

FIRST_CHUNK_TIMEOUT_S = 15.0
TOTAL_TIMEOUT_S = 45.0
RETRY_DELAY_S = 0.6


class LlmError(Exception):
    def __init__(self, code: LlmErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    audio_tokens: int = 0
    """Part of `input_tokens` that was audio (Gemini counts 32 tokens per second)."""


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class StreamEnd:
    usage: LlmUsage


StreamEvent = TextDelta | StreamEnd


class LlmProvider(Protocol):
    def stream(
        self,
        *,
        model: str,
        system: str,
        history: Sequence[tuple[ChatRole, str]],
        max_output_tokens: int,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        """Yield TextDelta chunks, then exactly one StreamEnd. Raise LlmError on failure."""
        ...

    async def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> tuple[str, LlmUsage]: ...

    async def transcribe(
        self,
        *,
        model: str,
        system: str,
        instruction: str,
        audio: bytes,
        mime: str,
        max_output_tokens: int,
    ) -> tuple[str, LlmUsage]:
        """Speech-to-text with temperature 0 (SPEC §5). Raise LlmError on failure."""
        ...


# --- Gemini -------------------------------------------------------------------


class GeminiProvider:
    def __init__(self, api_key: str, thinking_level: str = "") -> None:
        self._api_key = api_key
        self._thinking_level = thinking_level.upper()
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if not self._api_key:
            raise LlmError("not_configured", "GEMINI_API_KEY is empty")
        if self._client is None:
            from google import genai  # imported lazily: slow import, unused in tests

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, system: str, max_output_tokens: int, temperature: float):  # type: ignore[no-untyped-def]
        from google.genai import types

        thinking = (
            types.ThinkingConfig(thinking_level=self._thinking_level)
            if self._thinking_level
            else None
        )
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            thinking_config=thinking,
        )

    @staticmethod
    def _contents(history: Sequence[tuple[ChatRole, str]]):  # type: ignore[no-untyped-def]
        from google.genai import types

        return [
            types.Content(role=role, parts=[types.Part.from_text(text=text)])
            for role, text in history
        ]

    @staticmethod
    def _usage(metadata) -> LlmUsage:  # type: ignore[no-untyped-def]
        if metadata is None:
            return LlmUsage()
        output = (metadata.candidates_token_count or 0) + (metadata.thoughts_token_count or 0)
        audio = sum(
            detail.token_count or 0
            for detail in (metadata.prompt_tokens_details or [])
            if str(getattr(detail.modality, "value", detail.modality)).upper() == "AUDIO"
        )
        return LlmUsage(
            input_tokens=metadata.prompt_token_count or 0,
            output_tokens=output,
            audio_tokens=audio,
        )

    @staticmethod
    def _map_error(exc: Exception) -> LlmError:
        from google.genai import errors

        if isinstance(exc, LlmError):
            return exc
        if isinstance(exc, errors.APIError):
            if exc.code == 429:
                return LlmError("quota", str(exc))
            if exc.code >= 500:
                return LlmError("unavailable", str(exc))
            return LlmError("bad_request", str(exc))
        if isinstance(exc, TimeoutError):
            return LlmError("unavailable", "timeout")
        log.exception("Unexpected Gemini error")
        return LlmError("unavailable", type(exc).__name__)

    async def stream(
        self,
        *,
        model: str,
        system: str,
        history: Sequence[tuple[ChatRole, str]],
        max_output_tokens: int,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        if not model:
            raise LlmError("not_configured", "model name is empty")
        usage = LlmUsage()
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                client = self._get_client()
                response = await asyncio.wait_for(
                    client.aio.models.generate_content_stream(
                        model=model,
                        contents=self._contents(history),
                        config=self._config(system, max_output_tokens, temperature),
                    ),
                    FIRST_CHUNK_TIMEOUT_S,
                )
                async for chunk in response:
                    if chunk.usage_metadata is not None:
                        usage = self._usage(chunk.usage_metadata)
                    text = chunk.text or ""
                    if text:
                        yield TextDelta(text)
        except Exception as exc:  # noqa: BLE001 — mapped to a typed error
            raise self._map_error(exc) from exc
        yield StreamEnd(usage)

    async def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> tuple[str, LlmUsage]:
        if not model:
            raise LlmError("not_configured", "model name is empty")
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                response = await self._get_client().aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=self._config(system, max_output_tokens, temperature),
                )
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        return (response.text or "").strip(), self._usage(response.usage_metadata)

    async def transcribe(
        self,
        *,
        model: str,
        system: str,
        instruction: str,
        audio: bytes,
        mime: str,
        max_output_tokens: int,
    ) -> tuple[str, LlmUsage]:
        from google.genai import types

        if not model:
            raise LlmError("not_configured", "model name is empty")
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=audio, mime_type=mime),
                    types.Part.from_text(text=instruction),
                ],
            )
        ]
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_S):
                response = await self._get_client().aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=self._config(system, max_output_tokens, 0.0),
                )
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        return (response.text or "").strip(), self._usage(response.usage_metadata)


# --- retry + fallback ----------------------------------------------------------


@dataclass(frozen=True)
class ModelChoice:
    model: str
    role: Literal["chat", "utility"]


def chat_model_chain(settings: Settings, *, budget_exceeded: bool) -> list[ModelChoice]:
    """Models to try for Track 1, in order (SPEC §1: cheapest model once over budget)."""
    chain: list[ModelChoice] = []
    if not budget_exceeded and settings.gemini_chat_model:
        chain.append(ModelChoice(settings.gemini_chat_model, "chat"))
    if settings.gemini_utility_model:
        chain.append(ModelChoice(settings.gemini_utility_model, "utility"))
    return chain


async def stream_with_fallback(
    llm: LlmProvider,
    chain: Sequence[ModelChoice],
    *,
    system: str,
    history: Sequence[tuple[ChatRole, str]],
    max_output_tokens: int,
    temperature: float,
) -> AsyncIterator[tuple[ModelChoice, StreamEvent]]:
    """Stream from the first model that works.

    Each model gets one retry for transient errors (quota/unavailable). Once any
    text has been sent, errors are not retried (the client already shows a
    partial reply) and propagate to the caller.
    """
    if not chain:
        raise LlmError("not_configured", "no Gemini model configured")
    last_error: LlmError | None = None
    for choice in chain:
        for attempt in range(2):
            started = False
            try:
                async for event in llm.stream(
                    model=choice.model,
                    system=system,
                    history=history,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                ):
                    if isinstance(event, TextDelta):
                        started = True
                    yield choice, event
                return
            except LlmError as exc:
                if started:
                    raise
                last_error = exc
                log.warning("LLM %s attempt %d failed: %s", choice.model, attempt + 1, exc)
                if exc.code in ("bad_request", "not_configured"):
                    break  # retrying the same model will not help
                if attempt == 0:
                    await asyncio.sleep(RETRY_DELAY_S)
    assert last_error is not None
    raise last_error


# --- test double ---------------------------------------------------------------


class FakeLlm:
    """Deterministic provider for tests. Never touches the network."""

    def __init__(
        self,
        reply: str = "Cześć! Jak się masz?",
        summary: str = "Summary.",
        fail_models: dict[str, LlmErrorCode] | None = None,
        transcript: str = "Cześć, mam na imię Pedro.",
        transcribe_failures: list[LlmErrorCode] | None = None,
        stream_delay_s: float = 0.0,
    ) -> None:
        self.reply = reply
        self.summary = summary
        self.fail_models = fail_models or {}
        self.transcript = transcript
        self.transcribe_failures = list(transcribe_failures or [])
        self.stream_delay_s = stream_delay_s
        self.stream_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.transcribe_calls: list[dict[str, object]] = []

    async def stream(
        self,
        *,
        model: str,
        system: str,
        history: Sequence[tuple[ChatRole, str]],
        max_output_tokens: int,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        self.stream_calls.append({"model": model, "system": system, "history": list(history)})
        if model in self.fail_models:
            raise LlmError(self.fail_models[model], "fake failure")
        words = self.reply.split(" ")
        for i, word in enumerate(words):
            if self.stream_delay_s:
                await asyncio.sleep(self.stream_delay_s)
            yield TextDelta(word if i == 0 else " " + word)
        yield StreamEnd(LlmUsage(input_tokens=100, output_tokens=len(words)))

    async def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> tuple[str, LlmUsage]:
        self.complete_calls.append({"model": model, "system": system, "prompt": prompt})
        if model in self.fail_models:
            raise LlmError(self.fail_models[model], "fake failure")
        return self.summary, LlmUsage(input_tokens=50, output_tokens=10)

    async def transcribe(
        self,
        *,
        model: str,
        system: str,
        instruction: str,
        audio: bytes,
        mime: str,
        max_output_tokens: int,
    ) -> tuple[str, LlmUsage]:
        self.transcribe_calls.append(
            {
                "model": model,
                "system": system,
                "instruction": instruction,
                "mime": mime,
                "bytes": len(audio),
            }
        )
        if self.transcribe_failures:
            raise LlmError(self.transcribe_failures.pop(0), "fake failure")
        return self.transcript, LlmUsage(input_tokens=200, output_tokens=12, audio_tokens=160)
