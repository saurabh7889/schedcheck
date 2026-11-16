"""Tests for systematic exploration (DFS over choice points)."""

from __future__ import annotations

import asyncio

from schedcheck import Bug, explore_systematic


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


def make_withdraw_scenario():
    """Create a fresh withdraw scenario."""
    acc = BankAccount(100)

    async def scenario() -> BankAccount:
        t1 = asyncio.create_task(acc.withdraw(80), name="W1")
        t2 = asyncio.create_task(acc.withdraw(80), name="W2")
        await t1
        await t2
        return acc

    return scenario()


def test_systematic_explore_finds_withdraw_race() -> None:
    """Systematic exploration should find the withdraw race condition."""
    bugs, stats = explore_systematic(
        make_withdraw_scenario,
        check=lambda acc: acc.balance >= 0,
        max_schedules=50,
        max_bugs=1,
    )

    assert len(bugs) >= 1
    bug = bugs[0]
    assert isinstance(bug, Bug)
    assert bug.schedule.failure is not None
    assert stats.total_schedules_explored > 0
    assert stats.bugs_found >= 1


def test_systematic_explore_respects_max_bugs() -> None:
    """Should stop after finding max_bugs bugs (across different schedules)."""
    # Use a program with multiple choice points that can fail in different ways
    call_count = 0

    async def flaky_program() -> int:
        nonlocal call_count
        # Create some choice points
        t1 = asyncio.create_task(asyncio.sleep(0), name="A")
        t2 = asyncio.create_task(asyncio.sleep(0), name="B")
        await t1
        await t2

        call_count += 1
        if call_count % 2 == 1:
            return -1  # fails check
        return 42  # passes check

    bugs, stats = explore_systematic(
        flaky_program,
        check=lambda r: r > 0,
        max_bugs=2,
        max_schedules=10,
    )

    # Should stop after finding max_bugs (2) even though more schedules exist
    assert len(bugs) == 2
    assert stats.bugs_found == 2


def test_systematic_explore_respects_max_schedules() -> None:
    """Should stop after exploring max_schedules."""
    # Program with multiple choice points
    async def program() -> int:
        t1 = asyncio.create_task(asyncio.sleep(0), name="A")
        t2 = asyncio.create_task(asyncio.sleep(0), name="B")
        await t1
        await t2
        return 42

    bugs, stats = explore_systematic(
        program,
        check=lambda r: r == 42,
        max_schedules=3,
    )

    assert stats.total_schedules_explored == 3
    assert stats.terminated_early


def test_systematic_explore_respects_max_depth() -> None:
    """Should respect max_depth bound."""

    async def deep_program() -> int:
        for _ in range(10):
            await asyncio.sleep(0)
        return 42

    bugs, stats = explore_systematic(
        deep_program,
        check=lambda r: r == 42,
        max_depth=3,
        max_schedules=100,
    )

    assert stats.max_depth_reached <= 3


def test_systematic_explore_no_bug_returns_empty() -> None:
    """Correct program should return empty bug list."""

    async def correct_program() -> int:
        await asyncio.sleep(0)
        return 42

    bugs, stats = explore_systematic(
        correct_program,
        check=lambda result: result == 42,
        max_schedules=20,
    )

    assert bugs == []
    assert stats.bugs_found == 0


def test_systematic_explore_catches_deadlock() -> None:
    """Should catch deadlock as a bug."""

    def make_deadlock():
        async def deadlock() -> None:
            event = asyncio.Event()

            async def stuck() -> None:
                await event.wait()

            t = asyncio.create_task(stuck(), name="Stuck")
            await t

        return deadlock()

    bugs, stats = explore_systematic(
        make_deadlock,
        max_schedules=10,
    )

    assert len(bugs) >= 1
    assert "DeadlockError" in bugs[0].error


def test_systematic_explore_stats_tracked() -> None:
    """ExplorationStats should track relevant metrics."""

    async def program() -> int:
        t1 = asyncio.create_task(asyncio.sleep(0), name="A")
        t2 = asyncio.create_task(asyncio.sleep(0), name="B")
        await t1
        await t2
        return 42

    bugs, stats = explore_systematic(
        program,
        check=lambda r: r == 42,
        max_schedules=10,
    )

    assert stats.total_schedules_explored > 0
    assert stats.max_depth_reached >= 0
    assert isinstance(stats.terminated_early, bool)