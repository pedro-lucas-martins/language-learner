"""Flashcards from the learner's own mistakes (SPEC §5).

Grammar card: front = the message with the wrong part marked; back = correction + rule.
Pronunciation card: front = the word (▶ listen, 🎙 try again); back = the tip.
The same front is never stored twice for a user (also enforced by a unique constraint).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Flashcard
from app.protocol import GrammarError, PronIssue

MARK_OPEN, MARK_CLOSE = "«", "»"


def grammar_front(message: str, err: GrammarError) -> str:
    """The message with the wrong substring marked, e.g. 'Ja mam «dwa kot» w domu.'"""
    index = message.casefold().find(err.e.casefold())
    if index < 0:
        return f"{MARK_OPEN}{err.e}{MARK_CLOSE}"
    end = index + len(err.e)
    return f"{message[:index]}{MARK_OPEN}{message[index:end]}{MARK_CLOSE}{message[end:]}"


def grammar_back(err: GrammarError) -> str:
    lines = [err.c, err.r]
    if err.p.strip():
        lines.append(err.p)
    return "\n".join(lines)


async def add_from_feedback(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    lang: str,
    message_id: uuid.UUID,
    message: str,
    errs: list[GrammarError],
    pron: list[PronIssue],
) -> int:
    """Create cards for new mistakes. Returns how many were added."""
    candidates: list[Flashcard] = [
        Flashcard(
            user_id=user_id,
            kind="grammar",
            front=grammar_front(message, err),
            back=grammar_back(err),
            lang=lang,
            source_message_id=message_id,
        )
        for err in errs
    ] + [
        Flashcard(
            user_id=user_id,
            kind="pronunciation",
            front=issue.w,
            back=issue.tip,
            word=issue.w,
            lang=lang,
            source_message_id=message_id,
        )
        for issue in pron
    ]
    if not candidates:
        return 0
    existing = set(
        await db.execute(
            select(Flashcard.kind, Flashcard.front).where(
                Flashcard.user_id == user_id,
                Flashcard.front.in_([c.front for c in candidates]),
            )
        )
    )
    added = 0
    for card in candidates:
        key = (card.kind, card.front)
        if key in existing:
            continue
        existing.add(key)
        db.add(card)
        added += 1
    await db.commit()
    return added
