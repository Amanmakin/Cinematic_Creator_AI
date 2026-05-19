"""Factory that builds the gltf_assembler LangGraph node.

Converts the compiled BlenderDsl (with PlaneCards carrying asset_refs)
into a .glb file served by the API, then sets execution_status to
'gltf_assembled' so the frontend can load it in Three.js.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable

from orchestrator.state import AgentState

logger = logging.getLogger(__name__)


def make_gltf_assembler_node(
    uar_root: str,
    renders_root: str,
) -> Callable[[AgentState], dict]:
    """Return a LangGraph node that assembles the final .glb from DSL + UAR textures."""

    def gltf_assembler_node(state: AgentState) -> dict:
        from api.render.gltf_builder import build_glb
        from orchestrator.node_logger import node_step

        assert state.scene_graph is not None, "gltf_assembler requires a compiled scene_graph"

        project_id = state.project_id
        renders_dir = Path(renders_root) / project_id
        renders_dir.mkdir(parents=True, exist_ok=True)

        plane_cards = [
            obj for obj in state.scene_graph.scene.objects
            if getattr(obj, "kind", None) == "plane_card"
        ]

        with node_step(
            "gltf_assembler",
            plane_cards=len(plane_cards),
            uar_root=uar_root,
        ) as out:
            try:
                glb_path = build_glb(
                    dsl=state.scene_graph,
                    uar_root=uar_root,
                    out_dir=str(renders_dir),
                )

                # Copy to a stable, predictable path so the serving endpoint
                # can find it without knowing the scene hash.
                assembled_path = renders_dir / "assembled.glb"
                shutil.copy2(glb_path, assembled_path)

                glb_url = f"/projects/{project_id}/assembled.glb"
                out.update(status="gltf_assembled", glb_path=str(assembled_path))

                return {
                    "gltf_assembled_path": glb_url,
                    "execution_status": "gltf_assembled",
                }

            except Exception as exc:
                logger.error("gltf_assembler failed: %s", exc, exc_info=True)
                out.update(status="failed", error=str(exc))
                return {
                    "execution_status": "failed",
                    "error_log": state.error_log + [f"gltf_assembler: {exc}"],
                }

    return gltf_assembler_node
