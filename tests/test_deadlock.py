"""Tests for deadlock detection."""

from __future__ import annotations

import asyncio

import pytest

from schedcheck import DeadlockError, run


def test_circular_wait_deadlock_detected() -> None:
    """Two tasks each waiting for the other's event is a classic deadlock."""
    async def deadlock_program() -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()

        async def task_a() -> None:
            await event_b.wait()  # waits for B to set event_b
            event_a.set()

        async def task_b() -> None:
            await event_a.wait()  # waits for A to set event_a
            event_b.set()

        a = asyncio.create_task(task_a(), name="A")
        b = asyncio.create_task(task_b(), name="B")
        await a
        await b

    with pytest.raises(DeadlockError, match=r"Deadlock.*pending"):
        run(deadlock_program())


def test_deadlock_records_schedule_failure() -> None:
    """DeadlockError should be recorded in schedule.failure."""
    async def deadlock_program() -> None:
        event = asyncio.Event()

        async def forever_waiter() -> None:
            await event.wait()  # nobody ever sets this event

        t = asyncio.create_task(forever_waiter(), name="StuckTask")
        await t

    with pytest.raises(DeadlockError) as exc_info:
        run(deadlock_program())

    assert hasattr(exc_info.value, "schedule")
    assert "DeadlockError" in exc_info.value.schedule.failure
    assert "Stuck tasks" in str(exc_info.value)


def test_deadlock_mentions_stuck_task_names() -> None:
    """The DeadlockError message should list the names of stuck tasks."""
    async def deadlock_program() -> None:
        event = asyncio.Event()

        async def waiter_x() -> None:
            await event.wait()

        async def waiter_y() -> None:
            await event.wait()

        x = asyncio.create_task(waiter_x(), name="WaiterX")
        y = asyncio.create_task(waiter_y(), name="WaiterY")
        await asyncio.gather(x, y)

    with pytest.raises(DeadlockError, match=r"WaiterX") as exc_info:
        run(deadlock_program())

    msg = str(exc_info.value)
    assert "WaiterX" in msg
    assert "WaiterY" in msg


def test_no_deadlock_on_normal_program() -> None:
    """A program that finishes normally should not trigger deadlock detection."""
    async def normal_program() -> str:
        event = asyncio.Event()

        async def setter() -> None:
            await asyncio.sleep(0)
            event.set()

        async def waiter() -> str:
            await event.wait()
            return "done"

        t_set = asyncio.create_task(setter(), name="Setter")
        t_wait = asyncio.create_task(waiter(), name="Waiter")
        result = await t_wait
        await t_set
        return result

    result, schedule = run(normal_program())
    assert result == "done"
    assert schedule.failure is None
