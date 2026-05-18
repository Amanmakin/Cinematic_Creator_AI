"""Per-project generation strategy settings and telemetry stats."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.dag.reducers import get_events
from api.persistence.projects_db import project_exists
from api.settings import settings

router = APIRouter()


class GenerationConfig(BaseModel):
    strategy: str = Field(
        default="local_fallback",
        description="local_only | local_fallback",
    )
    use_smaller_models: bool = Field(
        default=True,
        description="Use SD1.5 instead of SDXL locally (faster, lower quality)",
    )
    timeout_local_sec: int = Field(default=600, ge=10, le=600)


_VALID_STRATEGIES = {"local_only", "local_fallback"}

_DEFAULTS = GenerationConfig(
    strategy=settings.generation_strategy,
    use_smaller_models=settings.use_smaller_models_locally,
    timeout_local_sec=settings.generation_timeout_local,
)


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS generation_settings (
            project_id          TEXT PRIMARY KEY,
            strategy            TEXT NOT NULL,
            use_smaller_models  INTEGER NOT NULL,
            timeout_local_sec   INTEGER NOT NULL
        )
    """)
    await db.commit()


async def _fetch_config(project_id: str) -> GenerationConfig | None:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT project_id, strategy, use_smaller_models, timeout_local_sec FROM generation_settings WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return GenerationConfig(
        strategy=row["strategy"],
        use_smaller_models=bool(row["use_smaller_models"]),
        timeout_local_sec=row["timeout_local_sec"],
    )


async def _upsert_config(project_id: str, config: GenerationConfig) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        await db.execute(
            """INSERT INTO generation_settings
               (project_id, strategy, use_smaller_models, timeout_local_sec)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                   strategy = excluded.strategy,
                   use_smaller_models = excluded.use_smaller_models,
                   timeout_local_sec = excluded.timeout_local_sec""",
            (
                project_id,
                config.strategy,
                int(config.use_smaller_models),
                config.timeout_local_sec,
            ),
        )
        await db.commit()


@router.get("/{project_id}/generation-settings", response_model=GenerationConfig)
async def get_generation_settings(project_id: str) -> GenerationConfig:
    """Return the generation strategy for this project (falls back to global defaults)."""
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    config = await _fetch_config(project_id)
    return config or _DEFAULTS


@router.patch("/{project_id}/generation-settings", response_model=GenerationConfig)
async def update_generation_settings(
    project_id: str,
    body: GenerationConfig,
) -> GenerationConfig:
    """Update the generation strategy for this project. Takes effect immediately."""
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if body.strategy not in _VALID_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid strategy. Choose from {sorted(_VALID_STRATEGIES)}",
        )
    await _upsert_config(project_id, body)
    return body


class GenerationStats(BaseModel):
    total_generations: int
    local_count: int
    fallback_count: int
    total_cost_usd: float
    local_avg_time_sec: float | None


@router.get("/{project_id}/generation-stats", response_model=GenerationStats)
async def get_generation_stats(project_id: str) -> GenerationStats:
    """Return cost/time breakdown for local generation on this project."""
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    events = await get_events(project_id, kind="AssetGenerated")

    local_times: list[float] = []
    total_cost = 0.0
    fallback_count = 0

    for ev in events:
        p = ev["payload"]
        t = p.get("inference_time_sec", 0.0)
        total_cost += p.get("cost_usd", 0.0)
        if p.get("fallback_triggered"):
            fallback_count += 1
        local_times.append(t)

    def _avg(lst: list[float]) -> float | None:
        return round(sum(lst) / len(lst), 2) if lst else None

    return GenerationStats(
        total_generations=len(events),
        local_count=len(local_times),
        fallback_count=fallback_count,
        total_cost_usd=round(total_cost, 4),
        local_avg_time_sec=_avg(local_times),
    )
