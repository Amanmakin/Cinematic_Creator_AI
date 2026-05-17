"""Local diffusers inference service — exposes /health and /generate over HTTP."""

from __future__ import annotations

import logging
import os
import uuid

import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CinematicVideoCreator Diffusers Service")

device = os.getenv("DEVICE", "cpu")
smaller_model = os.getenv("SMALLER_MODEL", "true").lower() == "true"

if smaller_model:
    model_id = os.getenv("MODEL_ID", "runwayml/stable-diffusion-v1-5")
    logger.info("Loading SD1.5: %s on %s", model_id, device)
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float32,
        safety_checker=None,
    )
else:
    model_id = os.getenv("MODEL_ID", "stabilityai/stable-diffusion-xl-base-1.0")
    logger.info("Loading SDXL: %s on %s", model_id, device)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        use_safetensors=True,
    )

pipe = pipe.to(device)
pipe.enable_attention_slicing()
logger.info("Model loaded. Ready to serve.")


class GenerateRequest(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    seed: int | None = None
    num_inference_steps: int = 20


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": model_id, "device": device}


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    """Generate an image from a prompt and return the file path."""
    generator = torch.Generator(device=device)
    if req.seed is not None:
        generator = generator.manual_seed(req.seed)

    try:
        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or None,
            width=min(req.width, 1024),
            height=min(req.height, 1024),
            num_inference_steps=req.num_inference_steps,
            generator=generator,
        )
    except Exception as exc:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    image = result.images[0]
    out_path = f"/tmp/gen_{uuid.uuid4().hex}.png"
    image.save(out_path)
    logger.info("Generated image saved to %s", out_path)
    return {"image_url": f"file://{out_path}"}


@app.get("/images/{filename}")
def serve_image(filename: str) -> FileResponse:
    """Serve a generated image by filename (for non-volume-mount setups)."""
    path = f"/tmp/{filename}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")
