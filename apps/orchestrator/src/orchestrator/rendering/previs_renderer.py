"""High-level previsualization renderer.

Wraps BlenderRuntime and maps PlannedShot objects to rendered WireframeFrames.
Returns URL paths (/previs/<project_id>/...) rather than filesystem paths so
the FastAPI static-file mount can serve them directly to the browser.
"""

from __future__ import annotations

from typing import Literal

from orchestrator.cinematics.camera_planner import PlannedShot
from orchestrator.rendering.blender_runtime import BlenderRuntime
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.schemas.previsualization import CameraTransform, LightingInfo, WireframeFrame


def _subjects_from_scene(scene_graph: BlenderDsl) -> list[dict]:
    out = []
    for s in scene_graph.scene.subjects:
        out.append({
            "aabb_min": [s.aabb_min.x, s.aabb_min.y, s.aabb_min.z],
            "aabb_max": [s.aabb_max.x, s.aabb_max.y, s.aabb_max.z],
            "description": s.description,
        })
    return out


class PrevisRenderer:
    def __init__(
        self,
        output_dir: str,
        project_id: str,
        url_prefix: str = "/previs",
        resolution: tuple[int, int] = (1280, 720),
        engine: Literal["blender_eevee", "opengl"] = "blender_eevee",
        blender_path: str = "/Applications/Blender.app/Contents/MacOS/blender",
    ) -> None:
        self.project_id = project_id
        self.url_prefix = url_prefix.rstrip("/")
        self.resolution = resolution
        self.engine = engine
        project_output_dir = f"{output_dir}/{project_id}"
        self._runtime = BlenderRuntime(output_dir=project_output_dir, blender_path=blender_path)

    def _url(self, filename: str) -> str:
        return f"{self.url_prefix}/{self.project_id}/{filename}"

    def render_frame(self, shot: PlannedShot, subjects: list[dict] | None = None) -> WireframeFrame:
        image_path, thumb_path = self._runtime.render_frame(
            frame_index=shot.frame_index,
            camera_position=shot.position,
            camera_rotation=shot.rotation,
            focal_length_mm=shot.focal_length_mm,
            key_light_direction=shot.key_light_direction,
            fill_intensity=shot.fill_intensity,
            rim_enabled=shot.rim_enabled,
            resolution=self.resolution,
            subjects=subjects,
        )
        # Store URL paths, not filesystem paths
        frame_filename = f"frame_{shot.frame_index:03d}.png"
        thumb_filename = f"thumb_{shot.frame_index:03d}.png"
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
            viewport_image_path=self._url(frame_filename),
            viewport_thumbnail_path=self._url(thumb_filename),
            notes=shot.notes,
        )

    def render_sequence(
        self,
        shots: list[PlannedShot],
        scene_graph: BlenderDsl | None = None,
    ) -> list[WireframeFrame]:
        subjects = _subjects_from_scene(scene_graph) if scene_graph else None
        return [self.render_frame(shot, subjects=subjects) for shot in shots]
