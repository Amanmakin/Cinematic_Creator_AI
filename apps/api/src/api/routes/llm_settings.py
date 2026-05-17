"""Global LLM model/endpoint settings (not per-project)."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.settings import settings
from orchestrator import llm as llm_module

router = APIRouter()

_TABLE = "llm_settings"


class LLMConfig(BaseModel):
    provider: str = Field(
        default="openai",
        description="openai | ollama | custom",
    )
    model: str = Field(default="gpt-4o-mini")
    base_url: str = Field(
        default="",
        description="Leave empty for OpenAI. Set to e.g. http://localhost:11434/v1 for Ollama.",
    )


PRESETS: dict[str, LLMConfig] = {
    "openai_mini": LLMConfig(provider="openai", model="gpt-4o-mini", base_url=""),
    "openai_4o": LLMConfig(provider="openai", model="gpt-4o", base_url=""),
    "ollama_llama3": LLMConfig(
        provider="ollama", model="llama3", base_url="http://localhost:11434/v1"
    ),
    "ollama_mistral": LLMConfig(
        provider="ollama", model="mistral", base_url="http://localhost:11434/v1"
    ),
}


async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            provider TEXT NOT NULL,
            model    TEXT NOT NULL,
            base_url TEXT NOT NULL
        )
    """)
    await db.commit()


async def _fetch() -> LLMConfig | None:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT * FROM {_TABLE} WHERE id = 1") as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return LLMConfig(provider=row["provider"], model=row["model"], base_url=row["base_url"])


async def _upsert(cfg: LLMConfig) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await _ensure_table(db)
        await db.execute(
            f"""INSERT INTO {_TABLE} (id, provider, model, base_url) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    model    = excluded.model,
                    base_url = excluded.base_url""",
            (cfg.provider, cfg.model, cfg.base_url),
        )
        await db.commit()


def _apply(cfg: LLMConfig) -> None:
    llm_module.configure_llm(
        model=cfg.model,
        base_url=cfg.base_url or None,
    )


async def load_and_apply_saved() -> None:
    """Called at startup to restore persisted LLM config."""
    cfg = await _fetch()
    if cfg:
        _apply(cfg)


@router.get("/llm-settings", response_model=LLMConfig)
async def get_llm_settings() -> LLMConfig:
    cfg = await _fetch()
    return cfg or LLMConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


@router.patch("/llm-settings", response_model=LLMConfig)
async def update_llm_settings(body: LLMConfig) -> LLMConfig:
    await _upsert(body)
    _apply(body)
    return body


@router.get("/llm-settings/presets")
async def list_presets() -> dict:
    return {k: v.model_dump() for k, v in PRESETS.items()}
