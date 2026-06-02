"""Shap-E text→3D inference service.

POST /generate { "prompt": str, "guidance_scale"?: float, "karras_steps"?: int }
    → multipart response with `mesh.glb` + `bounds.json` (same layout as TripoSR
    service for adapter symmetry).

Lazy-loads the text-conditioned 300M Shap-E model on first request; serves one
inference at a time.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import tempfile
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Shap-E text→3D service")

DEVICE = os.getenv("DEVICE", "cpu")
# Shap-E (like TripoSR) decodes the mesh with the model's up-axis along +Z, but
# the glTF spec and every consumer downstream (the three.js previs viewer,
# Blender's glTF importer) treat +Y as up. Without correction the model loads
# rotated 90° onto its back ("lying on the floor"). We re-orient Z-up → Y-up (a
# -90° rotation about X maps +Z → +Y) before measuring bounds and exporting, so
# the GLB is a spec-correct Y-up asset — matching docker/triposr/app.py. Set the
# env var to 0 to skip if a future Shap-E build changes convention.
UP_AXIS_ROT_X_DEG = float(os.getenv("SHAP_E_ROT_X_DEG", "-90"))
_MODEL_BUNDLE: dict[str, Any] | None = None
_MODEL_LOCK = asyncio.Lock()


class GenerateRequest(BaseModel):
    prompt: str
    guidance_scale: float = 15.0
    karras_steps: int = 32
    seed: int | None = None


def _load_model() -> dict[str, Any]:
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE
    logger.info("Loading Shap-E weights on %s …", DEVICE)
    import torch
    from shap_e.diffusion.gaussian_diffusion import diffusion_from_config  # type: ignore[import]
    from shap_e.diffusion.sample import sample_latents  # type: ignore[import]
    from shap_e.models.download import load_config, load_model  # type: ignore[import]
    from shap_e.util.notebooks import decode_latent_mesh  # type: ignore[import]

    xm = load_model("transmitter", device=DEVICE)
    model = load_model("text300M", device=DEVICE)
    diffusion = diffusion_from_config(load_config("diffusion"))

    _MODEL_BUNDLE = {
        "xm": xm,
        "model": model,
        "diffusion": diffusion,
        "sample_latents": sample_latents,
        "decode_latent_mesh": decode_latent_mesh,
        "torch": torch,
    }
    logger.info("Shap-E ready.")
    return _MODEL_BUNDLE


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": "Shap-E text300M", "device": DEVICE, "loaded": _MODEL_BUNDLE is not None}


@app.post("/generate")
async def generate(req: GenerateRequest) -> Response:
    if not req.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    async with _MODEL_LOCK:
        loop = asyncio.get_event_loop()
        try:
            glb_bytes, bounds = await loop.run_in_executor(None, _infer, req)
        except Exception as exc:
            logger.exception("Shap-E inference failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    boundary = "shape-mesh-boundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"mesh.glb\"; filename=\"mesh.glb\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + glb_bytes + (
        f"\r\n--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"bounds.json\"; filename=\"bounds.json\"\r\n"
        f"Content-Type: application/json\r\n\r\n"
    ).encode() + json.dumps(bounds).encode() + f"\r\n--{boundary}--\r\n".encode()

    return Response(
        content=body,
        media_type=f"multipart/form-data; boundary={boundary}",
    )


def _infer(req: GenerateRequest) -> tuple[bytes, dict[str, float]]:
    import trimesh  # type: ignore[import]

    bundle = _load_model()
    torch = bundle["torch"]

    latents = bundle["sample_latents"](
        batch_size=1,
        model=bundle["model"],
        diffusion=bundle["diffusion"],
        guidance_scale=req.guidance_scale,
        model_kwargs=dict(texts=[req.prompt]),
        progress=False,
        clip_denoised=True,
        use_fp16=False,
        use_karras=True,
        karras_steps=req.karras_steps,
        sigma_min=1e-3,
        sigma_max=160,
        s_churn=0,
    )

    tri_mesh = bundle["decode_latent_mesh"](bundle["xm"], latents[0]).tri_mesh()
    verts = tri_mesh.verts  # type: ignore[attr-defined]
    faces = tri_mesh.faces  # type: ignore[attr-defined]

    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    # Re-orient Z-up (Shap-E) → Y-up (glTF standard) before measuring bounds +
    # exporting, so bounds.json matches the exported geometry.
    if UP_AXIS_ROT_X_DEG:
        m.apply_transform(
            trimesh.transformations.rotation_matrix(
                math.radians(UP_AXIS_ROT_X_DEG), [1.0, 0.0, 0.0]
            )
        )
    mn, mx = m.bounds
    bounds = {
        "min_x": float(mn[0]), "min_y": float(mn[1]), "min_z": float(mn[2]),
        "max_x": float(mx[0]), "max_y": float(mx[1]), "max_z": float(mx[2]),
    }
    with tempfile.TemporaryDirectory() as tmp:
        glb_path = os.path.join(tmp, "out.glb")
        m.export(glb_path, file_type="glb")
        with open(glb_path, "rb") as f:
            glb_bytes = f.read()
    return glb_bytes, bounds
