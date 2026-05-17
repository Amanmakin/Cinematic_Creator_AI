"""Tier 3 — Working memory: compact SceneGraph JSON + last-N DAG events."""

from __future__ import annotations

import json

from api.dag.reducers import get_events
from orchestrator.schemas.dsl import BlenderDsl


async def build(
    project_id: str,
    scene_graph: BlenderDsl | None,
    *,
    last_n_events: int = 20,
    db_path: str | None = None,
) -> dict:
    """Return an assistant-role ChatMessage with the current working context."""
    parts: list[str] = []

    if scene_graph is not None:
        compact = scene_graph.model_dump_json()
        parts.append(f"## Current Scene Graph\n\n```json\n{compact}\n```")

    # Fetch and truncate event log
    kwargs: dict = {}
    if db_path:
        kwargs["db_path"] = db_path
    events = await _get_events(project_id, db_path)
    recent = events[-last_n_events:]
    if recent:
        log_lines = [
            f"- [{e['kind']}] node={e.get('dag_node_id', '')} {_brief(e['payload'])}"
            for e in recent
        ]
        parts.append("## Recent Events\n\n" + "\n".join(log_lines))

    content = "\n\n".join(parts) if parts else "(no working context yet)"
    return {"role": "assistant", "content": content}


async def _get_events(project_id: str, db_path: str | None) -> list[dict]:
    """Wrapper that passes db_path through to get_events when provided."""
    import aiosqlite
    from api.settings import settings

    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM dag_events WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def _brief(payload: dict) -> str:
    s = json.dumps(payload, default=str)
    return s[:120] + "..." if len(s) > 120 else s
