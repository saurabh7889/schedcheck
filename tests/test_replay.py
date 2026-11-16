"""Tests for ReplayEventLoop, exact replay, and divergence detection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from schedcheck import (
    DivergenceError,
    ReplayEventLoop,
    Schedule,
    replay,
    run,
)


async def _worker(name: str, log: list[str]) -> None:
    for i in range(3):
        log.append(f"{name}-{i}")
        await asyncio.sleep(0)


async def _concurrent_program(log: list[str]) -> list[str]:
    t1 = asyncio.create_task(_worker("Task-A", log), name="Task-A")
    t2 = asyncio.create_task(_worker("Task-B", log), name="Task-B")
    await t1
    await t2
    return log


def test_replay_matches_original_run_exactly() -> None:
    """Replaying a recorded schedule reproduces the exact execution order and schedule."""
    original_log: list[str] = []
    res_orig, orig_sched = run(_concurrent_program(original_log), seed=42)

    replay_log: list[str] = []
    res_rep, rep_sched = replay(_concurrent_program(replay_log), orig_sched)

    assert res_orig == res_rep
    assert original_log == replay_log
    assert orig_sched.choices == rep_sched.choices
    assert orig_sched.tasks == rep_sched.tasks
    assert orig_sched.seed == rep_sched.seed


def test_replay_reproduces_failure() -> None:
    """If an original run fails with an exception, replaying reproduces that failure."""
    async def failing_worker() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom on step 1")

    async def main() -> None:
        t1 = asyncio.create_task(failing_worker(), name="FailingTask")
        t2 = asyncio.create_task(_worker("Other", []), name="Other")
        await t1
        await t2

    with pytest.raises(RuntimeError, match="boom on step 1") as orig_exc_info:
        run(main(), seed=7)

    orig_schedule = orig_exc_info.value.schedule
    assert orig_schedule.failure == "RuntimeError: boom on step 1"

    # Replay the failing schedule
    with pytest.raises(RuntimeError, match="boom on step 1") as rep_exc_info:
        replay(main(), orig_schedule)

    assert rep_exc_info.value.schedule.failure == orig_schedule.failure


def test_replay_divergence_wrong_task_name() -> None:
    """If the ready task does not match the schedule's expected task, raise DivergenceError."""
    # Create an invalid schedule where task name at step 0 is mismatched
    tampered_schedule = Schedule(
        version=1,
        choices=[0],
        tasks=["NonExistentTask"],
    )

    with pytest.raises(DivergenceError, match=r"Divergence at step 0: expected task 'NonExistentTask'"):
        replay(_concurrent_program([]), tampered_schedule)


def test_replay_divergence_out_of_bounds_choice() -> None:
    """If a schedule choice index is out of bounds for the ready tasks, raise DivergenceError."""
    tampered_schedule = Schedule(
        version=1,
        choices=[99],
        tasks=["Task-A"],
    )

    with pytest.raises(DivergenceError, match=r"Choice index 99 at step 0 is out of range"):
        replay(_concurrent_program([]), tampered_schedule)


def test_replay_divergence_schedule_exhausted() -> None:
    """If the program requires another choice after the schedule is exhausted, raise DivergenceError."""
    # Program needs multiple choice points, but schedule only provides 1
    short_schedule = Schedule(
        version=1,
        choices=[0],
        tasks=["Task-A"],
    )

    with pytest.raises(DivergenceError, match=r"Schedule exhausted: needed choice at step 1"):
        replay(_concurrent_program([]), short_schedule)


def test_replay_divergence_schedule_underflow() -> None:
    """If the program finishes before consuming all scheduled choices, raise DivergenceError."""
    async def single_choice_program() -> None:
        t1 = asyncio.create_task(asyncio.sleep(0), name="T1")
        t2 = asyncio.create_task(asyncio.sleep(0), name="T2")
        await t1
        await t2

    # Schedule expects 5 choices, but single_choice_program will finish in fewer
    long_schedule = Schedule(
        version=1,
        choices=[0, 0, 0, 0, 0],
        tasks=["T1", "T2", "T1", "T2", "T1"],
    )

    with pytest.raises(DivergenceError, match=r"Schedule underflow: program completed after"):
        replay(single_choice_program(), long_schedule)


def test_bank_withdraw_race_condition_and_exact_replay(tmp_path: Path) -> None:
    """Demonstrate end-to-end race condition discovery, disk persistence, and replay."""
    class BankAccount:
        def __init__(self, balance: int = 100) -> None:
            self.balance = balance

        async def withdraw(self, amount: int) -> bool:
            if self.balance >= amount:
                await asyncio.sleep(0)  # Simulated race window
                self.balance -= amount
                return True
            return False

    async def scenario(acc: BankAccount) -> tuple[bool, bool]:
        t1 = asyncio.create_task(acc.withdraw(80), name="W1")
        t2 = asyncio.create_task(acc.withdraw(80), name="W2")
        r1 = await t1
        r2 = await t2
        return r1, r2

    # 1. Discover the race condition with seeded random exploration
    bug_schedule: Schedule | None = None
    for seed in range(50):
        acc = BankAccount(100)
        (r1, r2), sched = run(scenario(acc), seed=seed)
        if acc.balance < 0:
            bug_schedule = sched
            assert acc.balance == -60
            assert r1 is True and r2 is True
            break

    assert bug_schedule is not None, "Race condition should be found within 50 seeds"

    # 2. Save schedule to disk and reload it
    file_path = tmp_path / "failing_withdraw.json"
    bug_schedule.save(file_path)
    loaded_schedule = Schedule.load(file_path)
    assert loaded_schedule == bug_schedule

    # 3. Exact replay: Reproduce the exact bug deterministically
    replay_acc = BankAccount(100)
    (rep_r1, rep_r2), replay_sched = replay(scenario(replay_acc), loaded_schedule)

    assert replay_acc.balance == -60
    assert rep_r1 is True and rep_r2 is True
    assert replay_sched.choices == bug_schedule.choices
    assert replay_sched.tasks == bug_schedule.tasks
