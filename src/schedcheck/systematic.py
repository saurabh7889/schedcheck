"""Systematic exploration: DFS over scheduling choices with bounds."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product
from typing import Any, Type

from schedcheck.loop import ControllableEventLoop, run
from schedcheck.schedule import Schedule
from schedcheck.explore import Bug


@dataclass
class ExplorationStats:
    """Statistics from a systematic exploration run."""
    total_schedules_explored: int = 0
    bugs_found: int = 0
    max_depth_reached: int = 0
    pruned: int = 0
    terminated_early: bool = False


def _make_preset_loop_class(choices: list[int]) -> Type[ControllableEventLoop]:
    """Create a ControllableEventLoop subclass that follows preset choices."""
    class PresetChoiceEventLoop(ControllableEventLoop):
        def __init__(self) -> None:
            super().__init__()
            self._preset_choices = choices
            self._choice_index = 0

        def choose(self, ready_names: list[str]) -> int:
            if self._choice_index >= len(self._preset_choices):
                # No more preset choices - default to first task
                return 0
            choice = self._preset_choices[self._choice_index]
            self._choice_index += 1
            # Clamp to valid range
            if choice >= len(ready_names):
                return 0
            return choice

    return PresetChoiceEventLoop


def _discover_choice_widths(program_factory: Callable[[], Any]) -> list[int]:
    """Discover the number of ready tasks at each choice point by running once."""
    widths: list[int] = []

    class WidthDiscoveryLoop(ControllableEventLoop):
        def choose(self, ready_names: list[str]) -> int:
            widths.append(len(ready_names))
            return 0  # Always pick first

    def width_factory() -> WidthDiscoveryLoop:
        return WidthDiscoveryLoop()

    try:
        run(program_factory(), loop_cls=WidthDiscoveryLoop)
    except Exception:
        pass

    return widths


def _generate_choice_sequences(
    widths: list[int],
    max_depth: int | None = None,
    max_schedules: int | None = None,
) -> Iterator[list[int]]:
    """Generate all combinations of choices up to bounds."""
    if not widths:
        yield []
        return

    # Apply max_depth
    if max_depth is not None:
        widths = widths[:max_depth]

    # Generate all combinations
    count = 0
    for choice_combo in product(*[range(w) for w in widths]):
        yield list(choice_combo)
        count += 1
        if max_schedules is not None and count >= max_schedules:
            break


def explore_systematic(
    program_factory: Callable[[], Any],
    *,
    check: Callable[[Any], bool | None] | None = None,
    max_depth: int | None = None,
    max_schedules: int | None = None,
    max_bugs: int = 1,
) -> tuple[list[Bug], ExplorationStats]:
    """
    Systematically explore all scheduling choices via exhaustive search.

    Unlike random exploration, this exhaustively explores the scheduling tree
    (within bounds) to find ALL bugs up to the given limits.

    Args:
        program_factory: Callable returning a fresh coroutine
        check: Optional invariant check
        max_depth: Maximum depth of choice points to explore (default: unlimited)
        max_schedules: Maximum number of complete schedules to explore (default: unlimited)
        max_bugs: Stop after finding this many bugs (default: 1)

    Returns:
        Tuple of (list of Bug objects, ExplorationStats)
    """
    bugs: list[Bug] = []
    stats = ExplorationStats()

    # Discover choice point structure
    widths = _discover_choice_widths(program_factory)
    stats.max_depth_reached = len(widths)

    # Generate choice sequences
    sequences = list(_generate_choice_sequences(
        widths,
        max_depth=max_depth,
        max_schedules=max_schedules,
    ))

    for i, choices in enumerate(sequences):
        if max_schedules is not None and i >= max_schedules:
            stats.terminated_early = True
            break

        if max_bugs is not None and len(bugs) >= max_bugs:
            stats.terminated_early = True
            break

        # Run with this choice sequence using a dynamically created loop class
        loop_cls = _make_preset_loop_class(choices)

        try:
            result, schedule = run(program_factory(), loop_cls=loop_cls)
            stats.total_schedules_explored += 1

            # Check invariant
            if check is not None:
                try:
                    check_result = check(result)
                except Exception as exc:
                    msg = f"{type(exc).__name__}: {exc}"
                    schedule.failure = msg
                    bugs.append(Bug(seed=i, schedule=schedule, error=msg))
                    stats.bugs_found += 1
                else:
                    if check_result is False:
                        msg = "Invariant check returned False"
                        schedule.failure = msg
                        bugs.append(Bug(seed=i, schedule=schedule, error=msg))
                        stats.bugs_found += 1

        except Exception as exc:
            # Program crashed - record as bug
            sched = getattr(exc, "schedule", Schedule(seed=i))
            bugs.append(Bug(
                seed=i,
                schedule=sched,
                error=f"{type(exc).__name__}: {exc}",
            ))
            stats.bugs_found += 1
            stats.total_schedules_explored += 1
    else:
        # Loop completed without break - check if we hit max_schedules limit
        if max_schedules is not None and len(sequences) >= max_schedules:
            stats.terminated_early = True

    return bugs, stats