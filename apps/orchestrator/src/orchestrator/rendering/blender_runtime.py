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
    "wood":    (0.78, 0.52, 0.25, 1.0),
    "metal":   (0.65, 0.67, 0.70, 1.0),
    "plastic": (0.30, 0.55, 0.75, 1.0),
    "fabric":  (0.45, 0.30, 0.18, 1.0),
    "glass":   (0.70, 0.85, 0.90, 1.0),
    "stone":   (0.55, 0.52, 0.48, 1.0),
    "default": (0.33, 0.36, 0.48, 1.0),
}
_mat_cache = {}

def hex_to_rgba(hex_str):
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b, 1.0)

def _set_mat_color(mat, rgba):
    """Set base color via BSDF node (Blender 4.x) with diffuse_color fallback (3.x)."""
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs[0].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.75
    mat.diffuse_color = rgba  # 3.x fallback

def get_material(hint, color_hex=None):
    key = color_hex if color_hex else hint
    if key not in _mat_cache:
        rgba = hex_to_rgba(color_hex) if color_hex else MATERIAL_COLORS.get(hint, MATERIAL_COLORS["default"])
        mat = bpy.data.materials.new(name=f"mat_{key[:16]}")
        _set_mat_color(mat, rgba)
        _mat_cache[key] = mat
    return _mat_cache[key]

def apply_gradient_vertex_colors(obj, top_hex, bottom_hex):
    mesh = obj.data
    if not mesh.vertices:
        return
    zs = [v.co.z for v in mesh.vertices]
    min_z, max_z = min(zs), max(zs)
    z_range = max_z - min_z
    if z_range < 1e-6:
        return
    def parse(h):
        h = h.lstrip("#")
        return (int(h[0:2],16)/255.0, int(h[2:4],16)/255.0, int(h[4:6],16)/255.0)
    top_rgb = parse(top_hex)
    bot_rgb = parse(bottom_hex)
    # Blender 4.x+: use color_attributes; fallback to 3.x vertex_colors
    try:
        ca = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
        for i, loop in enumerate(mesh.loops):
            vz = mesh.vertices[loop.vertex_index].co.z
            t = (vz - min_z) / z_range
            ca.data[i].color = (
                top_rgb[0]*t + bot_rgb[0]*(1-t),
                top_rgb[1]*t + bot_rgb[1]*(1-t),
                top_rgb[2]*t + bot_rgb[2]*(1-t),
                1.0,
            )
        try:
            mesh.color_attributes.active_color = ca
        except Exception:
            pass
    except AttributeError:
        vc = mesh.vertex_colors.new(name="Col")
        for i, loop in enumerate(mesh.loops):
            vz = mesh.vertices[loop.vertex_index].co.z
            t = (vz - min_z) / z_range
            vc.data[i].color = (
                top_rgb[0]*t + bot_rgb[0]*(1-t),
                top_rgb[1]*t + bot_rgb[1]*(1-t),
                top_rgb[2]*t + bot_rgb[2]*(1-t),
                1.0,
            )
    # White Principled BSDF base so vertex color shows through in glTF
    mat = bpy.data.materials.new(name=f"mat_grad_{obj.name[:8]}")
    _set_mat_color(mat, (1.0, 1.0, 1.0, 1.0))
    obj.data.materials.clear()
    obj.data.materials.append(mat)

def _displace_mountain(obj, peak_h, base_r, roughness, freq):
    """Push a cone's side vertices radially + slightly vertically using fractal noise."""
    from mathutils import noise as _mn
    mesh = obj.data
    base_z = min(v.co.z for v in mesh.vertices)
    for v in mesh.vertices:
        if v.co.z - base_z < 1e-4:
            continue  # leave base ring planted on the ground
        nv = mathutils.Vector((v.co.x * freq, v.co.y * freq, v.co.z * freq))
        n = _mn.fractal(nv, 0.5, 2.0, 4)
        flat = mathutils.Vector((v.co.x, v.co.y, 0.0))
        if flat.length > 1e-6:
            radial = flat.normalized() * (n * base_r * roughness)
            v.co.x += radial.x
            v.co.y += radial.y
        v.co.z += n * peak_h * 0.08
    mesh.update()

