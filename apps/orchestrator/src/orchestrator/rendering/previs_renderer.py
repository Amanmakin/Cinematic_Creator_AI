"""High-level previsualization renderer.

Wraps BlenderRuntime and maps PlannedShot objects to rendered WireframeFrames.
Returns URL paths (/previs/<project_id>/...) rather than filesystem paths so
the FastAPI static-file mount can serve them directly to the browser.
"""

from __future__ import annotations

from typing import Literal

from orchestrator.cinematics.camera_planner import PlannedShot
from orchestrator.rendering.blender_runtime import BlenderRuntime
from orchestrator.rendering.sheet_composer import compose_wireframe_sheet
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.schemas.mesh_asset import MeshAsset
from orchestrator.schemas.previsualization import CameraTransform, LightingInfo, WireframeFrame
from orchestrator.schemas.wire_geometry import WireframeGeometry


def _mesh_assets_to_dicts(assets: list[MeshAsset] | None) -> list[dict] | None:
    if not assets:
        return None
    out: list[dict] = []
    for m in assets:
        out.append({
            "asset_id":   m.asset_id,
            "glb_path":   m.glb_path,
            "position":   list(m.position),
            "rotation":   list(m.rotation),
            "scale":      list(m.scale),
            "target_path": m.target_path,
        })
    return out


def _primitives_from_geometry(geo: WireframeGeometry) -> list[dict]:
    return [
        {
            "kind":               p.kind,
            "label":              p.label,
            "x": p.x, "y": p.y, "z": p.z,
            "width":              p.width,
            "depth":              p.depth,
            "height":             p.height,
            "rot_x":              p.rot_x,
            "rot_y":              p.rot_y,
            "rot_z":              p.rot_z,
            "material_hint":      p.material_hint,
            "color_hex":          p.color_hex,
            "gradient_bottom_hex": p.gradient_bottom_hex,
            "roughness":          p.roughness,
            "noise_frequency":    p.noise_frequency,
            "subdivisions":       p.subdivisions,
        }
        for p in geo.primitives
    ]


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

    def render_frame(
        self,
        shot: PlannedShot,
        subjects: list[dict] | None = None,
        primitives: list[dict] | None = None,
        mesh_assets: list[dict] | None = None,
    ) -> WireframeFrame:
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
            primitives=primitives,
            mesh_assets=mesh_assets,
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
        wire_geometry: WireframeGeometry | None = None,
        mesh_assets: list[MeshAsset] | None = None,
    ) -> list[WireframeFrame]:
        subjects = _subjects_from_scene(scene_graph) if scene_graph else None
        primitives = _primitives_from_geometry(wire_geometry) if wire_geometry else None
        meshes = _mesh_assets_to_dicts(mesh_assets)
        return [
            self.render_frame(shot, subjects=subjects, primitives=primitives, mesh_assets=meshes)
            for shot in shots
        ]

    @property
    def output_dir(self):
        return self._runtime.output_dir

    def render_wireframe_sheet(
        self,
        scene_graph: BlenderDsl | None = None,
        wire_geometry: WireframeGeometry | None = None,
        subject_label: str = "Object",
        mesh_assets: list[MeshAsset] | None = None,
    ) -> tuple[str, str | None, str, str | None]:
        """Render a multi-view wireframe reference sheet.

        Returns (sheet_url, glb_url, sheet_fs_path, persp_fs_path) — glb_url is None when
        Blender export failed; persp_fs_path is the clean perspective view for img2img.
        """
        primitives = _primitives_from_geometry(wire_geometry) if wire_geometry else None
        subjects   = _subjects_from_scene(scene_graph) if scene_graph else None
        meshes     = _mesh_assets_to_dicts(mesh_assets)

        view_paths = self._runtime.render_sheet(
            primitives=primitives,
            subjects=subjects,
            resolution=(640, 480),
            mesh_assets=meshes,
        )
        stats           = view_paths.pop("stats", {})
        glb_fs_path     = view_paths.pop("wireframe_glb", None)
        persp_fs_path   = view_paths.get("persp")  # clean single perspective view for img2img

        sheet_filename = "wireframe_sheet.png"
        sheet_fs_path  = str(self._runtime.output_dir / sheet_filename)

        compose_wireframe_sheet(
            view_paths=view_paths,
            stats=stats,
            subject_label=subject_label,
            output_path=sheet_fs_path,
        )

        glb_url = self._url("wireframe.glb") if glb_fs_path else None
        return self._url(sheet_filename), glb_url, sheet_fs_path, persp_fs_path
