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
import bpy, json, math, sys, mathutils

data = json.loads(sys.argv[sys.argv.index("--") + 1])

# ── Clean slate ──────────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col   = scene.collection

# ── Render settings ──────────────────────────────────────────────────────────
scene.render.engine                     = "BLENDER_WORKBENCH"
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_x, scene.render.resolution_y = data["resolution"]
scene.render.filepath                   = data["output_path"]

# Dark background via world color (most reliable in headless Workbench)
world = bpy.data.worlds.new("PrevisWorld")
world.use_nodes = False
world.color = (0.06, 0.06, 0.10)
scene.world = world
shading = scene.display.shading
shading.background_type  = "WORLD"
shading.light            = "STUDIO"
shading.color_type       = "MATERIAL"
shading.show_object_outline = True
shading.object_outline_color = (0.25, 0.60, 1.0)

# ── Primitive renderer ────────────────────────────────────────────────────────
GHOST_COLOR = (0.06, 0.14, 0.28, 1.0)
WIRE_COLOR  = (0.25, 0.65, 1.0, 1.0)

def _add_wireframe(obj, thickness):
    gm = bpy.data.materials.new(obj.name + "_g")
    gm.diffuse_color = GHOST_COLOR
    obj.data.materials.append(gm)
    wm = bpy.data.materials.new(obj.name + "_w")
    wm.diffuse_color = WIRE_COLOR
    obj.data.materials.append(wm)
    wf = obj.modifiers.new("WF", "WIREFRAME")
    wf.thickness = thickness
    wf.use_even_offset = True
    wf.use_relative_offset = False
    wf.material_offset = 1

def render_primitive(p, wt):
    kind = p.get("kind", "box")
    x, y, z = p["x"], p["y"], p["z"]
    w, d, h = max(p["width"], 0.01), max(p["depth"], 0.01), max(p["height"], 0.01)
    rx = math.radians(p.get("rot_x", 0))
    ry = math.radians(p.get("rot_y", 0))
    rz = math.radians(p.get("rot_z", 0))

    if kind == "cylinder":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        obj.rotation_euler = (rx, ry, rz)
    elif kind == "sphere":
        r = max(w, d, h) / 2
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=r, location=(x, y, z))
        obj = bpy.context.active_object
        obj.rotation_euler = (rx, ry, rz)
    else:  # box
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        obj.rotation_euler = (rx, ry, rz)

    obj.name = p.get("label", kind)
    _add_wireframe(obj, wt)
    return obj

# ── Build scene from LLM primitives (or fall back to subject AABBs) ───────────
primitives = data.get("primitives", [])
subjs      = data.get("subjects", [])
all_corners = []

if primitives:
    # Compute scene bounds from primitive extents
    for p in primitives:
        hw, hd, hh = p["width"]/2, p["depth"]/2, p["height"]/2
        all_corners += [
            (p["x"]-hw, p["y"]-hd, p["z"]-hh),
            (p["x"]+hw, p["y"]+hd, p["z"]+hh),
        ]
    # Wireframe tube thickness = 1.5% of scene diagonal
    xs = [c[0] for c in all_corners]; ys = [c[1] for c in all_corners]; zs = [c[2] for c in all_corners]
    diag = math.sqrt((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2 + (max(zs)-min(zs))**2)
    wt = max(diag * 0.015, 0.005)
    for p in primitives:
        render_primitive(p, wt)

elif subjs:
    # Fall back to AABB boxes when no primitives provided
    for subj in subjs:
        mn, mx = subj["aabb_min"], subj["aabb_max"]
        w  = max(abs(mx[0]-mn[0]), 0.05)
        d  = max(abs(mx[1]-mn[1]), 0.05)
        h  = max(abs(mx[2]-mn[2]), 0.05)
        cx = (mn[0]+mx[0])/2; cy = (mn[1]+mx[1])/2; cz = (mn[2]+mx[2])/2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        _add_wireframe(obj, max(min(w,d,h)*0.04, 0.01))
        for dx in (mn[0], mx[0]):
            for dy in (mn[1], mx[1]):
                for dz in (mn[2], mx[2]):
                    all_corners.append((dx, dy, dz))

else:
    # Nothing from the pipeline — show a generic box placeholder
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
    obj = bpy.context.active_object
    obj.scale = (0.5, 0.5, 0.9)
    _add_wireframe(obj, 0.02)
    all_corners = [(-0.25,-0.25,0),(0.25,0.25,0.9)]
    wf.material_offset = 1
    all_corners = [(-0.5,-0.5,0),(0.5,-0.5,0),(-0.5,0.5,0),(0.5,0.5,0),
                   (-0.5,-0.5,1),(0.5,-0.5,1),(-0.5,0.5,1),(0.5,0.5,1)]

# ── Ground plane ─────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"
gnd_mat = bpy.data.materials.new("GroundMat")
gnd_mat.diffuse_color = (0.08, 0.09, 0.12, 1.0)
ground.data.materials.append(gnd_mat)

# ── Compute scene bounds ──────────────────────────────────────────────────────
xs = [v[0] for v in all_corners]
ys = [v[1] for v in all_corners]
zs = [v[2] for v in all_corners]
centroid = mathutils.Vector((
    (min(xs) + max(xs)) / 2,
    (min(ys) + max(ys)) / 2,
    (min(zs) + max(zs)) / 2,
))
scene_radius = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)) / 2

