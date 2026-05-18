"""Plan9 unit + integration tests.

Covers:
- GenerationMode parsing (D3)
- CameraPlanner determinism (D6)
- Routing functions: route_after_wireframe, route_after_model (D9)
- wireframe_previs_generator_node (D4) — with BlenderRuntime stubbed
- Integration flows: wireframe-only, model-only, full-video, escalations
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from conftest import make_valid_dsl
from orchestrator.cinematics.camera_planner import CameraPlanner, PlannerConfig
from orchestrator.graph import route_after_model, route_after_wireframe
from orchestrator.nodes.generation_mode_parser import (
    generation_mode_parser_node,
    parse_generation_mode,
)
from orchestrator.schemas.previsualization import (
    CameraTransform,
    LightingInfo,
    Previsualization,
    WireframeFrame,
)
from orchestrator.state import AgentState, GenerationMode


# ── helpers ────────────────────────────────────────────────────────────────

def _state(canon, user_prompt: str = "test", **kwargs) -> AgentState:
    return AgentState(user_prompt=user_prompt, project_canon=canon, **kwargs)


def _minimal_previs() -> Previsualization:
    frame = WireframeFrame(
        frame_index=0,
        time_start_s=0.0,
        time_end_s=3.0,
        camera=CameraTransform(position=(0.0, -3.0, 1.6), rotation=(0.0, 0.0, 0.0), focal_length_mm=50.0),
        lighting=LightingInfo(key_light_direction=(1.0, -1.0, 2.0), fill_intensity=0.3, rim_enabled=False),
        viewport_image_path="/tmp/frame_000.png",
        viewport_thumbnail_path="/tmp/thumb_000.png",
    )
    return Previsualization(frames=[frame], mood="neutral", palette_hint="modern", render_engine="blender_eevee")


# ── D3 — generation mode parser ────────────────────────────────────────────

class TestParseGenerationMode:
    def test_wireframe_keyword(self):
        assert parse_generation_mode("give me a wireframe") == GenerationMode.wireframe

    def test_layout_keyword(self):
        assert parse_generation_mode("show layout only") == GenerationMode.wireframe

    def test_blocking_keyword(self):
        assert parse_generation_mode("blocking pass please") == GenerationMode.wireframe

    def test_previs_keyword(self):
        assert parse_generation_mode("quick previs check") == GenerationMode.wireframe

    def test_model_keyword(self):
        assert parse_generation_mode("generate model renders") == GenerationMode.model

    def test_render_keyword(self):
        assert parse_generation_mode("I need a 2d render") == GenerationMode.model

    def test_scene_keyword(self):
        assert parse_generation_mode("set the scene") == GenerationMode.model

    def test_default_video(self):
        assert parse_generation_mode("create a short cinematic clip") == GenerationMode.video

    def test_ambiguous_defaults_to_video(self):
        assert parse_generation_mode("") == GenerationMode.video

    def test_node_returns_mode(self, canon, low_ambiguity_intent):
        dsl = make_valid_dsl()
        state = _state(
            canon,
            user_prompt="wireframe layout please",
            intent=low_ambiguity_intent,
            scene_graph=dsl,
        )
        result = generation_mode_parser_node(state)
        assert result["generation_mode"] == GenerationMode.wireframe




# ── D6 — camera planner ────────────────────────────────────────────────────

class TestCameraPlanner:
    def test_generates_shots(self, valid_dsl):
        planner = CameraPlanner()
        shots = planner.generate_shots(valid_dsl)
        assert len(shots) >= 1

    def test_deterministic_output(self, valid_dsl):
        planner = CameraPlanner()
        shots_a = planner.generate_shots(valid_dsl)
        shots_b = planner.generate_shots(valid_dsl)
        assert len(shots_a) == len(shots_b)
        for a, b in zip(shots_a, shots_b):
            assert a.position == b.position
            assert a.focal_length_mm == b.focal_length_mm

    def test_closeup_for_high_intensity(self, valid_dsl):
        planner = CameraPlanner()
        cfg = PlannerConfig(emotional_intensity=0.95)
        shots = planner.generate_shots(valid_dsl, config=cfg)
        types = [s.shot_type for s in shots]
        assert "closeup" in types

    def test_all_frames_have_sequential_indices(self, valid_dsl):
        planner = CameraPlanner()
        shots = planner.generate_shots(valid_dsl)
        indices = [s.frame_index for s in shots]
        assert indices == list(range(len(shots)))

    def test_time_ranges_are_non_negative(self, valid_dsl):
        planner = CameraPlanner()
        shots = planner.generate_shots(valid_dsl)
        for shot in shots:
            assert shot.time_start_s >= 0
            assert shot.time_end_s >= shot.time_start_s


# ── D9 — route_after_wireframe ─────────────────────────────────────────────

class TestRouteAfterWireframe:
    def test_approved_non_wireframe_goes_to_dispatcher(self, canon):
        s = _state(
            canon,
            execution_status="previsualization_approved",
            generation_mode=GenerationMode.video,
        )
        assert route_after_wireframe(s) == "creative_dispatcher"

    def test_approved_wireframe_mode_ends(self, canon):
        from langgraph.graph import END

        s = _state(
            canon,
            execution_status="previsualization_approved",
            generation_mode=GenerationMode.wireframe,
        )
        assert route_after_wireframe(s) == END

    def test_feedback_loops_back(self, canon):
        s = _state(
            canon,
            execution_status="previsualization_feedback",
            generation_mode=GenerationMode.video,
        )
        assert route_after_wireframe(s) == "wireframe_previs_generator"

    def test_reject_rewinds_to_scene_graph(self, canon):
        s = _state(
            canon,
            execution_status="intent_validated",
            generation_mode=GenerationMode.video,
        )
        assert route_after_wireframe(s) == "scene_graph_generator"


# ── D9 — route_after_model ─────────────────────────────────────────────────

class TestRouteAfterModel:
    def test_approved_video_mode_goes_to_physical_validation(self, canon):
        s = _state(
            canon,
            execution_status="model_approved",
            generation_mode=GenerationMode.video,
        )
        assert route_after_model(s) == "physical_validation"

    def test_approved_model_mode_ends(self, canon):
        from langgraph.graph import END

        s = _state(
            canon,
            execution_status="model_approved",
            generation_mode=GenerationMode.model,
        )
        assert route_after_model(s) == END

    def test_model_feedback_loops_back(self, canon):
        s = _state(
            canon,
            execution_status="model_feedback",
            generation_mode=GenerationMode.video,
        )
        assert route_after_model(s) == "visual_generator"

    def test_model_reject_rewinds_to_wireframe(self, canon):
        s = _state(
            canon,
            execution_status="previsualization_approved",
            generation_mode=GenerationMode.video,
        )
        assert route_after_model(s) == "wireframe_previs_generator"


# ── D4 — wireframe_previs_generator_node (renderer stubbed) ───────────────

class TestWireframePrevisGeneratorNode:
    def _make_state(self, canon, low_ambiguity_intent):
        dsl = make_valid_dsl()
        return _state(
            canon,
            "cinematic clip",
            intent=low_ambiguity_intent,
            scene_graph=dsl,
            generation_mode=GenerationMode.video,
        )

    def test_node_returns_previsualization(self, canon, low_ambiguity_intent):
        from orchestrator.nodes.wireframe_previs_generator import wireframe_previs_generator_node

        state = self._make_state(canon, low_ambiguity_intent)

        fake_frame = WireframeFrame(
            frame_index=0,
            time_start_s=0.0,
            time_end_s=3.0,
            camera=CameraTransform(position=(0.0, -3.0, 1.6), rotation=(0.0, 0.0, 0.0), focal_length_mm=50.0),
            lighting=LightingInfo(key_light_direction=(1.0, -1.0, 2.0), fill_intensity=0.3, rim_enabled=False),
            viewport_image_path="/tmp/f.png",
            viewport_thumbnail_path="/tmp/t.png",
        )

        mock_renderer = MagicMock()
        mock_renderer.render_sequence.return_value = [fake_frame]

        with patch("orchestrator.nodes.wireframe_previs_generator.PrevisRenderer", return_value=mock_renderer):
            result = wireframe_previs_generator_node(state)

        assert result["execution_status"] == "previsualization_generated"
        previs = result["previsualization"]
        assert isinstance(previs, Previsualization)
        assert len(previs.frames) == 1
        assert result["previsualization_feedback"] is None

    def test_node_clears_prior_feedback(self, canon, low_ambiguity_intent):
        from orchestrator.nodes.wireframe_previs_generator import wireframe_previs_generator_node

        state = self._make_state(canon, low_ambiguity_intent)
        state = state.model_copy(update={"previsualization_feedback": "camera too tight"})

        fake_frame = WireframeFrame(
            frame_index=0,
            time_start_s=0.0,
            time_end_s=3.0,
            camera=CameraTransform(position=(0.0, -3.0, 1.6), rotation=(0.0, 0.0, 0.0), focal_length_mm=50.0),
            lighting=LightingInfo(key_light_direction=(1.0, -1.0, 2.0), fill_intensity=0.3, rim_enabled=False),
            viewport_image_path="/tmp/f.png",
            viewport_thumbnail_path="/tmp/t.png",
        )
        mock_renderer = MagicMock()
        mock_renderer.render_sequence.return_value = [fake_frame]

        with patch("orchestrator.nodes.wireframe_previs_generator.PrevisRenderer", return_value=mock_renderer):
            result = wireframe_previs_generator_node(state)

        assert result["previsualization_feedback"] is None

    def test_node_requires_scene_graph(self, canon, low_ambiguity_intent):
        from orchestrator.nodes.wireframe_previs_generator import wireframe_previs_generator_node

        # Build a state then manually clear scene_graph to simulate missing scene
        dsl = make_valid_dsl()
        state = _state(canon, "x", intent=low_ambiguity_intent, scene_graph=dsl)
        state = state.model_copy(update={"scene_graph": None})
        with pytest.raises(AssertionError):
            wireframe_previs_generator_node(state)


# ── Integration: generation_mode_parser sets mode correctly ───────────────

class TestGenerationModeParserIntegration:
    def test_wireframe_only_flow_sets_wireframe_mode(self, canon, low_ambiguity_intent):
        dsl = make_valid_dsl()
        state = _state(canon, "I need wireframe blocking", intent=low_ambiguity_intent, scene_graph=dsl)
        result = generation_mode_parser_node(state)
        assert result["generation_mode"] == GenerationMode.wireframe

    def test_model_only_flow_sets_model_mode(self, canon, low_ambiguity_intent):
        dsl = make_valid_dsl()
        state = _state(canon, "generate 2d renders of the scene", intent=low_ambiguity_intent, scene_graph=dsl)
        result = generation_mode_parser_node(state)
        assert result["generation_mode"] == GenerationMode.model

    def test_video_flow_default(self, canon, low_ambiguity_intent):
        dsl = make_valid_dsl()
        state = _state(canon, "create a commercial video", intent=low_ambiguity_intent, scene_graph=dsl)
        result = generation_mode_parser_node(state)
        assert result["generation_mode"] == GenerationMode.video
