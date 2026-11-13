"""Topics data and picker (SPEC §8)."""

import random
from collections import Counter

from app.services import topics


def test_topics_file_is_valid_and_portuguese_only() -> None:
    items = topics.load_topics()
    per_level = Counter(t.level for t in items)
    assert set(per_level) == {"A1", "A2", "B1", "B2", "C1"}
    assert all(n >= 25 for n in per_level.values())
    assert {t.lang for t in items} == {"pt-BR"}
    assert len({t.text for t in items}) == len(items)
    assert topics.available("pt-BR") and not topics.available("pl-PL")


def test_pick_matches_language_and_level_and_does_not_repeat() -> None:
    items = topics.load_topics()
    used: set[str] = set()
    rng = random.Random(1)
    picked = [topics.pick(items, lang="pt-BR", level="B1", used=used, rng=rng) for _ in range(25)]
    assert all(t is not None and t.level == "B1" for t in picked)
    assert len({t.id for t in picked if t}) == 25  # all different until the level is exhausted


def test_pick_starts_over_when_exhausted() -> None:
    items = topics.load_topics()
    used = {t.id for t in items if t.level == "A1"}
    again = topics.pick(items, lang="pt-BR", level="A1", used=used, rng=random.Random(2))
    assert again is not None and again.level == "A1"
    assert used == {again.id}  # the A1 history was reset, other levels untouched


def test_no_topic_for_polish() -> None:
    assert (
        topics.pick(topics.load_topics(), lang="pl-PL", level="A1", used=set(), rng=random.Random())
        is None
    )
