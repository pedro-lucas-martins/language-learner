"""Origin allowlist shared by REST CORS and the manual WebSocket check.

FastAPI's CORSMiddleware does not apply to WebSocket handshakes, so the
WebSocket route must call `is_allowed_origin` itself (SPEC §3).
"""

import re
from functools import lru_cache

from app.config import Settings


@lru_cache(maxsize=8)
def _compile(pattern: str) -> re.Pattern[str] | None:
    if not pattern:
        return None
    return re.compile(pattern)


def is_allowed_origin(origin: str | None, settings: Settings) -> bool:
    """Return True only for exact allowlisted origins or the project's own Vercel previews."""
    if not origin:
        return False
    origin = origin.rstrip("/")
    if origin in settings.allowed_origins:
        return True
    pattern = _compile(settings.vercel_preview_regex)
    return bool(pattern and pattern.fullmatch(origin))
