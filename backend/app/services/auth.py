"""Access tokens (SPEC §3).

Tokens are 32 random bytes (URL-safe base64). Only their SHA-256 is stored: the
token has full entropy, so a slow password hash adds nothing here.
"""

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def authenticate(db: AsyncSession, token: str | None) -> User | None:
    """Return the user owning `token`, or None. Never raises on bad input."""
    if not token or len(token) > 200:
        return None
    digest = hash_token(token.strip())
    user = await db.scalar(select(User).where(User.access_token_hash == digest))
    if user is None:
        return None
    # Defence in depth: constant-time comparison of the stored digest.
    if not hmac.compare_digest(user.access_token_hash, digest):
        return None
    return user


async def create_user(
    db: AsyncSession,
    *,
    name: str,
    native_lang: str,
    level: str = "A1",
) -> tuple[User, str]:
    """Create a learner and return (user, plaintext token). The token is shown once."""
    if native_lang not in ("pt-BR", "pl-PL"):
        raise ValueError("native_lang must be pt-BR or pl-PL")
    target_lang = "pl-PL" if native_lang == "pt-BR" else "pt-BR"
    token = generate_token()
    user = User(
        name=name.strip()[:80],
        native_lang=native_lang,
        target_lang=target_lang,
        level=level,
        user_facts="",
        recast_pronunciation=True,
        access_token_hash=hash_token(token),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, token
