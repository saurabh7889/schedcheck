"""@explore decorator for easy integration with test functions."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

# Avoid circular import by importing at runtime
# from schedcheck import Bug, explore, explore_systematic
# from schedcheck.systematic import ExplorationStats


T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def explore_test(
    *,
    seeds: range | list[int] | None = None,
    max_bugs: int = 1,
    check: Callable[[Any], bool | None] | None = None,
    systematic: bool = False,
    max_schedules: int | None = None,
    max_depth: int | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., None]]:
    """
    Decorator to automatically explore an async test function for race conditions.

    Usage:
        @explore_test(seeds=range(100), check=lambda result: result.balance >= 0)
        async def test_withdraw():
            ...

    Args:
        seeds: Seeds to try for random exploration (default: range(100))
        max_bugs: Maximum bugs to find (default: 1)
        check: Invariant check function (default: None - only catches crashes)
        systematic: Use systematic exploration instead of random (default: False)
        max_schedules: Max schedules for systematic exploration (default: unlimited)
        max_depth: Max depth for systematic exploration (default: unlimited)
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Import here to avoid circular imports
            from schedcheck import explore, explore_systematic
            from schedcheck.systematic import ExplorationStats

            # The decorated function should return a coroutine or be async
            # We need to call it fresh each time
            def program_factory():
                return func(*args, **kwargs)

            if systematic:
                bugs, stats = explore_systematic(
                    program_factory,
                    check=check,
                    max_schedules=max_schedules,
                    max_depth=max_depth,
                    max_bugs=max_bugs,
                )
                if bugs:
                    # Print summary
                    print(f"\n{'='*60}")
                    print(f"Systematic Exploration Summary")
                    print(f"{'='*60}")
                    print(f"Schedules explored: {stats.total_schedules_explored}")
                    print(f"Bugs found: {len(bugs)}")
                    print(f"Max depth reached: {stats.max_depth_reached}")
                    if stats.terminated_early:
                        print(f"Terminated early (bound reached)")
                    # Raise the first bug as an assertion error
                    raise AssertionError(f"Bug found: {bugs[0].error}\nSchedule: {bugs[0].schedule.choices}")
            else:
                seeds_to_use = seeds if seeds is not None else range(100)
                bugs = explore(
                    program_factory,
                    check=check,
                    seeds=seeds_to_use,
                    max_bugs=max_bugs,
                )
                if bugs:
                    raise AssertionError(f"Bug found with seed {bugs[0].seed}: {bugs[0].error}\nSchedule: {bugs[0].schedule.choices}")

            return None  # Test passed if no bugs found

        return wrapper  # type: ignore
    return decorator


# Also provide a simpler alias
explore = explore_test