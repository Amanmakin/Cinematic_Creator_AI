FROM python:3.11-slim

WORKDIR /app

# System deps for PIL/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch keeps the image lean (~1.5 GB vs ~6 GB for CUDA).
# Override base image and add nvidia runtime in docker-compose for GPU.
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi uvicorn[standard] diffusers transformers accelerate safetensors pillow

COPY inference_api.py /app/

ENV MODEL_ID=runwayml/stable-diffusion-v1-5
ENV SMALLER_MODEL=true
ENV DEVICE=cpu

EXPOSE 8000

CMD ["uvicorn", "inference_api:app", "--host", "0.0.0.0", "--port", "8000"]
