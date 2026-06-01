FROM python:3.11-slim

WORKDIR /app

# build-essential + cmake + headers needed to compile torchmcubes (C++ ext)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgl1 libglib2.0-0 git \
    build-essential cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch on Mac M-series; override base + add CUDA in compose for GPU.
# Only install our server-side deps here; transformers/tokenizers/etc. are
# pinned by TripoSR's own requirements.txt below — preinstalling them causes
# pip to backtrack endlessly resolving conflicts.
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi uvicorn[standard] python-multipart onnxruntime

# TripoSR source — installed from the official repo at build time. We strip:
#   - gradio/gradio-client: container serves via FastAPI (app.py); loose pins
#     also conflict with TripoSR's pinned transformers==4.35.0.
#   - xatlas/moderngl: needed only for UV unwrap + GL preview; both fail to
#     build on slim images (need X11/GL headers). app.py exports GLB via
#     trimesh without UVs, so neither is required.
RUN git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git /opt/TripoSR && \
    grep -v -E '^(gradio|gradio-client|xatlas|moderngl)' /opt/TripoSR/requirements.txt > /tmp/triposr-req.txt && \
    pip install --no-cache-dir -r /tmp/triposr-req.txt
ENV PYTHONPATH=/opt/TripoSR

# torchmcubes is required by TripoSR's marching-cubes extractor. On CPU-only
# systems the wheel index has nothing, so build from source. FORCE_CUDA=0
# tells setup.py to skip CUDA bits; --no-build-isolation lets it see the torch
# we just installed above.
ENV FORCE_CUDA=0
RUN pip install --no-cache-dir --no-build-isolation \
    git+https://github.com/tatsy/torchmcubes.git \
    || (echo "torchmcubes build failed — falling back to PyMCubes shim" && \
        pip install --no-cache-dir PyMCubes && \
        printf 'import mcubes\nimport torch\n\ndef marching_cubes(volume, threshold=0.0, *args, **kwargs):\n    v_np = volume.detach().cpu().numpy() if hasattr(volume, "detach") else volume\n    verts, faces = mcubes.marching_cubes(v_np, float(threshold))\n    return torch.from_numpy(verts).float(), torch.from_numpy(faces.astype("int64"))\n\ndef grid_interp(*args, **kwargs):\n    raise NotImplementedError("torchmcubes.grid_interp shim not implemented; only marching_cubes is provided")\n' \
        > /usr/local/lib/python3.11/site-packages/torchmcubes.py)

COPY app.py /app/

ENV DEVICE=cpu
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "600"]
