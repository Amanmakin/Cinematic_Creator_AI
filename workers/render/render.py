"""Blender render script — ONLY file that imports bpy.

Usage (invoked by blender_runner.py):
    blender --background --python render.py -- <glb_path> <extras_json> <out_dir>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy  # type: ignore[import]  # only available inside Blender


def _parse_args() -> tuple[str, str, str]:
    argv = sys.argv
    try:
        sep = argv.index("--")
    except ValueError:
        raise SystemExit("Usage: blender --background --python render.py -- <glb> <extras> <out>")
    args = argv[sep + 1:]
    if len(args) < 3:
        raise SystemExit("Expected: <glb_path> <extras_json_path> <out_dir>")
    return args[0], args[1], args[2]


def _import_glb(glb_path: str) -> None:
    bpy.ops.import_scene.gltf(filepath=glb_path)


def _configure_camera(cam_info: dict) -> None:
    cam_data = bpy.data.cameras.new("CVC_Camera")
    cam_data.lens = cam_info["focal_mm"]
    cam_data.sensor_width = cam_info.get("sensor_mm", 36.0)
    cam_data.clip_start = cam_info.get("clip_start", 0.01)
    cam_data.clip_end = cam_info.get("clip_end", 1000.0)
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = cam_info.get("f_stop", 2.8)

    cam_obj = bpy.data.objects.new("CVC_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    pos = cam_info["position"]
    cam_obj.location = (pos[0], pos[1], pos[2])

    rot = cam_info.get("rotation_euler")
    look_at = cam_info.get("look_at")

    if rot:
        cam_obj.rotation_euler = (
            math.radians(rot[0]),
            math.radians(rot[1]),
            math.radians(rot[2]),
        )
    elif look_at:
        # Point camera toward look_at using track-to constraint
        constraint = cam_obj.constraints.new("TRACK_TO")
        target = bpy.data.objects.new("CVC_LookAt", None)
        target.location = (look_at[0], look_at[1], look_at[2])
        bpy.context.scene.collection.objects.link(target)
        constraint.target = target
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"


def _configure_lights(lights_info: list[dict]) -> None:
    for i, li in enumerate(lights_info):
        light_data = bpy.data.lights.new(f"CVC_Light_{i}", type="POINT")
        light_data.energy = li["intensity"]
        kelvin = li["color_kelvin"]
        r, g, b = _kelvin_to_rgb(kelvin)
        light_data.color = (r, g, b)

        light_obj = bpy.data.objects.new(f"CVC_Light_{i}", light_data)
        bpy.context.scene.collection.objects.link(light_obj)
        pos = li["position"]
        light_obj.location = (pos[0], pos[1], pos[2])


def _configure_world(world_info: dict) -> None:
    world = bpy.data.worlds.new("CVC_World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bc = world_info.get("background_color", [0.05, 0.05, 0.05])
    bg.inputs[0].default_value = (bc[0], bc[1], bc[2], 1.0)
    bpy.context.scene.world = world


def _setup_eevee(resolution: tuple[int, int] | None = None) -> None:
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    if resolution:
        bpy.context.scene.render.resolution_x = resolution[0]
        bpy.context.scene.render.resolution_y = resolution[1]
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.image_settings.color_mode = "RGBA"


def _kelvin_to_rgb(kelvin: int) -> tuple[float, float, float]:
    """Approximate conversion of color temperature to linear RGB."""
    t = kelvin / 100.0
    if t <= 66:
        r = 1.0
        g = max(0.0, min(1.0, (99.4708025861 * math.log(t) - 161.1195681661) / 255.0))
        if t <= 19:
            b = 0.0
        else:
            b = max(0.0, min(1.0, (138.5177312231 * math.log(t - 10) - 305.0447927307) / 255.0))
    else:
        r = max(0.0, min(1.0, (329.698727446 * (t - 60) ** -0.1332047592) / 255.0))
        g = max(0.0, min(1.0, (288.1221695283 * (t - 60) ** -0.0755148492) / 255.0))
        b = 1.0
    return r, g, b


def main() -> None:
    glb_path, extras_path, out_dir = _parse_args()
    extras = json.loads(Path(extras_path).read_text())

    # Clear default scene objects
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    _import_glb(glb_path)

    cam_info = extras.get("cvc_camera", {})
    if cam_info:
        _configure_camera(cam_info)

    lights_info = extras.get("cvc_lights", [])
    _configure_lights(lights_info)

    world_info = extras.get("cvc_world", {})
    _configure_world(world_info)

    _setup_eevee()

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    frame_path = str(out_path / "frame_0000.png")

    bpy.context.scene.render.filepath = frame_path
    bpy.context.scene.frame_set(0)

    print(f"CVC_FRAME:0:rendering to {frame_path}", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"CVC_FRAME:0:done", flush=True)


if __name__ == "__main__":
    main()
