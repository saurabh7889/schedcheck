"""Deterministic replay of recorded execution schedules."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

from schedcheck.loop import ControllableEventLoop
from schedcheck.schedule import Schedule

T = TypeVar("T")


class DivergenceError(Exception):
    """Raised when replaying a schedule diverges from the recorded execution trace."""


class ReplayEventLoop(ControllableEventLoop):
    """An event loop that replays a recorded Schedule choice-by-choice."""

    def __init__(self, schedule: Schedule) -> None:
        super().__init__()
        self._target_schedule = schedule
        self._step_index = 0
        # Preserve original seed from the target schedule
        self.schedule.seed = schedule.seed

    def choose(self, ready_names: list[str]) -> int:
        """Return the next recorded choice, verifying that the expected task is chosen."""
        if self._step_index >= len(self._target_schedule.choices):
            raise DivergenceError(
                f"Schedule exhausted: needed choice at step {self._step_index}, "
                f"but schedule only has {len(self._target_schedule.choices)} choices. "
                f"Ready tasks: {ready_names}"
            )

        choice = self._target_schedule.choices[self._step_index]
        expected_task = self._target_schedule.tasks[self._step_index]

        if not (0 <= choice < len(ready_names)):
            raise DivergenceError(
                f"Choice index {choice} at step {self._step_index} is out of range "
                f"for ready tasks: {ready_names}"
            )

        chosen_task = ready_names[choice]
        if chosen_task != expected_task:
            raise DivergenceError(
                f"Divergence at step {self._step_index}: expected task '{expected_task}' "
                f"at index {choice}, but found '{chosen_task}'. "
                f"Ready tasks: {ready_names}"
            )

        self._step_index += 1
        return choice


def replay(
    coro: Coroutine[Any, Any, T],
    schedule: Schedule,
) -> tuple[T, Schedule]:
    """Replay a coroutine using the exact decisions recorded in `schedule`.

    Args:
        coro: The coroutine to run.
        schedule: The recorded schedule to replay.

    Returns:
        A tuple of (result, replay_schedule).

    Raises:
        DivergenceError: If the execution path diverges from the recorded schedule.
    """
    recorded_loop: ReplayEventLoop | None = None

    def loop_factory() -> ReplayEventLoop:
        nonlocal recorded_loop
        recorded_loop = ReplayEventLoop(schedule=schedule)
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

    # Check whether all choices from the target schedule were consumed
    if recorded_loop._step_index < len(schedule.choices):
        raise DivergenceError(
            f"Schedule underflow: program completed after {recorded_loop._step_index} choice points, "
            f"but schedule expected {len(schedule.choices)} choices"
        )

    return result, recorded_loop.schedule
