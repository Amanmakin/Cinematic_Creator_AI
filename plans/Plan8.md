# Plan 8 — Hybrid Adapter: Local Diffusers + Replicate Fallback

> Status: **Not started**
> Depends on: Plan2 (HTTP surface), Plan4 (Blender DSL)
> Unblocks: cost reduction for development; offline capability for Mac/Linux users; production fallback for quality

## Context

Currently, all generative tasks (SDXL image generation, ControlNet inpainting, background removal) route through Replicate via API. This requires:
- REPLICATE_API_KEY credentials
- Internet connectivity for every generation
- Per-image API charges (~$0.05-0.30 per SDXL image)

Mac M-series users (M4 Air, M3 Pro, etc.) can run SDXL locally via Docker, though slower than GPU. Plan8 introduces a **hybrid adapter** that:
1. Tries local Docker services first (free, running in containers for isolation)
2. Falls back to Replicate on failure or for production quality
3. Lets users configure strategy per-task (cost vs. quality vs. speed)

**Constraint**: All local models run in Docker containers only (no direct Python/pip installations on the Mac).

## Goal

Enable cost-effective, offline-capable image generation for development via Docker, with transparent fallback to cloud for production or when local inference fails. Preserve existing Replicate adapter as a quality/speed option.

## Deliverables

### D1. Hybrid adapter abstraction

Create `apps/api/src/api/adapters/hybrid_adapter.py`:
```python
class HybridAdapter(ProviderAdapter):
    """Delegates to local diffusers, falls back to Replicate on error or config."""
    
    name = "hybrid"
    version = "1.0.0"
    
    def __init__(self, api_key: str, strategy: str = "local_fallback"):
        # Strategies:
        # - "local_only": fail if local inference unavailable
        # - "local_fallback": local first, Replicate on error
        # - "replicate_only": ignore local, always use Replicate
        # - "replicate_fallback": Replicate first, local on API failure
        self._strategy = strategy
        self._replicate = ReplicateAdapter(api_key)
        self._local = LocalDiffusersAdapter()
```

### D2. Local inference via Docker

Create `apps/api/src/api/adapters/local_docker_adapter.py`:
```python
class LocalDockerAdapter(ProviderAdapter):
    """Calls local Docker services for image generation (Ollama, diffusers API, etc.)."""
    
    def __init__(self, docker_base_url: str = "http://localhost:8000"):
        self.docker_base_url = docker_base_url  # Default port for local diffusers service
        self._http_client = None
    
    async def health_check(self) -> bool:
        """Verify Docker service is running and healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.docker_base_url}/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutError):
            return False
    
    def supports(self, intent: CreativeIntent) -> bool:
        return intent.kind in {"generate_subject", "generate_background", "regenerate_layer"}
    
    async def execute(self, payload: ProviderPayload) -> AssetRef:
        # Verify Docker service is available
        if not await self.health_check():
            raise ProviderUnavailable(
                f"Local Docker service unavailable at {self.docker_base_url}. "
                "Run: docker compose up -d diffusers"
            )
        
        headers = {"Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(
                    f"{self.docker_base_url}/generate",
                    headers=headers,
                    json=payload.inputs
                )
                resp.raise_for_status()
                result = resp.json()
                output_url = result["image_url"]
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"Docker service unreachable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(f"Docker service error {exc.response.status_code}") from exc
        
        asset_id = _short_hash(output_url + str(time.time()))
        return AssetRef(
            asset_id=asset_id,
            adapter=self.name,
            adapter_version=self.version,
        )
```

**Docker setup** via `docker-compose.yml`:
```yaml
services:
  diffusers:
    image: ghcr.io/huggingface/diffusers:latest  # or custom image
    # Alternative: build custom image with SDXL + ControlNet
    # build: ./docker/diffusers
    container_name: cinematic-diffusers
    ports:
      - "8000:8000"
    environment:
      - MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0
      - DEVICE=cpu  # or 'metal' for Mac, 'cuda' for GPU
      - SMALLER_MODEL=false  # Set to true for M4 Air to use SD1.5
    volumes:
      - ./docker/models:/root/.cache/huggingface  # Persist downloaded models
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

Or create a **custom Dockerfile** for optimized Mac inference:
```dockerfile
# docker/diffusers/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi uvicorn torch torchvision transformers diffusers \
    accelerate safetensors peft xformers

COPY inference_api.py /app/

ENV MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0
ENV DEVICE=cpu
ENV SMALLER_MODEL=false

