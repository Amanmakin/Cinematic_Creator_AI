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
_SHEET_RENDER_SCRIPT = '''
import bpy, json, math, sys, os, mathutils

data = json.loads(sys.argv[sys.argv.index("--") + 1])

# ── Clean slate ────────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col   = scene.collection

scene.render.engine                     = "BLENDER_WORKBENCH"
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_x, scene.render.resolution_y = data["resolution"]

world = bpy.data.worlds.new("PrevisWorld")
world.use_nodes = False
world.color = (0.05, 0.05, 0.08)
scene.world = world
shading = scene.display.shading
shading.background_type = "WORLD"
# Blender 5.x: WIREFRAME render mode produces blank images; use SOLID+FLAT instead
shading.type = "SOLID"
try:
    shading.light = "FLAT"
except (TypeError, AttributeError):
    pass
try:
    shading.color_type = "MATERIAL"
except (TypeError, AttributeError):
    pass
try:
    shading.show_object_outline = True
    shading.object_outline_color = (0.78, 0.80, 0.90)
except (TypeError, AttributeError):
    pass

MATERIAL_COLORS = {
    "wood":    (0.55, 0.35, 0.18, 1.0),
    "metal":   (0.65, 0.67, 0.70, 1.0),
    "plastic": (0.30, 0.55, 0.75, 1.0),
    "fabric":  (0.60, 0.45, 0.55, 1.0),
    "glass":   (0.70, 0.85, 0.90, 1.0),
    "stone":   (0.55, 0.52, 0.48, 1.0),
    "default": (0.33, 0.36, 0.48, 1.0),
}
_mat_cache = {}

def get_material(hint):
    if hint not in _mat_cache:
        rgba = MATERIAL_COLORS.get(hint, MATERIAL_COLORS["default"])
        mat = bpy.data.materials.new(name=f"mat_{hint}")
        mat.diffuse_color = rgba
        _mat_cache[hint] = mat
    return _mat_cache[hint]

def build_primitive(p):
    kind = p.get("kind", "box")
    x, y, z = p["x"], p["y"], p["z"]
    w, d, h = max(p["width"], 0.01), max(p["depth"], 0.01), max(p["height"], 0.01)
    rx = math.radians(p.get("rot_x", 0))
    ry = math.radians(p.get("rot_y", 0))
    rz = math.radians(p.get("rot_z", 0))
    if kind == "cylinder":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        # Add horizontal ring loops for denser side topology
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=2)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "sphere":
        r = max(w, d, h) / 2
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=r, location=(x, y, z))
        obj = bpy.context.active_object
    else:  # box
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        # Dense subdivision gives the characteristic topology grid look
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")
    obj.rotation_euler = (rx, ry, rz)
    obj.name = p.get("label", kind)
    mat_hint = p.get("material_hint", "default")
    obj.data.materials.clear()
    obj.data.materials.append(get_material(mat_hint))
    return obj

primitives = data.get("primitives", [])
subjs      = data.get("subjects", [])
all_corners = []
mesh_objects = []

if primitives:
    for p in primitives:
        hw, hd, hh = p["width"]/2, p["depth"]/2, p["height"]/2
        all_corners += [(p["x"]-hw, p["y"]-hd, p["z"]-hh), (p["x"]+hw, p["y"]+hd, p["z"]+hh)]
    for p in primitives:
        mesh_objects.append(build_primitive(p))
elif subjs:
    for s in subjs:
        mn, mx = s["aabb_min"], s["aabb_max"]
        w  = max(abs(mx[0]-mn[0]), 0.05); d = max(abs(mx[1]-mn[1]), 0.05); h = max(abs(mx[2]-mn[2]), 0.05)
        cx = (mn[0]+mx[0])/2; cy = (mn[1]+mx[1])/2; cz = (mn[2]+mx[2])/2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")
        mesh_objects.append(obj)
        for dx in (mn[0], mx[0]):
            for dy in (mn[1], mx[1]):
                for dz in (mn[2], mx[2]):
                    all_corners.append((dx, dy, dz))
else:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
    obj = bpy.context.active_object
    obj.scale = (0.5, 0.5, 0.9)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=3)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh_objects.append(obj)
    all_corners = [(-0.25,-0.25,0),(0.25,0.25,0.9)]

# ── Mesh stats ─────────────────────────────────────────────────────────────
bpy.context.view_layer.update()
total_verts = total_edges = total_faces = total_tris = 0
for obj in mesh_objects:
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj  = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        total_verts += len(mesh.vertices)
        total_edges += len(mesh.edges)
        total_faces += len(mesh.polygons)
        total_tris  += sum(len(p.vertices) - 2 for p in mesh.polygons)
        eval_obj.to_mesh_clear()
    except Exception:
        m = obj.data
        total_verts += len(m.vertices)
        total_edges += len(m.edges)
        total_faces += len(m.polygons)

# ── Scene bounds ───────────────────────────────────────────────────────────
xs  = [v[0] for v in all_corners]; ys = [v[1] for v in all_corners]; zs = [v[2] for v in all_corners]
scx = (min(xs)+max(xs))/2;         scy = (min(ys)+max(ys))/2;        scz = (min(zs)+max(zs))/2
sw  = max(xs)-min(xs);             sd  = max(ys)-min(ys);             sh  = max(zs)-min(zs)
centroid     = mathutils.Vector((scx, scy, scz))
scene_radius = max(sw, sd, sh) / 2

# ── Camera helpers ─────────────────────────────────────────────────────────
def make_camera(name, pos, target, ortho=False, ortho_scale=1.0, focal=50):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = focal
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale
    cam_obj = bpy.data.objects.new(name, cam_data)
    col.objects.link(cam_obj)
    cam_obj.location = mathutils.Vector(pos)
    look = (mathutils.Vector(target) - mathutils.Vector(pos)).normalized()
    cam_obj.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    return cam_obj

def render_view(cam_obj, path):
    scene.camera = cam_obj
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

# ── Orthographic views ─────────────────────────────────────────────────────
dist       = max(scene_radius * 5, 3.0)
ort_scale  = max(sw, sd, sh) * 1.35
top_scale  = max(sw, sd) * 1.35
target     = (scx, scy, scz)
output_dir = data["output_dir"]

for vname, pos, is_ortho, ort_sc in [
    ("front", (scx, scy - dist, scz), True,  ort_scale),
    ("side",  (scx + dist, scy, scz), True,  ort_scale),
    ("back",  (scx, scy + dist, scz), True,  ort_scale),
    ("top",   (scx, scy, scz + dist), True,  top_scale),
]:
    cam = make_camera(vname, pos, target, ortho=is_ortho, ortho_scale=ort_sc)
    render_view(cam, os.path.join(output_dir, f"{vname}.png"))

# ── Perspective view ───────────────────────────────────────────────────────
fov_half = math.atan(36.0 / (2.0 * 50.0))
standoff = max(scene_radius / (math.tan(fov_half) * 0.42), scene_radius * 1.5, 0.3)
persp_dir = mathutils.Vector((0.7, -1.0, 0.6)).normalized()
persp_pos = centroid + persp_dir * standoff
cam = make_camera("persp", persp_pos, target, ortho=False, focal=50)
render_view(cam, os.path.join(output_dir, "persp.png"))

# ── Detail close-up views ──────────────────────────────────────────────────
def prim_center(ps):
    return (sum(p["x"] for p in ps)/len(ps), sum(p["y"] for p in ps)/len(ps), sum(p["z"] for p in ps)/len(ps))

def prim_radius(ps):
    return max(max(p["width"], p["depth"], p["height"]) for p in ps) * 1.5

detail_regions = []
if primitives:
    by_z   = sorted(primitives, key=lambda p: p["z"], reverse=True)
    n      = max(len(by_z), 1)
    top_g  = by_z[:max(1, n//3)]
    bot_g  = by_z[max(1, n*2//3):] or by_z[-1:]
    right_g = sorted(primitives, key=lambda p: p["x"], reverse=True)[:max(1, n//4)]
    seat_g  = [p for p in primitives if any(k in p.get("label","").lower() for k in ("seat","body","base"))]
    if not seat_g:
        seat_g = by_z[max(1,n//3):max(1,n*2//3)] or primitives[:1]

    for group in (top_g, bot_g, right_g, seat_g):
        if group:
            detail_regions.append((prim_center(group), prim_radius(group)))

# Fill to exactly 4 close-ups
fallbacks = [
    mathutils.Vector((scx + sw*0.3, scy - sd*0.3, scz + sh*0.5)),
    mathutils.Vector((scx - sw*0.3, scy - sd*0.3, scz + sh*0.2)),
    mathutils.Vector((scx + sw*0.3, scy + sd*0.3, scz + sh*0.1)),
    mathutils.Vector((scx,          scy,           scz + sh*0.7)),
]
while len(detail_regions) < 4:
    fb = fallbacks[len(detail_regions)]
    detail_regions.append(((fb.x, fb.y, fb.z), scene_radius * 0.4))

detail_dir = mathutils.Vector((0.6, -0.9, 0.5)).normalized()
for i, (center, radius) in enumerate(detail_regions[:4]):
    cv = mathutils.Vector(center)
    fov_h = math.atan(36.0 / (2.0 * 85.0))
    so = max(radius / (math.tan(fov_h) * 0.55), radius * 1.8, 0.05)
    pos = cv + detail_dir * so
    cam = make_camera(f"detail_{i}", pos, center, ortho=False, focal=85)
    render_view(cam, os.path.join(output_dir, f"detail_{i}.png"))

# ── Write stats JSON ───────────────────────────────────────────────────────
stats = {
    "vertices":         total_verts,
    "edges":            total_edges,
    "faces":            total_faces,
    "triangles":        total_tris,
    "primitive_labels": [p.get("label", f"prim_{i}") for i, p in enumerate(primitives)],
}
with open(os.path.join(output_dir, "stats.json"), "w") as f:
    json.dump(stats, f)

# ── glTF export ────────────────────────────────────────────────────────────
try:
    glb_path = os.path.join(output_dir, "wireframe.glb")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in mesh_objects:
        obj.select_set(True)
    if mesh_objects:
        bpy.context.view_layer.objects.active = mesh_objects[0]
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        use_selection=True,
        export_format="GLB",
        export_apply=True,
    )
except Exception as _e:
    print(f"glTF export failed: {_e}")
'''

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

