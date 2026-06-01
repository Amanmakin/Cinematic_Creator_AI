"""Factory that builds the visual_generator LangGraph node with injected dependencies."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable

from api.adapters.base import CreativeAdapter, ProviderUnavailable
from api.orchestrator.budget import BudgetExceeded, BudgetLedger
from api.settings import settings
from api.uar.store import UARStore
from orchestrator.schemas.creative import CreativeIntent, LayerAsset
from orchestrator.schemas.mesh_asset import MeshAsset
from orchestrator.state import AgentState, CreativeEvent

logger = logging.getLogger(__name__)

_DEFAULT_BLENDER = "/Applications/Blender.app/Contents/MacOS/blender"
_DEFAULT_PREVIS_OUTPUT = "previs_renders"


@dataclass
class SimpleProjectCtx:
    project_id: str
    uar_root: str


def make_visual_generator_node(
    adapter: CreativeAdapter,
    uar: UARStore,
    ledger: BudgetLedger,
) -> Callable[[AgentState], dict]:
    """Return a LangGraph node function closed over adapter, uar, and ledger."""

    async def _generate_one(
        intent: CreativeIntent,
        ctx: SimpleProjectCtx,
        locked_paths: set[str],
        events: list[CreativeEvent],
        assets: list[LayerAsset],
    ) -> None:
        payload = adapter.translate(intent, ctx)
        estimate = adapter.cost_estimate(payload)

        try:
            asset, was_cached = await ledger.spend(
                ctx.project_id,
                estimate,
                lambda: uar.get_or_create(intent, adapter, ctx, locked_paths),
            )
        except BudgetExceeded as exc:
            events.append(
                CreativeEvent(
                    kind="BudgetExceeded",
                    target_path=intent.target_path,
                    detail=str(exc),
                )
            )
            return
        except ProviderUnavailable as exc:
            events.append(
                CreativeEvent(
                    kind="LayerGenerationFailed",
                    target_path=intent.target_path,
                    detail=str(exc),
                )
            )
            return

        assets.append(asset)
        event_kind = "LockedAssetReused" if was_cached else "LayerGenerated"
        events.append(
            CreativeEvent(
                kind=event_kind,
                target_path=intent.target_path,
                asset_id=asset.id,
            )
        )

    def visual_generator_node(state: AgentState) -> dict:
        project_id = state.project_id
        ctx = SimpleProjectCtx(project_id=project_id, uar_root=settings.uar_root)

        locked_paths = {lock.path for lock in state.semantic_locks}
        new_events: list[CreativeEvent] = []
        new_assets: list[LayerAsset] = []

        has_budget_exceeded = False

        async def _run_all() -> None:
            await asyncio.gather(*(
                _generate_one(intent, ctx, locked_paths, new_events, new_assets)
                for intent in state.creative_intents
            ))

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

        if loop.is_running():
            # Inside an already-running loop (e.g., FastAPI). Use run_in_executor.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run_all())
                future.result()
        else:
            loop.run_until_complete(_run_all())

        has_budget_exceeded = any(e.kind == "BudgetExceeded" for e in new_events)
        status = "budget_exceeded" if has_budget_exceeded else "model_generated"

        # Rewrite DSL subject asset_refs
        scene_graph = state.scene_graph
        if scene_graph is not None:
            asset_by_target = {a.id: a for a in new_assets}
            event_target_map = {
                e.target_path: e.asset_id
                for e in new_events
                if e.asset_id is not None
            }
            updated_subjects = []
            for i, subj in enumerate(scene_graph.scene.subjects):
                target = f"scene.subjects[{i}]"
                aid = event_target_map.get(target)
                updated_subjects.append(subj.model_copy(update={"asset_ref": aid}))
            updated_scene = scene_graph.scene.model_copy(
                update={"subjects": updated_subjects}
            )
            scene_graph = scene_graph.model_copy(update={"scene": updated_scene})

        # Build API-accessible URLs for the generated images so the frontend
        # can display them in the model approval viewport.
        if has_budget_exceeded:
            model_render_urls = None
        else:
            bg_render_urls = [
                f"/projects/{project_id}/assets/{a.id}/rgba"
                for a in new_assets
            ]
            # Object/landscape subjects are produced as meshes (no 2-D layer of
            # their own), so the loop above only yields the background. Lead the
            # overlay with a shaded render of the hero mesh — with TripoSR's baked
            # vertex colors — so the model-approval view shows the actual textured
            # model rather than just the background layer.
            mesh_render_urls: list[str] = []
            if state.mesh_assets:
                try:
                    mesh_render_urls = _render_mesh_beauty(project_id, state.mesh_assets)
                except Exception as exc:  # noqa: BLE001 — never fail the node on a preview render
                    logger.warning("mesh beauty render failed: %s", exc)
            model_render_urls = mesh_render_urls + bg_render_urls

        return {
            "generated_assets": state.generated_assets + new_assets,
            "creative_events": state.creative_events + new_events,
            "scene_graph": scene_graph,
            "execution_status": status,
            "model_renders": model_render_urls,
        }

    return visual_generator_node


def _render_mesh_beauty(project_id: str, mesh_assets: list[MeshAsset]) -> list[str]:
    """Render a shaded beauty shot of the hero mesh(es) via Blender.

    Returns ``[url]`` (a ``/previs/...`` path the static mount serves) or ``[]``
    when there is no mesh or Blender is unavailable. Imported here to keep the
    orchestrator rendering dependency lazy.
    """
    from orchestrator.rendering.previs_renderer import PrevisRenderer

    blender_path = os.environ.get("BLENDER_PATH", _DEFAULT_BLENDER)
    output_dir = os.environ.get("PREVIS_OUTPUT_DIR", _DEFAULT_PREVIS_OUTPUT)
    renderer = PrevisRenderer(
        output_dir=output_dir,
        project_id=project_id,
        blender_path=blender_path,
    )
    url = renderer.render_model_beauty(mesh_assets)
    return [url] if url else []
