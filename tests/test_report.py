"""Tests for the timeline report generator."""

from __future__ import annotations

from schedcheck import Schedule, timeline


def test_timeline_contains_header_fields() -> None:
    """The timeline output should contain seed, choice count, and status."""
    sched = Schedule(seed=42, choices=[0, 1], tasks=["A", "B"])
    report = timeline(sched)

    assert "Seed:    42" in report
    assert "Choices: 2" in report
    assert "Status:  OK" in report


def test_timeline_failure_status_and_section() -> None:
    """When schedule.failure is set, status is FAILURE and the failure section appears."""
    sched = Schedule(
        seed=7,
        choices=[0],
        tasks=["Worker"],
        failure="RuntimeError: kaboom",
    )
    report = timeline(sched)

    assert "Status:  FAILURE" in report
    assert "--- Failure ---" in report
    assert "RuntimeError: kaboom" in report


def test_timeline_choice_points_listed_correctly() -> None:
    """Each choice point should appear with its step number, index, and task name."""
    sched = Schedule(seed=1, choices=[0, 1, 0], tasks=["X", "Y", "X"])
    report = timeline(sched)

    assert "--- Choice Points ---" in report
    # Step 1: index 0, task X
    # Step 2: index 1, task Y
    # Step 3: index 0, task X
    lines = report.splitlines()
    # Find lines that have step numbers (digit at the start after whitespace)
    data_lines = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
    assert len(data_lines) == 3

    # Verify content of each data line
    assert "X" in data_lines[0]
    assert "Y" in data_lines[1]
    assert "X" in data_lines[2]


def test_timeline_no_choice_points_message() -> None:
    """An empty schedule (no choice points) should show the '(no choice points)' message."""
    sched = Schedule(seed=99)
    report = timeline(sched)

    assert "(no choice points)" in report
    assert "--- Choice Points ---" not in report


def test_timeline_no_seed_shows_none() -> None:
    """When seed is None, the report should show '(none)' for the seed."""
    sched = Schedule(choices=[0], tasks=["T"])
    report = timeline(sched)

    assert "Seed:    (none)" in report


def test_timeline_returns_string() -> None:
    """timeline() should always return a string."""
    sched = Schedule()
    report = timeline(sched)
    assert isinstance(report, str)
    assert "=== schedcheck Timeline ===" in report
