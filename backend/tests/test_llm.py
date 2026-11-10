from collections.abc import AsyncIterator

import pytest

from app.services import llm as llm_mod
from app.services.llm import (
    FakeLlm,
    LlmError,
    LlmUsage,
    ModelChoice,
    StreamEnd,
    StreamEvent,
    TextDelta,
    chat_model_chain,
    stream_with_fallback,
)
from tests.conftest import make_settings

CHAIN = [ModelChoice("chat-model", "chat"), ModelChoice("utility-model", "utility")]


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_mod, "RETRY_DELAY_S", 0)


async def _collect(provider: object, chain: list[ModelChoice]) -> list[tuple[str, StreamEvent]]:
    return [
        (choice.model, event)
        async for choice, event in stream_with_fallback(
            provider,  # type: ignore[arg-type]
            chain,
            system="s",
            history=[("user", "hi")],
            max_output_tokens=10,
            temperature=0.5,
        )
    ]


async def test_uses_first_model_when_it_works() -> None:
    fake = FakeLlm(reply="Cześć tam")
    events = await _collect(fake, CHAIN)
    assert {model for model, _ in events} == {"chat-model"}
    assert "".join(e.text for _, e in events if isinstance(e, TextDelta)) == "Cześć tam"
    assert isinstance(events[-1][1], StreamEnd)


async def test_transient_failure_is_retried_then_falls_back() -> None:
    fake = FakeLlm(fail_models={"chat-model": "unavailable"})
    events = await _collect(fake, CHAIN)
    models_called = [call["model"] for call in fake.stream_calls]
    assert models_called == ["chat-model", "chat-model", "utility-model"]
    assert events[0][0] == "utility-model"


async def test_bad_request_is_not_retried() -> None:
    fake = FakeLlm(fail_models={"chat-model": "bad_request"})
    await _collect(fake, CHAIN)
    assert [call["model"] for call in fake.stream_calls] == ["chat-model", "utility-model"]


async def test_all_models_failing_raises_last_error() -> None:
    fake = FakeLlm(fail_models={"chat-model": "quota", "utility-model": "quota"})
    with pytest.raises(LlmError) as info:
        await _collect(fake, CHAIN)
    assert info.value.code == "quota"


async def test_empty_chain_is_not_configured() -> None:
    with pytest.raises(LlmError) as info:
        await _collect(FakeLlm(), [])
    assert info.value.code == "not_configured"


class _BreaksMidStream:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, **_: object) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        yield TextDelta("partial")
        raise LlmError("unavailable", "connection dropped")

    async def complete(self, **_: object) -> tuple[str, LlmUsage]:
        raise NotImplementedError


async def test_failure_after_text_is_not_retried() -> None:
    provider = _BreaksMidStream()
    with pytest.raises(LlmError):
        await _collect(provider, CHAIN)
    assert provider.calls == 1


def test_chain_uses_only_cheap_model_when_over_budget() -> None:
    settings = make_settings()
    assert chat_model_chain(settings, budget_exceeded=False) == CHAIN
    assert chat_model_chain(settings, budget_exceeded=True) == [CHAIN[1]]


def test_chain_skips_unconfigured_models() -> None:
    settings = make_settings(gemini_chat_model="", gemini_utility_model="")
    assert chat_model_chain(settings, budget_exceeded=False) == []
