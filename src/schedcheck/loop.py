"""Controllable event loop for deterministic asyncio task scheduling.

DESIGN DECISION: RUNNING ONE HANDLE AT A TIME VS. BATCH REORDERING
-----------------------------------------------------------------
In stock asyncio, `BaseEventLoop._run_once` executes ready handles in batches
(`ntodo = len(self._ready)`). Any callbacks scheduled while executing that
batch are deferred to subsequent iterations of the loop.

We intentionally choose to RUN ONE HANDLE AT A TIME (one decision per step)
rather than reordering the ready queue before each batch runs. Here is why:

1. Exactly one decision per choice point:
   A choice point represents the question: "Which ready task runs next?"
   If we reordered the whole batch upfront, a single choice either has to
   specify a full permutation of all ready tasks, or multiple decisions
   would be made at once without observing intermediate state changes.
   Running one handle at a time ensures every choice point corresponds to
   exactly ONE decision.

2. Reactivity to dynamic state changes:
   Running a task for one step can immediately wake up other tasks (e.g.
   resolving a Future, releasing a Lock, setting an Event) or yield and
   re-enqueue itself (e.g. `await asyncio.sleep(0)`). With batch reordering,
   newly readied tasks are trapped behind the remainder of the stale batch.
   Running one handle at a time allows the scheduler to re-evaluate the full
   set of ready tasks at every single step.

3. Arbitrary interleaving and race condition exploration:
   Stock asyncio's batch loop acts as a round-robin fairness enforcer: every
   ready task in the batch MUST run once before any task can run a second time.
   That prevents discovering race conditions where one task rushes ahead or
   starves another. Tasks still only suspend at await points; we only change
   which ready task runs next. By running one handle at a time, custom `choose`
   strategies (such as prioritizing one task until completion) can interleave
   tasks arbitrarily while preserving clean termination.
"""

from __future__ import annotations

import asyncio
import asyncio.tasks
import heapq
import math
from typing import Any, Coroutine, TypeVar

from schedcheck.schedule import Schedule

T = TypeVar("T")


# ==============================================================================
# Asyncio Internals Adapter
# All uses of private asyncio attributes are isolated here for easy maintenance.
# ==============================================================================

def _extract_task_from_handle(handle: asyncio.Handle) -> asyncio.Task | None:
    """Map an asyncio.Handle back to its owning Task, or return None if it is not a task.

    When using _PyTask, the handle's callback is a bound method on the task
    (such as `_Task__step` or `_Task__wakeup`), so `__self__` points directly
    to the Task instance.
    """
    callback = getattr(handle, "_callback", None)
    target = getattr(callback, "__self__", None)
    if isinstance(target, (asyncio.Task, asyncio.tasks._PyTask)):
        return target
    return None


def _py_task_factory(
    loop: asyncio.AbstractEventLoop,
    coro: Coroutine[Any, Any, Any],
    **kwargs: Any,
) -> asyncio.tasks._PyTask:
    """Task factory that creates pure-Python tasks (asyncio.tasks._PyTask).

    C-accelerated tasks hide their bound step and wakeup callbacks inside opaque
    wrapper objects. Using _PyTask guarantees that `handle._callback.__self__`
    transparently references the Task instance across Python 3.12+.

    If no name is given (or name is None), assigns a deterministic name from the
    event loop's per-instance counter ("Task-1", "Task-2", ...), starting at 1.
    """
    if kwargs.get("name") is None:
        if isinstance(loop, ControllableEventLoop):
            kwargs["name"] = f"Task-{loop._task_counter}"
            loop._task_counter += 1
    return asyncio.tasks._PyTask(coro, loop=loop, **kwargs)


def _poll_io_and_timers(loop: asyncio.SelectorEventLoop) -> None:
    """Poll selector I/O and transfer expired timers to loop._ready.

    This encapsulates the timing and I/O polling steps of BaseEventLoop._run_once.
    """
    # 1. Prune cancelled timer handles from the heap when their fraction is high
    sched_count = len(loop._scheduled)
    if sched_count > 100 and (loop._timer_cancelled_count / sched_count) > 0.5:
        new_scheduled = []
        for handle in loop._scheduled:
            if handle._cancelled:
                handle._scheduled = False
            else:
                new_scheduled.append(handle)
        heapq.heapify(new_scheduled)
        loop._scheduled = new_scheduled
        loop._timer_cancelled_count = 0
    else:
        while loop._scheduled and loop._scheduled[0]._cancelled:
            loop._timer_cancelled_count -= 1
            handle = heapq.heappop(loop._scheduled)
            handle._scheduled = False

    # 2. Compute selector timeout based on ready handles and upcoming timers
    timeout: float | None = None
    if loop._ready or loop._stopping:
        timeout = 0
    elif loop._scheduled:
        timeout = loop._scheduled[0]._when - loop.time()
        if timeout > 86400:
            timeout = 86400
        elif timeout < 0:
            timeout = 0

    # 3. Poll for I/O events and dispatch them
    event_list = loop._selector.select(timeout)
    loop._process_events(event_list)

    # 4. Move expired timers into the ready queue
    now = loop.time()
    end_time = now + max(loop._clock_resolution, math.ulp(now))
    while loop._scheduled:
        handle = loop._scheduled[0]
        if handle._when >= end_time:
            break
        handle = heapq.heappop(loop._scheduled)
        handle._scheduled = False
        loop._ready.append(handle)


