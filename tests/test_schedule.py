"""Tests for the Schedule data structure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schedcheck.schedule import Schedule


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """A Schedule saved to disk and loaded back must equal the original object."""
    original = Schedule(
        seed=42,
        choices=[0, 1, 0],
        tasks=["U1", "U2", "U1"],
        failure=None,
    )
    file_path = tmp_path / "schedule.json"
    original.save(file_path)

    loaded = Schedule.load(file_path)
    assert loaded == original


def test_save_format(tmp_path: Path) -> None:
    """The saved JSON must be human-readable with indent=2 and match the expected schema."""
    schedule = Schedule(
        seed=42,
        choices=[0, 1, 0],
        tasks=["U1", "U2"],
        failure=None,
    )
    file_path = tmp_path / "schedule.json"
    schedule.save(file_path)

    raw_text = file_path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text)

    assert parsed == {
        "version": 1,
        "seed": 42,
        "choices": [0, 1, 0],
        "tasks": ["U1", "U2"],
        "failure": None,
    }
    # Check that indent=2 formatting was used (e.g. lines indented with two spaces)
    assert '  "seed": 42' in raw_text


def test_save_and_load_with_failure(tmp_path: Path) -> None:
    """A schedule containing a failure message roundtrips correctly."""
    schedule = Schedule(
        seed=123,
        choices=[0],
        tasks=["Task-1"],
        failure="AssertionError: values differ",
    )
    file_path = tmp_path / "failed_schedule.json"
    schedule.save(file_path)

    loaded = Schedule.load(file_path)
    assert loaded == schedule
    assert loaded.failure == "AssertionError: values differ"


def test_save_load_roundtrip_with_failure_and_version(tmp_path: Path) -> None:
    """Test 3(a): Schedule round-trip with failure set and explicit version."""
    original = Schedule(
        version=1,
        seed=42,
        choices=[0, 1],
        tasks=["Task-1", "Task-2"],
        failure="RuntimeError: worker exploded",
    )
    file_path = tmp_path / "schedule_failure_version.json"
    original.save(file_path)

    loaded = Schedule.load(file_path)
    assert loaded == original
    assert loaded.version == 1
    assert loaded.failure == "RuntimeError: worker exploded"


def test_load_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    """Test 3(b): Load of a missing file raises FileNotFoundError."""
    missing_path = tmp_path / "nonexistent.json"
    with pytest.raises(FileNotFoundError):
        Schedule.load(missing_path)


def test_default_values() -> None:
    """A Schedule created without arguments has empty lists, version=1, and None for optional fields."""
    schedule = Schedule()
    assert schedule.version == 1
    assert schedule.seed is None
    assert schedule.choices == []
    assert schedule.tasks == []
    assert schedule.failure is None
