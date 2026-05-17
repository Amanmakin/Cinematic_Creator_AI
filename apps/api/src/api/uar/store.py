"""Universal Asset Registry — content-addressed, cache-first asset store."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import TYPE_CHECKING

import aiosqlite

from api.uar import paths as uar_paths
from orchestrator.schemas.creative import CreativeIntent, LayerAsset

if TYPE_CHECKING:
    from api.adapters.base import CreativeAdapter, ProjectCtx


def _prompt_hash(intent: CreativeIntent, adapter_version: str) -> str:
    canonical = json.dumps(
        {
            "kind": intent.kind,
            "target_path": intent.target_path,
            "parameters": intent.parameters,
            "seed": intent.seed,
        },
        sort_keys=True,
    )
    return hashlib.sha256((canonical + adapter_version).encode()).hexdigest()


async def _init_uar_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            paths_json TEXT NOT NULL,
            adapter TEXT NOT NULL,
            adapter_version TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            project_id TEXT NOT NULL,
            target_path TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_prompt_hash ON assets(prompt_hash)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_project_target ON assets(project_id, target_path)"
    )
    await db.commit()


class UARStore:
    def __init__(self, db_path: str, uar_root: str) -> None:
        self._db_path = db_path
        self._uar_root = uar_root

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await _init_uar_table(db)

    async def get_by_target(
        self, project_id: str, target_path: str
    ) -> LayerAsset | None:
        """Return the existing asset for a locked target path, if any."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM assets WHERE project_id = ? AND target_path = ? LIMIT 1",
                (project_id, target_path),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_asset(dict(row))

    async def get_by_id(self, asset_id: str) -> LayerAsset | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM assets WHERE id = ?", (asset_id,)
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_asset(dict(row))

    async def get_or_create(
        self,
        intent: CreativeIntent,
        adapter: "CreativeAdapter",
        ctx: "ProjectCtx",
        locked_paths: set[str],
    ) -> tuple[LayerAsset, bool]:
        """Return (asset, was_cached).

        If target_path is locked, always return the existing asset for that path.
        Otherwise check prompt_hash cache; generate if missing.
        """
        # Locked-layer shortcut
        if intent.target_path in locked_paths:
            existing = await self.get_by_target(ctx.project_id, intent.target_path)
            if existing is not None:
                return existing, True

        ph = _prompt_hash(intent, adapter.version)

        # Cache hit on prompt_hash
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM assets WHERE prompt_hash = ? LIMIT 1", (ph,)
            ) as cur:
                row = await cur.fetchone()
        if row is not None:
            return _row_to_asset(dict(row)), True

        # Cache miss — generate
        payload = adapter.translate(intent, ctx)
        asset_ref = await adapter.execute(payload)

        sha = asset_ref.asset_id
        uar_paths.ensure_asset_dir(self._uar_root, ctx.project_id, sha)

        r_path = uar_paths.rgba_path(self._uar_root, ctx.project_id, sha)
        a_path = uar_paths.alpha_mask_path(self._uar_root, ctx.project_id, sha)
        d_path = uar_paths.depth_map_path(self._uar_root, ctx.project_id, sha)

        # Write placeholder files atomically — real data would be downloaded from asset_ref URL
        _write_placeholder(r_path, b"RGBA_PLACEHOLDER")
        _write_placeholder(a_path, b"ALPHA_PLACEHOLDER")
        _write_placeholder(d_path, b"DEPTH_PLACEHOLDER")

        kind_map = {
            "generate_subject": "subject",
            "regenerate_layer": "subject",
            "generate_background": "background",
            "generate_foreground_fx": "fx",
        }
        layer_kind = kind_map.get(intent.kind, "subject")

        asset = LayerAsset(
            id=sha,
            kind=layer_kind,  # type: ignore[arg-type]
            rgba_path=r_path,
            alpha_mask_path=a_path,
            depth_map_path=d_path,
            bbox_px=(0, 0, 1024, 1024),
            adapter=adapter.name,
            adapter_version=adapter.version,
            created_at=time.time(),
        )

        paths_json = json.dumps(
            {"rgba": r_path, "alpha": a_path, "depth": d_path}
        )
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO assets
                   (id, kind, paths_json, adapter, adapter_version, prompt_hash, project_id, target_path, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    asset.id,
                    asset.kind,
                    paths_json,
                    asset.adapter,
                    asset.adapter_version,
                    ph,
                    ctx.project_id,
                    intent.target_path,
                    asset.created_at,
                ),
            )
            await db.commit()

        return asset, False


def _write_placeholder(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _row_to_asset(row: dict) -> LayerAsset:
    p = json.loads(row["paths_json"])
    return LayerAsset(
        id=row["id"],
        kind=row["kind"],  # type: ignore[arg-type]
        rgba_path=p["rgba"],
        alpha_mask_path=p["alpha"],
        depth_map_path=p["depth"],
        bbox_px=(0, 0, 1024, 1024),
        adapter=row["adapter"],
        adapter_version=row["adapter_version"],
        created_at=row["created_at"],
    )
