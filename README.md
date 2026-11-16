# schedcheck

**Deterministic schedule explorer for asyncio programs.**

`schedcheck` helps you find, reproduce, and debug race conditions in asyncio code by controlling the task execution order. It provides:

- **Random exploration** — Run your program under many random seeds to discover race conditions
- **Systematic exploration** — Exhaustively explore all scheduling choices (bounded) to find ALL bugs
- **Exact replay** — Reproduce any bug deterministically from a saved schedule
- **Timeline reports** — Human-readable execution traces showing what happened at each choice point
- **Deadlock detection** — Automatically detects when tasks are stuck waiting forever

---

## Installation

```bash
pip install schedcheck
```

Or for development:

```bash
git clone https://github.com/yourname/schedcheck
cd schedcheck
pip install -e .
```

---

## Quick Start

```python
import asyncio
from schedcheck import explore, timeline, replay

class BankAccount:
    def __init__(self, balance=100):
        self.balance = balance

    async def withdraw(self, amount):
        if self.balance >= amount:
            await asyncio.sleep(0)  # Race window!
            self.balance -= amount
            return True
        return False

async def scenario():
    account = BankAccount(100)
    t1 = asyncio.create_task(account.withdraw(80), name="Withdrawal-1")
    t2 = asyncio.create_task(account.withdraw(80), name="Withdrawal-2")
    await t1
    await t2
    return account

# 1. EXPLORE: Find the bug
bugs = explore(scenario, check=lambda acc: acc.balance >= 0, seeds=range(50))
bug = bugs[0]

# 2. REPORT: See what happened
print(timeline(bug.schedule))

# 3. REPLAY: Reproduce exactly
replay_account = BankAccount(100)
replay(scenario, bug.schedule)  # Bug reproduced deterministically!
```

---

## Four Ways to Use schedcheck

### 1. Python API: `explore()` — Random Exploration

Run your program under many random seeds:

```python
from schedcheck import explore

bugs = explore(
    lambda: my_async_program(),
    check=lambda result: result.is_valid(),  # Optional invariant check
    seeds=range(1000),                        # Seeds to try
    max_bugs=10,                              # Stop after finding this many
)
```

### 2. Python API: `explore_systematic()` — Exhaustive Search

Explore ALL scheduling choices up to bounds:

```python
from schedcheck import explore_systematic

bugs, stats = explore_systematic(
    lambda: my_async_program(),
    check=lambda result: result.is_valid(),
    max_schedules=1000,   # Max schedules to explore
    max_depth=20,         # Max choice point depth
    max_bugs=5,           # Stop after finding this many bugs
)

print(f"Explored {stats.total_schedules_explored} schedules")
print(f"Found {len(bugs)} bugs")
```

### 3. Python API: `replay()` + `timeline()` — Debug

```python
from schedcheck import replay, timeline

# Save a failing schedule
bugs = explore(...)
bugs[0].schedule.save("bug.json")

# Generate human-readable report
print(timeline(bugs[0].schedule))

# Replay exactly
result, replay_schedule = replay(lambda: my_program(), bugs[0].schedule)
```

### 4. CLI — Command Line Interface

```bash
# Random exploration
schedcheck explore my_module.py my_scenario --check my_invariant --seeds-start 0 --seeds-end 1000

# Systematic exploration
schedcheck explore-systematic my_module.py my_scenario --check my_invariant --max-schedules 500 --max-depth 15

# Generate report from saved schedule
schedcheck report bug.json

# Replay a saved schedule
schedcheck replay my_module.py my_scenario bug.json
```

---

## Key Concepts

### Choice Points

A **choice point** occurs whenever more than one asyncio task is ready to run. schedcheck intercepts these moments and decides which task runs next.

```
Normal asyncio:  Runs tasks in FIFO order (round-robin within a batch)
schedcheck:      Controls EXACTLY which ready task runs at each choice point
```

### Schedules

A **Schedule** records:
- `choices`: The index chosen at each choice point
- `tasks`: The name of the task that was chosen
- `seed`: Random seed (if applicable)
- `failure`: Error message if the run failed

Schedules are portable JSON files — save them, share them, replay them.

### Deterministic Replay