CMD ["uvicorn", "inference_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Sample `inference_api.py`:
```python
from fastapi import FastAPI
from pydantic import BaseModel
import torch
from diffusers import StableDiffusionXLPipeline

app = FastAPI()
device = os.getenv("DEVICE", "cpu")
model_id = os.getenv("MODEL_ID", "stabilityai/stable-diffusion-xl-base-1.0")

# Load model once at startup
if os.getenv("SMALLER_MODEL", "false").lower() == "true":
    model_id = "runwayml/stable-diffusion-v1-5"

pipe = StableDiffusionXLPipeline.from_pretrained(model_id, torch_dtype=torch.float32)
pipe = pipe.to(device)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generate")
async def generate(request: dict):
    """Generate image from prompt."""
    prompt = request.get("prompt", "")
    negative = request.get("negative_prompt", "")
    
    image = pipe(
        prompt=prompt,
        negative_prompt=negative,
        num_inference_steps=30
    ).images[0]
    
    # Save to shared volume and return URL
    image_path = f"/tmp/generated_{uuid.uuid4()}.png"
    image.save(image_path)
    return {"image_url": f"file://{image_path}"}
```

### D3. Settings & strategy config

**Global defaults** in `apps/api/src/api/settings.py`:
```python
class GenerationSettings(BaseSettings):
    GENERATION_STRATEGY: str = Field(
        default="local_fallback",
        description="local_only | local_fallback | replicate_only | replicate_fallback"
    )
    GENERATION_TIMEOUT_LOCAL: int = Field(
        default=180,
        description="Timeout for local inference (seconds). M4 Air SDXL ~120-300s"
    )
    GENERATION_TIMEOUT_REPLICATE: int = Field(
        default=120,
        description="Timeout for Replicate API calls"
    )
    USE_SMALLER_MODELS_LOCALLY: bool = Field(
        default=True,
        description="Use Stable Diffusion 1.5 instead of SDXL on Mac/CPU (faster, lower quality)"
    )
```

**Per-project overrides** in `apps/api/src/dag/reducers.py`:
```python
class GenerationConfig(BaseModel):
    strategy: str = "local_fallback"
    use_smaller_models: bool = True
    timeout_local_sec: int = 180
    timeout_replicate_sec: int = 120

# Stored in ProjectMetadata
class ProjectMetadata(BaseModel):
    ...existing fields...
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)
```

**Runtime settings API** in `apps/api/src/routes/projects.py`:
```python
@router.patch("/projects/{id}/generation-settings")
async def update_generation_settings(
    id: str,
    config: GenerationConfig,
    db: Database,
) -> GenerationConfig:
    """Update generation strategy for this project. Changes take effect immediately."""
    project = await db.fetch_one("SELECT * FROM projects WHERE id = ?", (id,))
    metadata = ProjectMetadata.model_validate_json(project["metadata"])
    metadata.generation_config = config
    await db.execute(
        "UPDATE projects SET metadata = ? WHERE id = ?",
        (metadata.model_dump_json(), id)
    )
    return config

@router.get("/projects/{id}/generation-settings")
async def get_generation_settings(id: str, db: Database) -> GenerationConfig:
    """Fetch current generation settings for this project."""
    project = await db.fetch_one("SELECT * FROM projects WHERE id = ?", (id,))
    metadata = ProjectMetadata.model_validate_json(project["metadata"])
    return metadata.generation_config
```

**Adapter injection with per-project config** in `graph_dep.py`:
```python
async def get_adapter(project_id: str, db: Database, global_settings: GenerationSettings) -> ProviderAdapter:
    # Fetch per-project config, fall back to global defaults
    project = await db.fetch_one("SELECT metadata FROM projects WHERE id = ?", (project_id,))
    metadata = ProjectMetadata.model_validate_json(project["metadata"])
    config = metadata.generation_config
    
    if config.strategy.startswith("local"):
        return HybridAdapter(
            api_key=global_settings.REPLICATE_API_KEY,
            strategy=config.strategy,
            local_timeout=config.timeout_local_sec,
            replicate_timeout=config.timeout_replicate_sec,
            prefer_smaller_models=config.use_smaller_models,
        )
    else:
        return ReplicateAdapter(global_settings.REPLICATE_API_KEY)
```

### D4. Docker service configuration

**Environment-based model selection** in `docker-compose.yml`:

For **Mac M4 Air** (slower, free):
```yaml
diffusers:
  environment:
    - MODEL_ID=runwayml/stable-diffusion-v1-5  # Faster (~60s)
    - DEVICE=cpu
    - SMALLER_MODEL=true
```

For **Mac M4 Pro** (medium speed):
```yaml
diffusers:
  environment:
    - MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0  # Better quality
    - DEVICE=cpu
    - SMALLER_MODEL=false
```

For **Linux with GPU**:
```yaml
diffusers:
  environment:
    - MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0
    - DEVICE=cuda
    - SMALLER_MODEL=false
    - NVIDIA_VISIBLE_DEVICES=all
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

Define in settings for **runtime model switching**:
```python
# apps/api/src/api/settings.py
class GenerationSettings(BaseSettings):
    DOCKER_DIFFUSERS_URL: str = Field(
        default="http://localhost:8000",
        description="Local Docker diffusers service endpoint"
    )
    DOCKER_SMALLER_MODEL: bool = Field(
        default=True,
        description="Use SD1.5 in Docker (faster on M4) vs SDXL"
    )
    DOCKER_DEVICE: str = Field(
        default="cpu",
        description="Device for Docker container: cpu, metal (Mac), cuda (GPU)"
    )
```

### D5. Error handling & fallback flow

In `HybridAdapter.execute()`:
```python
async def execute(self, payload: ProviderPayload) -> AssetRef:
    if self._strategy == "local_fallback":
        try:
            return await self._local.execute(payload)
        except (TimeoutError, RuntimeError, MemoryError) as e:
            logger.warning(f"Local inference failed: {e}. Falling back to Replicate.")
            return await self._replicate.execute(payload)
    elif self._strategy == "replicate_fallback":
        try:
            return await self._replicate.execute(payload)
        except ProviderUnavailable as e:
            logger.warning(f"Replicate unavailable: {e}. Trying local.")
            return await self._local.execute(payload)
    elif self._strategy == "local_only":
        return await self._local.execute(payload)
    elif self._strategy == "replicate_only":
        return await self._replicate.execute(payload)
```

### D6. Cost & performance telemetry

Extend `apps/api/src/dag/reducers.py` to track:
```python
class AssetGenerated(Event):
    asset_id: str
    provider: str          # "local_diffusers" or "replicate"
    model_used: str        # "sd1.5", "sdxl", etc.
    inference_time_sec: float
    cost_usd: float        # 0 for local, ~0.05-0.30 for Replicate
    fallback_triggered: bool
```

Add a `/projects/{id}/generation-stats` endpoint:
```python
@router.get("/projects/{id}/generation-stats")
async def get_generation_stats(id: str, db: Database):
    """Return cost/time breakdown across local vs. Replicate."""
    # Count events by provider, sum times & costs
    return {
        "total_generations": 42,
        "local_count": 38,
        "replicate_count": 4,
        "total_cost_usd": 1.20,
        "local_avg_time_sec": 120,
        "replicate_avg_time_sec": 8,
    }
```

### D7. UI settings panel

Create `apps/web/components/GenerationSettingsPanel.tsx`:
```tsx
export function GenerationSettingsPanel({ projectId }: { projectId: string }) {
  const [config, setConfig] = useState<GenerationConfig | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchGenerationSettings(projectId).then(setConfig);
  }, [projectId]);

  const handleStrategyChange = async (strategy: string) => {
    setSaving(true);
    const updated = { ...config, strategy };
    await updateGenerationSettings(projectId, updated);
    setConfig(updated);
    setSaving(false);
  };

  return (
    <div className="p-4 border rounded bg-gray-50">
      <h3 className="font-bold mb-4">Image Generation Strategy</h3>
      
      <div className="space-y-3">
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="strategy"
            value="local_fallback"
            checked={config?.strategy === "local_fallback"}
            onChange={(e) => handleStrategyChange(e.target.value)}
            disabled={saving}
          />
          <span>Local first, fallback to Replicate (default, cheapest)</span>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="strategy"
            value="replicate_only"
            checked={config?.strategy === "replicate_only"}
            onChange={(e) => handleStrategyChange(e.target.value)}
            disabled={saving}
          />
          <span>Replicate only (fastest, ~$0.05-0.30 per image)</span>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="strategy"
            value="local_only"
            checked={config?.strategy === "local_only"}
            onChange={(e) => handleStrategyChange(e.target.value)}
            disabled={saving}
          />
          <span>Local only (offline, no API key needed)</span>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="strategy"
            value="replicate_fallback"
            checked={config?.strategy === "replicate_fallback"}
            onChange={(e) => handleStrategyChange(e.target.value)}
            disabled={saving}
          />
          <span>Replicate first, fallback to local</span>
        </label>
      </div>

      <div className="mt-4 space-y-2">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={config?.use_smaller_models || false}
            onChange={(e) =>
              handleStrategyChange({
                ...config,
                use_smaller_models: e.target.checked,
              })
            }
            disabled={saving}
          />
          <span>Use faster SD1.5 locally (lower quality, ~60s vs SDXL ~180s)</span>
        </label>
      </div>

      {saving && <p className="text-gray-500 mt-2">Saving...</p>}
    </div>
  );
}
```

Integrate into project settings page (e.g., `apps/web/app/(workspace)/settings/page.tsx`):
```tsx
import { GenerationSettingsPanel } from "@/components/GenerationSettingsPanel";

