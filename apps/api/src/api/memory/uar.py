"""UAR embedding extension — adds an `embedding` BLOB column to the assets table.

Plan3 UARStore owns the assets table; this module adds the embedding column via a
migration and provides helpers to write/read embeddings alongside existing rows.
"""

from __future__ import annotations

import aiosqlite

from api.memory.embeddings import embed_to_blob
from api.settings import settings


async def migrate(db_path: str | None = None) -> None:
    """Add `embedding BLOB` to assets if it doesn't exist yet (idempotent)."""
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        # SQLite PRAGMA table_info returns rows; check for the column.
        async with db.execute("PRAGMA table_info(assets)") as cur:
            cols = {row[1] async for row in cur}
        if "embedding" not in cols:
            await db.execute("ALTER TABLE assets ADD COLUMN embedding BLOB")
            await db.commit()


async def set_embedding(asset_id: str, text: str, db_path: str | None = None) -> None:
    """Compute and persist an embedding for *asset_id*."""
    path = db_path or settings.db_path
    blob = embed_to_blob(text)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE assets SET embedding = ? WHERE id = ?", (blob, asset_id)
        )
        await db.commit()


async def get_embedding(asset_id: str, db_path: str | None = None) -> bytes | None:
    path = db_path or settings.db_path
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT embedding FROM assets WHERE id = ?", (asset_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None
