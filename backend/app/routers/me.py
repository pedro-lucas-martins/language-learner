"""REST: current learner (lets the frontend validate a token before opening the socket)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.protocol import UserInfo
from app.services.auth import authenticate

router = APIRouter()


async def current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = await authenticate(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/me", response_model=UserInfo)
async def me(user: Annotated[User, Depends(current_user)]) -> UserInfo:
    return UserInfo(
        name=user.name,
        native_lang=user.native_lang,  # type: ignore[arg-type]
        target_lang=user.target_lang,  # type: ignore[arg-type]
        ui_lang=(user.ui_lang or user.native_lang),  # type: ignore[arg-type]
        level=user.level,  # type: ignore[arg-type]
        recast_pronunciation=user.recast_pronunciation,
    )
