"""Assemble a .glb from a validated BlenderDsl + UAR textures."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pygltflib

from api.uar import paths as uar_paths
from orchestrator.schemas.dsl import BlenderDsl, PlaneCard

if TYPE_CHECKING:
    pass

_VENDOR_PREFIX = "cvc_"


def _canonical_json(dsl: BlenderDsl) -> str:
    return dsl.model_dump_json(exclude_none=True)


def scene_hash(dsl: BlenderDsl) -> str:
    return hashlib.sha256(_canonical_json(dsl).encode()).hexdigest()


def _load_rgba_bytes(path: str) -> bytes:
    p = Path(path)
    if p.exists() and p.stat().st_size > 0:
        return p.read_bytes()
    # Return a 1×1 transparent placeholder PNG if missing / placeholder
    return _make_1x1_transparent_png()


def _make_1x1_transparent_png() -> bytes:
    """Minimal 1×1 transparent RGBA PNG (67 bytes)."""
    import zlib
    def _pack(*args):
        return struct.pack(*args)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = _pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = _pack(">I", 13) + b"IHDR" + ihdr_data + _pack(">I", ihdr_crc)

    raw_data = b"\x00\xff\xff\xff\xff"
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = _pack(">I", len(compressed)) + b"IDAT" + compressed + _pack(">I", idat_crc)

    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = _pack(">I", 0) + b"IEND" + _pack(">I", iend_crc)
    return signature + ihdr + idat + iend


def _quad_geometry(
    position: tuple[float, float, float],
    scale: tuple[float, float, float],
) -> tuple[bytes, bytes, bytes]:
    """Return (positions_bytes, normals_bytes, uvs_bytes) for a unit quad."""
    px, py, pz = position
    sx, sy = scale[0], scale[1]
    half_x, half_y = sx / 2, sy / 2

    verts = np.array([
        [px - half_x, py - half_y, pz],
        [px + half_x, py - half_y, pz],
        [px + half_x, py + half_y, pz],
        [px - half_x, py + half_y, pz],
    ], dtype=np.float32)

    normals = np.tile([0.0, 0.0, 1.0], (4, 1)).astype(np.float32)

    uvs = np.array([
        [0.0, 1.0],
        [1.0, 1.0],
        [1.0, 0.0],
        [0.0, 0.0],
    ], dtype=np.float32)

    return verts.tobytes(), normals.tobytes(), uvs.tobytes()


def _depth_displaced_geometry(
    position: tuple[float, float, float],
    scale: tuple[float, float, float],
    depth_bytes: bytes,
    grid: int = 32,
) -> tuple[bytes, bytes, bytes]:
    """Sample depth map on a grid and displace vertices along +Z normal."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(depth_bytes)).convert("L").resize((grid, grid))
        depth_arr = np.array(img, dtype=np.float32) / 255.0
    except Exception:
        depth_arr = np.zeros((grid, grid), dtype=np.float32)

    px, py, pz = position
    sx, sy = scale[0], scale[1]

    rows, cols = grid, grid
    verts = []
    normals = []
    uvs = []
    for r in range(rows):
        for c in range(cols):
            u = c / (cols - 1)
            v = r / (rows - 1)
            x = px - sx / 2 + u * sx
            y = py - sy / 2 + v * sy
            z = pz + float(depth_arr[r, c]) * 0.1
            verts.append([x, y, z])
            normals.append([0.0, 0.0, 1.0])
            uvs.append([u, 1.0 - v])

    return (
        np.array(verts, dtype=np.float32).tobytes(),
        np.array(normals, dtype=np.float32).tobytes(),
        np.array(uvs, dtype=np.float32).tobytes(),
    )


def _quad_indices() -> bytes:
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint16)
    return indices.tobytes()


def _grid_indices(grid: int) -> bytes:
    rows, cols = grid, grid
    tris = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            i = r * cols + c
            tris += [i, i + 1, i + cols, i + 1, i + cols + 1, i + cols]
    return np.array(tris, dtype=np.uint32).tobytes()


