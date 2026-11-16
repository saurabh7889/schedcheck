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
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from schedcheck import RandomEventLoop, replay, run


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


async def transfer_scenario(account: BankAccount) -> tuple[bool, bool]:
    """Run two concurrent $80 withdrawals against the account."""
    t1 = asyncio.create_task(account.withdraw(80), name="Withdrawal-1")
    t2 = asyncio.create_task(account.withdraw(80), name="Withdrawal-2")
    r1 = await t1
    r2 = await t2
    return r1, r2


def main() -> None:
    # 1. Run with Random exploration until the race condition is discovered
    print("Searching for race condition with RandomEventLoop...")
    bug_found = False
    failing_schedule = None

    for seed in range(50):
        account = BankAccount(100)
        (r1, r2), schedule = run(transfer_scenario(account), seed=seed)

        if account.balance < 0:
            print(f"-> Race condition found with seed {seed}!")
            print(f"   Final balance: ${account.balance} (Withdrawals: {r1}, {r2})")
            print(f"   Schedule choices: {schedule.choices}")
            print(f"   Schedule tasks:   {schedule.tasks}")
            failing_schedule = schedule
            bug_found = True
            break

    if not bug_found or failing_schedule is None:
        print("No race condition triggered in initial seed search.")
        return

    # 2. Save the reproducing schedule to disk
    schedule_file = Path("bug_schedule.json")
    failing_schedule.save(schedule_file)
    print(f"\nSaved failing schedule to {schedule_file.name}")

    # 3. Exact replay: Reproduce the exact bug on demand
    print("\nReplaying the saved schedule...")
    replay_account = BankAccount(100)
    (rep_r1, rep_r2), rep_schedule = replay(transfer_scenario(replay_account), failing_schedule)

    print(f"-> Replay finished!")
    print(f"   Final balance: ${replay_account.balance} (Withdrawals: {rep_r1}, {rep_r2})")
    assert replay_account.balance == -60, "Bug did not reproduce on replay!"
    print("   Bug successfully and deterministically reproduced!")

    # Clean up demo file
    if schedule_file.exists():
        schedule_file.unlink()


if __name__ == "__main__":
    main()
