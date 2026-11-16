"""Schedule data structure for recording and replaying task execution choices."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Schedule:
    """Represents a recorded sequence of scheduling decisions.

    Attributes:
        version: Schema version of the schedule format (defaults to 1).
        seed: Random seed if choices were generated with a PRNG, or None.
        choices: The index chosen at each choice point.
        tasks: The name of the task chosen at each choice point.
        failure: An error message or exception representation if the run failed,
            or None if the run succeeded.
    """

    version: int = 1
    seed: int | None = None
    choices: list[int] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    failure: str | None = None

    def save(self, path: str | Path) -> None:
        """Serialize this schedule to a human-readable JSON file."""
        target_path = Path(path)
        with target_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> Schedule:
        """Load and deserialize a Schedule from a JSON file."""
        target_path = Path(path)
        with target_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            version=data.get("version", 1),
            seed=data.get("seed"),
            choices=data.get("choices", []),
            tasks=data.get("tasks", []),
            failure=data.get("failure"),
        )
