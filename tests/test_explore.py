"""Tests for the explore() function and Bug dataclass."""

from __future__ import annotations

import asyncio

from schedcheck import Bug, DeadlockError, explore, run


class BankAccount:
    """Simple bank account for race condition tests."""

    def __init__(self, balance: int = 100) -> None:
        self.balance = balance

    async def withdraw(self, amount: int) -> bool:
        if self.balance >= amount:
            await asyncio.sleep(0)
            self.balance -= amount
            return True
        return False


def test_explore_finds_withdraw_race_condition() -> None:
    """explore() finds the classic withdraw race condition within a few seeds."""
    def make_scenario() -> asyncio.coroutines:
        acc = BankAccount(100)

        async def scenario() -> BankAccount:
            t1 = asyncio.create_task(acc.withdraw(80), name="W1")
            t2 = asyncio.create_task(acc.withdraw(80), name="W2")
            await t1
            await t2
            return acc

        return scenario()

    bugs = explore(
        make_scenario,
        check=lambda acc: acc.balance >= 0,
        seeds=range(50),
    )

    assert len(bugs) >= 1
    bug = bugs[0]
    assert isinstance(bug, Bug)
    assert bug.schedule.seed is not None
    assert bug.error  # non-empty error message
    assert bug.schedule.failure is not None


def test_explore_returns_empty_when_no_bug() -> None:
    """If the program is correct for all seeds, explore() returns an empty list."""
    async def correct_program() -> int:
        await asyncio.sleep(0)
        return 42

    bugs = explore(
        correct_program,
        check=lambda result: result == 42,
        seeds=range(20),
    )

    assert bugs == []


def test_explore_check_returning_false_is_a_bug() -> None:
    """A check function that returns False should be recorded as a bug."""
    async def program() -> int:
        return 42

    bugs = explore(
        program,
        check=lambda result: False,  # always fails
        seeds=range(1),
    )

    assert len(bugs) == 1
    assert "Invariant check returned False" in bugs[0].error


def test_explore_check_raising_exception_is_a_bug() -> None:
    """A check function that raises should be recorded as a bug."""
    async def program() -> int:
        return -1

    bugs = explore(
        program,
        check=lambda result: (_ for _ in ()).throw(AssertionError(f"bad value: {result}")),
        seeds=range(1),
    )

    # The lambda above is awkward; use a proper function instead
    def check_positive(result: int) -> None:
        assert result > 0, f"Expected positive, got {result}"

    bugs = explore(
        program,
        check=check_positive,
        seeds=range(1),
    )

    assert len(bugs) == 1
    assert "AssertionError" in bugs[0].error
    assert "Expected positive" in bugs[0].error


def test_explore_max_bugs_limits_results() -> None:
    """explore() stops after finding max_bugs bugs."""
    async def always_bad() -> int:
        return -1

    bugs = explore(
        always_bad,
        check=lambda r: r > 0,
        seeds=range(100),
        max_bugs=3,
    )

    assert len(bugs) == 3


def test_explore_catches_deadlock() -> None:
    """explore() catches DeadlockError as a bug."""
    def make_deadlock() -> asyncio.coroutines:
        async def deadlock() -> None:
            event = asyncio.Event()

            async def stuck() -> None:
                await event.wait()

            t = asyncio.create_task(stuck(), name="Stuck")
            await t

        return deadlock()

    bugs = explore(
        make_deadlock,
        seeds=range(1),
    )

    assert len(bugs) == 1
    assert "DeadlockError" in bugs[0].error


def test_explore_catches_program_exception() -> None:
    """explore() catches exceptions raised by the program itself."""
    async def crashing_program() -> None:
        raise RuntimeError("kaboom")

    bugs = explore(
        crashing_program,
        seeds=range(1),
    )

    assert len(bugs) == 1
    assert "RuntimeError" in bugs[0].error
    assert "kaboom" in bugs[0].error


def test_explore_without_check_only_catches_crashes() -> None:
    """Without a check function, explore() only catches crashes (not return values)."""
    async def returns_negative() -> int:
        return -999

    bugs = explore(
        returns_negative,
        seeds=range(10),
    )

    # No check function → no bugs, even though the return value is unusual
    assert bugs == []


def test_bug_contains_schedule_with_seed() -> None:
    """Each Bug's schedule preserves the seed that triggered it."""
    async def bad_program() -> int:
        return 0

    bugs = explore(
        bad_program,
        check=lambda r: r > 0,
        seeds=[42, 99, 7],
        max_bugs=1,
    )

    assert len(bugs) == 1
    assert bugs[0].seed == 42
    assert bugs[0].schedule.seed == 42
