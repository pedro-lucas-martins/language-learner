"""REST: the learner's flashcards and SM-2 reviews (SPEC §5). Bearer token like /me."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Flashcard, User
from app.routers.me import current_user
from app.services import sm2

router = APIRouter(prefix="/flashcards")

MAX_LIST = 200


class FlashcardOut(BaseModel):
    id: uuid.UUID
    kind: Literal["grammar", "pronunciation"]
    front: str
    back: str
    word: str | None
    lang: str
    due_at: datetime
    repetitions: int
    interval_days: int


class ReviewIn(BaseModel):
    grade: int = Field(ge=0, le=5)


def _out(card: Flashcard) -> FlashcardOut:
    return FlashcardOut.model_validate(card, from_attributes=True)


async def _own_card(db: AsyncSession, user: User, card_id: uuid.UUID) -> Flashcard:
    card = await db.get(Flashcard, card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


@router.get("", response_model=list[FlashcardOut])
async def list_cards(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    due: Annotated[bool, Query(description="only cards due now")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST)] = 50,
) -> list[FlashcardOut]:
    query = select(Flashcard).where(Flashcard.user_id == user.id)
    if due:
        query = query.where(Flashcard.due_at <= datetime.now(UTC)).order_by(Flashcard.due_at)
    else:
        query = query.order_by(Flashcard.created_at.desc())
    cards = (await db.scalars(query.limit(limit))).all()
    return [_out(c) for c in cards]


@router.post("/{card_id}/review", response_model=FlashcardOut)
async def review_card(
    card_id: uuid.UUID,
    body: ReviewIn,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FlashcardOut:
    card = await _own_card(db, user, card_id)
    schedule = sm2.review(
        ease=card.ease,
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        grade=body.grade,
        now=datetime.now(UTC),
    )
    card.ease = schedule.ease
    card.interval_days = schedule.interval_days
    card.repetitions = schedule.repetitions
    card.due_at = schedule.due_at
    await db.commit()
    await db.refresh(card)
    return _out(card)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    card = await _own_card(db, user, card_id)
    await db.delete(card)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
