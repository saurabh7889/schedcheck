"""Tests for RandomEventLoop and seeded exploration."""

from __future__ import annotations

import asyncio

from schedcheck import RandomEventLoop, run


async def _concurrent_branching_worker(name: str, log: list[str]) -> None:
    for step in range(3):
        log.append(f"{name}-{step}")
        await asyncio.sleep(0)


async def _branching_program(log: list[str]) -> list[str]:
    t1 = asyncio.create_task(_concurrent_branching_worker("A", log), name="A")
    t2 = asyncio.create_task(_concurrent_branching_worker("B", log), name="B")
    t3 = asyncio.create_task(_concurrent_branching_worker("C", log), name="C")
    await t1
    await t2
    await t3
    return log


def test_random_loop_deterministic_with_same_seed() -> None:
    """Running the same program twice with the same seed produces identical schedules and logs."""
    log1: list[str] = []
    res1, sched1 = run(_branching_program(log1), seed=42)

    log2: list[str] = []
    res2, sched2 = run(_branching_program(log2), seed=42)

    assert res1 == res2
    assert log1 == log2
    assert sched1 == sched2
    assert sched1.choices == sched2.choices
    assert sched1.tasks == sched2.tasks
    assert sched1.seed == 42
    assert sched2.seed == 42


def test_random_loop_different_seeds_produce_different_schedules() -> None:
    """Different random seeds produce different execution schedules on concurrent programs."""
    schedules: set[tuple[int, ...]] = set()

    for seed in range(10):
        log: list[str] = []
        _, sched = run(_branching_program(log), seed=seed)
        schedules.add(tuple(sched.choices))

    # A 3-task program has many choice points; 10 different seeds should explore multiple paths
    assert len(schedules) > 1


def test_random_loop_records_seed_in_schedule() -> None:
    """The seed passed to RandomEventLoop is preserved in schedule.seed."""
    async def dummy() -> None:
        await asyncio.sleep(0)

    _, sched = run(dummy(), seed=999)
    assert sched.seed == 999


def test_random_loop_cls_direct_instantiation() -> None:
    """RandomEventLoop can be instantiated directly and passed as loop_cls."""
    log: list[str] = []
    res, sched = run(
        _branching_program(log),
        loop_cls=RandomEventLoop,
        seed=123,
    )
    assert sched.seed == 123
    assert len(sched.choices) > 0
