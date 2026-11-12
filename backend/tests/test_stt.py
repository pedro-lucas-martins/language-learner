"""STT service (SPEC §5): verbatim prompt, retry, usage and seconds."""

import pytest

from app.services import stt_service
from app.services.llm import FakeLlm, LlmUsage
from app.services.stt_service import SttError, gemini_mime, stt_system_prompt, transcribe
from tests.conftest import make_settings


class Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[str, LlmUsage, float]] = []

    async def __call__(self, model: str, usage: LlmUsage, seconds: float) -> None:
        self.rows.append((model, usage, seconds))


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt_service, "RETRY_DELAY_S", 0)


async def run(llm: FakeLlm, record: Recorder, **settings: object) -> stt_service.SttResult:
    return await transcribe(
        llm,
        make_settings(gemini_stt_model="stt-model", **settings),
        audio=b"x" * 4000,
        mime="audio/webm;codecs=opus",
        target_lang="pl-PL",
        native_lang="pt-BR",
        record=record,
    )


def test_prompt_demands_verbatim_in_both_directions() -> None:
    pl = stt_system_prompt("pl-PL", "pt-BR")
    pt = stt_system_prompt("pt-BR", "pl-PL")
    for prompt in (pl, pt):
        assert "verbatim" in prompt
        assert "Never correct" in prompt
    assert "learning Polish" in pl and "native language is Brazilian Portuguese" in pl
    assert "learning Brazilian Portuguese" in pt and "native language is Polish" in pt


def test_gemini_mime_strips_codec_parameters() -> None:
    assert gemini_mime("audio/webm;codecs=opus") == "audio/webm"
    assert gemini_mime("audio/MP4") == "audio/mp4"


async def test_transcribes_and_records_audio_seconds() -> None:
    llm, record = FakeLlm(transcript=' "Ja mam dwa kot." '), Recorder()
    result = await run(llm, record)
    assert result.text == "Ja mam dwa kot."  # kept verbatim, only quotes/space trimmed
    call = llm.transcribe_calls[0]
    assert call["model"] == "stt-model" and call["mime"] == "audio/webm"
    assert record.rows[0][0] == "stt-model"
    assert record.rows[0][2] == 5.0  # 160 audio tokens / 32 per second


async def test_transient_error_is_retried_once() -> None:
    llm, record = FakeLlm(transcribe_failures=["unavailable"]), Recorder()
    result = await run(llm, record)
    assert len(llm.transcribe_calls) == 2 and result.text


async def test_two_failures_raise_failed() -> None:
    llm, record = FakeLlm(transcribe_failures=["quota", "quota"]), Recorder()
    with pytest.raises(SttError) as info:
        await run(llm, record)
    assert info.value.code == "failed" and record.rows == []


async def test_bad_request_is_not_retried() -> None:
    llm = FakeLlm(transcribe_failures=["bad_request"])
    with pytest.raises(SttError):
        await run(llm, Recorder())
    assert len(llm.transcribe_calls) == 1


async def test_empty_transcript_is_an_error_but_still_billed() -> None:
    llm, record = FakeLlm(transcript="  "), Recorder()
    with pytest.raises(SttError) as info:
        await run(llm, record)
    assert info.value.code == "empty" and len(record.rows) == 1


async def test_missing_model_is_not_configured() -> None:
    with pytest.raises(SttError) as info:
        await transcribe(
            FakeLlm(),
            make_settings(),
            audio=b"x",
            mime="audio/webm",
            target_lang="pl-PL",
            native_lang="pt-BR",
            record=Recorder(),
        )
    assert info.value.code == "not_configured"