# ── Camera: focal-length-aware framing so the subject always fills the frame ──
focal_mm    = data["camera"]["focal_length_mm"]
planned_pos = mathutils.Vector(data["camera"]["position"])

# Compute the standoff that makes scene_radius fill `desired_fill` of frame height.
# Wide lenses (establishing) show more environment; long lenses (close-up) fill more.
fov_half = math.atan(36.0 / (2.0 * focal_mm))   # half-FOV in radians
if focal_mm <= 28:
    desired_fill = 0.18   # ultra-wide: chair is small, lots of environment
elif focal_mm <= 40:
    desired_fill = 0.28   # wide: establishing shot
elif focal_mm <= 65:
    desired_fill = 0.42   # medium
else:
    desired_fill = 0.60   # telephoto / close-up

standoff = max(scene_radius / (math.tan(fov_half) * desired_fill), scene_radius * 1.5, 0.3)

# Viewing direction: use planned camera direction as the angle hint only.
view_dir = (planned_pos - centroid)
if view_dir.length < 0.1:
    view_dir = mathutils.Vector((0.6, -1.0, 0.5))
view_dir = view_dir.normalized()

# Enforce 3/4 view: rotate laterally 25° if camera is nearly straight-on
flat_xy = mathutils.Vector((view_dir.x, view_dir.y, 0.0))
if flat_xy.length > 0.01 and abs(view_dir.x) / flat_xy.length < 0.25:
    angle = math.radians(25)
    vx = view_dir.x * math.cos(angle) - view_dir.y * math.sin(angle)
    vy = view_dir.x * math.sin(angle) + view_dir.y * math.cos(angle)
    view_dir = mathutils.Vector((vx, vy, view_dir.z)).normalized()

# Enforce minimum 20° elevation so we look slightly down onto the subject
flat_len = mathutils.Vector((view_dir.x, view_dir.y, 0.0)).length
if flat_len > 0.01 and math.atan2(view_dir.z, flat_len) < math.radians(20):
    flat_n   = mathutils.Vector((view_dir.x, view_dir.y, 0.0)).normalized()
    view_dir = (flat_n * math.cos(math.radians(20)) +
                mathutils.Vector((0, 0, 1)) * math.sin(math.radians(20))).normalized()

cam_pos = centroid + view_dir * standoff

cam_data      = bpy.data.cameras.new("PrevisCamera")
cam_data.lens = focal_mm
cam_obj       = bpy.data.objects.new("PrevisCamera", cam_data)
col.objects.link(cam_obj)
scene.camera = cam_obj

cam_obj.location      = cam_pos
cam_obj.rotation_mode = "XYZ"
look = (centroid - cam_pos).normalized()
cam_obj.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()

# ── Key light for Workbench Studio shading ────────────────────────────────────
sun      = bpy.data.lights.new("Key", type="SUN")
sun.energy = 3.0
sun_obj  = bpy.data.objects.new("Key", sun)
col.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(50), 0, math.radians(45))

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
        primitives: list[dict] | None = None,
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
            "primitives": primitives or [],
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
