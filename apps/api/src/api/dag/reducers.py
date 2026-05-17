"""DAG event store — SQLite-backed append-only log keyed by project_id.

Events record task lifecycle, render progress, approvals, and failures.
The store is the source of truth for cancellation lookups and approval gates.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal

import aiosqlite

from api.settings import settings

EventKind = Literal[
    "TaskEnqueued",
    "TaskStarted",
    "TaskCancelled",
    "PreviewFrameReady",
    "PreviewCompleted",
    "FinalRenderRequested",
    "FinalRenderBlocked",
    "FinalRenderApproved",
    "FinalRenderCompleted",
    "RenderFailed",
    "EncodingFailed",
    # Plan7 memory events
    "RejectionCaptured",
    "StyleOverridePinned",
    "HistoryCompressed",
    # Plan8 hybrid adapter telemetry
    "AssetGenerated",
]


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dag_events (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            kind        TEXT NOT NULL,
            dag_node_id TEXT,
            arq_job_id  TEXT,
            scene_hash  TEXT,
            payload     TEXT NOT NULL,
            created_at  REAL NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dag_events_project ON dag_events(project_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dag_events_node ON dag_events(project_id, dag_node_id)"
    )
    await db.commit()


async def init_dag_tables() -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)


async def record_event(
    project_id: str,
    kind: EventKind,
    payload: dict[str, Any],
    *,
    dag_node_id: str | None = None,
    arq_job_id: str | None = None,
    scene_hash: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    now = time.time()
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        await db.execute(
            """INSERT INTO dag_events
               (id, project_id, kind, dag_node_id, arq_job_id, scene_hash, payload, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event_id, project_id, kind, dag_node_id, arq_job_id, scene_hash,
             json.dumps(payload), now),
        )
        await db.commit()
    return event_id


async def get_events(
    project_id: str,
    *,
    kind: EventKind | None = None,
    dag_node_id: str | None = None,
    scene_hash: str | None = None,
) -> list[dict]:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        db.row_factory = aiosqlite.Row
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if dag_node_id:
            clauses.append("dag_node_id = ?")
            params.append(dag_node_id)
        if scene_hash:
            clauses.append("scene_hash = ?")
            params.append(scene_hash)
        sql = f"SELECT * FROM dag_events WHERE {' AND '.join(clauses)} ORDER BY created_at"
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [
        {**dict(r), "payload": json.loads(r["payload"])}
        for r in rows
    ]


async def has_event(
    project_id: str,
    kind: EventKind,
    *,
    scene_hash: str | None = None,
    dag_node_id: str | None = None,
) -> bool:
    events = await get_events(
        project_id, kind=kind, scene_hash=scene_hash, dag_node_id=dag_node_id
    )
    return len(events) > 0


async def get_arq_job_ids(project_id: str, dag_node_id: str) -> list[str]:
    """Return all arq job IDs recorded under TaskEnqueued for a node."""
    events = await get_events(project_id, kind="TaskEnqueued", dag_node_id=dag_node_id)
    return [e["arq_job_id"] for e in events if e.get("arq_job_id")]


async def count_retries(project_id: str, dag_node_id: str) -> int:
    """Count how many TaskEnqueued events exist for this node (= number of attempts)."""
    events = await get_events(project_id, kind="TaskEnqueued", dag_node_id=dag_node_id)
    return len(events)


async def clear_retries(project_id: str, dag_node_id: str) -> None:
    """Delete TaskEnqueued events for a node so the retry counter resets."""
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        await db.execute(
            "DELETE FROM dag_events WHERE project_id=? AND dag_node_id=? AND kind='TaskEnqueued'",
            (project_id, dag_node_id),
        )
        await db.commit()
