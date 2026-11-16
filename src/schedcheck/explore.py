"""Automated exploration: run a program under many random seeds to find bugs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

from schedcheck.loop import run
from schedcheck.schedule import Schedule

T = TypeVar("T")


@dataclass
class Bug:
    """A single bug discovered during exploration.

    Attributes:
        seed: The random seed that triggered the bug.
        schedule: The full Schedule that reproduces the bug.
        error: Human-readable description of what went wrong.
    """

    seed: int
    schedule: Schedule
    error: str


def explore(
    program_factory: Callable[[], Any],
    *,
    check: Callable[[Any], bool | None] | None = None,
    seeds: Iterable[int] = range(100),
    max_bugs: int = 1,
) -> list[Bug]:
    """Run a program under many random seeds and return any bugs found.

    Args:
        program_factory: A callable that returns a fresh coroutine each time.
            Must be callable multiple times (coroutines can only be awaited once).
        check: An optional invariant function called with the program's return value.
            - If it raises an exception (e.g. AssertionError), that's a bug.
            - If it returns False, that's a bug.
            - If it returns True or None, the run is considered passing.
        seeds: An iterable of integer seeds to try (default: 0..99).
        max_bugs: Stop after finding this many bugs (default: 1).

    Returns:
        A list of Bug objects, one per failing seed. Empty if no bugs found.
    """
    bugs: list[Bug] = []

    for seed in seeds:
        # 1. Run the program with this seed
        try:
            result, schedule = run(program_factory(), seed=seed)
        except Exception as exc:
            # Program crashed (including DeadlockError) — that's a bug
            sched = getattr(exc, "schedule", Schedule(seed=seed))
            bugs.append(Bug(
                seed=seed,
                schedule=sched,
                error=f"{type(exc).__name__}: {exc}",
            ))
            if len(bugs) >= max_bugs:
                break
            continue

        # 2. If the program returned, check the invariant
        if check is not None:
            try:
                check_result = check(result)
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                schedule.failure = msg
                bugs.append(Bug(seed=seed, schedule=schedule, error=msg))
                if len(bugs) >= max_bugs:
                    break
                continue

            if check_result is False:
                msg = "Invariant check returned False"
                schedule.failure = msg
                bugs.append(Bug(seed=seed, schedule=schedule, error=msg))
                if len(bugs) >= max_bugs:
                    break

    return bugs