world = bpy.data.worlds.new("PrevisWorld")
world.use_nodes = False
world.color = (0.05, 0.05, 0.08)
scene.world = world
shading = scene.display.shading
shading.background_type = "WORLD"
# Blender 5.x: WIREFRAME render mode produces blank images; use SOLID+FLAT instead
shading.type = "SOLID"
try:
    shading.light = "FLAT"
except (TypeError, AttributeError):
    pass
try:
    shading.color_type = "MATERIAL"
except (TypeError, AttributeError):
    pass
try:
    shading.show_object_outline = True
    shading.object_outline_color = (0.78, 0.80, 0.90)
except (TypeError, AttributeError):
    pass

MATERIAL_COLORS = {
    "wood":    (0.55, 0.35, 0.18, 1.0),
    "metal":   (0.65, 0.67, 0.70, 1.0),
    "plastic": (0.30, 0.55, 0.75, 1.0),
    "fabric":  (0.60, 0.45, 0.55, 1.0),
    "glass":   (0.70, 0.85, 0.90, 1.0),
    "stone":   (0.55, 0.52, 0.48, 1.0),
    "default": (0.33, 0.36, 0.48, 1.0),
}
_mat_cache = {}

def get_material(hint):
    if hint not in _mat_cache:
        rgba = MATERIAL_COLORS.get(hint, MATERIAL_COLORS["default"])
        mat = bpy.data.materials.new(name=f"mat_{hint}")
        mat.diffuse_color = rgba
        _mat_cache[hint] = mat
    return _mat_cache[hint]

