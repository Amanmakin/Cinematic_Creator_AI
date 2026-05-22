"""Factory that builds the mesh_generator LangGraph node with injected deps.

Mirrors `creative_dispatch.make_visual_generator_node` so the orchestrator
graph stays agnostic of HTTP / SQLite / OpenAI specifics.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Callable

from api.adapters.base import ProviderUnavailable
from api.adapters.poly_haven_adapter import PolyHavenAdapter
from api.adapters.text_to_3d_adapter import TextTo3DAdapter
from api.settings import settings
from api.uar.store import UARStore
from orchestrator.nodes.mesh_generator import make_mesh_generator_node
from orchestrator.schemas.creative import CreativeIntent
from orchestrator.schemas.mesh_asset import MeshAsset
from orchestrator.state import AgentState

logger = logging.getLogger(__name__)


def make_api_mesh_generator_node(
    *,
    uar: UARStore,
    text_to_3d: TextTo3DAdapter,
    poly_haven: PolyHavenAdapter,
) -> Callable[[AgentState], dict]:
    """Return a sync LangGraph node that drives the async mesh adapter."""

    async def _adapter(
        intent: CreativeIntent,
        *,
        project_id: str,
        subject_class: str,
    ) -> MeshAsset | None:
        # Re-use existing mesh for a locked target.
        if intent.target_path:
            existing = await uar.get_mesh_by_target(project_id, intent.target_path)
            if existing is not None:
                return existing

        prompt: str = intent.parameters.get("prompt") or ""
        if not prompt:
            return None

        # Landscape: Poly Haven first, fall back to text→3D on miss.
        if subject_class == "landscape":
            try:
                match = await poly_haven.resolve(prompt)
            except ProviderUnavailable as exc:
                logger.warning("PolyHaven resolve failed (%s); falling back to text_to_3d", exc)
                match = None
            if match is not None:
                with open(match.glb_path, "rb") as f:
                    glb_bytes = f.read()
                # Bounds unknown for prebuilt asset — approximate from a unit box;
                # downstream Blender import re-derives the true bounds.
                from orchestrator.schemas.mesh_asset import BBox3
                bounds = BBox3(min_x=-1, min_y=-1, min_z=0, max_x=1, max_y=1, max_z=2)
                return await uar.store_mesh(
                    project_id=project_id,
                    glb_bytes=glb_bytes,
                    bounds_m=bounds,
                    source="poly_haven",
                    target_path=intent.target_path,
                    adapter=poly_haven.name,
                    adapter_version=poly_haven.version,
                )

        # Object (or landscape fallback): text_to_3d.
        result = await text_to_3d.generate(prompt, seed=intent.seed)
        return await uar.store_mesh(
            project_id=project_id,
            glb_bytes=result.glb_bytes,
            bounds_m=result.bounds,
            source=result.source,  # type: ignore[arg-type]
            target_path=intent.target_path,
            adapter=text_to_3d.name,
            adapter_version=text_to_3d.version,
        )

    async_node = make_mesh_generator_node(_adapter)

    def mesh_generator_node(state: AgentState) -> dict:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, async_node(state))
                return fut.result()
        return loop.run_until_complete(async_node(state))

    return mesh_generator_node
