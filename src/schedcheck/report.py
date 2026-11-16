"""Human-readable timeline report from a Schedule."""

from __future__ import annotations

from schedcheck.schedule import Schedule


def timeline(schedule: Schedule) -> str:
    """Produce a human-readable timeline report from a Schedule.

    Shows every choice point: what index was chosen and which task it was.

    Example output::

        === schedcheck Timeline ===
        Seed:    42
        Choices: 3
        Status:  FAILURE

        --- Choice Points ---
          #  Index  Chosen Task
          1      0  Withdrawal-1
          2      0  Withdrawal-2
          3      1  Withdrawal-2

        --- Failure ---
        AssertionError: balance is -60
    """
    lines: list[str] = []

    # Header
    lines.append("=== schedcheck Timeline ===")
    seed_str = str(schedule.seed) if schedule.seed is not None else "(none)"
    lines.append(f"Seed:    {seed_str}")
    lines.append(f"Choices: {len(schedule.choices)}")
    status = "FAILURE" if schedule.failure else "OK"
    lines.append(f"Status:  {status}")
    lines.append("")

    # Choice points table
    if schedule.choices:
        lines.append("--- Choice Points ---")

        # Compute column widths for alignment
        max_step_width = len(str(len(schedule.choices)))
        max_index_width = max(len(str(c)) for c in schedule.choices)
        step_width = max(max_step_width, 1)
        index_width = max(max_index_width, 5)

        header = f"  {'#':>{step_width}}  {'Index':>{index_width}}  Chosen Task"
        lines.append(header)

        for i, (choice, task) in enumerate(
            zip(schedule.choices, schedule.tasks), start=1
        ):
            row = f"  {i:>{step_width}}  {choice:>{index_width}}  {task}"
            lines.append(row)
    else:
        lines.append("(no choice points)")

    # Failure section
    if schedule.failure:
        lines.append("")
        lines.append("--- Failure ---")
        lines.append(schedule.failure)

    return "\n".join(lines)