Given the same schedule, `replay()` will execute the **exact same interleaving** every time. This means:
- Bugs are 100% reproducible
- You can debug with print statements, debuggers, etc.
- CI can store failing schedules as regression tests

---

## Demo Bugs

The `examples/demo_bugs.py` file contains four classic concurrency bugs:

| Bug | Description | Invariant |
|-----|-------------|-----------|
| `make_withdraw_scenario` | Bank account race condition | Balance ≥ 0 |
| `make_counter_scenario` | Lost updates in counter | Counter == 10 |
| `make_channel_scenario` | Message reordering | Messages == ["A","B","C"] |
| `make_deadlock_scenario` | Circular wait deadlock | (detected automatically) |

Try them:

```bash
# Random exploration
schedcheck explore examples/demo_bugs.py make_withdraw_scenario --check check_balance_non_negative --seeds-end 50

# Systematic exploration
schedcheck explore-systematic examples/demo_bugs.py make_counter_scenario --check check_counter_correct --max-schedules 200

# Deadlock (no check needed - detected automatically)
schedcheck explore examples/demo_bugs.py make_deadlock_scenario --seeds-end 5
```

---

## @explore_test Decorator

For pytest-style tests:

```python
from schedcheck import explore_test

@explore_test(seeds=range(100), check=lambda acc: acc.balance >= 0)
async def test_withdraw_race():
    account = BankAccount(100)
    t1 = asyncio.create_task(account.withdraw(80), name="W1")
    t2 = asyncio.create_task(account.withdraw(80), name="W2")
    await t1
    await t2
    return account
```

If a bug is found, the test fails with the schedule details.

---

## Honest Limits

| Limitation | Details |
|------------|---------|
| **State space explosion** | The number of schedules grows exponentially with choice points. Use `max_schedules` and `max_depth` bounds. |
| **Only asyncio** | Works with `asyncio` tasks, not threads or multiprocessing. |
| **Pure Python tasks** | Uses `asyncio.tasks._PyTask` for introspection; C-accelerated tasks may not work. |
| **No data race detection** | Only finds bugs visible through scheduling interleavings + invariants. |
| **Timers approximated** | `sleep()` and timers work but exact timing isn't modeled. |
| **External I/O** | Network/disk I/O is not controlled; use mocks for deterministic tests. |

---

## Architecture

```
schedcheck/
├── loop.py           # ControllableEventLoop - core scheduling control
├── schedule.py       # Schedule data structure + JSON serialization
├── explore.py        # Random exploration (explore)
├── systematic.py     # Systematic exploration (explore_systematic)
├── replay.py         # Exact replay (ReplayEventLoop, replay)
├── report.py         # Timeline report generator (timeline)
├── decorator.py      # @explore_test decorator
├── cli.py            # Command-line interface
├── viewer.py         # Tkinter GUI viewer
└── __init__.py       # Public API exports
```

### How it works

1. **ControllableEventLoop** extends `asyncio.SelectorEventLoop`
2. Overrides `_run_once()` to execute **one handle at a time**
3. At each choice point (>1 ready task), calls `choose(ready_names)`
4. `RandomEventLoop.choose()` picks randomly (seeded)
5. `PresetChoiceEventLoop.choose()` follows a recorded schedule
6. `ReplayEventLoop.choose()` verifies and follows a schedule exactly

---

## GUI Viewer (Bonus)

A Tkinter-based GUI for visualizing and comparing schedules:

```bash
# Install with GUI support
pip install schedcheck[gui]

# Launch viewer
schedcheck-viewer
```

Or run directly:
```bash
python -m schedcheck.viewer
```

### Viewer Features

| Feature | Description |
|---------|-------------|
| **Open Schedule** | Load a `.json` schedule file |
| **Timeline View** | Human-readable execution trace |
| **Choice Points Table** | Step-by-step breakdown of scheduling decisions |
| **Failure Details** | Exception/error that caused the bug |
| **Comparison Mode** | Load two schedules side-by-side |
| **Diff View** | Highlight differences between schedules |
| **Export Report** | Save timeline as text file |
| **Save As** | Save schedule to new location |

---

## Requirements

- Python ≥ 3.12
- No external dependencies (stdlib only; `tkinter` is in stdlib)

---

## License

MIT License