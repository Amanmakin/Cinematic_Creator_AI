"""arq task: summarise the last batch of DAG events into a CompressedChunk.

Scheduled automatically when the event count for a project crosses a multiple of
COMPRESS_EVERY.  The task is idempotent: it checks whether the latest event is
already covered by an existing chunk before calling the LLM.
"""

from __future__ import annotations

import json
import logging
import uuid

import aiosqlite
from langchain_core.messages import HumanMessage, SystemMessage

from api.memory.compressed import CompressedChunk, init_table, insert_chunk
from api.memory.embeddings import embed
from api.settings import settings

log = logging.getLogger(__name__)

COMPRESS_EVERY = 20  # new chunk after every N events


async def maybe_schedule_compression(project_id: str, ctx) -> None:
    """Enqueue compress_history if the project has hit a 20-event boundary.

    Call this from any place that appends a DAG event (e.g. record_event).
    *ctx* is an arq job context dict with a ``redis`` key.
    """
    count = await _event_count(project_id)
    if count > 0 and count % COMPRESS_EVERY == 0:
        await ctx["redis"].enqueue_job(
            "compress_history",
            project_id,
            _queue_name="arq:compress",
        )


async def compress_history(ctx: dict, project_id: str) -> None:
    """arq task — summarise the oldest uncovered event batch into a CompressedChunk."""
    await init_table()

    events = await _all_events(project_id)
    if not events:
        return

    # Find the last event already covered by a chunk.
    last_covered_id = await _last_covered_event_id(project_id)
    if last_covered_id:
        covered_ids = {e["id"] for e in events}
        try:
            start_idx = next(i for i, e in enumerate(events) if e["id"] == last_covered_id) + 1
        except StopIteration:
            start_idx = 0
    else:
        start_idx = 0

    batch = events[start_idx: start_idx + COMPRESS_EVERY]
    if not batch:
        return

    summary = await _summarise(batch)
    embedding = embed(summary)

    chunk = CompressedChunk(
        id=str(uuid.uuid4()),
        project_id=project_id,
        from_event_id=batch[0]["id"],
        to_event_id=batch[-1]["id"],
        summary=summary,
        embedding=embedding,
    )
    await insert_chunk(chunk)
    log.info("compress_history: wrote chunk %s for project %s (%d events)",
             chunk.id[:8], project_id, len(batch))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _event_count(project_id: str) -> int:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM dag_events WHERE project_id = ?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _all_events(project_id: str) -> list[dict]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM dag_events WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


async def _last_covered_event_id(project_id: str) -> str | None:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            """SELECT to_event_id FROM compressed_chunks
               WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def _summarise(events: list[dict]) -> str:
    from orchestrator import llm as llm_module

    lines = [
        f"- {e['kind']}: node={e.get('dag_node_id', 'n/a')} "
        f"payload={json.dumps(e['payload'], default=str)[:200]}"
        for e in events
    ]
    system = SystemMessage(content=(
        "You are a summariser for a cinematic video creation system. "
        "Summarise the following event log entries concisely (≤500 tokens). "
        "Focus on what changed, what was approved or rejected, and any errors."
    ))
    human = HumanMessage(content="\n".join(lines))
    llm = llm_module.make_llm(temperature=0.0)
    response = llm.invoke([system, human])
    return str(response.content)