def _displace_terrain(obj, peak_h, roughness, freq):
    """Multi-octave fractal displacement on Z for a subdivided plane."""
    from mathutils import noise as _mn
    mesh = obj.data
    for v in mesh.vertices:
        nv = mathutils.Vector((v.co.x * freq, v.co.y * freq, 0.0))
        n = _mn.fractal(nv, 0.55, 2.1, 5)
        v.co.z += n * peak_h * roughness
    mesh.update()

def build_primitive(p):
    kind = p.get("kind", "box")
    x, y, z = p["x"], p["y"], p["z"]
    w, d, h = max(p["width"], 0.01), max(p["depth"], 0.01), max(p["height"], 0.01)
    rx = math.radians(p.get("rot_x", 0))
    ry = math.radians(p.get("rot_y", 0))
    rz = math.radians(p.get("rot_z", 0))
    if kind == "cylinder":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        # Add horizontal ring loops for denser side topology
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "sphere":
        r = max(w, d, h) / 2
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, radius=r, location=(x, y, z))
        obj = bpy.context.active_object
    elif kind == "cone":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=r, radius2=0.0, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=2)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "mountain":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=r, radius2=0.0, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=6)
        bpy.ops.object.mode_set(mode="OBJECT")
        _displace_mountain(
            obj,
            peak_h=h,
            base_r=r,
            roughness=p.get("roughness") if p.get("roughness") is not None else 0.35,
            freq=p.get("noise_frequency") if p.get("noise_frequency") is not None else 3.0,
        )
    elif kind == "terrain":
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        subs = p.get("subdivisions") if p.get("subdivisions") is not None else 48
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        # subdivide takes number_cuts per existing edge; cap to a safe value
        bpy.ops.mesh.subdivide(number_cuts=max(1, min(subs, 64)))
        bpy.ops.object.mode_set(mode="OBJECT")
        _displace_terrain(
            obj,
            peak_h=h,
            roughness=p.get("roughness") if p.get("roughness") is not None else 0.6,
            freq=p.get("noise_frequency") if p.get("noise_frequency") is not None else 1.5,
        )
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
    color_hex = p.get("color_hex")
    grad_bottom = p.get("gradient_bottom_hex")
    mat_hint = p.get("material_hint", "default")
    if grad_bottom and color_hex:
        obj.data.materials.clear()
        obj.data.materials.append(get_material(mat_hint, color_hex))
        apply_gradient_vertex_colors(obj, color_hex, grad_bottom)
    else:
        obj.data.materials.clear()
        obj.data.materials.append(get_material(mat_hint, color_hex))
    return obj

def import_mesh_asset(m):
    """Import a glb mesh asset and place it. Returns the imported root object (or None)."""
    glb_path = m.get("glb_path")
    if not glb_path or not os.path.exists(glb_path):
        print(f"mesh_asset skipped: missing glb_path {glb_path!r}")
        return None
    pre = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=glb_path)
    except Exception as _e:
        print(f"gltf import failed for {glb_path}: {_e}")
        return None
    imported = [o for o in bpy.data.objects if o not in pre]
    if not imported:
        return []
    # Transform via the topmost parent so child meshes follow.
    root = next((o for o in imported if o.parent is None), imported[0])
    pos = m.get("position", [0.0, 0.0, 0.0])
    rot = m.get("rotation", [0.0, 0.0, 0.0])
    scl = m.get("scale", [1.0, 1.0, 1.0])
    root.location = (pos[0], pos[1], pos[2])
    root.rotation_euler = (math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2]))
    root.scale = (scl[0], scl[1], scl[2])
    return imported

def world_corners(objs):
    """World-space bound-box corners of every MESH object."""
    pts = []
    for obj in objs:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ mathutils.Vector(corner)
            pts.append((wc.x, wc.y, wc.z))
    return pts

primitives = data.get("primitives", [])
subjs      = data.get("subjects", [])
mesh_assets = data.get("mesh_assets", [])
all_corners = []
mesh_objects = []

# Mesh assets take precedence when present (Plan10 text→3D pipeline).
if mesh_assets:
    for ma in mesh_assets:
        mesh_objects.extend(import_mesh_asset(ma))
    # Derive bounds from the actual imported geometry (world space).
    bpy.context.view_layer.update()
    all_corners += world_corners(mesh_objects)
    if not all_corners:
        all_corners = [(-1.0, -1.0, 0.0), (1.0, 1.0, 1.0)]
