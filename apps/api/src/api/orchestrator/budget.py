"""Per-project token budget ledger backed by SQLite."""

from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable, TypeVar

import aiosqlite

T = TypeVar("T")

_DEFAULT_CAP = 10_000


async def _init_budget_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS budget_ledger (
            project_id TEXT PRIMARY KEY,
            cap INTEGER NOT NULL,
            spent INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS budget_reservations (
            reservation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'reserved'
        )
    """)
    await db.commit()


class BudgetExceeded(Exception):
    def __init__(self, project_id: str, required: int, remaining: int) -> None:
        super().__init__(
            f"Project {project_id}: budget exceeded — need {required}, remaining {remaining}"
        )
        self.project_id = project_id
        self.required = required
        self.remaining = remaining


class BudgetLedger:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)

    async def ensure_project(self, project_id: str, cap: int = _DEFAULT_CAP) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            await db.execute(
                """INSERT OR IGNORE INTO budget_ledger (project_id, cap, spent, updated_at)
                   VALUES (?, ?, 0, ?)""",
                (project_id, cap, time.time()),
            )
            await db.commit()

    async def remaining(self, project_id: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT cap, spent FROM budget_ledger WHERE project_id = ?", (project_id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return _DEFAULT_CAP
        return max(0, row["cap"] - row["spent"])

    async def top_up(self, project_id: str, amount: int) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            await db.execute(
                """INSERT INTO budget_ledger (project_id, cap, spent, updated_at)
                   VALUES (?, ?, 0, ?)
                   ON CONFLICT(project_id) DO UPDATE SET
                       cap = cap + excluded.cap,
                       updated_at = excluded.updated_at""",
                (project_id, amount, time.time()),
            )
            await db.commit()
        return await self.remaining(project_id)

    async def reserve(self, project_id: str, estimate: int) -> str:
        """Reserve *estimate* tokens.  Returns a reservation_id for later commit/refund.

        Raises BudgetExceeded if insufficient budget remains.
        """
        rem = await self.remaining(project_id)
        if estimate > rem:
            raise BudgetExceeded(project_id, estimate, rem)

        reservation_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            await db.execute(
                """INSERT OR IGNORE INTO budget_ledger (project_id, cap, spent, updated_at)
                   VALUES (?, ?, 0, ?)""",
                (project_id, _DEFAULT_CAP, time.time()),
            )
            await db.execute(
                """UPDATE budget_ledger SET spent = spent + ?, updated_at = ?
                   WHERE project_id = ?""",
                (estimate, time.time(), project_id),
            )
            await db.execute(
                """INSERT INTO budget_reservations (reservation_id, project_id, amount, created_at, status)
                   VALUES (?, ?, ?, ?, 'reserved')""",
                (reservation_id, project_id, estimate, time.time()),
            )
            await db.commit()
        return reservation_id

    async def commit(self, project_id: str, reservation_id: str, amount: int) -> None:
        """Mark a reservation committed (tokens are consumed — nothing to undo)."""
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            await db.execute(
                "UPDATE budget_reservations SET status='committed' WHERE reservation_id=?",
                (reservation_id,),
            )
            await db.commit()

    async def refund(self, project_id: str, reservation_id: str) -> None:
        """Refund a reserved (but not yet committed) budget token back to the ledger."""
        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT amount, status FROM budget_reservations WHERE reservation_id=?",
                (reservation_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None or row["status"] != "reserved":
                return
            amount = row["amount"]
            await db.execute(
                """UPDATE budget_ledger SET spent = MAX(0, spent - ?), updated_at = ?
                   WHERE project_id = ?""",
                (amount, time.time(), project_id),
            )
            await db.execute(
                "UPDATE budget_reservations SET status='refunded' WHERE reservation_id=?",
                (reservation_id,),
            )
            await db.commit()

    async def spend(
        self,
        project_id: str,
        estimate: int,
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        """Check budget, run fn, then deduct. Raises BudgetExceeded if insufficient."""
        reservation_id = await self.reserve(project_id, estimate)
        try:
            result = await fn()
            await self.commit(project_id, reservation_id, estimate)
            return result
        except Exception:
            await self.refund(project_id, reservation_id)
            raise
