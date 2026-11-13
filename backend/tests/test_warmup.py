"""Warm-up: free calls only, at most every few minutes, failures ignored."""

import pytest

from app.services import warmup


class Target:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def warm(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("network down")


@pytest.fixture(autouse=True)
def _reset() -> None:
    warmup.reset()


async def test_warms_every_target_and_ignores_failures() -> None:
    ok, broken = Target(), Target(fail=True)
    assert await warmup.warm_up([ok, broken, None, object()], now=100.0)
    assert ok.calls == 1 and broken.calls == 1


async def test_not_again_within_the_interval() -> None:
    target = Target()
    assert await warmup.warm_up([target], now=100.0)
    assert not await warmup.warm_up([target], now=100.0 + warmup.WARMUP_EVERY_S - 1)
    assert await warmup.warm_up([target], now=100.0 + warmup.WARMUP_EVERY_S + 1)
    assert target.calls == 2
