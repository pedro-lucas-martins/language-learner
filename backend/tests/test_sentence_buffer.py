"""Sentence buffer (SPEC §6): both languages, decimals, abbreviations, Polish dates."""

import pytest

from app.services.sentence_buffer import SentenceBuffer


def split(text: str, chunk: int = 3) -> list[str]:
    """Feed the text in small chunks like a stream, then flush."""
    buf = SentenceBuffer()
    out: list[str] = []
    for i in range(0, len(text), chunk):
        out += buf.push(text[i : i + chunk])
    rest = buf.flush()
    return out + ([rest] if rest else [])


def test_polish_reply_splits_on_sentence_ends() -> None:
    assert split("Cześć! Mam na imię Kasia i mieszkam w Krakowie. A ty, gdzie mieszkasz?") == [
        "Cześć! Mam na imię Kasia i mieszkam w Krakowie.",
        "A ty, gdzie mieszkasz?",
    ]


def test_portuguese_reply_splits_on_sentence_ends() -> None:
    assert split("Que legal que você gosta de café! Eu também. Você toma de manhã?") == [
        "Que legal que você gosta de café!",
        "Eu também. Você toma de manhã?",
    ]


def test_short_sentences_are_merged_until_min_chars() -> None:
    # "Oi! Tudo bem?" is under 15 characters, so it waits for the next sentence end.
    assert split("Oi! Tudo bem? Eu estou ótima, obrigada. E você, como vai?") == [
        "Oi! Tudo bem? Eu estou ótima, obrigada.",
        "E você, como vai?",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Kosztuje 3.5 złotego, to tanio. A u was?",
            ["Kosztuje 3.5 złotego, to tanio.", "A u was?"],
        ),
        ("Custa 2.50 reais por pessoa aqui. E aí?", ["Custa 2.50 reais por pessoa aqui.", "E aí?"]),
        (
            "Święto jest 11.11. i wtedy nie pracuję. A ty pracujesz?",
            ["Święto jest 11.11. i wtedy nie pracuję.", "A ty pracujesz?"],
        ),
        (
            "Lubię owoce, np. jabłka i gruszki. A ty?",
            ["Lubię owoce, np. jabłka i gruszki.", "A ty?"],
        ),
        (
            "Conheci a Sra. Silva ontem na padaria. Você conhece ela?",
            ["Conheci a Sra. Silva ontem na padaria.", "Você conhece ela?"],
        ),
        (
            "Mieszkam przy ul. Długiej od dwóch lat. Fajnie, prawda?",
            ["Mieszkam przy ul. Długiej od dwóch lat.", "Fajnie, prawda?"],
        ),
    ],
)
def test_no_split_on_decimals_dates_and_abbreviations(text: str, expected: list[str]) -> None:
    assert split(text) == expected


def test_ellipsis_question_runs_and_quotes() -> None:
    assert split('Ela disse: "Vamos sair hoje à noite!" E você foi?! Que coragem…') == [
        'Ela disse: "Vamos sair hoje à noite!"',
        "E você foi?! Que coragem…",
    ]


def test_newline_ends_a_sentence() -> None:
    assert split("Pierwsza linijka bez kropki\nDruga linijka też bez kropki") == [
        "Pierwsza linijka bez kropki",
        "Druga linijka też bez kropki",
    ]


def test_waits_for_the_next_character_before_splitting() -> None:
    buf = SentenceBuffer()
    assert buf.push("To kosztuje 3.") == []
    assert buf.push("5 zł, dobrze? ") == ["To kosztuje 3.5 zł, dobrze?"]


def test_chunking_does_not_change_the_result() -> None:
    text = "Byłam wczoraj w kinie. Film był super! Często chodzisz do kina?"
    assert split(text, 1) == split(text, 7) == split(text, 100)


def test_flush_returns_nothing_for_whitespace() -> None:
    buf = SentenceBuffer()
    buf.push("   ")
    assert buf.flush() is None
