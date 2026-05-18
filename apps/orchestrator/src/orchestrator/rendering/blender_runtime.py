"""Headless Blender runtime for wireframe previsualization rendering.

Launches `blender --background --python <script> -- <json>` and produces
PNG frames + thumbnails. No .blend file required — the scene is built
entirely from the JSON payload passed on the command line.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_MAC_BLENDER = "/Applications/Blender.app/Contents/MacOS/blender"

# Blender Python script — built once, written to a tempfile each call.
_RENDER_SCRIPT = '''
import bpy, json, math, sys

data = json.loads(sys.argv[sys.argv.index("--") + 1])

# ── Clean slate ──────────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col   = scene.collection

# ── Render settings ──────────────────────────────────────────────────────────
scene.render.engine                       = "BLENDER_WORKBENCH"
scene.render.image_settings.file_format   = "PNG"
scene.render.resolution_x, scene.render.resolution_y = data["resolution"]
scene.render.filepath                     = data["output_path"]

shading = scene.display.shading
shading.light                = "STUDIO"
shading.show_object_outline  = True
shading.show_shadows         = True

# ── Ground plane ─────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"
gm = bpy.data.materials.new("GroundMat")
gm.diffuse_color = (0.12, 0.12, 0.12, 1.0)
ground.data.materials.append(gm)

# ── Subject placeholder boxes ────────────────────────────────────────────────
for i, subj in enumerate(data.get("subjects", [])):
    mn = subj["aabb_min"]
    mx = subj["aabb_max"]
    cx = (mn[0] + mx[0]) / 2
    cy = (mn[1] + mx[1]) / 2
    cz = (mn[2] + mx[2]) / 2
    sx = max(abs(mx[0] - mn[0]), 0.1)
    sy = max(abs(mx[1] - mn[1]), 0.1)
    sz = max(abs(mx[2] - mn[2]), 0.1)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    obj = bpy.context.active_object
    obj.scale = (sx, sy, sz)
    obj.name  = f"Subject_{i}"

    wf = obj.modifiers.new("Wireframe", "WIREFRAME")
    wf.thickness = 0.015

    sm = bpy.data.materials.new(f"SubjectMat_{i}")
    sm.diffuse_color = (0.18, 0.45, 0.85, 1.0)
    obj.data.materials.append(sm)

# Default subject when none supplied (unit cube at origin)
if not data.get("subjects"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
    obj = bpy.context.active_object
    obj.name = "SubjectPlaceholder"
    wf = obj.modifiers.new("Wireframe", "WIREFRAME")
    wf.thickness = 0.015
    sm = bpy.data.materials.new("PlaceholderMat")
    sm.diffuse_color = (0.18, 0.45, 0.85, 1.0)
    obj.data.materials.append(sm)

# ── Camera ───────────────────────────────────────────────────────────────────
cam_data       = bpy.data.cameras.new("PrevisCamera")
cam_data.lens  = data["camera"]["focal_length_mm"]
cam_obj        = bpy.data.objects.new("PrevisCamera", cam_data)
col.objects.link(cam_obj)
scene.camera = cam_obj

cam_obj.location = data["camera"]["position"]
cam_obj.rotation_mode   = "XYZ"
cam_obj.rotation_euler  = [r * math.pi / 180 for r in data["camera"]["rotation"]]

# ── Lights ───────────────────────────────────────────────────────────────────
kd = data["lighting"]["key_light_direction"]
sun        = bpy.data.lights.new("KeyLight", type="SUN")
sun.energy = 3.0
sun_obj    = bpy.data.objects.new("KeyLight", sun)
col.objects.link(sun_obj)
sun_obj.location       = kd
sun_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

fi = data["lighting"]["fill_intensity"]
if fi > 0:
    fill        = bpy.data.lights.new("FillLight", type="AREA")
    fill.energy = fi * 120
    fill.size   = 6.0
    fill_obj    = bpy.data.objects.new("FillLight", fill)
    col.objects.link(fill_obj)
    fill_obj.location = (-4, -4, 5)

if data["lighting"]["rim_enabled"]:
    rim        = bpy.data.lights.new("RimLight", type="SPOT")
    rim.energy = 250
    rim_obj    = bpy.data.objects.new("RimLight", rim)
    col.objects.link(rim_obj)
    rim_obj.location       = (0, 5, 4)
    rim_obj.rotation_euler = (math.radians(-40), 0, 0)

# ── Render ───────────────────────────────────────────────────────────────────
bpy.ops.render.render(write_still=True)
'''


def _resolve_blender(blender_path: str) -> str:
    """Return a working Blender executable path or raise."""
    candidates = [blender_path, _MAC_BLENDER, "blender"]
    for c in candidates:
        if Path(c).is_file() or (c == "blender"):
            return c
    raise FileNotFoundError(
        f"Blender not found. Set BLENDER_PATH in .env (tried: {candidates})"
    )


class BlenderRuntime:
    def __init__(
        self,
        output_dir: str | None = None,
        blender_path: str = _MAC_BLENDER,
    ) -> None:
        self.output_dir  = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="previs_"))
        self.blender_path = blender_path

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
        subjects: list[dict] | None = None,
    ) -> tuple[str, str]:
        """Render one wireframe previs frame. Returns (image_path, thumbnail_path)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        image_path = str(self.output_dir / f"frame_{frame_index:03d}.png")
        thumb_path = str(self.output_dir / f"thumb_{frame_index:03d}.png")

        payload = {
            "output_path": image_path,
            "resolution":  list(resolution),
            "camera": {
                "position":       list(camera_position),
                "rotation":       list(camera_rotation),
                "focal_length_mm": focal_length_mm,
            },
            "lighting": {
                "key_light_direction": list(key_light_direction),
                "fill_intensity":      fill_intensity,
                "rim_enabled":         rim_enabled,
            },
            "subjects": subjects or [],
        }

        script_file = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w")
        try:
            script_file.write(_RENDER_SCRIPT)
            script_file.flush()
            script_file.close()
            self._run_blender(script_file.name, json.dumps(payload))
        finally:
            os.unlink(script_file.name)

        self._generate_thumbnail(image_path, thumb_path)
        return image_path, thumb_path

    def _run_blender(self, script_path: str, json_arg: str) -> None:
        try:
            exe = _resolve_blender(self.blender_path)
        except FileNotFoundError as exc:
            logger.warning("Blender unavailable — skipping render: %s", exc)
            return

        cmd = [exe, "--background", "--python", script_path, "--", json_arg]
        logger.debug("Blender cmd: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
            logger.debug("Blender stdout: %s", result.stdout[-2000:])
        except subprocess.TimeoutExpired:
            raise RuntimeError("Blender render timed out after 120 s")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Blender exited {exc.returncode}:\n{exc.stderr[-1000:]}"
            ) from exc

    def _generate_thumbnail(self, image_path: str, thumb_path: str) -> None:
        if not Path(image_path).exists():
            return
        try:
            from PIL import Image  # type: ignore[import]

            with Image.open(image_path) as img:
                img.thumbnail((320, 180))
                img.save(thumb_path)
        except Exception as exc:
            logger.debug("Thumbnail generation via PIL skipped (%s), copying full frame", exc)
            shutil.copy2(image_path, thumb_path)
