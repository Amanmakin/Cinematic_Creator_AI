FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch on Mac M-series; override base + add CUDA in compose for GPU.
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi uvicorn[standard] python-multipart pillow numpy \
    transformers diffusers accelerate safetensors trimesh \
    rembg onnxruntime einops omegaconf

# TripoSR source — installed from the official repo at build time.
RUN git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git /opt/TripoSR && \
    pip install --no-cache-dir -r /opt/TripoSR/requirements.txt || true
ENV PYTHONPATH=/opt/TripoSR

COPY app.py /app/

ENV DEVICE=cpu
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "600"]
