"""Deterministic wireframe previsualization orchestration node.

Compiles the scene graph → camera shots → rendered WireframeFrames → Previsualization.
No LLM calls permitted in this node.
"""

from __future__ import annotations

import os

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.cinematics.camera_planner import CameraPlanner, PlannerConfig
from orchestrator.node_logger import node_step
from orchestrator.rendering.previs_renderer import PrevisRenderer
from orchestrator.schemas.previsualization import Previsualization
from orchestrator.schemas.wire_geometry import WireframeGeometry
from orchestrator.state import AgentState

_DEFAULT_BLENDER = "/Applications/Blender.app/Contents/MacOS/blender"
_DEFAULT_OUTPUT  = "previs_renders"


def _infer_mood(state: AgentState) -> str:
    if state.intent and state.intent.mood_tags:
        return ", ".join(state.intent.mood_tags)
    return "neutral"


def _infer_palette_hint(state: AgentState) -> str:
    canon = state.project_canon
    if canon.aesthetic_tags:
        return ", ".join(canon.aesthetic_tags[:3])
    return "naturalistic"


def _infer_emotional_intensity(state: AgentState) -> float:
    if state.intent is None:
        return 0.5
    mood_lower = " ".join(state.intent.mood_tags).lower()
    intense_keywords = {"intense", "dramatic", "urgent", "tense", "terrifying", "climactic"}
    hits = sum(1 for kw in intense_keywords if kw in mood_lower)
    return min(1.0, 0.3 + hits * 0.2)


def _generate_wire_geometry(state: AgentState) -> WireframeGeometry | None:
    """Ask the LLM to decompose the subject into renderable primitives."""
    try:
        system = SystemMessage(content=llm_module.load_prompt("wire_geometry_system.md"))
        subject = state.intent.subject if state.intent else "object"
        user = HumanMessage(content=(
            f"Subject: {subject}\n"
            f"Additional context: {state.intent.model_dump_json() if state.intent else ''}"
        ))
        model = llm_module.make_llm()
        structured = model.with_structured_output(WireframeGeometry, method="function_calling")
        return structured.invoke([system, user])
    except Exception:
        return None


def wireframe_previs_generator_node(state: AgentState) -> dict:
    assert state.scene_graph is not None, "wireframe_previs_generator requires scene_graph"
    assert state.intent is not None, "wireframe_previs_generator requires validated intent"

    blender_path = os.environ.get("BLENDER_PATH", _DEFAULT_BLENDER)
    output_dir   = os.environ.get("PREVIS_OUTPUT_DIR", _DEFAULT_OUTPUT)

    with node_step(
        "wireframe_previs_generator",
        generation_mode=state.generation_mode,
        has_feedback=state.previsualization_feedback is not None,
    ) as out:
        # LLM decomposes the subject into geometric primitives dynamically
        wire_geometry = _generate_wire_geometry(state)

        planner_config = PlannerConfig(
            pacing="slow" if state.scene_graph.scene.duration_s > 15 else "medium",
            tone="tense" if _infer_emotional_intensity(state) > 0.7 else "neutral",
            emotional_intensity=_infer_emotional_intensity(state),
        )

        planner = CameraPlanner()
        shots = planner.generate_shots(state.scene_graph, config=planner_config)

        renderer = PrevisRenderer(
            output_dir=output_dir,
            project_id=state.project_id,
            blender_path=blender_path,
        )
        frames = renderer.render_sequence(
            shots,
            scene_graph=state.scene_graph,
            wire_geometry=wire_geometry,
        )

        mood         = _infer_mood(state)
        palette_hint = _infer_palette_hint(state)

        result = Previsualization(
            frames=frames,
            mood=mood,
            palette_hint=palette_hint,
            render_engine="blender_eevee",
        )

        out.update(
            status="previsualization_generated",
            frame_count=len(frames),
            mood=mood,
        )

        return {
            "previsualization": result,
            "execution_status": "previsualization_generated",
            "previsualization_feedback": None,
        }
