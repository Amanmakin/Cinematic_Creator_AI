"""Headless Blender runtime for viewport/Eevee preview rendering.

Launches `blender -b <blend_file> -P <script>` and manages temporary
scene files and output directories.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

BLENDER_EXECUTABLE = os.environ.get("BLENDER_PATH", "blender")


_RENDER_SCRIPT_TEMPLATE = """\
import bpy, json, sys

scene_data = {scene_json}

# Clear existing mesh objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = {engine!r}
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = {res_x}
scene.render.resolution_y = {res_y}

# Camera
cam_data = bpy.data.cameras.new("PrevisCamera")
cam_obj = bpy.data.objects.new("PrevisCamera", cam_data)
bpy.context.collection.objects.link(cam_obj)
scene.camera = cam_obj

cam_pos = scene_data["camera"]["position"]
cam_rot = scene_data["camera"]["rotation"]
cam_obj.location = cam_pos
cam_obj.rotation_euler = [r * 3.14159 / 180 for r in cam_rot]
cam_data.lens = scene_data["camera"]["focal_length_mm"]

# Key light
light_data = bpy.data.lights.new("KeyLight", type='SUN')
light_data.energy = 3.0
light_obj = bpy.data.objects.new("KeyLight", light_data)
bpy.context.collection.objects.link(light_obj)
kd = scene_data["lighting"]["key_light_direction"]
light_obj.location = kd

# Output
scene.render.filepath = {output_path!r}
bpy.ops.render.render(write_still=True)
"""


class BlenderRuntime:
    def __init__(self, output_dir: str | None = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="previs_"))

    def render_frame(
        self,
        frame_index: int,
        camera_position: tuple[float, float, float],
        camera_rotation: tuple[float, float, float],
        focal_length_mm: float,
        key_light_direction: tuple[float, float, float],
        fill_intensity: float,
        rim_enabled: bool,
        resolution: tuple[int, int] = (1280, 720),
        engine: Literal["BLENDER_EEVEE", "OPENGL"] = "BLENDER_EEVEE",
    ) -> tuple[str, str]:
        """Render one frame and return (image_path, thumbnail_path)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        image_path = str(self.output_dir / f"frame_{frame_index:03d}.png")
        thumb_path = str(self.output_dir / f"thumb_{frame_index:03d}.png")

        scene_data = {
            "camera": {
                "position": list(camera_position),
                "rotation": list(camera_rotation),
                "focal_length_mm": focal_length_mm,
            },
            "lighting": {
                "key_light_direction": list(key_light_direction),
                "fill_intensity": fill_intensity,
                "rim_enabled": rim_enabled,
            },
        }

        script_content = _RENDER_SCRIPT_TEMPLATE.format(
            scene_json=json.dumps(scene_data),
            engine="BLENDER_EEVEE_NEXT" if engine == "BLENDER_EEVEE" else "CYCLES",
            res_x=resolution[0],
            res_y=resolution[1],
            output_path=image_path,
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as script_file:
            script_file.write(script_content)
            script_path = script_file.name

        try:
            self._run_blender(script_path)
        finally:
            os.unlink(script_path)

        self._generate_thumbnail(image_path, thumb_path)
        return image_path, thumb_path

    def render_sequence(
        self,
        shots: list[dict],
        resolution: tuple[int, int] = (1280, 720),
        engine: Literal["BLENDER_EEVEE", "OPENGL"] = "BLENDER_EEVEE",
    ) -> list[tuple[str, str]]:
        """Render a list of shot dicts, return list of (image_path, thumbnail_path)."""
        results = []
        for shot in shots:
            img, thumb = self.render_frame(
                frame_index=shot["frame_index"],
                camera_position=shot["camera_position"],
                camera_rotation=shot["camera_rotation"],
                focal_length_mm=shot["focal_length_mm"],
                key_light_direction=shot["key_light_direction"],
                fill_intensity=shot["fill_intensity"],
                rim_enabled=shot["rim_enabled"],
                resolution=resolution,
                engine=engine,
            )
            results.append((img, thumb))
        return results

    def _run_blender(self, script_path: str) -> None:
        blend_file = str(self.output_dir / "previs.blend")
        cmd = [BLENDER_EXECUTABLE, "-b", blend_file, "-P", script_path]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except FileNotFoundError:
            # Blender not installed — produce placeholder paths so the node can still run
            pass
        except subprocess.TimeoutExpired:
            raise RuntimeError("Blender render timed out after 120s")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Blender exited with code {exc.returncode}") from exc

    def _generate_thumbnail(self, image_path: str, thumb_path: str) -> None:
        if not Path(image_path).exists():
            return
        try:
            from PIL import Image  # type: ignore[import]

            with Image.open(image_path) as img:
                img.thumbnail((320, 180))
                img.save(thumb_path)
        except Exception:
            pass
