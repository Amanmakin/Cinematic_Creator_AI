"""Tier 5 — Semantic retrieval index for RejectedConcepts and StyleOverrides.

Embeddings are stored as float32 BLOBs.  Cosine similarity is computed in Python
via numpy (already a project dependency) to keep the setup portable — no native
sqlite-vss extension required.
"""

from __future__ import annotations

import time
import uuid

import aiosqlite
import numpy as np

from api.memory.embeddings import blob_to_array, cosine_similarity, embed_to_blob, embed
from api.settings import settings


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

async def init_tables(db_path: str | None = None) -> None:
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rejected_concepts (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL,
                prompt      TEXT NOT NULL,
                reason      TEXT NOT NULL,
                embedding   BLOB NOT NULL,
                created_at  REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rc_project ON rejected_concepts(project_id)"
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS style_overrides (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL,
                description TEXT NOT NULL,
                embedding   BLOB NOT NULL,
                created_at  REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_so_project ON style_overrides(project_id)"
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

async def record_rejection(
    project_id: str,
    prompt: str,
    reason: str,
    db_path: str | None = None,
) -> str:
    path = db_path or settings.db_path
    rid = str(uuid.uuid4())
    blob = embed_to_blob(f"{prompt} {reason}")
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """INSERT INTO rejected_concepts
               (id, project_id, prompt, reason, embedding, created_at)
               VALUES (?,?,?,?,?,?)""",
            (rid, project_id, prompt, reason, blob, time.time()),
        )
        await db.commit()
    return rid


async def record_style_override(
    project_id: str,
    description: str,
    db_path: str | None = None,
) -> str:
    path = db_path or settings.db_path
    sid = str(uuid.uuid4())
    blob = embed_to_blob(description)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """INSERT INTO style_overrides
               (id, project_id, description, embedding, created_at)
               VALUES (?,?,?,?,?)""",
            (sid, project_id, description, blob, time.time()),
        )
        await db.commit()
    return sid


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

async def _top_k_rejections(
    project_id: str, query_vec: np.ndarray, k: int, db_path: str | None
) -> list[dict]:
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, prompt, reason, embedding FROM rejected_concepts WHERE project_id = ?",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()

    scored = []
    for r in rows:
        vec = blob_to_array(r["embedding"])
        score = cosine_similarity(query_vec, vec)
        scored.append({"prompt": r["prompt"], "reason": r["reason"], "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


async def _top_k_style_overrides(
    project_id: str, query_vec: np.ndarray, k: int, db_path: str | None
) -> list[dict]:
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, description, embedding FROM style_overrides WHERE project_id = ?",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()

    scored = []
    for r in rows:
        vec = blob_to_array(r["embedding"])
        score = cosine_similarity(query_vec, vec)
        scored.append({"description": r["description"], "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


async def build(
    project_id: str,
    query: str,
    *,
    top_k: int = 3,
    db_path: str | None = None,
) -> dict | None:
    """Return a system-role ChatMessage with relevant rejections and style overrides."""
    query_vec = np.array(embed(query), dtype=np.float32)

    rejections = await _top_k_rejections(project_id, query_vec, top_k, db_path)
    style_overrides = await _top_k_style_overrides(project_id, query_vec, top_k, db_path)

    parts: list[str] = []
    if rejections:
        lines = [f'- "{r["prompt"]}" → reason: {r["reason"]}' for r in rejections]
        parts.append(
            "### Previously Rejected Directions\n\nAvoid the following:\n" + "\n".join(lines)
        )
    if style_overrides:
        lines = [f"- {s['description']}" for s in style_overrides]
        parts.append("### Pinned Style Overrides\n\nAlways apply:\n" + "\n".join(lines))

    if not parts:
        return None

    return {"role": "system", "content": "## Retrieval Memory\n\n" + "\n\n".join(parts)}
