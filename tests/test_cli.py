"""Tests for CLI and decorator."""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from schedcheck import explore_test


def test_cli_explore_random() -> None:
    """CLI explore command finds race condition."""
    result = subprocess.run([
        sys.executable, "-m", "schedcheck", "explore",
        "examples/demo_bugs.py", "make_withdraw_scenario",
        "--check", "check_balance_non_negative",
        "--seeds-start", "0", "--seeds-end", "50",
        "--max-bugs", "1"
    ], capture_output=True, text=True, cwd="D:/SCHEDCHECK")

    assert result.returncode == 1  # Bug found
    assert "Found 1 bug(s)" in result.stdout
    assert "Invariant check returned False" in result.stdout


def test_cli_explore_systematic() -> None:
    """CLI explore-systematic command finds bugs exhaustively."""
    result = subprocess.run([
        sys.executable, "-m", "schedcheck", "explore-systematic",
        "examples/demo_bugs.py", "make_withdraw_scenario",
        "--check", "check_balance_non_negative",
        "--max-schedules", "50",
        "--max-bugs", "3"
    ], capture_output=True, text=True, cwd="D:/SCHEDCHECK")

    assert result.returncode == 1  # Bugs found
    assert "Schedules explored:" in result.stdout
    assert "Bugs found:" in result.stdout


def _load_demo_module():
    """Load the demo_bugs module."""
    spec = importlib.util.spec_from_file_location(
        "demo_bugs", "D:/SCHEDCHECK/examples/demo_bugs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_report() -> None:
    """CLI report command generates timeline."""
    # First generate a schedule
    import tempfile
    from schedcheck import explore

    demo = _load_demo_module()
    bugs = explore(demo.make_withdraw_scenario, check=demo.check_balance_non_negative, seeds=range(10), max_bugs=1)
    assert bugs

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        schedule_path = f.name

    bugs[0].schedule.save(schedule_path)

    # Now test report
    result = subprocess.run([
        sys.executable, "-m", "schedcheck", "report", schedule_path
    ], capture_output=True, text=True, cwd="D:/SCHEDCHECK")

    assert result.returncode == 0
    assert "=== schedcheck Timeline ===" in result.stdout
    assert "Status:  FAILURE" in result.stdout
    assert "Choice Points" in result.stdout


def test_cli_replay() -> None:
    """CLI replay command reproduces bug."""
    # First generate a schedule
    import tempfile
    from schedcheck import explore

    demo = _load_demo_module()
    bugs = explore(demo.make_withdraw_scenario, check=demo.check_balance_non_negative, seeds=range(10), max_bugs=1)
    assert bugs

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        schedule_path = f.name

    bugs[0].schedule.save(schedule_path)

    # Now test replay
    result = subprocess.run([
        sys.executable, "-m", "schedcheck", "replay",
        "D:/SCHEDCHECK/examples/demo_bugs.py", "make_withdraw_scenario", schedule_path
    ], capture_output=True, text=True, cwd="D:/SCHEDCHECK")

    assert result.returncode == 0
    assert "Replay successful!" in result.stdout


def test_explore_test_decorator() -> None:
    """@explore_test decorator catches bugs."""
    @explore_test(seeds=range(20), check=lambda acc: acc.balance >= 0)
    async def test_withdraw_race():
        from examples.demo_bugs import BankAccount
        account = BankAccount(100)
        t1 = asyncio.create_task(account.withdraw(80), name="W1")
        t2 = asyncio.create_task(account.withdraw(80), name="W2")
        await t1
        await t2
        return account

    # Should raise AssertionError because bug is found
    with pytest.raises(AssertionError, match="Bug found"):
        test_withdraw_race()


def test_explore_test_decorator_passes_on_correct() -> None:
    """@explore_test decorator passes when no bug."""
    @explore_test(seeds=range(20), check=lambda x: x == 42)
    async def test_correct():
        await asyncio.sleep(0)
        return 42

    # Should not raise
    test_correct()


def test_explore_test_decorator_systematic() -> None:
    """@explore_test decorator works with systematic mode."""
    @explore_test(
        check=lambda acc: acc.balance >= 0,
        systematic=True,
        max_schedules=50,
        max_bugs=1,
    )
    async def test_withdraw_systematic():
        from examples.demo_bugs import BankAccount
        account = BankAccount(100)
        t1 = asyncio.create_task(account.withdraw(80), name="W1")
        t2 = asyncio.create_task(account.withdraw(80), name="W2")
        await t1
        await t2
        return account

    # Should raise AssertionError because bug is found
    with pytest.raises(AssertionError, match="Bug found"):
        test_withdraw_systematic()