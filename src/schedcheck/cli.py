"""Command-line interface for schedcheck."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from schedcheck import (
    Bug,
    ControllableEventLoop,
    DivergenceError,
    ExplorationStats,
    RandomEventLoop,
    ReplayEventLoop,
    Schedule,
    explore,
    explore_systematic,
    replay,
    run,
    timeline,
)


def load_program(module_path: str, func_name: str) -> Any:
    """Load a program factory from a Python file."""
    path = Path(module_path)
    if not path.exists():
        raise FileNotFoundError(f"Module not found: {module_path}")

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, func_name):
        raise AttributeError(f"Function '{func_name}' not found in {module_path}")

    return getattr(module, func_name)


def cmd_explore(args: argparse.Namespace) -> int:
    """Explore command: run random exploration."""
    program_factory = load_program(args.module, args.function)

    check_func = None
    if args.check:
        check_func = load_program(args.check_module or args.module, args.check)

    bugs = explore(
        program_factory,
        check=check_func,
        seeds=range(args.seeds_start, args.seeds_end),
        max_bugs=args.max_bugs,
    )

    if not bugs:
        print("No bugs found.")
        return 0

    print(f"Found {len(bugs)} bug(s):")
    for i, bug in enumerate(bugs):
        print(f"\n--- Bug {i+1} ---")
        print(f"Seed: {bug.seed}")
        print(f"Error: {bug.error}")
        print(f"Choices: {bug.schedule.choices}")
        print(f"Tasks: {bug.schedule.tasks}")

    if args.save:
        bug.schedule.save(args.save)
        print(f"\nSaved first bug schedule to {args.save}")

    return 1 if bugs else 0


def cmd_explore_systematic(args: argparse.Namespace) -> int:
    """Explore systematic command: run systematic exploration."""
    program_factory = load_program(args.module, args.function)

    check_func = None
    if args.check:
        check_func = load_program(args.check_module or args.module, args.check)

    bugs, stats = explore_systematic(
        program_factory,
        check=check_func,
        max_depth=args.max_depth,
        max_schedules=args.max_schedules,
        max_bugs=args.max_bugs,
    )

    print(f"Schedules explored: {stats.total_schedules_explored}")
    print(f"Bugs found: {len(bugs)}")
    print(f"Max depth reached: {stats.max_depth_reached}")
    if stats.terminated_early:
        print("Terminated early (bound reached)")

    if not bugs:
        return 0

    print(f"\nFound {len(bugs)} bug(s):")
    for i, bug in enumerate(bugs):
        print(f"\n--- Bug {i+1} ---")
        print(f"Schedule index: {bug.seed}")
        print(f"Error: {bug.error}")
        print(f"Choices: {bug.schedule.choices}")
        print(f"Tasks: {bug.schedule.tasks}")

    if args.save:
        bug.schedule.save(args.save)
        print(f"\nSaved first bug schedule to {args.save}")

    return 1 if bugs else 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Replay command: replay a saved schedule."""
    program_factory = load_program(args.module, args.function)

    schedule = Schedule.load(args.schedule_file)

    try:
        result, replay_schedule = replay(program_factory(), schedule)
        print("Replay successful!")
        print(f"Result: {result}")
        print(f"Replay schedule choices: {replay_schedule.choices}")
        print(f"Replay schedule tasks: {replay_schedule.tasks}")
        if replay_schedule.failure:
            print(f"Failure reproduced: {replay_schedule.failure}")
        return 0
    except DivergenceError as e:
        print(f"Replay DIVERGED: {e}")
        return 2
    except Exception as e:
        print(f"Replay failed with error: {e}")
        return 1


def cmd_report(args: argparse.Namespace) -> int:
    """Report command: generate timeline report from schedule."""
    schedule = Schedule.load(args.schedule_file)
    print(timeline(schedule))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="schedcheck",
        description="Deterministic schedule explorer for asyncio",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # explore command
    explore_parser = subparsers.add_parser("explore", help="Random exploration for bugs")
    explore_parser.add_argument("module", help="Python file containing the program")
    explore_parser.add_argument("function", help="Function name returning a coroutine")
    explore_parser.add_argument("--check", help="Invariant check function name")
    explore_parser.add_argument("--check-module", help="Module containing check function (default: same as program)")
    explore_parser.add_argument("--seeds-start", type=int, default=0, help="Start seed (inclusive)")
    explore_parser.add_argument("--seeds-end", type=int, default=100, help="End seed (exclusive)")
    explore_parser.add_argument("--max-bugs", type=int, default=1, help="Maximum bugs to find")
    explore_parser.add_argument("--save", help="Save first bug schedule to file")
    explore_parser.set_defaults(func=cmd_explore)

    # explore-systematic command
    systematic_parser = subparsers.add_parser("explore-systematic", help="Systematic exploration (exhaustive, bounded)")
    systematic_parser.add_argument("module", help="Python file containing the program")
    systematic_parser.add_argument("function", help="Function name returning a coroutine")
    systematic_parser.add_argument("--check", help="Invariant check function name")
    systematic_parser.add_argument("--check-module", help="Module containing check function (default: same as program)")
    systematic_parser.add_argument("--max-depth", type=int, help="Maximum choice point depth")
    systematic_parser.add_argument("--max-schedules", type=int, help="Maximum schedules to explore")
    systematic_parser.add_argument("--max-bugs", type=int, default=1, help="Maximum bugs to find")
    systematic_parser.add_argument("--save", help="Save first bug schedule to file")
    systematic_parser.set_defaults(func=cmd_explore_systematic)

    # replay command
    replay_parser = subparsers.add_parser("replay", help="Replay a saved schedule")
    replay_parser.add_argument("module", help="Python file containing the program")
    replay_parser.add_argument("function", help="Function name returning a coroutine")
    replay_parser.add_argument("schedule_file", help="Schedule JSON file to replay")
    replay_parser.set_defaults(func=cmd_replay)

    # report command
    report_parser = subparsers.add_parser("report", help="Generate timeline report from schedule")
    report_parser.add_argument("schedule_file", help="Schedule JSON file")
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())