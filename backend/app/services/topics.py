"""Conversation topics (SPEC §8): ready-made icebreakers, zero LLM tokens. Pure logic."""

import json
import random
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "topics.json"


class Topic(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    lang: str = Field(pattern=r"^(pt-BR|pl-PL)$")
    level: str = Field(pattern=r"^(A1|A2|B1|B2|C1)$")
    theme: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=5, max_length=200)


_TOPICS = TypeAdapter(list[Topic])


@lru_cache
def load_topics(path: Path = DATA_FILE) -> tuple[Topic, ...]:
    topics = _TOPICS.validate_python(json.loads(path.read_text(encoding="utf-8")))
    ids = [t.id for t in topics]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate topic ids")
    return tuple(topics)


def available(lang: str, topics: Sequence[Topic] | None = None) -> bool:
    """Topics exist only for learners of Portuguese (approved exception, SPEC §1)."""
    return any(t.lang == lang for t in (topics if topics is not None else load_topics()))


def pick(
    topics: Sequence[Topic],
    *,
    lang: str,
    level: str,
    used: set[str],
    rng: random.Random,
) -> Topic | None:
    """An unused topic for this language and level. When all were used, start over.

    `used` is updated in place (the session's memory of what was already asked).
    """
    pool = [t for t in topics if t.lang == lang and t.level == level]
    if not pool:
        return None
    fresh = [t for t in pool if t.id not in used]
    if not fresh:
        used.difference_update(t.id for t in pool)
        fresh = pool
    topic = rng.choice(fresh)
    used.add(topic.id)
    return topic
