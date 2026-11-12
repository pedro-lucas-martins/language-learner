"""SM-2 spaced repetition (SPEC §5). Pure function.

Grades 0–5 as in SuperMemo 2. The UI maps its buttons to 1 (again), 3 (hard), 4 (good),
5 (easy). A failed card (grade < 3) comes back after `RELEARN_MINUTES` in the same day
instead of tomorrow, so it can be practised again while the mistake is fresh.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_EASE = 1.3
RELEARN_MINUTES = 10


@dataclass(frozen=True)
class Schedule:
    ease: float
    interval_days: int
    repetitions: int
    due_at: datetime


def review(
    *, ease: float, interval_days: int, repetitions: int, grade: int, now: datetime
) -> Schedule:
    if not 0 <= grade <= 5:
        raise ValueError("grade must be between 0 and 5")
    new_ease = max(MIN_EASE, ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    if grade < 3:
        return Schedule(
            ease=new_ease,
            interval_days=0,
            repetitions=0,
            due_at=now + timedelta(minutes=RELEARN_MINUTES),
        )
    repetitions += 1
    if repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = max(1, round(interval_days * new_ease))
    return Schedule(
        ease=round(new_ease, 4),
        interval_days=interval,
        repetitions=repetitions,
        due_at=now + timedelta(days=interval),
    )
