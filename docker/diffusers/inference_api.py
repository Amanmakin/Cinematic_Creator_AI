"""Local diffusers inference service — exposes /health and /generate over HTTP."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid

import torch
from diffusers import (
    DPMSolverMultistepScheduler,
    StableDiffusionImg2ImgPipeline,
    StableDiffusionPipeline,
    StableDiffusionXLImg2ImgPipeline,
    StableDiffusionXLPipeline,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CinematicVideoCreator Diffusers Service")

# Tokenizers (Rust/PyO3) cannot be accessed from two threads simultaneously.
_pipeline_lock = asyncio.Lock()

device = os.getenv("DEVICE", "cpu")
smaller_model = os.getenv("SMALLER_MODEL", "true").lower() == "true"

if smaller_model:
    model_id = os.getenv("MODEL_ID", "runwayml/stable-diffusion-v1-5")
    logger.info("Loading SD1.5 txt2img: %s on %s", model_id, device)
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float32,
        safety_checker=None,
    )
else:
    model_id = os.getenv("MODEL_ID", "stabilityai/stable-diffusion-xl-base-1.0")
    logger.info("Loading SDXL txt2img: %s on %s", model_id, device)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        use_safetensors=True,
    )

pipe = pipe.to(device)
pipe.enable_attention_slicing()
pipe.scheduler = DPMSolverMultistepScheduler.from_config(
    pipe.scheduler.config, algorithm_type="dpmsolver++"
)

# Build img2img pipeline by reusing the already-loaded model weights (no extra VRAM).
logger.info("Building img2img pipeline from shared weights…")
if smaller_model:
    img2img_pipe = StableDiffusionImg2ImgPipeline(**pipe.components).to(device)
else:
    img2img_pipe = StableDiffusionXLImg2ImgPipeline(**pipe.components).to(device)
img2img_pipe.enable_attention_slicing()

logger.info("Models loaded. Ready to serve.")


class GenerateRequest(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    seed: int | None = None
    num_inference_steps: int = 20
    # Optional wireframe conditioning: base64-encoded PNG for img2img
    init_image: str | None = None
    strength: float = 0.8  # 0 = keep init fully, 1 = ignore init completely


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": model_id, "device": device}


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    """Generate an image from a prompt and return the file path.

    When ``init_image`` is supplied (base64 PNG), uses img2img so the
    wireframe composition guides the layout of the generated model render.
    """
    import time

    generator = torch.Generator(device=device)
    if req.seed is not None:
        generator = generator.manual_seed(req.seed)

    w = min(req.width, 512)
    h = min(req.height, 512)

    if req.init_image:
        # img2img: wireframe sheet → textured model render
        raw = base64.b64decode(req.init_image)
        init_img = Image.open(io.BytesIO(raw)).convert("RGB").resize((w, h))

        def _run_img2img() -> object:
            return img2img_pipe(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt or None,
                image=init_img,
                strength=req.strength,
                num_inference_steps=req.num_inference_steps,
                generator=generator,
            )

        inference_fn = _run_img2img
        logger.info(
            "img2img inference: prompt=%r strength=%.2f steps=%d",
            req.prompt[:50], req.strength, req.num_inference_steps,
        )
    else:
        def _run_txt2img() -> object:
            return pipe(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt or None,
                width=w,
                height=h,
                num_inference_steps=req.num_inference_steps,
                generator=generator,
            )

        inference_fn = _run_txt2img
        logger.info("txt2img inference: prompt=%r steps=%d", req.prompt[:50], req.num_inference_steps)

    try:
        t0 = time.time()
        loop = asyncio.get_event_loop()
        async with _pipeline_lock:
            result = await loop.run_in_executor(None, inference_fn)
        elapsed = time.time() - t0
        logger.info("Inference completed in %.1fs", elapsed)
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
