"""dsl_compiler node — promotes approved SubjectPlaceholders to PlaneCards.

Runs after physical_validation passes. For every SubjectPlaceholder that has
an asset_ref (set by visual_generator), it creates a PlaneCard in scene.objects
positioned and scaled to match the placeholder's AABB. This is what build_glb()
reads when assembling the final .glb.
"""

from __future__ import annotations

from orchestrator.node_logger import node_step
from orchestrator.schemas.dsl import BlenderDsl, PlaneCard, Scene, Transform, Vec3
from orchestrator.state import AgentState


def _placeholder_to_plane_card(subject) -> PlaneCard | None:
    """Convert a SubjectPlaceholder with an asset_ref into a PlaneCard."""
    if subject.asset_ref is None:
        return None

    mn, mx = subject.aabb_min, subject.aabb_max

    center = Vec3(
        x=(mn.x + mx.x) / 2,
        y=(mn.y + mx.y) / 2,
        z=(mn.z + mx.z) / 2,
    )
    # Use the X/Y extents of the AABB as the card's width/height.
    # Z scale is kept at 1.0 since a PlaneCard has no depth.
    scale = Vec3(
        x=max(mx.x - mn.x, 0.1),
        y=max(mx.y - mn.y, 0.1),
        z=1.0,
    )

    return PlaneCard(
        asset_id=subject.asset_ref,
        transform=Transform(
            position=center,
            rotation_euler=Vec3(x=0, y=0, z=0),
            scale=scale,
        ),
        use_depth_map=True,
    )


def dsl_compiler_node(state: AgentState) -> dict:
    """Promote SubjectPlaceholders with asset_refs to PlaneCards in scene.objects."""
    assert state.scene_graph is not None, "dsl_compiler requires a scene_graph"

    scene = state.scene_graph.scene

    with node_step("dsl_compiler", subjects=len(scene.subjects)) as out:
        new_plane_cards: list[PlaneCard] = []
        promoted = 0
        skipped = 0

        for subject in scene.subjects:
            card = _placeholder_to_plane_card(subject)
            if card is not None:
                new_plane_cards.append(card)
                promoted += 1
            else:
                skipped += 1

        # Merge newly created PlaneCards with any existing scene objects
        updated_objects = list(scene.objects) + new_plane_cards

        updated_scene = scene.model_copy(update={"objects": updated_objects})
        updated_dsl = state.scene_graph.model_copy(update={"scene": updated_scene})

        out.update(promoted=promoted, skipped=skipped, status="dsl_compiled")

        return {
            "scene_graph": updated_dsl,
            "execution_status": "dsl_compiled",
        }