export default function SettingsPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Project Settings</h1>
      <GenerationSettingsPanel projectId={params.id} />
      {/* other settings panels... */}
    </div>
  );
}
```

## Critical files to create

```
apps/api/src/api/adapters/hybrid_adapter.py
apps/api/src/api/adapters/local_docker_adapter.py             # Calls Docker service
apps/api/src/routes/generation_settings.py                    # PATCH/GET generation config
apps/api/tests/test_hybrid_adapter_local_first.py
apps/api/tests/test_hybrid_adapter_fallback.py
apps/api/tests/test_docker_adapter_health_check.py
apps/api/tests/test_generation_settings_update.py
docker/diffusers/Dockerfile                                   # Custom image for SDXL
docker/diffusers/inference_api.py                             # FastAPI inference service
docker-compose.yml                                             # Services: diffusers, rembg, etc.
docker/models/.gitkeep                                         # Shared model cache volume
apps/web/components/GenerationSettingsPanel.tsx               # UI to change strategy/docker config
apps/web/components/GenerationStatsPanel.tsx                  # display cost/time breakdown
```

Modify:
- `apps/api/src/api/settings.py` — add `DOCKER_DIFFUSERS_URL`, `DOCKER_SMALLER_MODEL`, `DOCKER_DEVICE`
- `apps/api/src/api/graph_dep.py` — inject HybridAdapter with LocalDockerAdapter
- `apps/api/src/dag/reducers.py` — extend `ProjectMetadata` with `GenerationConfig`; track `AssetGenerated`
- `apps/api/src/routes/projects.py` — wire up generation settings endpoints
- `.env.example` — document new Docker settings

## Dependencies

**On Mac (FastAPI app):**
- `httpx` (already in requirements) — HTTP client to call Docker services
- `docker` (optional) — for programmatic docker-compose management

**Inside Docker container:**
- `torch`, `torchvision`, `transformers`, `diffusers` — all installed in Docker image
- `accelerate`, `safetensors`, `peft`, `xformers` — optional, for optimization

**Infrastructure:**
- Docker + Docker Compose installed on Mac
- ~5-10GB disk space for model cache (`docker/models/`)

## Verification

1. **Docker service startup**: `docker compose up -d diffusers` → verify container running, `docker logs cinematic-diffusers` shows model loaded.
2. **Health check**: `curl http://localhost:8000/health` → returns `{"status": "ok"}`.
3. **Health check integration**: With Docker running, `LocalDockerAdapter.health_check()` returns `True`. With Docker stopped, returns `False` and adapter fails gracefully.
4. **Settings UI**: Open project settings → GenerationSettingsPanel visible with 4 strategy radio buttons + "use smaller models" checkbox.
5. **Runtime strategy change**: Select "local_only" in UI → trigger generation → should call Docker. Select "replicate_only" → should use Replicate. Verify via `/projects/{id}/generation-stats` provider field.
6. **Settings persistence**: Change strategy to "local_only", close browser, reopen project → strategy should remain "local_only" (persisted to DB).
7. **Local generation**: Start Docker, set strategy to "local_fallback", generate a subject → verify `/projects/{id}/generation-stats` shows `local_count: 1`, `cost_usd: 0`, `inference_time_sec: ~60-180`.
8. **Fallback on Docker down**: Stop Docker, set `GENERATION_TIMEOUT_LOCAL=5`, trigger generation → should timeout waiting for Docker and fallback to Replicate.
9. **Fallback on Docker error**: Set Docker environment to invalid model ID, set strategy "local_fallback" → generation should fail with Docker error and fallback to Replicate.
10. **Model switching**: Edit `docker-compose.yml` to change `SMALLER_MODEL=false`, run `docker compose restart diffusers`, generate → should use SDXL (slower but better quality). Verify timing in stats.
11. **Cost tracking**: After 20 generations (15 local, 5 Replicate), `/projects/{id}/generation-stats` should show `cost_usd: ~0.25` (5 × $0.05 avg).

## Out of scope

- Video generation (requires even more VRAM; can add later)
- Custom model fine-tuning
- Quantization/compression of SDXL for faster inference (could be added)
- Running on mobile/iOS (use Replicate for iOS apps)
- Caching of generated images at inference level (caching should be at DAG/asset level)
