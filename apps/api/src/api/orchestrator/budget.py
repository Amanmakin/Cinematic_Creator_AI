"""Per-project token budget ledger backed by SQLite."""

from __future__ import annotations

import time
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

    async def spend(
        self,
        project_id: str,
        estimate: int,
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        """Check budget, run fn, then deduct. Raises BudgetExceeded if insufficient."""
        rem = await self.remaining(project_id)
        if estimate > rem:
            raise BudgetExceeded(project_id, estimate, rem)

        result = await fn()

        async with aiosqlite.connect(self._db_path) as db:
            await _init_budget_table(db)
            await db.execute(
                """INSERT INTO budget_ledger (project_id, cap, spent, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id) DO UPDATE SET
                       spent = spent + ?,
                       updated_at = excluded.updated_at""",
                (project_id, _DEFAULT_CAP, estimate, time.time(), estimate),
            )
            await db.commit()

        return result
