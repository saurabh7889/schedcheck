"""Tests for ControllableEventLoop and schedule recording."""

from __future__ import annotations

import asyncio
import pytest

from schedcheck.loop import ControllableEventLoop, run


async def _worker(name: str, log: list[tuple[str, int]]) -> None:
    """Helper worker that records its execution steps and yields with sleep(0)."""
    for i in range(3):
        log.append((name, i))
        await asyncio.sleep(0)


async def _two_workers_program(log: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Runs two named tasks concurrently, awaiting each."""
    t1 = asyncio.create_task(_worker("U1", log), name="U1")
    t2 = asyncio.create_task(_worker("U2", log), name="U2")
    await t1
    await t2
    return log


def test_default_loop_order_matches_stock_asyncio() -> None:
    """Test 1: With default choose, order produced must equal stock asyncio order."""
    stock_log: list[tuple[str, int]] = []
    asyncio.run(_two_workers_program(stock_log))

    ctrl_log: list[tuple[str, int]] = []
    result, schedule = run(_two_workers_program(ctrl_log))

    assert result == ctrl_log
    assert ctrl_log == stock_log
    assert ctrl_log == [
        ("U1", 0),
        ("U2", 0),
        ("U1", 1),
        ("U2", 1),
        ("U1", 2),
        ("U2", 2),
    ]


def test_recorded_schedule_matches_reasoned_expectation() -> None:
    """Test 2: Recorded schedule has the expected number of choice points and task names."""
    # --------------------------------------------------------------------------
    # REASONING FOR EXPECTED CHOICE POINTS AND TASK NAMES:
    # --------------------------------------------------------------------------
    # 1. Root task starts:
    #    `main` (the root task) runs first. Because it is the only ready task,
    #    this is NOT a choice point. `main` creates "U1" and "U2" (placing them
    #    in the ready queue), then suspends on `await t1`.
    #
    # 2. Choice Point 1:
    #    Ready tasks: ["U1", "U2"] (count=2 > 1).
    #    Default choose returns 0 -> "U1" runs.
    #    "U1" records ("U1", 0), yields via sleep(0), and is re-enqueued at back.
    #    Ready queue: ["U2", "U1"].
    #
    # 3. Choice Point 2:
    #    Ready tasks: ["U2", "U1"] (count=2 > 1).
    #    Default choose returns 0 -> "U2" runs.
    #    "U2" records ("U2", 0), yields via sleep(0), and is re-enqueued at back.
    #    Ready queue: ["U1", "U2"].
    #
    # 4. Choice Point 3:
    #    Ready tasks: ["U1", "U2"] (count=2 > 1).
    #    Default choose returns 0 -> "U1" runs step 1.
    #    Ready queue after sleep(0): ["U2", "U1"].
    #
    # 5. Choice Point 4:
    #    Ready tasks: ["U2", "U1"] (count=2 > 1).
    #    Default choose returns 0 -> "U2" runs step 1.
    #    Ready queue after sleep(0): ["U1", "U2"].
    #
    # 6. Choice Point 5:
    #    Ready tasks: ["U1", "U2"] (count=2 > 1).
    #    Default choose returns 0 -> "U1" runs step 2.
    #    Ready queue after sleep(0): ["U2", "U1"].
    #
    # 7. Choice Point 6:
    #    Ready tasks: ["U2", "U1"] (count=2 > 1).
    #    Default choose returns 0 -> "U2" runs step 2.
    #    Ready queue after sleep(0): ["U1", "U2"].
    #
    # 8. Choice Point 7:
    #    Ready tasks: ["U1", "U2"] (count=2 > 1).
    #    Default choose returns 0 -> "U1" runs.
    #    "U1" resumes from 3rd sleep(0), loop finishes, and "U1" completes.
    #    Completing "U1" awakens the root task waiting on t1.
    #    Ready queue now contains: ["U2", "<root_task>"].
    #
    # 9. Choice Point 8:
    #    Ready tasks: ["U2", "<root_task>"] (count=2 > 1).
    #    Default choose returns 0 -> "U2" runs.
    #    "U2" resumes from 3rd sleep(0), loop finishes, and "U2" completes.
    #    Ready queue now contains only: ["<root_task>"].
    #
    # 10. Completion (No choice point):
    #     Only 1 task is ready (`<root_task>`). Moments with 1 task are NOT
    #     choice points. The root task resumes, runs `await t2` (which is already
    #     finished and returns immediately), and terminates cleanly.
    #
    # CONCLUSION:
    # - Expected choice point count: 8
    # - Expected choices list: [0, 0, 0, 0, 0, 0, 0, 0]
    # - Expected chosen tasks: ["U1", "U2", "U1", "U2", "U1", "U2", "U1", "U2"]
    # --------------------------------------------------------------------------
    log: list[tuple[str, int]] = []
    result, schedule = run(_two_workers_program(log))

    assert schedule.choices == [0, 0, 0, 0, 0, 0, 0, 0]
    assert schedule.tasks == ["U1", "U2", "U1", "U2", "U1", "U2", "U1", "U2"]
    assert len(schedule.choices) == 8
    assert len(schedule.tasks) == 8
    assert schedule.failure is None


class LastIndexEventLoop(ControllableEventLoop):
    """Subclass of ControllableEventLoop that always picks the last ready task."""

    def choose(self, ready_names: list[str]) -> int:
        return len(ready_names) - 1


def test_last_index_loop_produces_different_order_and_finishes() -> None:
    """Test 3 & 2(a): Subclass choosing last index produces different order and asserts choices/tasks."""
    default_log: list[tuple[str, int]] = []
    run(_two_workers_program(default_log))

    last_log: list[tuple[str, int]] = []
    result, schedule = run(_two_workers_program(last_log), loop_cls=LastIndexEventLoop)

    # Must produce a DIFFERENT order than the default FIFO order
    assert last_log != default_log

    # Specifically, choosing the last task causes "U2" to execute all of its steps
    # before "U1" gets a turn, since "U2" repeatedly stays/re-enters at the last index.
    assert last_log == [
        ("U2", 0),
        ("U2", 1),
        ("U2", 2),
        ("U1", 0),
        ("U1", 1),
        ("U1", 2),
    ]
    assert result == last_log
    # 2(a) schedule.choices and schedule.tasks assertions for the last-index run:
    assert schedule.choices == [1, 1, 1, 1]
    assert schedule.tasks == ["U2", "U2", "U2", "U2"]
    assert len(schedule.choices) == 4
    assert len(schedule.tasks) == 4
    assert schedule.failure is None


def test_single_task_records_zero_choice_points() -> None:
    """Test 4: A program with only one task records zero choice points."""
    async def single_task() -> str:
        for _ in range(5):
            await asyncio.sleep(0)
        return "finished"

    result, schedule = run(single_task())

    assert result == "finished"
    assert len(schedule.choices) == 0
    assert len(schedule.tasks) == 0
    assert schedule.failure is None


def test_same_program_run_twice_gives_equal_schedules() -> None:
    """Test 2(b): Same program run twice gives equal schedules."""
    log1: list[tuple[str, int]] = []
    _, sched1 = run(_two_workers_program(log1))

    log2: list[tuple[str, int]] = []
    _, sched2 = run(_two_workers_program(log2))

    assert sched1 == sched2
    assert sched1.choices == sched2.choices
    assert sched1.tasks == sched2.tasks
    assert sched1.failure == sched2.failure


def test_asyncio_gather_three_tasks() -> None:
    """Test 2(c): A program using asyncio.gather of 3 tasks."""
    async def worker(name: str, log: list[str]) -> None:
        log.append(f"{name}-start")
        await asyncio.sleep(0)
        log.append(f"{name}-end")

    async def gather_program(log: list[str]) -> list[str]:
        t1 = asyncio.create_task(worker("W1", log), name="W1")
        t2 = asyncio.create_task(worker("W2", log), name="W2")
        t3 = asyncio.create_task(worker("W3", log), name="W3")
        await asyncio.gather(t1, t2, t3)
        return log

    stock_log: list[str] = []
    asyncio.run(gather_program(stock_log))

    ctrl_log: list[str] = []
    result, schedule = run(gather_program(ctrl_log))

    assert result == ctrl_log
    assert ctrl_log == stock_log
    assert ctrl_log == [
        "W1-start",
        "W2-start",
        "W3-start",
        "W1-end",
        "W2-end",
        "W3-end",
    ]
    assert schedule.choices == [0, 0, 0, 0, 0]
    assert schedule.tasks == ["W1", "W2", "W3", "W1", "W2"]
    assert schedule.failure is None


def test_event_wait_and_set() -> None:
    """Test 2(d): A program where one task sets an asyncio.Event and another waits."""
    async def waiter(event: asyncio.Event, log: list[str]) -> None:
        log.append("waiter-waiting")
        await event.wait()
        log.append("waiter-resumed")

    async def setter(event: asyncio.Event, log: list[str]) -> None:
        log.append("setter-start")
        await asyncio.sleep(0)
        log.append("setter-setting")
        event.set()
        log.append("setter-done")

    async def event_program(log: list[str]) -> list[str]:
        event = asyncio.Event()
        t_wait = asyncio.create_task(waiter(event, log), name="Waiter")
        t_set = asyncio.create_task(setter(event, log), name="Setter")
        await t_wait
        await t_set
        return log

    stock_log: list[str] = []
    asyncio.run(event_program(stock_log))

    ctrl_log: list[str] = []
    result, schedule = run(event_program(ctrl_log))

    assert result == ctrl_log
    assert ctrl_log == stock_log
    assert ctrl_log == [
        "waiter-waiting",
        "setter-start",
        "setter-setting",
        "setter-done",
        "waiter-resumed",
    ]
    # The only moment with >1 ready task is when Waiter and Setter are first spawned
    assert schedule.choices == [0]
    assert schedule.tasks == ["Waiter"]
    assert schedule.failure is None


def test_out_of_range_choose_raises_value_error() -> None:
    """Test 2(e): Out-of-range choose raises ValueError("choice N but only M tasks ready")."""
    class OutOfRangeHighLoop(ControllableEventLoop):
        def choose(self, ready_names: list[str]) -> int:
            return 99

    with pytest.raises(ValueError, match=r"^choice 99 but only 2 tasks ready$"):
        run(_two_workers_program([]), loop_cls=OutOfRangeHighLoop)

    class OutOfRangeNegativeLoop(ControllableEventLoop):
        def choose(self, ready_names: list[str]) -> int:
            return -1

    with pytest.raises(ValueError, match=r"^choice -1 but only 2 tasks ready$"):
        run(_two_workers_program([]), loop_cls=OutOfRangeNegativeLoop)


def test_task_exception_records_schedule_failure() -> None:
    """Test 2(f): A task that raises an exception records schedule.failure."""
    async def failing_worker() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("something exploded in task")

    # 1. Recovered failure: main catches the task's exception, finishes normally
    async def recovered_main() -> str:
        t = asyncio.create_task(failing_worker(), name="FailingWorker")
        try:
            await t
        except RuntimeError:
            pass
        return "recovered"

    result, schedule = run(recovered_main())
    assert result == "recovered"
    assert schedule.failure == "RuntimeError: something exploded in task"

    # 2. Unhandled failure: exception propagates out of run()
    async def unhandled_main() -> None:
        t = asyncio.create_task(failing_worker(), name="FailingWorker")
        await t

    with pytest.raises(RuntimeError, match="something exploded in task") as exc_info:
        run(unhandled_main())

    assert hasattr(exc_info.value, "schedule")
    assert exc_info.value.schedule.failure == "RuntimeError: something exploded in task"


def test_two_runs_gather_unnamed_coroutines_produce_equal_schedules() -> None:
    """Test 3(c): Two runs of an asyncio.gather program with 3 UNNAMED coroutines produce equal schedules."""
    async def unnamed_worker(log: list[str]) -> None:
        log.append("step")
        await asyncio.sleep(0)
        log.append("done")

    async def gather_unnamed(log: list[str]) -> list[str]:
        await asyncio.gather(unnamed_worker(log), unnamed_worker(log), unnamed_worker(log))
        return log

    log1: list[str] = []
    _, sched1 = run(gather_unnamed(log1))

    log2: list[str] = []
    _, sched2 = run(gather_unnamed(log2))

    # Deterministic per-loop task names ensure both runs have identical task sequences
    assert sched1.tasks == sched2.tasks
    assert sched1.choices == sched2.choices
    assert sched1.tasks == ["Task-2", "Task-3", "Task-4", "Task-2", "Task-3"]
    assert sched1.choices == [0, 0, 0, 0, 0]
    assert sched1 == sched2

