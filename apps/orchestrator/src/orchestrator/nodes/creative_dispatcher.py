"""creative_dispatcher node — walks BlenderDsl and emits CreativeIntents.

Pure Python, no I/O. Runs after scene_graph_generator and before visual_generator.
"""

from __future__ import annotations

import os
import random

from orchestrator.node_logger import node_step
from orchestrator.schemas.creative import CreativeIntent
from orchestrator.state import AgentState, CreativeEvent


def _lens_description(focal_mm: float) -> str:
    if focal_mm <= 28:
        return f"{focal_mm:.0f}mm ultra-wide angle lens"
    if focal_mm <= 40:
        return f"{focal_mm:.0f}mm wide angle lens"
    if focal_mm <= 65:
        return f"{focal_mm:.0f}mm normal lens"
    if focal_mm <= 100:
        return f"{focal_mm:.0f}mm portrait lens"
    return f"{focal_mm:.0f}mm telephoto lens"


def _wireframe_context(state: AgentState) -> tuple[str, str | None]:
    """Return (cinematic_context_string, wireframe_sheet_disk_path).

    Reads camera / lighting / mood from the approved previsualization and
    translates them into natural-language prompt terms.  Also returns the
    disk path of the wireframe sheet PNG so the adapter can use it for
    img2img conditioning.
    """
    if not state.previsualization:
        return "", None

    previs = state.previsualization

    parts: list[str] = []

    # Camera / lens
    if previs.frames:
        focal = previs.frames[0].camera.focal_length_mm
        parts.append(_lens_description(focal))
        lighting = previs.frames[0].lighting
        if lighting.rim_enabled:
            parts.append("rim lighting")
        if lighting.fill_intensity > 1.2:
            parts.append("bright fill lighting")
        elif lighting.fill_intensity < 0.4:
            parts.append("low fill, high contrast lighting")

    if previs.mood and previs.mood not in ("neutral", ""):
        parts.append(f"{previs.mood} mood")

    if previs.palette_hint and previs.palette_hint not in ("naturalistic", ""):
        parts.append(previs.palette_hint)

    context = ", ".join(parts)

    # Prefer the clean perspective view for img2img — single uncluttered wireframe
    # that resizes to 512×512 cleanly, unlike the multi-panel reference sheet.
    disk_path: str | None = None
    if previs.wireframe_persp_fs_path and os.path.exists(previs.wireframe_persp_fs_path):
        disk_path = previs.wireframe_persp_fs_path
    elif previs.wireframe_sheet_fs_path and os.path.exists(previs.wireframe_sheet_fs_path):
        disk_path = previs.wireframe_sheet_fs_path

    return context, disk_path


def creative_dispatcher_node(state: AgentState) -> dict:
    assert state.scene_graph is not None, "creative_dispatcher requires a scene_graph"

    scene = state.scene_graph.scene
    locked_paths = {lock.path for lock in state.semantic_locks}

    with node_step(
        "creative_dispatcher",
        subjects=len(scene.subjects),
        locked_paths=len(locked_paths),
    ) as out:
        intents: list[CreativeIntent] = []
        events: list[CreativeEvent] = []
        rng = random.Random(hash(state.user_prompt))

        wire_context, sheet_disk_path = _wireframe_context(state)

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

            # Enrich the prompt with wireframe camera/lighting context
            base_prompt = subject.description
            if wire_context:
                enhanced_prompt = f"{base_prompt}, {wire_context}, cinematic, photorealistic"
            else:
                enhanced_prompt = f"{base_prompt}, cinematic, photorealistic"

            params: dict = {
                "prompt": enhanced_prompt,
                "width": 512,
                "height": 512,
                "remove_background": True,
            }
            # Pass wireframe sheet for img2img conditioning when available
            if sheet_disk_path:
                params["wireframe_image_path"] = sheet_disk_path
            # Pass user-supplied reference images for style conditioning
            if state.sample_image_urls:
                params["reference_image_urls"] = list(state.sample_image_urls)

            intents.append(
                CreativeIntent(
                    kind="generate_subject",
                    target_path=target,
                    parameters=params,
                    seed=rng.randint(0, 2**31),
                    adapter_hint="local.sdxl",
                )
            )
            events.append(
                CreativeEvent(
                    kind="CreativeIntentDispatched",
                    target_path=target,
                    detail=f"generate_subject: {enhanced_prompt[:80]}",
                )
            )

        bg_target = "scene.background"
        if bg_target not in locked_paths:
            raw_bg = (
                state.project_canon.aesthetic_tags[0]
                if state.project_canon.aesthetic_tags
                else "cinematic background"
            )
            bg_prompt = f"{raw_bg}, {wire_context.strip(', ')}" if wire_context else raw_bg

            bg_params: dict = {
                "prompt": bg_prompt,
                "width": 512,
                "height": 512,
                "style": "photorealistic",
            }
            if sheet_disk_path:
                bg_params["wireframe_image_path"] = sheet_disk_path
            if state.sample_image_urls:
                bg_params["reference_image_urls"] = list(state.sample_image_urls)

            intents.append(
                CreativeIntent(
                    kind="generate_background",
                    target_path=bg_target,
                    parameters=bg_params,
                    seed=rng.randint(0, 2**31),
                    adapter_hint="local.sdxl",
                )
            )
            events.append(
                CreativeEvent(
                    kind="CreativeIntentDispatched",
                    target_path=bg_target,
                    detail=f"generate_background: {bg_prompt[:80]}",
                )
            )

        out.update(intents_dispatched=len(intents), status="creative_dispatching")
        return {
            "creative_intents": intents,
            "creative_events": state.creative_events + events,
            "execution_status": "creative_dispatching",
        }
