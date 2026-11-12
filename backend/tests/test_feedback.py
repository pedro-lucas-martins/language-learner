"""Track 2 (SPEC §5): prompts per direction, strict JSON validation, model choice."""

import json

import pytest

from app.services import feedback as fb
from app.services.llm import FakeLlm, LlmUsage
from tests.conftest import make_settings

MSG = "Wczoraj ja idę do sklep i kupiłem dwa kot."


def payload(**kw: object) -> str:
    return json.dumps(kw, ensure_ascii=False)


def test_prompt_pt_to_pl_explains_in_portuguese_with_polish_focus() -> None:
    prompt = fb.feedback_system_prompt("pl-PL", "pt-BR", with_audio=True)
    assert "Polish teacher" in prompt
    assert "written in Brazilian Portuguese" in prompt
    assert "MUST be written in Brazilian Portuguese. Never in English" in prompt
    assert "genitivo" in prompt  # the style example is in the explanation language
    assert "biernik" in prompt and "dokonany" in prompt  # grammar focus
    assert "ł (like English w" in prompt  # pronunciation focus
    assert "When unsure, do NOT report" in prompt


def test_prompt_pl_to_pt_explains_in_polish_with_portuguese_focus() -> None:
    prompt = fb.feedback_system_prompt("pt-BR", "pl-PL", with_audio=True)
    assert "Brazilian Portuguese teacher" in prompt
    assert "MUST be written in Polish. Never in English" in prompt
    assert "przyimek" in prompt
    assert "ser vs estar" in prompt and "avó vs avô" in prompt


def test_text_prompt_has_no_pronunciation_section() -> None:
    prompt = fb.feedback_system_prompt("pl-PL", "pt-BR", with_audio=False)
    assert "PRONUNCIATION" not in prompt
    assert '"pron" must be []' in prompt


def test_parses_grammar_and_pronunciation() -> None:
    raw = payload(
        ok=False,
        errs=[{"e": "do sklep", "c": "do sklepu", "r": "'do' pede genitivo.", "p": "Em PT..."}],
        pron=[{"w": "sklep", "heard": "esklep", "tip": "Não ponha 'e' antes.", "sev": "major"}],
    )
    result = fb.parse_feedback(raw, MSG, with_audio=True)
    assert result is not None and not result.ok
    assert result.errs[0].c == "do sklepu"
    assert result.pron[0].w == "sklep"


def test_full_ok_shape_from_structured_output_is_valid() -> None:
    result = fb.parse_feedback('{"ok": true, "errs": [], "pron": []}', MSG, with_audio=True)
    assert result is not None and result.ok


def test_ok_true_alone_is_valid() -> None:
    result = fb.parse_feedback('{"ok": true}', MSG, with_audio=True)
    assert result is not None and result.ok and result.errs == [] and result.pron == []


@pytest.mark.parametrize("raw", ["not json", "[]", '{"errs": []}', '{"ok": "maybe"}'])
def test_invalid_json_is_dropped(raw: str) -> None:
    assert fb.parse_feedback(raw, MSG, with_audio=False) is None


def test_json_in_code_fence_is_accepted() -> None:
    assert fb.parse_feedback('```json\n{"ok": true}\n```', MSG, with_audio=False) is not None


def test_items_not_in_the_message_are_dropped_and_lists_capped() -> None:
    errs = [{"e": "dwa kot", "c": "dwa koty", "r": "r", "p": ""}] * 2 + [
        {"e": "nie ma tego", "c": "x", "r": "r", "p": ""},  # not in the message
        {"e": "idę", "c": "idę", "r": "same", "p": ""},  # not a correction
        {"e": "ja idę", "c": "poszedłem", "r": "r", "p": ""},
        {"e": "kupiłem", "c": "kupiłam", "r": "r", "p": ""},  # 4th valid one: capped
    ]
    pron = [
        {"w": "kot", "heard": "kotch", "tip": "t", "sev": "minor"},
        {"w": "pies", "heard": "pjes", "tip": "t", "sev": "major"},  # word not said
        {"w": "kot", "heard": "x", "tip": "t", "sev": "loud"},  # invalid severity
    ]
    result = fb.parse_feedback(payload(ok=False, errs=errs, pron=pron), MSG, with_audio=True)
    assert result is not None
    assert [e.e for e in result.errs] == ["dwa kot", "dwa kot", "ja idę"]
    assert [p.w for p in result.pron] == ["kot"]


def test_text_feedback_never_has_pronunciation() -> None:
    raw = payload(ok=False, errs=[], pron=[{"w": "kot", "heard": "k", "tip": "t", "sev": "major"}])
    result = fb.parse_feedback(raw, MSG, with_audio=False)
    assert result is not None and result.pron == [] and result.ok


def test_case_and_spacing_do_not_matter_for_matching() -> None:
    raw = payload(ok=False, errs=[{"e": "Do  Sklep", "c": "do sklepu", "r": "r", "p": ""}])
    result = fb.parse_feedback(raw, MSG, with_audio=False)
    assert result is not None and len(result.errs) == 1


def test_needs_feedback_from_three_words() -> None:
    assert not fb.needs_feedback("Cześć Kasia")
    assert fb.needs_feedback("Mam dwa kot")


def test_model_choice_and_budget() -> None:
    s = make_settings(gemini_feedback_model="fb", gemini_utility_model="util")
    assert fb.feedback_model(s, budget_exceeded=False) == "fb"
    assert fb.feedback_model(s, budget_exceeded=True) == "util"


class Recorder:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, LlmUsage]] = []

    async def __call__(self, role: str, model: str, usage: LlmUsage) -> None:
        self.rows.append((role, model, usage))


async def run(llm: FakeLlm, budget: bool = False) -> tuple[fb.FeedbackResult | None, Recorder]:
    record = Recorder()
    result = await fb.analyze(
        llm,
        make_settings(gemini_feedback_model="fb", gemini_utility_model="util"),
        text=MSG,
        audio=None,
        target_lang="pl-PL",
        native_lang="pt-BR",
        budget_exceeded=budget,
        record=record,
    )
    return result, record


async def test_analyze_records_usage_with_role(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLlm()
    result, record = await run(llm)
    assert llm.analyze_calls[0]["json_schema"] is fb.FEEDBACK_JSON_SCHEMA
    assert result is not None and result.ok
    assert record.rows[0][:2] == ("feedback", "fb")
    _, record = await run(FakeLlm(), budget=True)
    assert record.rows[0][:2] == ("utility", "util")


async def test_analyze_retries_once_then_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fb, "RETRY_DELAY_S", 0)
    llm = FakeLlm(analyze_failures=["unavailable"])
    result, _ = await run(llm)
    assert result is not None and len(llm.analyze_calls) == 2
    llm = FakeLlm(analyze_failures=["quota", "quota"])
    result, record = await run(llm)
    assert result is None and record.rows == []


async def test_invalid_model_output_is_billed_but_ignored() -> None:
    result, record = await run(FakeLlm(analysis="sorry, I can't"))
    assert result is None and len(record.rows) == 1


def test_pronunciation_heard_exactly_as_written_is_dropped() -> None:
    pron = [
        {"w": "sklep", "heard": "Sklep.", "tip": "t", "sev": "minor"},
        {"w": "kot", "heard": "kotchi", "tip": "t", "sev": "major"},
    ]
    result = fb.parse_feedback(payload(ok=False, errs=[], pron=pron), MSG, with_audio=True)
    assert result is not None and [p.w for p in result.pron] == ["kot"]
