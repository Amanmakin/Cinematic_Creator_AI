"""Deterministic cinematic camera planner.

Derives shot list from scene graph metadata without any LLM call.
Same inputs always produce the same output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from orchestrator.schemas.dsl import BlenderDsl

ShotType = Literal["wide_establishing", "medium", "over_shoulder", "closeup", "aerial"]


@dataclass
class PlannedShot:
    frame_index: int
    shot_type: ShotType
    time_start_s: float
    time_end_s: float
    # Camera transform
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    focal_length_mm: float
    # Lighting
    key_light_direction: tuple[float, float, float]
    fill_intensity: float
    rim_enabled: bool
    notes: str | None = None


@dataclass
class PlannerConfig:
    pacing: Literal["slow", "medium", "fast"] = "medium"
    tone: Literal["tense", "neutral", "joyful", "sad"] = "neutral"
    emotional_intensity: float = 0.5  # 0.0 – 1.0


def _classify_environment_scale(scene: BlenderDsl) -> Literal["small", "medium", "large", "epic"]:
    duration = scene.scene.duration_s
    subject_count = len(scene.scene.subjects) + len(scene.scene.objects)
    if duration > 30 or subject_count > 8:
        return "epic"
    if duration > 10 or subject_count > 4:
        return "large"
    if subject_count > 1:
        return "medium"
    return "small"


def _detect_dialogue(scene: BlenderDsl) -> bool:
    descriptions = [s.description.lower() for s in scene.scene.subjects]
    keywords = {"talk", "speak", "convers", "dialogue", "say", "tell"}
    return any(any(kw in d for kw in keywords) for d in descriptions)


def _base_camera_from_dsl(scene: BlenderDsl) -> tuple[tuple[float, float, float], float]:
    cam = scene.scene.camera
    pos = (cam.position.x, cam.position.y, cam.position.z)
    return pos, cam.focal_mm


def _key_light_from_scene(scene: BlenderDsl) -> tuple[float, float, float]:
    key_lights = [l for l in scene.scene.lights if l.kind == "key"]
    if key_lights:
        kl = key_lights[0]
        return (kl.position.x, kl.position.y, kl.position.z)
    return (1.0, -1.0, 2.0)


def _shot_for_establishing(base_pos: tuple, base_focal: float, t_start: float, t_end: float, idx: int, key_dir: tuple) -> PlannedShot:
    bx, by, bz = base_pos
    return PlannedShot(
        frame_index=idx,
        shot_type="wide_establishing",
        time_start_s=t_start,
        time_end_s=t_end,
        position=(bx, by - 8.0, bz + 3.0),
        rotation=(15.0, 0.0, 0.0),
        focal_length_mm=24.0,
        key_light_direction=key_dir,
        fill_intensity=0.4,
        rim_enabled=False,
        notes="Wide establishing — environment scale is large/epic",
    )


def _shot_for_closeup(base_pos: tuple, base_focal: float, t_start: float, t_end: float, idx: int, key_dir: tuple) -> PlannedShot:
    bx, by, bz = base_pos
    return PlannedShot(
        frame_index=idx,
        shot_type="closeup",
        time_start_s=t_start,
        time_end_s=t_end,
        position=(bx, by - 0.6, bz + 0.1),
        rotation=(0.0, 0.0, 0.0),
        focal_length_mm=85.0,
        key_light_direction=key_dir,
        fill_intensity=0.2,
        rim_enabled=True,
        notes="Close-up — high emotional intensity",
    )


def _shot_for_ots(base_pos: tuple, base_focal: float, t_start: float, t_end: float, idx: int, key_dir: tuple) -> PlannedShot:
    bx, by, bz = base_pos
    return PlannedShot(
        frame_index=idx,
        shot_type="over_shoulder",
        time_start_s=t_start,
        time_end_s=t_end,
        position=(bx + 0.4, by - 1.2, bz + 0.15),
        rotation=(5.0, 15.0, 0.0),
        focal_length_mm=50.0,
        key_light_direction=key_dir,
        fill_intensity=0.35,
        rim_enabled=True,
        notes="Over-the-shoulder — dialogue between subjects",
    )


def _shot_default(base_pos: tuple, base_focal: float, t_start: float, t_end: float, idx: int, key_dir: tuple) -> PlannedShot:
    return PlannedShot(
        frame_index=idx,
        shot_type="medium",
        time_start_s=t_start,
        time_end_s=t_end,
        position=base_pos,
        rotation=(0.0, 0.0, 0.0),
        focal_length_mm=base_focal,
        key_light_direction=key_dir,
        fill_intensity=0.3,
        rim_enabled=False,
    )


class CameraPlanner:
    def generate_shots(
        self,
        scene_graph: BlenderDsl,
        config: PlannerConfig | None = None,
    ) -> list[PlannedShot]:
        cfg = config or PlannerConfig()
        scene = scene_graph
        env_scale = _classify_environment_scale(scene)
        dialogue = _detect_dialogue(scene)
        base_pos, base_focal = _base_camera_from_dsl(scene)
        key_dir = _key_light_from_scene(scene)

        total_s = scene.scene.duration_s
        fps = scene.scene.fps

        shots: list[PlannedShot] = []

        # Opening shot
        if env_scale in ("large", "epic"):
            opening_end = min(total_s * 0.2, 3.0)
            shots.append(_shot_for_establishing(base_pos, base_focal, 0.0, opening_end, 0, key_dir))
        else:
            shots.append(_shot_default(base_pos, base_focal, 0.0, min(total_s * 0.3, 4.0), 0, key_dir))

        # Mid section
        if shots:
            mid_start = shots[-1].time_end_s
        else:
            mid_start = 0.0
        mid_end = total_s * 0.8

        if dialogue:
            shots.append(_shot_for_ots(base_pos, base_focal, mid_start, mid_end, len(shots), key_dir))
        elif cfg.emotional_intensity > 0.8:
            shots.append(_shot_for_closeup(base_pos, base_focal, mid_start, mid_end, len(shots), key_dir))
        else:
            shots.append(_shot_default(base_pos, base_focal, mid_start, mid_end, len(shots), key_dir))

        # Closing shot
        if shots:
            closing_start = shots[-1].time_end_s
        else:
            closing_start = total_s * 0.8
        if env_scale in ("large", "epic"):
            shots.append(_shot_for_establishing(base_pos, base_focal, closing_start, total_s, len(shots), key_dir))
        else:
            shots.append(_shot_default(base_pos, base_focal, closing_start, total_s, len(shots), key_dir))

        return shots
