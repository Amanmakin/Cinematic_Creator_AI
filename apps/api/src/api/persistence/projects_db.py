"""SQLite persistence for ProjectCanon and semantic locks.

LangGraph checkpoints are stored by SqliteSaver (separate DB handle).
This module only persists what LangGraph doesn't: project metadata and locks.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import aiosqlite

from api.settings import settings


async def init_db() -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                canon_json TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS locks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                path TEXT NOT NULL,
                asset_id TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def create_project(canon_dict: dict) -> str:
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO projects (id, created_at, canon_json) VALUES (?, ?, ?)",
            (project_id, now, json.dumps(canon_dict)),
        )
        await db.commit()
    return project_id


async def get_project_canon(project_id: str) -> dict | None:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT canon_json FROM projects WHERE id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return json.loads(row[0])


async def project_exists(project_id: str) -> bool:
    return await get_project_canon(project_id) is not None


async def get_locks(project_id: str) -> list[dict]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, path, asset_id, reason, created_at FROM locks WHERE project_id = ?",
            (project_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def add_lock(project_id: str, path: str, asset_id: str | None, reason: str) -> dict:
    lock_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO locks (id, project_id, path, asset_id, reason, created_at) VALUES (?,?,?,?,?,?)",
            (lock_id, project_id, path, asset_id, reason, now),
        )
        await db.commit()
    return {"id": lock_id, "project_id": project_id, "path": path, "asset_id": asset_id, "reason": reason, "created_at": now}


async def delete_lock(project_id: str, lock_path: str) -> bool:
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute(
            "DELETE FROM locks WHERE project_id = ? AND path = ?", (project_id, lock_path)
        )
        await db.commit()
        return cursor.rowcount > 0


def get_sqlite_checkpointer():
    """Return a SqliteSaver for LangGraph checkpoints."""
    from langgraph.checkpoint.sqlite import SqliteSaver
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    return SqliteSaver(conn)
