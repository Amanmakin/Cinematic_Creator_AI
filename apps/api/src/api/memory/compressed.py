"""Tier 4 — Compressed history: LLM-summarised chunks of the event log.

CompressedChunk rows are written by the compress_history arq task.
This module initialises the table and provides read helpers used by build_context.
"""

from __future__ import annotations

import time
import uuid

import aiosqlite
from pydantic import BaseModel

from api.settings import settings


class CompressedChunk(BaseModel):
    id: str
    project_id: str
    from_event_id: str
    to_event_id: str
    summary: str           # <= 500 tokens
    embedding: list[float] # for retrieval


async def init_table(db_path: str | None = None) -> None:
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS compressed_chunks (
                id           TEXT PRIMARY KEY,
                project_id   TEXT NOT NULL,
                from_event_id TEXT NOT NULL,
                to_event_id  TEXT NOT NULL,
                summary      TEXT NOT NULL,
                embedding    BLOB,
                created_at   REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_cc_project ON compressed_chunks(project_id)"
        )
        await db.commit()


async def insert_chunk(chunk: CompressedChunk, db_path: str | None = None) -> None:
    import struct

    path = db_path or settings.db_path
    emb_blob = struct.pack(f"<{len(chunk.embedding)}f", *chunk.embedding)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """INSERT OR REPLACE INTO compressed_chunks
               (id, project_id, from_event_id, to_event_id, summary, embedding, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (chunk.id, chunk.project_id, chunk.from_event_id, chunk.to_event_id,
             chunk.summary, emb_blob, time.time()),
        )
        await db.commit()


async def get_chunks(
    project_id: str, *, last_k: int = 3, db_path: str | None = None
) -> list[CompressedChunk]:
    import struct

    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM compressed_chunks WHERE project_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (project_id, last_k),
        ) as cur:
            rows = await cur.fetchall()

    result = []
    for r in rows:
        r = dict(r)
        emb: list[float] = []
        if r["embedding"]:
            n = len(r["embedding"]) // 4
            emb = list(struct.unpack(f"<{n}f", r["embedding"]))
        result.append(CompressedChunk(
            id=r["id"],
            project_id=r["project_id"],
            from_event_id=r["from_event_id"],
            to_event_id=r["to_event_id"],
            summary=r["summary"],
            embedding=emb,
        ))
    return list(reversed(result))  # chronological order


async def build(
    project_id: str, *, last_k: int = 3, db_path: str | None = None
) -> dict | None:
    """Return a system-role ChatMessage with compressed history, or None if empty."""
    chunks = await get_chunks(project_id, last_k=last_k, db_path=db_path)
    if not chunks:
        return None
    summaries = "\n\n".join(
        f"[Chunk {i+1}: events {c.from_event_id[:8]}…{c.to_event_id[:8]}]\n{c.summary}"
        for i, c in enumerate(chunks)
    )
    return {"role": "system", "content": f"## Compressed History\n\n{summaries}"}
