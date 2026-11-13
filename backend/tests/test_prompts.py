import pytest

from app.services.memory import Turn
from app.services.prompts import chat_system_prompt, summary_user_prompt, truncate_words


@pytest.mark.parametrize(
    ("target", "native", "language"),
    [("pl-PL", "pt-BR", "Polish"), ("pt-BR", "pl-PL", "Brazilian Portuguese")],
)
def test_prompt_targets_the_right_language_for_both_directions(
    target: str, native: str, language: str
) -> None:
    prompt = chat_system_prompt(
        target_lang=target, native_lang=native, level="A1", user_facts="", summary=""
    )
    assert f"Reply ONLY in {language}." in prompt
    assert "Never explain grammar" in prompt
    assert "Level A1" in prompt


def test_static_part_comes_first_and_is_identical_across_users() -> None:
    a = chat_system_prompt(
        target_lang="pl-PL",
        native_lang="pt-BR",
        level="B1",
        user_facts="Likes football.",
        summary="x",
    )
    b = chat_system_prompt(
        target_lang="pl-PL", native_lang="pt-BR", level="C1", user_facts="", summary=""
    )
    static_a = a.split("\n\nLevel ")[0]
    static_b = b.split("\n\nLevel ")[0]
    assert static_a == static_b
    assert a.index("Likes football.") > a.index("Level B1")
    assert a.index("Summary of this conversation") > a.index("Likes football.")


def test_empty_facts_and_summary_are_omitted() -> None:
    prompt = chat_system_prompt(
        target_lang="pt-BR", native_lang="pl-PL", level="A2", user_facts=" ", summary=""
    )
    assert "What you know about the learner" not in prompt
    assert "Summary of this conversation" not in prompt


def test_summary_prompt_lists_turns() -> None:
    text = summary_user_prompt("old", [Turn("hi", "hello"), Turn("bye", "ciao")])
    assert "Previous summary: old" in text
    assert "Learner: bye" in text and "Friend: hello" in text


def test_truncate_words() -> None:
    assert truncate_words("a b c d", 2) == "a b"
    assert truncate_words("a b", 5) == "a b"


def test_correction_rule_beginner_explains_in_ui_language() -> None:
    from app.services.prompts import chat_system_prompt

    prompt = chat_system_prompt(
        target_lang="pl-PL",
        native_lang="pt-BR",
        level="A1",
        user_facts="",
        summary="",
        correct=True,
        explain_lang="pt-BR",
    )
    assert "correcting ONE mistake only" in prompt
    assert "never 'correct' a form that is already right" in prompt
    assert "counts toward your length limit" in prompt
    assert "ONE short sentence in Brazilian Portuguese saying why" in prompt
    assert "Never explain grammar" not in prompt


def test_correction_rule_from_b1_stays_in_target_language() -> None:
    from app.services.prompts import chat_system_prompt

    prompt = chat_system_prompt(
        target_lang="pt-BR",
        native_lang="pl-PL",
        level="B1",
        user_facts="",
        summary="",
        correct=True,
        explain_lang="pl-PL",
    )
    assert "correcting ONE mistake only" in prompt
    assert "Say the correction in Brazilian Portuguese only" in prompt
    assert "saying why" not in prompt


def test_correction_off_keeps_the_no_correction_rule() -> None:
    from app.services.prompts import chat_system_prompt

    prompt = chat_system_prompt(
        target_lang="pl-PL",
        native_lang="pt-BR",
        level="A1",
        user_facts="",
        summary="",
    )
    assert "Never explain grammar" in prompt
    assert "Correction in the conversation" not in prompt