def build_glb(dsl: BlenderDsl, uar_root: str, out_dir: str, project_id: str = "") -> str:
    """Assemble a .glb from BlenderDsl and UAR assets.

    Returns the path to the written .glb file.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    sha = scene_hash(dsl)
    glb_path = out_path / f"{sha}.glb"

    gltf = pygltflib.GLTF2()
    gltf.asset = pygltflib.Asset(version="2.0", generator="CinematicVideoCreator/Plan4")
    gltf.scene = 0
    gltf.scenes = [pygltflib.Scene(nodes=[])]

    scene = dsl.scene
    all_blobs: list[bytes] = []

    def _add_blob(data: bytes) -> tuple[int, int]:
        """Append data to blob list; return (byte_offset, byte_length)."""
        offset = sum(len(b) for b in all_blobs)
        all_blobs.append(data)
        return offset, len(data)

    for obj in scene.objects:
        if not isinstance(obj, PlaneCard):
            continue

        pos = obj.transform.position
        rot = obj.transform.rotation_euler
        scl = obj.transform.scale

        if project_id:
            rgba_path = uar_paths.rgba_path(uar_root, project_id, obj.asset_id)
            depth_path = uar_paths.depth_map_path(uar_root, project_id, obj.asset_id)
        else:
            rgba_path = str(Path(uar_root) / obj.asset_id / "rgba.png")
            depth_path = str(Path(uar_root) / obj.asset_id / "depth.png")

        rgba_bytes = _load_rgba_bytes(rgba_path)
        depth_bytes = _load_rgba_bytes(depth_path)

        grid = 32
        if obj.use_depth_map:
            pos_bytes, nrm_bytes, uv_bytes = _depth_displaced_geometry(
                (pos.x, pos.y, pos.z), (scl.x, scl.y, scl.z), depth_bytes, grid=grid
            )
            idx_bytes = _grid_indices(grid)
            n_verts = grid * grid
            idx_component = pygltflib.UNSIGNED_INT
            idx_count = (grid - 1) ** 2 * 6
        else:
            pos_bytes, nrm_bytes, uv_bytes = _quad_geometry(
                (pos.x, pos.y, pos.z), (scl.x, scl.y, scl.z)
            )
            idx_bytes = _quad_indices()
            n_verts = 4
            idx_component = pygltflib.UNSIGNED_SHORT
            idx_count = 6

        # Texture
        tex_blob_offset, tex_blob_len = _add_blob(rgba_bytes)
        tex_buf_view = len(gltf.bufferViews)
        gltf.bufferViews.append(pygltflib.BufferView(
            buffer=0, byteOffset=tex_blob_offset, byteLength=tex_blob_len
        ))
        img_idx = len(gltf.images)
        gltf.images.append(pygltflib.Image(bufferView=tex_buf_view, mimeType="image/png"))
        sampler_idx = len(gltf.samplers)
        gltf.samplers.append(pygltflib.Sampler(
            magFilter=pygltflib.LINEAR, minFilter=pygltflib.LINEAR_MIPMAP_LINEAR,
            wrapS=pygltflib.CLAMP_TO_EDGE, wrapT=pygltflib.CLAMP_TO_EDGE,
        ))
        tex_idx = len(gltf.textures)
        gltf.textures.append(pygltflib.Texture(sampler=sampler_idx, source=img_idx))

        mat_idx = len(gltf.materials)
        gltf.materials.append(pygltflib.Material(
            name=f"mat_{obj.asset_id}",
            pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
                baseColorTexture=pygltflib.TextureInfo(index=tex_idx),
                metallicFactor=0.0,
                roughnessFactor=1.0,
            ),
            alphaMode="BLEND",
            doubleSided=True,
        ))

        # Geometry bufferViews & accessors
        pos_off, pos_len = _add_blob(pos_bytes)
        nrm_off, nrm_len = _add_blob(nrm_bytes)
        uv_off, uv_len = _add_blob(uv_bytes)
        idx_off, idx_len = _add_blob(idx_bytes)

        def _bv(offset: int, length: int, target: int | None = None) -> int:
            i = len(gltf.bufferViews)
            gltf.bufferViews.append(pygltflib.BufferView(
                buffer=0, byteOffset=offset, byteLength=length, target=target
            ))
            return i

        bv_pos = _bv(pos_off, pos_len, pygltflib.ARRAY_BUFFER)
        bv_nrm = _bv(nrm_off, nrm_len, pygltflib.ARRAY_BUFFER)
        bv_uv = _bv(uv_off, uv_len, pygltflib.ARRAY_BUFFER)
        bv_idx = _bv(idx_off, idx_len, pygltflib.ELEMENT_ARRAY_BUFFER)

        def _acc(bv: int, comp_type: int, acc_type: str, count: int, **kw) -> int:
            i = len(gltf.accessors)
            gltf.accessors.append(pygltflib.Accessor(
                bufferView=bv, componentType=comp_type, type=acc_type, count=count, **kw
            ))
            return i

        pos_acc = _acc(bv_pos, pygltflib.FLOAT, "VEC3", n_verts)
        nrm_acc = _acc(bv_nrm, pygltflib.FLOAT, "VEC3", n_verts)
        uv_acc = _acc(bv_uv, pygltflib.FLOAT, "VEC2", n_verts)
        idx_acc = _acc(bv_idx, idx_component, "SCALAR", idx_count)

        mesh_idx = len(gltf.meshes)
        gltf.meshes.append(pygltflib.Mesh(
            name=f"plane_card_{obj.asset_id}",
            primitives=[pygltflib.Primitive(
                attributes=pygltflib.Attributes(
                    POSITION=pos_acc, NORMAL=nrm_acc, TEXCOORD_0=uv_acc
                ),
                indices=idx_acc,
                material=mat_idx,
            )],
        ))

        node_idx = len(gltf.nodes)
        gltf.nodes.append(pygltflib.Node(
            name=f"PlaneCard_{obj.asset_id}",
            mesh=mesh_idx,
            translation=[pos.x, pos.y, pos.z],
            rotation=None,
            scale=[scl.x, scl.y, scl.z],
            extras={
                f"{_VENDOR_PREFIX}kind": "plane_card",
                f"{_VENDOR_PREFIX}asset_id": obj.asset_id,
                f"{_VENDOR_PREFIX}use_depth_map": obj.use_depth_map,
                f"{_VENDOR_PREFIX}rotation_euler": [rot.x, rot.y, rot.z],
            },
        ))
        gltf.scenes[0].nodes.append(node_idx)

    # Camera and lights as extras on the scene
    cam = scene.camera
    cam_extras = {
        f"{_VENDOR_PREFIX}camera": {
            "focal_mm": cam.focal_mm,
            "sensor_mm": cam.sensor_mm,
            "position": [cam.position.x, cam.position.y, cam.position.z],
            "rotation_euler": (
                [cam.rotation_euler.x, cam.rotation_euler.y, cam.rotation_euler.z]
                if cam.rotation_euler else None
            ),
            "look_at": (
                [cam.look_at.x, cam.look_at.y, cam.look_at.z]
                if cam.look_at else None
            ),
            "f_stop": cam.f_stop,
            "clip_start": cam.clip_start,
            "clip_end": cam.clip_end,
        },
        f"{_VENDOR_PREFIX}lights": [
            {
                "kind": l.kind,
                "position": [l.position.x, l.position.y, l.position.z],
                "intensity": l.intensity,
                "color_kelvin": l.color_kelvin,
            }
            for l in scene.lights
        ],
        f"{_VENDOR_PREFIX}animations": [
            {
                "target_path": t.target_path,
                "times": t.times,
                "values": t.values,
                "interp": t.interp,
            }
            for t in scene.animations
        ],
        f"{_VENDOR_PREFIX}world": {
            "background_color": list(scene.world.background_color),
            "hdri_ref": scene.world.hdri_ref,
        },
        f"{_VENDOR_PREFIX}dsl_hash": sha,
    }
    gltf.scenes[0].extras = cam_extras

    # Single merged buffer
    merged = b"".join(all_blobs)
    gltf.buffers = [pygltflib.Buffer(byteLength=len(merged))]
    gltf.set_binary_blob(merged)

    # Write .extras.json alongside the .glb for the Blender runner
    extras_path = out_path / f"{sha}.extras.json"
    extras_path.write_text(json.dumps(cam_extras, indent=2))

    gltf.save_binary(str(glb_path))
    return str(glb_path)