elif primitives:
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
    if obj.type != "MESH" or obj.data is None:
        continue
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
    try:
        bpy.ops.export_scene.gltf(
            filepath=glb_path,
            use_selection=True,
            export_format="GLB",
            export_apply=True,
            export_colors=True,
        )
    except TypeError:
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
import bpy, json, math, os, sys, mathutils

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
    "wood":    (0.78, 0.52, 0.25, 1.0),
    "metal":   (0.65, 0.67, 0.70, 1.0),
    "plastic": (0.30, 0.55, 0.75, 1.0),
    "fabric":  (0.45, 0.30, 0.18, 1.0),
    "glass":   (0.70, 0.85, 0.90, 1.0),
    "stone":   (0.55, 0.52, 0.48, 1.0),
    "default": (0.33, 0.36, 0.48, 1.0),
}
_mat_cache = {}

def hex_to_rgba(hex_str):
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b, 1.0)

def _set_mat_color(mat, rgba):
    """Set base color via BSDF node (Blender 4.x) with diffuse_color fallback (3.x)."""
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs[0].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.75
    mat.diffuse_color = rgba  # 3.x fallback

def get_material(hint, color_hex=None):
    key = color_hex if color_hex else hint
    if key not in _mat_cache:
        rgba = hex_to_rgba(color_hex) if color_hex else MATERIAL_COLORS.get(hint, MATERIAL_COLORS["default"])
        mat = bpy.data.materials.new(name=f"mat_{key[:16]}")
        _set_mat_color(mat, rgba)
        _mat_cache[key] = mat
    return _mat_cache[key]

def apply_gradient_vertex_colors(obj, top_hex, bottom_hex):
    mesh = obj.data
    if not mesh.vertices:
        return
    zs = [v.co.z for v in mesh.vertices]
    min_z, max_z = min(zs), max(zs)
    z_range = max_z - min_z
    if z_range < 1e-6:
        return
    def parse(h):
        h = h.lstrip("#")
        return (int(h[0:2],16)/255.0, int(h[2:4],16)/255.0, int(h[4:6],16)/255.0)
    top_rgb = parse(top_hex)
    bot_rgb = parse(bottom_hex)
    try:
        ca = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
        for i, loop in enumerate(mesh.loops):
            vz = mesh.vertices[loop.vertex_index].co.z
            t = (vz - min_z) / z_range
            ca.data[i].color = (
                top_rgb[0]*t + bot_rgb[0]*(1-t),
                top_rgb[1]*t + bot_rgb[1]*(1-t),
                top_rgb[2]*t + bot_rgb[2]*(1-t),
                1.0,
            )
        try:
            mesh.color_attributes.active_color = ca
        except Exception:
            pass
    except AttributeError:
        vc = mesh.vertex_colors.new(name="Col")
        for i, loop in enumerate(mesh.loops):
            vz = mesh.vertices[loop.vertex_index].co.z
            t = (vz - min_z) / z_range
            vc.data[i].color = (
                top_rgb[0]*t + bot_rgb[0]*(1-t),
                top_rgb[1]*t + bot_rgb[1]*(1-t),
                top_rgb[2]*t + bot_rgb[2]*(1-t),
                1.0,
            )
    mat = bpy.data.materials.new(name=f"mat_grad_{obj.name[:8]}")
    _set_mat_color(mat, (1.0, 1.0, 1.0, 1.0))
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# ── Primitive builder ─────────────────────────────────────────────────────────
def _displace_mountain(obj, peak_h, base_r, roughness, freq):
    from mathutils import noise as _mn
    mesh = obj.data
    base_z = min(v.co.z for v in mesh.vertices)
    for v in mesh.vertices:
        if v.co.z - base_z < 1e-4:
            continue
        nv = mathutils.Vector((v.co.x * freq, v.co.y * freq, v.co.z * freq))
        n = _mn.fractal(nv, 0.5, 2.0, 4)
        flat = mathutils.Vector((v.co.x, v.co.y, 0.0))
        if flat.length > 1e-6:
            radial = flat.normalized() * (n * base_r * roughness)
            v.co.x += radial.x
            v.co.y += radial.y
        v.co.z += n * peak_h * 0.08
    mesh.update()

def _displace_terrain(obj, peak_h, roughness, freq):
    from mathutils import noise as _mn
    mesh = obj.data
    for v in mesh.vertices:
        nv = mathutils.Vector((v.co.x * freq, v.co.y * freq, 0.0))
        n = _mn.fractal(nv, 0.55, 2.1, 5)
        v.co.z += n * peak_h * roughness
    mesh.update()

