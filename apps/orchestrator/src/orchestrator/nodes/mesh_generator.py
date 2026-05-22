"""mesh_generator node — turns CreativeIntents into MeshAssets.

Sister node to visual_generator. Walks the `CreativeIntent` list, dispatches
mesh-targeted intents to the right adapter based on `subject_class`:

- ``object``    → text_to_3d adapter (DALL-E + TripoSR or Shap-E)
- ``landscape`` → Poly Haven adapter; on miss, falls back to text_to_3d

The actual API-side wiring (HTTP, UAR persistence, budget) is supplied via
the `MeshAdapterProtocol` injected by the API layer — this keeps the
orchestrator package free of HTTP/SQLite concerns and mirrors the
visual_generator seam.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Protocol

from orchestrator.node_logger import node_step
from orchestrator.schemas.creative import CreativeIntent
from orchestrator.schemas.mesh_asset import MeshAsset
from orchestrator.state import AgentState, CreativeEvent

log = logging.getLogger(__name__)


class MeshAdapter(Protocol):
    """Async callable that resolves one mesh intent into a MeshAsset."""

    async def __call__(
        self, intent: CreativeIntent, *, project_id: str, subject_class: str
    ) -> MeshAsset | None: ...


def make_mesh_generator_node(adapter: MeshAdapter) -> Callable[[AgentState], Awaitable[dict]]:
    """Build the LangGraph node closure bound to a concrete adapter."""

    async def mesh_generator_node(state: AgentState) -> dict:
        with node_step(
            "mesh_generator",
            intents=len(state.creative_intents),
            subject_class=state.subject_class or "—",
        ) as out:
            assets: list[MeshAsset] = list(state.mesh_assets)
            events: list[CreativeEvent] = []
            failures = 0

            for intent in state.creative_intents:
                if intent.output_kind != "mesh" and intent.kind != "generate_mesh":
                    continue

                try:
                    asset = await adapter(
                        intent,
                        project_id=state.project_id,
                        subject_class=state.subject_class or "object",
                    )
                except Exception as exc:  # noqa: BLE001 — adapter contract: bubble as failure event
                    log.exception("mesh_generator adapter raised")
                    failures += 1
                    events.append(
                        CreativeEvent(
                            kind="LayerGenerationFailed",
                            target_path=intent.target_path,
                            detail=f"mesh_generator: {exc}",
                        )
                    )
                    continue

                if asset is None:
                    failures += 1
                    events.append(
                        CreativeEvent(
                            kind="LayerGenerationFailed",
                            target_path=intent.target_path,
                            detail="mesh_generator: adapter returned None",
                        )
                    )
                    continue

                assets.append(asset)
                events.append(
                    CreativeEvent(
                        kind="LayerGenerated",
                        target_path=intent.target_path,
                        asset_id=asset.asset_id,
                        detail=f"mesh_generated: {asset.source}",
                    )
                )

            status = "mesh_generated" if not failures else "mesh_generation_failed"
            out.update(
                meshes=len(assets) - len(state.mesh_assets),
                failures=failures,
                status=status,
            )

            return {
                "mesh_assets": assets,
                "creative_events": state.creative_events + events,
                "execution_status": status,
            }

    return mesh_generator_node
