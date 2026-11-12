"""SM-2 scheduling (SPEC §5)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.sm2 import MIN_EASE, RELEARN_MINUTES, review

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


def step(card: tuple[float, int, int], grade: int) -> tuple[float, int, int]:
    s = review(ease=card[0], interval_days=card[1], repetitions=card[2], grade=grade, now=NOW)
    return s.ease, s.interval_days, s.repetitions


def test_good_answers_grow_1_6_then_by_ease() -> None:
    card = (2.5, 0, 0)
    card = step(card, 4)
    assert card == (2.5, 1, 1)
    card = step(card, 4)
    assert card == (2.5, 6, 2)
    card = step(card, 4)
    assert card == (2.5, 15, 3)


def test_easy_raises_ease_and_hard_lowers_it() -> None:
    assert step((2.5, 0, 0), 5)[0] == pytest.approx(2.6)
    assert step((2.5, 0, 0), 3)[0] == pytest.approx(2.36)


def test_failure_resets_and_comes_back_soon() -> None:
    s = review(ease=2.5, interval_days=15, repetitions=3, grade=1, now=NOW)
    assert (s.repetitions, s.interval_days) == (0, 0)
    assert s.due_at == NOW + timedelta(minutes=RELEARN_MINUTES)
    assert s.ease < 2.5


def test_ease_never_drops_below_minimum() -> None:
    card = (1.35, 0, 0)
    for _ in range(5):
        card = step(card, 0)
    assert card[0] == MIN_EASE


def test_due_date_follows_interval() -> None:
    s = review(ease=2.5, interval_days=6, repetitions=2, grade=4, now=NOW)
    assert s.due_at == NOW + timedelta(days=s.interval_days)


@pytest.mark.parametrize("grade", [-1, 6])
def test_invalid_grade(grade: int) -> None:
    with pytest.raises(ValueError):
        review(ease=2.5, interval_days=0, repetitions=0, grade=grade, now=NOW)