def _run_handle(loop: asyncio.SelectorEventLoop, handle: asyncio.Handle) -> None:
    """Execute a single handle safely, honoring loop._debug if enabled."""
    if handle._cancelled:
        return
    if loop._debug:
        try:
            loop._current_handle = handle
            handle._run()
        finally:
            loop._current_handle = None
    else:
        handle._run()


# ==============================================================================
# Controllable Event Loop
# ==============================================================================

class ControllableEventLoop(asyncio.SelectorEventLoop):
    """An asyncio event loop that controls task execution order and records decisions."""

    def __init__(self) -> None:
        super().__init__()
        self._task_counter = 1
        # Install the pure-Python task factory so all created tasks can be inspected
        self.set_task_factory(_py_task_factory)
        self.schedule = Schedule()
        self._failed = False

    def choose(self, ready_names: list[str]) -> int:
        """Choose the index of the task to run next from `ready_names`.

        Default implementation returns 0, preserving stock asyncio FIFO order.
        Subclasses can override this to implement custom scheduling strategies.
        """
        return 0

    def _record_choice(self, index: int, task_name: str) -> None:
        """Record a single scheduling decision in the schedule."""
        self.schedule.choices.append(index)
        self.schedule.tasks.append(task_name)

    def _run_once(self) -> None:
        """Execute one step of the event loop.

        Polls for I/O and ready timers, then executes at most one handle. If more
        than one task is ready, invokes `choose()` to decide which task runs next.
        """
        _poll_io_and_timers(self)

        # Discard cancelled handles at the head of the ready queue
        while self._ready and self._ready[0]._cancelled:
            self._ready.popleft()

        if not self._ready:
            return

        # If the front handle is a non-task callback (e.g. an internal callback
        # or I/O notification), execute it in FIFO order without a choice point.
        head_task = _extract_task_from_handle(self._ready[0])
        if head_task is None:
            handle = self._ready.popleft()
            _run_handle(self, handle)
            return

        # The front handle is a task. Check how many tasks are ready to run:
        ready_task_handles: list[tuple[asyncio.Handle, str]] = []
        for handle in self._ready:
            if handle._cancelled:
                continue
            task = _extract_task_from_handle(handle)
            if task is not None:
                ready_task_handles.append((handle, task.get_name()))

        if len(ready_task_handles) > 1 and not self._failed:
            # Choice point: more than one task is ready to run
            ready_names = [name for _, name in ready_task_handles]
            try:
                idx = self.choose(ready_names)
                if not (0 <= idx < len(ready_task_handles)):
                    raise ValueError(
                        f"choice {idx} but only {len(ready_task_handles)} tasks ready"
                    )
            except BaseException:
                # Mark as failed so subsequent loop cleanup (e.g. cancelling tasks
                # in asyncio.run's finally block) drains via FIFO without re-invoking choose.
                self._failed = True
                raise

            chosen_handle, chosen_name = ready_task_handles[idx]
            self._record_choice(idx, chosen_name)
            self._ready.remove(chosen_handle)
            handle_to_run = chosen_handle
        else:
            # Only one task is ready (or loop is cleaning up after failure): run FIFO
            handle_to_run = self._ready.popleft()

        _run_handle(self, handle_to_run)

        # If the handle belonged to a task and the task failed with an exception,
        # record the failure on the schedule.
        task = _extract_task_from_handle(handle_to_run)
        if task is not None and task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None and self.schedule.failure is None:
                msg = str(exc)
                self.schedule.failure = (
                    f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
                )


def run(
    coro: Coroutine[Any, Any, T],
    loop_cls: type[ControllableEventLoop] = ControllableEventLoop,
) -> tuple[T, Schedule]:
    """Run a coroutine on our controllable loop and return (result, schedule)."""
    recorded_loop: ControllableEventLoop | None = None

    def loop_factory() -> ControllableEventLoop:
        nonlocal recorded_loop
        recorded_loop = loop_cls()
        return recorded_loop

    try:
        result = asyncio.run(coro, loop_factory=loop_factory)
    except Exception as exc:
        if recorded_loop is not None:
            if recorded_loop.schedule.failure is None:
                msg = str(exc)
                recorded_loop.schedule.failure = (
                    f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
                )
            setattr(exc, "schedule", recorded_loop.schedule)
        raise

    assert recorded_loop is not None
    return result, recorded_loop.schedule