# ── Primitive builder ─────────────────────────────────────────────────────────
def render_primitive(p):
    kind = p.get("kind", "box")
    x, y, z = p["x"], p["y"], p["z"]
    w, d, h = max(p["width"], 0.01), max(p["depth"], 0.01), max(p["height"], 0.01)
    rx = math.radians(p.get("rot_x", 0))
    ry = math.radians(p.get("rot_y", 0))
    rz = math.radians(p.get("rot_z", 0))

    if kind == "cylinder":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=2)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "sphere":
        r = max(w, d, h) / 2
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=r, location=(x, y, z))
        obj = bpy.context.active_object
    else:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")

    obj.rotation_euler = (rx, ry, rz)
    obj.name = p.get("label", kind)
    mat_hint = p.get("material_hint", "default")
    obj.data.materials.clear()
    obj.data.materials.append(get_material(mat_hint))
    return obj

# ── Build scene from LLM primitives (or fall back to subject AABBs) ───────────
primitives = data.get("primitives", [])
subjs      = data.get("subjects", [])
all_corners = []

if primitives:
    for p in primitives:
        hw, hd, hh = p["width"]/2, p["depth"]/2, p["height"]/2
        all_corners += [
            (p["x"]-hw, p["y"]-hd, p["z"]-hh),
            (p["x"]+hw, p["y"]+hd, p["z"]+hh),
        ]
    for p in primitives:
        render_primitive(p)

