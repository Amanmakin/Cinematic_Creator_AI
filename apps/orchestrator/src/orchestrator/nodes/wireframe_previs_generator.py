"""Deterministic wireframe previsualization orchestration node.

Compiles the scene graph → camera shots → rendered WireframeFrames → Previsualization.
No LLM calls permitted in this node.
"""

from __future__ import annotations

import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

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


_MATERIAL_KEYWORDS: list[tuple[str, list[str]]] = [
    ("wood",    ["wood", "wooden", "timber", "oak", "pine", "walnut", "mahogany", "teak"]),
    ("metal",   ["metal", "steel", "iron", "alumin", "chrome", "brass", "copper"]),
    ("plastic", ["plastic", "polym", "acrylic", "resin", "pvc"]),
    ("fabric",  ["fabric", "cloth", "upholster", "velvet", "leather", "cushion"]),
    ("glass",   ["glass", "crystal", "transparent"]),
    ("stone",   ["stone", "rock", "marble", "granite", "concrete", "brick"]),
]


def _infer_material_from_subject(subject: str) -> str:
    low = subject.lower()
    for hint, keywords in _MATERIAL_KEYWORDS:
        if any(k in low for k in keywords):
            return hint
    return "default"


def _apply_material_hints(geo: WireframeGeometry, subject: str) -> WireframeGeometry:
    """Override material_hint on all primitives that the LLM left as 'default'."""
    if all(p.material_hint == "default" for p in geo.primitives):
        inferred = _infer_material_from_subject(subject)
        if inferred != "default":
            for p in geo.primitives:
                p.material_hint = inferred
    return geo


def _generate_wire_geometry(state: AgentState) -> WireframeGeometry | None:
    """Ask the LLM to decompose the subject into renderable primitives."""
    try:
        system = SystemMessage(content=llm_module.load_prompt("wire_geometry_system.md"))
        subject = state.intent.subject if state.intent else "object"
        feedback_section = (
            f"\nUser feedback on the previous wireframe (MUST be addressed): {state.previsualization_feedback}\n"
            if state.previsualization_feedback
            else ""
        )
        user = HumanMessage(content=(
            f"Subject: {subject}\n"
            f"Additional context: {state.intent.model_dump_json() if state.intent else ''}"
            f"{feedback_section}"
        ))
        model = llm_module.make_llm()
        structured = model.with_structured_output(WireframeGeometry, include_raw=True, method="function_calling")
        result = structured.invoke([system, user])
        geo: WireframeGeometry = result["parsed"]
        if geo is None:
            logger.warning("WireframeGeometry parsing_error: %s", result.get("parsing_error"))
            return None
        return geo
    except Exception as exc:
        logger.warning("_generate_wire_geometry failed: %s", exc)
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
        if wire_geometry and state.intent:
            wire_geometry = _apply_material_hints(wire_geometry, state.intent.subject)

        planner_config = PlannerConfig(
            pacing="slow" if state.scene_graph.scene.duration_s > 15 else "medium",
            tone="tense" if _infer_emotional_intensity(state) > 0.7 else "neutral",
            emotional_intensity=_infer_emotional_intensity(state),
        )

        planner = CameraPlanner()
        shots = planner.generate_shots(state.scene_graph, config=planner_config)

        subject_label = state.intent.subject if state.intent else "Object"

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

        sheet_url: str | None = None
        sheet_fs_path: str | None = None
        persp_fs_path: str | None = None
        glb_url: str | None = None
        try:
            sheet_url, glb_url, sheet_fs_path, persp_fs_path = renderer.render_wireframe_sheet(
                scene_graph=state.scene_graph,
                wire_geometry=wire_geometry,
                subject_label=subject_label,
            )
        except Exception as exc:
            logger.warning("render_wireframe_sheet failed: %s", exc)

        mood         = _infer_mood(state)
        palette_hint = _infer_palette_hint(state)

        result = Previsualization(
            frames=frames,
            mood=mood,
            palette_hint=palette_hint,
            render_engine="blender_eevee",
            wireframe_sheet_path=sheet_url,
            wireframe_sheet_fs_path=sheet_fs_path,
            wireframe_persp_fs_path=persp_fs_path,
            wireframe_glb_path=glb_url,
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
