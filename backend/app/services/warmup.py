"""Open the provider connections before the first turn (free metadata calls only).

The first voice turn after a restart was ~2–5 s slower: DNS, TLS and auth happen on the
first request. When a learner connects, this pings each provider with a call that is not
billed (model/voice metadata), at most once every `WARMUP_EVERY_S` per process.
"""

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

log = logging.getLogger(__name__)

WARMUP_EVERY_S = 300.0
_last_warmup: float | None = None
_tasks: set[asyncio.Task[None]] = set()


async def _warm_one(target: Any) -> None:
    warm = getattr(target, "warm", None)
    if warm is None:
        return
    try:
        await asyncio.wait_for(warm(), 10)
    except Exception as exc:  # noqa: BLE001 — warming is best effort
        log.info("Warm-up of %s failed: %s", type(target).__name__, exc)


async def warm_up(targets: Iterable[Any], *, now: float | None = None) -> bool:
    """Warm every target that has an async `warm()`. Returns False when skipped (too soon)."""
    global _last_warmup
    current = time.monotonic() if now is None else now
    if _last_warmup is not None and current - _last_warmup < WARMUP_EVERY_S:
        return False
    _last_warmup = current
    await asyncio.gather(*(_warm_one(t) for t in targets if t is not None))
    return True


def schedule(targets: Iterable[Any]) -> None:
    """Fire and forget (kept referenced so the task is not garbage-collected)."""
    task = asyncio.create_task(_run(list(targets)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run(targets: list[Any]) -> None:
    await warm_up(targets)


def reset() -> None:
    """For tests."""
    global _last_warmup
    _last_warmup = None
