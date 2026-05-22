"""mesh_dispatcher node — emits mesh-only CreativeIntents before wireframe previs.

Runs after scene_graph_generator. For `subject_class in {"object", "landscape"}`,
walks the scene's subjects and emits one `generate_mesh` intent per subject so
`mesh_generator` can produce real MeshAssets before the wireframe previs stage
renders them.

For `subject_class == "abstract"` (or unknown), this node is a no-op — the
abstract path stays on wire primitives + image generation.

Background image intents are still emitted later by `creative_dispatcher`,
which runs after the wireframe-approval interrupt.
"""

from __future__ import annotations

import random

from orchestrator.node_logger import node_step
from orchestrator.schemas.creative import CreativeIntent
from orchestrator.state import AgentState, CreativeEvent


def mesh_dispatcher_node(state: AgentState) -> dict:
    assert state.scene_graph is not None, "mesh_dispatcher requires a scene_graph"

    subj_class = state.subject_class or "object"
    use_mesh = subj_class in ("object", "landscape")

    with node_step(
        "mesh_dispatcher",
        subject_class=subj_class,
        emit_mesh=use_mesh,
    ) as out:
        if not use_mesh:
            out.update(intents_dispatched=0, status="creative_dispatching")
            return {"execution_status": "creative_dispatching"}

        scene = state.scene_graph.scene
        locked_paths = {lock.path for lock in state.semantic_locks}
        rng = random.Random(hash(state.user_prompt))

        intents: list[CreativeIntent] = list(state.creative_intents)
        events: list[CreativeEvent] = []

        for i, subject in enumerate(scene.subjects):
            target = f"scene.subjects[{i}]"
            if target in locked_paths and subject.asset_ref is not None:
                events.append(
                    CreativeEvent(
                        kind="LockedAssetReused",
                        target_path=target,
                        asset_id=subject.asset_ref,
                        detail="locked subject skipped (mesh)",
                    )
                )
                continue

            params: dict = {
                "prompt": subject.description,
                "subject_class": subj_class,
            }
            if state.sample_image_urls:
                params["reference_image_url"] = state.sample_image_urls[0]

            intents.append(
                CreativeIntent(
                    kind="generate_mesh",
                    target_path=target,
                    parameters=params,
                    seed=rng.randint(0, 2**31),
                    adapter_hint="text_to_3d",
                    output_kind="mesh",
                )
            )
            events.append(
                CreativeEvent(
                    kind="CreativeIntentDispatched",
                    target_path=target,
                    detail=f"generate_mesh ({subj_class}): {subject.description[:80]}",
                )
            )

        out.update(intents_dispatched=len(events), status="creative_dispatching")
        return {
            "creative_intents": intents,
            "creative_events": state.creative_events + events,
            "execution_status": "creative_dispatching",
        }