def render_primitive(p):
    kind = p.get("kind", "box")
    x, y, z = p["x"], p["y"], p["z"]
    w, d, h = max(p["width"], 0.01), max(p["depth"], 0.01), max(p["height"], 0.01)
    rx = math.radians(p.get("rot_x", 0))
    ry = math.radians(p.get("rot_y", 0))
    rz = math.radians(p.get("rot_z", 0))

    if kind == "cylinder":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "sphere":
        r = max(w, d, h) / 2
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, radius=r, location=(x, y, z))
        obj = bpy.context.active_object
    elif kind == "cone":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=r, radius2=0.0, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=2)
        bpy.ops.object.mode_set(mode="OBJECT")
    elif kind == "mountain":
        r = max(w, d) / 2
        bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=r, radius2=0.0, depth=h, location=(x, y, z))
        obj = bpy.context.active_object
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=6)
        bpy.ops.object.mode_set(mode="OBJECT")
        _displace_mountain(
            obj,
            peak_h=h,
            base_r=r,
            roughness=p.get("roughness") if p.get("roughness") is not None else 0.35,
            freq=p.get("noise_frequency") if p.get("noise_frequency") is not None else 3.0,
        )
    elif kind == "terrain":
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        subs = p.get("subdivisions") if p.get("subdivisions") is not None else 48
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=max(1, min(subs, 64)))
        bpy.ops.object.mode_set(mode="OBJECT")
        _displace_terrain(
            obj,
            peak_h=h,
            roughness=p.get("roughness") if p.get("roughness") is not None else 0.6,
            freq=p.get("noise_frequency") if p.get("noise_frequency") is not None else 1.5,
        )
    else:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        obj = bpy.context.active_object
        obj.scale = (w, d, h)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=3)
        bpy.ops.object.mode_set(mode="OBJECT")

    obj.rotation_euler = (rx, ry, rz)
    obj.name = p.get("label", kind)
    color_hex = p.get("color_hex")
    grad_bottom = p.get("gradient_bottom_hex")
    mat_hint = p.get("material_hint", "default")
    if grad_bottom and color_hex:
        obj.data.materials.clear()
        obj.data.materials.append(get_material(mat_hint, color_hex))
        apply_gradient_vertex_colors(obj, color_hex, grad_bottom)
    else:
        obj.data.materials.clear()
        obj.data.materials.append(get_material(mat_hint, color_hex))
    return obj

def import_mesh_asset(m):
    glb_path = m.get("glb_path")
    if not glb_path or not os.path.exists(glb_path):
        print(f"mesh_asset skipped: missing glb_path {glb_path!r}")
        return None
    pre = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=glb_path)
    except Exception as _e:
        print(f"gltf import failed for {glb_path}: {_e}")
        return None
    imported = [o for o in bpy.data.objects if o not in pre]
    if not imported:
        return []
    root = next((o for o in imported if o.parent is None), imported[0])
    pos = m.get("position", [0.0, 0.0, 0.0])
    rot = m.get("rotation", [0.0, 0.0, 0.0])
    scl = m.get("scale", [1.0, 1.0, 1.0])
    root.location = (pos[0], pos[1], pos[2])
    root.rotation_euler = (math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2]))
    root.scale = (scl[0], scl[1], scl[2])
    return imported

def world_corners(objs):
    pts = []
    for obj in objs:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            wc = obj.matrix_world @ mathutils.Vector(corner)
            pts.append((wc.x, wc.y, wc.z))
    return pts

# ── Build scene from LLM primitives (or fall back to subject AABBs) ───────────
primitives = data.get("primitives", [])
subjs      = data.get("subjects", [])
mesh_assets = data.get("mesh_assets", [])
all_corners = []

if mesh_assets:
    imported_objs = []
    for ma in mesh_assets:
        imported_objs.extend(import_mesh_asset(ma))
    bpy.context.view_layer.update()
    all_corners += world_corners(imported_objs)
    if not all_corners:
        all_corners = [(-1.0, -1.0, 0.0), (1.0, 1.0, 1.0)]
elif primitives:
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
        mesh_assets: list[dict] | None = None,
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
            "mesh_assets": mesh_assets or [],
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
        mesh_assets: list[dict] | None = None,
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
            "mesh_assets": mesh_assets or [],
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
