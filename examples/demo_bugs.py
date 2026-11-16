"""Demo buggy programs for schedcheck CLI demonstration."""

from __future__ import annotations

import asyncio


# ==============================================================================
# Bug 1: Classic Bank Account Race Condition
# ==============================================================================

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


def make_withdraw_scenario() -> asyncio.coroutines:
    """Create a fresh withdraw scenario (coroutine factory)."""
    account = BankAccount(100)

    async def scenario() -> BankAccount:
        t1 = asyncio.create_task(account.withdraw(80), name="Withdrawal-1")
        t2 = asyncio.create_task(account.withdraw(80), name="Withdrawal-2")
        await t1
        await t2
        return account

    return scenario()


def check_balance_non_negative(account: BankAccount) -> bool:
    """Invariant: balance should never be negative."""
    return account.balance >= 0


# ==============================================================================
# Bug 2: Lost Update in Counter
# ==============================================================================

class Counter:
    """A simple counter that loses updates due to race condition."""

    def __init__(self) -> None:
        self.value = 0

    async def increment(self) -> None:
        """Increment the counter (not atomic!)."""
        current = self.value
        await asyncio.sleep(0)  # Race window
        self.value = current + 1


def make_counter_scenario() -> asyncio.coroutines:
    """Create a counter increment scenario."""
    counter = Counter()

    async def scenario() -> Counter:
        tasks = [
            asyncio.create_task(counter.increment(), name=f"Increment-{i}")
            for i in range(10)
        ]
        for t in tasks:
            await t
        return counter

    return scenario()


def check_counter_correct(counter: Counter) -> bool:
    """Invariant: counter should equal number of increments (10)."""
    return counter.value == 10


# ==============================================================================
# Bug 3: Message Ordering in Channel
# ==============================================================================

class MessageChannel:
    """A simple message channel where order can be corrupted."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, msg: str) -> None:
        """Send a message (order not guaranteed under concurrency)."""
        await asyncio.sleep(0)  # Race window
        self.messages.append(msg)


def make_channel_scenario() -> asyncio.coroutines:
    """Create a message ordering scenario."""
    channel = MessageChannel()

    async def scenario() -> MessageChannel:
        t1 = asyncio.create_task(channel.send("A"), name="Sender-A")
        t2 = asyncio.create_task(channel.send("B"), name="Sender-B")
        t3 = asyncio.create_task(channel.send("C"), name="Sender-C")
        await t1
        await t2
        await t3
        return channel

    return scenario()


def check_message_order(channel: MessageChannel) -> bool:
    """Invariant: messages should be in order A, B, C."""
    return channel.messages == ["A", "B", "C"]


# ==============================================================================
# Bug 4: Deadlock Example
# ==============================================================================

def make_deadlock_scenario() -> asyncio.coroutines:
    """Create a deadlock scenario."""
    async def scenario() -> None:
        event_a = asyncio.Event()
        event_b = asyncio.Event()

        async def task_a() -> None:
            await event_b.wait()
            event_a.set()

        async def task_b() -> None:
            await event_a.wait()
            event_b.set()

        a = asyncio.create_task(task_a(), name="Task-A")
        b = asyncio.create_task(task_b(), name="Task-B")
        await a
        await b

    return scenario()