import random

import pytest

from app.services.memory import ConversationMemory, Turn


def test_window_keeps_last_turns_and_moves_older_to_pending() -> None:
    mem = ConversationMemory(window_turns=3, summary_batch_turns=3)
    for i in range(5):
        mem.add_turn(f"u{i}", f"a{i}")
    assert [t.user for t in mem.window] == ["u2", "u3", "u4"]
    assert mem.pending_count == 2
    # Pending turns are still sent to the LLM until summarized.
    assert [t.user for t in mem.context_turns()] == ["u0", "u1", "u2", "u3", "u4"]


def test_summary_is_requested_only_after_a_full_batch() -> None:
    mem = ConversationMemory(window_turns=3, summary_batch_turns=3)
    for i in range(5):
        mem.add_turn(f"u{i}", f"a{i}")
    assert not mem.needs_summary()
    mem.add_turn("u5", "a5")
    assert mem.needs_summary()


def test_apply_summary_removes_only_reserved_turns() -> None:
    mem = ConversationMemory(window_turns=3, summary_batch_turns=3)
    for i in range(6):
        mem.add_turn(f"u{i}", f"a{i}")
    previous, turns = mem.begin_summary()
    assert previous == ""
    assert [t.user for t in turns] == ["u0", "u1", "u2"]
    # A turn arrives while the summary is being generated.
    mem.add_turn("u6", "a6")
    assert not mem.needs_summary()  # one summary at a time
    mem.apply_summary("  talked about food  ")
    assert mem.summary == "talked about food"
    assert [t.user for t in mem.context_turns()] == ["u3", "u4", "u5", "u6"]


def test_abort_keeps_turns_pending() -> None:
    mem = ConversationMemory(window_turns=1, summary_batch_turns=1)
    mem.add_turn("u0", "a0")
    mem.add_turn("u1", "a1")
    mem.begin_summary()
    mem.abort_summary()
    assert [t.user for t in mem.context_turns()] == ["u0", "u1"]
    assert mem.needs_summary()


def test_misuse_is_rejected() -> None:
    mem = ConversationMemory()
    with pytest.raises(RuntimeError):
        mem.apply_summary("x")
    with pytest.raises(ValueError):
        ConversationMemory(window_turns=0)


@pytest.mark.parametrize("seed", range(25))
def test_invariant_no_turn_is_ever_lost(seed: int) -> None:
    """SPEC §4.2: every turn is in the context sent to the LLM or already summarized."""
    rng = random.Random(seed)
    mem = ConversationMemory(window_turns=rng.randint(1, 4), summary_batch_turns=rng.randint(1, 4))
    summarized: list[Turn] = []
    in_flight: list[Turn] | None = None
    all_turns: list[Turn] = []

    for i in range(rng.randint(5, 60)):
        mem.add_turn(f"u{i}", f"a{i}")
        all_turns.append(Turn(f"u{i}", f"a{i}"))

        if in_flight is None and mem.needs_summary():
            _, in_flight = mem.begin_summary()
        elif in_flight is not None and rng.random() < 0.5:
            if rng.random() < 0.8:
                mem.apply_summary(f"summary up to {in_flight[-1].user}")
                summarized += in_flight
            else:
                mem.abort_summary()
            in_flight = None

        context = mem.context_turns()
        # Nothing summarized is sent twice, nothing else is missing, order is kept.
        assert summarized + context == all_turns
        # The window never exceeds its size.
        assert len(mem.window) <= mem.window_turns
