"""Demonstration of a classic asyncio race condition: Bank Account Withdraw.

Scenario:
An account has an initial balance of $100.
Two concurrent tasks each attempt to withdraw $80.
Correct invariant: Balance should never drop below $0. Only one withdrawal should succeed.

Race condition:
Task A checks balance ($100 >= $80) -> passes.
Before Task A deducts the amount, it yields (e.g. simulated network I/O or sleep(0)).
Task B runs, checks balance ($100 >= $80) -> passes.
Both tasks deduct $80, resulting in a balance of -$60 (invariant broken!).

This example shows the four stages of schedcheck:
1. EXPLORE         — automatically search for race conditions across many random seeds.
2. EXPLORE SYSTEMATIC — exhaustively explore all scheduling choices (bounded).
3. REPORT          — see a human-readable timeline of what happened.
4. REPLAY          — reproduce the exact same bug deterministically.
"""

from __future__ import annotations

import asyncio

from schedcheck import explore, explore_systematic, replay, timeline


class BankAccount:
    """A bank account susceptible to a race condition without synchronization."""

    def __init__(self, initial_balance: int = 100) -> None:
        self.balance = initial_balance

    async def withdraw(self, amount: int) -> bool:
        """Attempt to withdraw money from the account."""
        if self.balance >= amount:
            # Simulate latency (e.g. database query, authorization check)
            await asyncio.sleep(0)
            self.balance -= amount
            return True
        return False


def make_scenario():
    """Create a fresh scenario coroutine (needed because coroutines are single-use)."""
    account = BankAccount(100)

    async def scenario() -> BankAccount:
        t1 = asyncio.create_task(account.withdraw(80), name="Withdrawal-1")
        t2 = asyncio.create_task(account.withdraw(80), name="Withdrawal-2")
        await t1
        await t2
        return account

    return scenario()


def main() -> None:
    # ── Stage 1: EXPLORE (Random) ──────────────────────────────────────────
    print("=" * 60)
    print("Stage 1: Exploring for race conditions (random seeds)...")
    print("=" * 60)

    bugs = explore(
        make_scenario,
        check=lambda acc: acc.balance >= 0,
        seeds=range(50),
        max_bugs=1,
    )

    if not bugs:
        print("No race condition found. All 50 seeds passed.")
        return

    bug = bugs[0]
    print(f"Bug found with seed {bug.seed}!")
    print(f"Error: {bug.error}")

    # ── Stage 2: EXPLORE SYSTEMATIC ────────────────────────────────────────
    print()
    print("=" * 60)
    print("Stage 2: Systematic exploration (exhaustive, bounded)...")
    print("=" * 60)

    sys_bugs, stats = explore_systematic(
        make_scenario,
        check=lambda acc: acc.balance >= 0,
        max_schedules=50,
        max_bugs=5,
    )

    print(f"Explored {stats.total_schedules_explored} schedules")
    print(f"Found {len(sys_bugs)} unique bug schedules")
    print(f"Max depth reached: {stats.max_depth_reached}")
    if stats.terminated_early:
        print("Search terminated early (bound reached)")

    # Show the different bug schedules found
    for i, sys_bug in enumerate(sys_bugs[:3]):
        print(f"  Bug {i+1}: choices={sys_bug.schedule.choices}, tasks={sys_bug.schedule.tasks}")

    # Use the first bug for report/replay
    bug = bugs[0]

    # ── Stage 3: REPORT ────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("Stage 3: Timeline report of the failing execution")
    print("=" * 60)
    print()
    print(timeline(bug.schedule))

    # ── Stage 4: REPLAY ────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("Stage 4: Replaying the exact bug...")
    print("=" * 60)

    replay_account = BankAccount(100)

    async def replay_scenario() -> BankAccount:
        t1 = asyncio.create_task(replay_account.withdraw(80), name="Withdrawal-1")
        t2 = asyncio.create_task(replay_account.withdraw(80), name="Withdrawal-2")
        await t1
        await t2
        return replay_account

    _, replay_schedule = replay(replay_scenario(), bug.schedule)

    print(f"Replay finished! Final balance: ${replay_account.balance}")
    assert replay_account.balance == -60, "Bug did not reproduce on replay!"
    print("Bug successfully and deterministically reproduced!")


if __name__ == "__main__":
    main()
