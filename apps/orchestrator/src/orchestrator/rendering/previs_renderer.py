"""High-level previsualization renderer.

Wraps BlenderRuntime and maps PlannedShot objects to rendered WireframeFrames.
"""

from __future__ import annotations

from typing import Literal

from orchestrator.cinematics.camera_planner import PlannedShot
from orchestrator.rendering.blender_runtime import BlenderRuntime
from orchestrator.schemas.previsualization import CameraTransform, LightingInfo, WireframeFrame


class PrevisRenderer:
    def __init__(
        self,
        output_dir: str | None = None,
        resolution: tuple[int, int] = (1280, 720),
        engine: Literal["blender_eevee", "opengl"] = "blender_eevee",
    ) -> None:
        self.resolution = resolution
        self.engine: Literal["blender_eevee", "opengl"] = engine
        self._runtime = BlenderRuntime(output_dir=output_dir)

    def render_frame(self, shot: PlannedShot) -> WireframeFrame:
        blender_engine = "BLENDER_EEVEE" if self.engine == "blender_eevee" else "OPENGL"
        image_path, thumb_path = self._runtime.render_frame(
            frame_index=shot.frame_index,
            camera_position=shot.position,
            camera_rotation=shot.rotation,
            focal_length_mm=shot.focal_length_mm,
            key_light_direction=shot.key_light_direction,
            fill_intensity=shot.fill_intensity,
            rim_enabled=shot.rim_enabled,
            resolution=self.resolution,
            engine=blender_engine,
        )
        return WireframeFrame(
            frame_index=shot.frame_index,
            time_start_s=shot.time_start_s,
            time_end_s=shot.time_end_s,
            camera=CameraTransform(
                position=shot.position,
                rotation=shot.rotation,
                focal_length_mm=shot.focal_length_mm,
            ),
            lighting=LightingInfo(
                key_light_direction=shot.key_light_direction,
                fill_intensity=shot.fill_intensity,
                rim_enabled=shot.rim_enabled,
            ),
            viewport_image_path=image_path,
            viewport_thumbnail_path=thumb_path,
            notes=shot.notes,
        )

    def render_sequence(self, shots: list[PlannedShot]) -> list[WireframeFrame]:
        return [self.render_frame(shot) for shot in shots]
