"""TripoSR image→3D inference service.

POST /generate
    multipart/form-data with field `image` (PNG/JPG) → multipart response:
      - part `mesh.glb`        application/octet-stream
      - part `bounds.json`     application/json  ({min_x,min_y,min_z,max_x,max_y,max_z})

The model is lazy-loaded on first request and gated by an asyncio lock so we
serve one inference at a time (TripoSR uses ~6–8 GB of memory).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TripoSR image→3D service")

DEVICE = os.getenv("DEVICE", "cpu")
# Marching-cubes grid resolution for mesh extraction. The TripoSR default (256)
# peaks well above an 8 GB Docker VM on CPU and gets SIGKILLed; 128 keeps the
# memory peak safe while staying detailed enough for previs. Override via env.
MC_RESOLUTION = int(os.getenv("MC_RESOLUTION", "128"))
_MODEL: Any | None = None
_MODEL_LOCK = asyncio.Lock()


def _load_model() -> Any:
    """Lazy-import + load TripoSR. Returns the inference model."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    logger.info("Loading TripoSR weights on %s …", DEVICE)
    from tsr.system import TSR  # type: ignore[import]

    model = TSR.from_pretrained(
        "stabilityai/TripoSR",
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    model.renderer.set_chunk_size(8192)
    model.to(DEVICE)
    _MODEL = model
    logger.info("TripoSR ready.")
    return model


def _bounds_from_mesh(mesh: Any) -> dict[str, float]:
    """trimesh.Trimesh → axis-aligned bbox dict."""
    mn, mx = mesh.bounds  # shape (2, 3)
    return {
        "min_x": float(mn[0]), "min_y": float(mn[1]), "min_z": float(mn[2]),
        "max_x": float(mx[0]), "max_y": float(mx[1]), "max_z": float(mx[2]),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": "TripoSR", "device": DEVICE, "loaded": _MODEL is not None}


@app.post("/generate")
async def generate(image: UploadFile = File(...)) -> Response:
    raw = await image.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc

    async with _MODEL_LOCK:
        loop = asyncio.get_event_loop()
        try:
            mesh, bounds = await loop.run_in_executor(None, _infer, img)
        except Exception as exc:
            logger.exception("TripoSR inference failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    boundary = "tsr-mesh-boundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"mesh.glb\"; filename=\"mesh.glb\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + mesh + (
        f"\r\n--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"bounds.json\"; filename=\"bounds.json\"\r\n"
        f"Content-Type: application/json\r\n\r\n"
    ).encode() + json.dumps(bounds).encode() + f"\r\n--{boundary}--\r\n".encode()

    return Response(
        content=body,
        media_type=f"multipart/form-data; boundary={boundary}",
    )


def _infer(img: Image.Image) -> tuple[bytes, dict[str, float]]:
    """Synchronous inference path — runs inside an executor thread."""
    import trimesh  # type: ignore[import]

    model = _load_model()
    # Background-remove + center the input image (TripoSR's expected preprocessing).
    try:
        from rembg import remove  # type: ignore[import]
        rgba = remove(img)
    except Exception:
        rgba = img

    arr = np.array(rgba.convert("RGBA")) / 255.0
    rgb = arr[..., :3] * arr[..., 3:4] + (1.0 - arr[..., 3:4]) * 0.5
    proc = Image.fromarray((rgb * 255.0).astype("uint8"))

    with tempfile.TemporaryDirectory() as tmp:
        scene_codes = model([proc], device=DEVICE)
        meshes = model.extract_mesh(scene_codes, has_vertex_color=False, resolution=MC_RESOLUTION)
        tri = meshes[0]
        bounds = _bounds_from_mesh(tri)
        glb_path = os.path.join(tmp, "out.glb")
        tri.export(glb_path, file_type="glb")
        with open(glb_path, "rb") as f:
            glb_bytes = f.read()

    return glb_bytes, bounds