elif subjs:
    for subj in subjs:
        mn, mx = subj["aabb_min"], subj["aabb_max"]
        w  = max(abs(mx[0]-mn[0]), 0.05)
        d  = max(abs(mx[1]-mn[1]), 0.05)
        h  = max(abs(mx[2]-mn[2]), 0.05)
        cx = (mn[0]+mx[0])/2; cy = (mn[1]+mx[1])/2; cz = (mn[2]+mx[2])/2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")
        for dx in (mn[0], mx[0]):
            for dy in (mn[1], mx[1]):
                for dz in (mn[2], mx[2]):
                    all_corners.append((dx, dy, dz))

else:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
    obj = bpy.context.active_object
    obj.scale = (0.5, 0.5, 0.9)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=3)
    bpy.ops.object.mode_set(mode="OBJECT")
    all_corners = [(-0.5,-0.5,0),(0.5,0.5,0.9)]

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

# ── Camera: focal-length-aware framing so the subject fills the frame ────────
focal_mm    = data["camera"]["focal_length_mm"]
planned_pos = mathutils.Vector(data["camera"]["position"])

# Fill factors: subject radius fills this fraction of frame height.
# Higher values → camera closer → subject larger in frame.
fov_half = math.atan(36.0 / (2.0 * focal_mm))
if focal_mm <= 28:
    desired_fill = 0.50
elif focal_mm <= 40:
    desired_fill = 0.60
elif focal_mm <= 65:
    desired_fill = 0.70
else:
    desired_fill = 0.80

standoff = max(scene_radius / (math.tan(fov_half) * desired_fill), scene_radius * 1.1, 0.3)

# Use planned camera position as the view-angle hint.
view_dir = (planned_pos - centroid)
if view_dir.length < 0.1:
    view_dir = mathutils.Vector((0.6, -1.0, 0.5))
view_dir = view_dir.normalized()

# Only enforce a minimum horizontal offset when camera is nearly perfectly overhead
# (flat_len < 5% of total) to avoid a degenerate up-vector.  Do NOT enforce
# elevation — the camera planner intentionally uses overhead shots.
flat_len = mathutils.Vector((view_dir.x, view_dir.y, 0.0)).length
if flat_len < 0.05:
    view_dir = mathutils.Vector((0.6, -0.8, view_dir.z)).normalized()

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

    def render_sheet(
        self,
        primitives: list[dict] | None = None,
        subjects: list[dict] | None = None,
        resolution: tuple[int, int] = (640, 480),
    ) -> dict:
        """Render 9 views (4 ortho + perspective + 4 details) for the wireframe sheet.

        Returns a dict with keys: front, side, back, top, persp, detail_0..3, stats.
        Values are filesystem paths (or None if Blender is unavailable).
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "output_dir": str(self.output_dir),
            "resolution": list(resolution),
            "primitives": primitives or [],
            "subjects": subjects or [],
        }

        script_file = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w")
        try:
            script_file.write(_SHEET_RENDER_SCRIPT)
            script_file.flush()
            script_file.close()
            self._run_blender(script_file.name, json.dumps(payload))
        finally:
            os.unlink(script_file.name)

        stats: dict = {}
        stats_path = self.output_dir / "stats.json"
        if stats_path.exists():
            with open(stats_path) as f:
                stats = json.load(f)

        result: dict = {"stats": stats}
        for name in ("front", "side", "back", "top", "persp",
                      "detail_0", "detail_1", "detail_2", "detail_3"):
            p = self.output_dir / f"{name}.png"
            result[name] = str(p) if p.exists() else None
        glb = self.output_dir / "wireframe.glb"
        result["wireframe_glb"] = str(glb) if glb.exists() else None
        return result

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
