"""Flashcards: created from feedback, deduplicated, reviewed and deleted over REST."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import session_factory
from app.models import Flashcard, User
from app.protocol import GrammarError, PronIssue
from app.services import flashcards as cards
from tests.conftest import add_user

ERR = GrammarError(e="dwa kot", c="dwa koty", r="Depois de 2–4: plural.", p="Em PT: dois gatos.")
PRON = PronIssue(w="kot", heard="kotchi", tip="Sem vogal no fim.", sev="major")


def _user_id(engine: Engine, name: str = "Pedro") -> uuid.UUID:
    with Session(engine) as db:
        return db.scalars(select(User.id).where(User.name == name)).one()


def test_grammar_front_marks_the_mistake_in_context() -> None:
    assert cards.grammar_front("Ja mam dwa kot w domu.", ERR) == "Ja mam «dwa kot» w domu."
    assert cards.grammar_front("Mam DWA KOT.", ERR) == "Mam «DWA KOT»."
    assert cards.grammar_front("inny tekst", ERR) == "«dwa kot»"
    assert cards.grammar_back(ERR) == "dwa koty\nDepois de 2–4: plural.\nEm PT: dois gatos."


async def test_cards_are_created_once(sync_engine: Engine) -> None:
    add_user(sync_engine)
    user_id = _user_id(sync_engine)
    kwargs = dict(
        user_id=user_id,
        lang="pl-PL",
        message_id=uuid.uuid4(),
        message="Ja mam dwa kot w domu.",
        errs=[ERR, ERR],
        pron=[PRON],
    )
    async with session_factory()() as db:
        assert await cards.add_from_feedback(db, **kwargs) == 2  # type: ignore[arg-type]
        assert await cards.add_from_feedback(db, **kwargs) == 0  # type: ignore[arg-type]
    with Session(sync_engine) as db:
        stored = db.scalars(select(Flashcard).order_by(Flashcard.kind)).all()
    assert [(c.kind, c.front, c.word) for c in stored] == [
        ("grammar", "Ja mam «dwa kot» w domu.", None),
        ("pronunciation", "kot", "kot"),
    ]


def _seed(engine: Engine, user_id: uuid.UUID, *, front: str, due_in: timedelta) -> uuid.UUID:
    with Session(engine) as db:
        card = Flashcard(
            user_id=user_id,
            kind="grammar",
            front=front,
            back="b",
            lang="pl-PL",
            ease=2.5,
            interval_days=0,
            repetitions=0,
            due_at=datetime.now(UTC) + due_in,
        )
        db.add(card)
        db.commit()
        return card.id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rest_lists_due_cards_and_reviews(client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine)
    user_id = _user_id(sync_engine)
    due = _seed(sync_engine, user_id, front="due", due_in=timedelta(minutes=-5))
    _seed(sync_engine, user_id, front="later", due_in=timedelta(days=3))

    assert client.get("/flashcards").status_code == 401
    all_cards = client.get("/flashcards", headers=_auth(token)).json()
    assert {c["front"] for c in all_cards} == {"due", "later"}
    due_cards = client.get("/flashcards?due=true", headers=_auth(token)).json()
    assert [c["front"] for c in due_cards] == ["due"]

    reviewed = client.post(f"/flashcards/{due}/review", json={"grade": 4}, headers=_auth(token))
    assert reviewed.status_code == 200
    assert reviewed.json()["repetitions"] == 1 and reviewed.json()["interval_days"] == 1
    assert client.get("/flashcards?due=true", headers=_auth(token)).json() == []

    bad = client.post(f"/flashcards/{due}/review", json={"grade": 9}, headers=_auth(token))
    assert bad.status_code == 422


def test_rest_cannot_touch_other_users_cards(client: TestClient, sync_engine: Engine) -> None:
    add_user(sync_engine, name="Pedro")
    other_token = add_user(sync_engine, native="pl-PL", name="Ola")
    card = _seed(sync_engine, _user_id(sync_engine, "Pedro"), front="mine", due_in=timedelta(0))
    headers = _auth(other_token)
    assert client.get("/flashcards", headers=headers).json() == []
    assert (
        client.post(f"/flashcards/{card}/review", json={"grade": 4}, headers=headers).status_code
        == 404
    )
    assert client.delete(f"/flashcards/{card}", headers=headers).status_code == 404


def test_rest_delete(client: TestClient, sync_engine: Engine) -> None:
    token = add_user(sync_engine)
    card = _seed(sync_engine, _user_id(sync_engine), front="x", due_in=timedelta(0))
    assert client.delete(f"/flashcards/{card}", headers=_auth(token)).status_code == 204
    assert client.get("/flashcards", headers=_auth(token)).json() == []
