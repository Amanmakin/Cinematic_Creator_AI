# Plan 8 — Hybrid Adapter: Local Diffusers + Replicate Fallback

> Status: **Implemented**
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

## Codebase Corrections (vs. original draft)

| Original draft | Actual codebase |
|---|---|
| `ProviderAdapter` base class | `CreativeAdapter` (Protocol in `adapters/base.py`) |
| `LocalDiffusersAdapter` | `LocalDockerAdapter` (consistent naming) |
| `apps/api/src/routes/` | `apps/api/src/api/routes/` |
| `apps/api/src/dag/reducers.py` | `apps/api/src/api/dag/reducers.py` |
| `ProjectMetadata` model | New `generation_settings` SQLite table (no such model exists) |
| Per-project `get_adapter()` injection | Global strategy from `Settings`; per-project overrides in DB read at request time |

## Goal

Enable cost-effective, offline-capable image generation for development via Docker, with transparent fallback to cloud for production or when local inference fails. Preserve existing Replicate adapter as a quality/speed option.

## Deliverables

### D1. Hybrid adapter abstraction

`apps/api/src/api/adapters/hybrid_adapter.py`:
```python
class HybridAdapter(CreativeAdapter):
    """Delegates to LocalDockerAdapter, falls back to ReplicateAdapter on error or config."""

    name = "hybrid"
    version = "1.0.0"

    # Strategies:
    # - "local_only"         — fail if local inference unavailable
    # - "local_fallback"     — local first, Replicate on error (default)
    # - "replicate_only"     — ignore local, always use Replicate
    # - "replicate_fallback" — Replicate first, local on API failure
```

### D2. Local inference via Docker

`apps/api/src/api/adapters/local_docker_adapter.py` — HTTP client that calls the Docker diffusers service.

`docker/diffusers/Dockerfile` — custom image with FastAPI + PyTorch + diffusers.

`docker/diffusers/inference_api.py` — FastAPI service that loads SDXL (or SD1.5) and exposes `/health` + `/generate`.

### D3. Settings & strategy config

**Global defaults** added to `apps/api/src/api/settings.py`:
```
GENERATION_STRATEGY=local_fallback   # local_only | local_fallback | replicate_only | replicate_fallback
DOCKER_DIFFUSERS_URL=http://localhost:8000
GENERATION_TIMEOUT_LOCAL=180         # seconds; M4 Air SDXL ~120-300s
GENERATION_TIMEOUT_REPLICATE=120
USE_SMALLER_MODELS_LOCALLY=true      # SD1.5 instead of SDXL on CPU (faster, lower quality)
```

**Per-project overrides** stored in a new `generation_settings` SQLite table (project_id, strategy, use_smaller_models, timeout_local_sec, timeout_replicate_sec).

**Endpoints** in `apps/api/src/api/routes/generation_settings.py`:
- `GET  /projects/{id}/generation-settings` — return per-project config (or global defaults)
- `PATCH /projects/{id}/generation-settings` — update per-project override
- `GET  /projects/{id}/generation-stats` — cost/time breakdown from `AssetGenerated` dag events

### D4. Docker service configuration

`docker-compose.yml` gains a `diffusers` service alongside existing `redis`.

Environment-based model selection:
- Mac M4 Air (CPU): `SMALLER_MODEL=true`, `DEVICE=cpu`, ~60s per image
- Mac M4 Pro (CPU): `SMALLER_MODEL=false`, `DEVICE=cpu`, ~180s per image
- Linux GPU: `DEVICE=cuda` with nvidia runtime

### D5. Error handling & fallback flow

In `HybridAdapter.execute()`:
- `local_fallback`: try local, catch `(ProviderUnavailable, TimeoutError, RuntimeError)`, log, fall back to Replicate
- `replicate_fallback`: try Replicate, catch `ProviderUnavailable`, fall back to local
- `local_only` / `replicate_only`: single provider, no fallback

### D6. Cost & performance telemetry

New `EventKind` `"AssetGenerated"` added to `apps/api/src/api/dag/reducers.py`.

Payload fields:
```json
{
  "asset_id": "...",
  "provider": "local_diffusers | replicate",
  "model_used": "sd1.5 | sdxl",
  "inference_time_sec": 92.3,
  "cost_usd": 0.0,
  "fallback_triggered": false
}
```

`GET /projects/{id}/generation-stats` aggregates these events.

### D7. UI settings panel

`apps/web/components/GenerationSettingsPanel.tsx` — 4-option radio for strategy + checkbox for smaller models.

`apps/web/components/GenerationStatsPanel.tsx` — shows local vs. Replicate count, total cost, avg inference times.

## Files Created / Modified

**Created:**
```
apps/api/src/api/adapters/hybrid_adapter.py
apps/api/src/api/adapters/local_docker_adapter.py
apps/api/src/api/routes/generation_settings.py
apps/api/tests/test_hybrid_adapter_local_first.py
apps/api/tests/test_hybrid_adapter_fallback.py
apps/api/tests/test_docker_adapter_health_check.py
apps/api/tests/test_generation_settings_update.py
docker/diffusers/Dockerfile
docker/diffusers/inference_api.py
docker/models/.gitkeep
apps/web/components/GenerationSettingsPanel.tsx
apps/web/components/GenerationStatsPanel.tsx
```

**Modified:**
```
apps/api/src/api/settings.py           — DOCKER_DIFFUSERS_URL, GENERATION_STRATEGY, timeouts, USE_SMALLER_MODELS_LOCALLY
apps/api/src/api/adapters/__init__.py  — export HybridAdapter, LocalDockerAdapter
apps/api/src/api/graph_dep.py          — inject HybridAdapter (global strategy from settings)
apps/api/src/api/dag/reducers.py       — add "AssetGenerated" EventKind
apps/api/src/api/main.py               — mount generation_settings router
docker-compose.yml                     — add diffusers service
```

## Verification

1. `docker compose up -d diffusers` → `docker logs cinematic-diffusers` shows model loaded.
2. `curl http://localhost:8000/health` → `{"status": "ok"}`.
3. With Docker running, `LocalDockerAdapter.health_check()` returns `True`; stopped returns `False`.
4. Open project settings → `GenerationSettingsPanel` visible with 4 strategy options.
5. Strategy persisted: select "local_only", refresh → still "local_only".
6. Set strategy "local_fallback", generate → `/projects/{id}/generation-stats` shows `local_count: 1, cost_usd: 0`.
7. Stop Docker, set `GENERATION_TIMEOUT_LOCAL=5`, generate → timeout and fallback to Replicate triggers.
8. `GET /projects/{id}/generation-stats` after 5 Replicate generations shows `cost_usd: ~0.25`.

## Out of scope

- Video generation (requires even more VRAM)
- Custom model fine-tuning
- Quantization/compression of SDXL for faster inference
- Running on mobile/iOS
- Caching generated images at inference level (caching at DAG/asset level only)
