"""creative_dispatcher node — walks BlenderDsl and emits CreativeIntents.

Pure Python, no I/O. Runs after scene_graph_generator and before visual_generator.
"""

from __future__ import annotations

import random

from orchestrator.schemas.creative import CreativeIntent
from orchestrator.state import AgentState, CreativeEvent


def creative_dispatcher_node(state: AgentState) -> dict:
    assert state.scene_graph is not None, "creative_dispatcher requires a scene_graph"

    locked_paths = {lock.path for lock in state.semantic_locks}
    intents: list[CreativeIntent] = []
    events: list[CreativeEvent] = []

    scene = state.scene_graph.scene
    rng = random.Random(hash(state.user_prompt))

    # Walk subjects
    for i, subject in enumerate(scene.subjects):
        target = f"scene.subjects[{i}]"
        if target in locked_paths and subject.asset_ref is not None:
            events.append(
                CreativeEvent(
                    kind="LockedAssetReused",
                    target_path=target,
                    asset_id=subject.asset_ref,
                    detail="locked subject skipped",
                )
            )
            continue

        intent = CreativeIntent(
            kind="generate_subject",
            target_path=target,
            parameters={
                "prompt": subject.description,
                "width": 1024,
                "height": 1024,
                "remove_background": True,
            },
            seed=rng.randint(0, 2**31),
            adapter_hint="replicate.sdxl",
        )
        intents.append(intent)
        events.append(
            CreativeEvent(
                kind="CreativeIntentDispatched",
                target_path=target,
                detail=f"generate_subject: {subject.description[:60]}",
            )
        )

    # Emit a background intent derived from the project canon
    bg_target = "scene.background"
    if bg_target not in locked_paths:
        bg_prompt = (
            state.project_canon.aesthetic_tags[0]
            if state.project_canon.aesthetic_tags
            else "cinematic background"
        )
        intents.append(
            CreativeIntent(
                kind="generate_background",
                target_path=bg_target,
                parameters={
                    "prompt": bg_prompt,
                    "width": 1920,
                    "height": 1080,
                    "style": "photorealistic",
                },
                seed=rng.randint(0, 2**31),
                adapter_hint="replicate.sdxl",
            )
        )
        events.append(
            CreativeEvent(
                kind="CreativeIntentDispatched",
                target_path=bg_target,
                detail=f"generate_background: {bg_prompt[:60]}",
            )
        )

    return {
        "creative_intents": intents,
        "creative_events": state.creative_events + events,
        "execution_status": "creative_dispatching",
    }
