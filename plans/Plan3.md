# Plan 3 — Creative Abstraction Layer + Visual Generation

> Status: **Not started**
> Depends on: Plan1 (LangGraph engine), Plan2 (HTTP surface + FE)
> Unblocks: Plan4 (DSL plane-cards need real textures), Plan6

## Integration with the LangGraph orchestrator

Plan3 adds **two new LangGraph nodes** between `scene_graph_generator` and `physical_validation`:
- `creative_dispatcher` — pure Python, walks the `BlenderDsl` and emits a list of `CreativeIntent`s for any subject/background that needs imagery.
- `visual_generator` — async node that calls `ReplicateAdapter.execute()` for each intent (concurrently), populates the UAR, and rewrites the DSL so every `SubjectPlaceholder` becomes a `PlaneCard` referencing a real `LayerAsset` id.

The DSL grows accordingly: `SubjectPlaceholder` → `PlaneCard` (defined in Plan4). For Plan3 we extend the DSL minimally to support an `asset_ref: str | None` on subjects so the engine can carry texture references through `physical_validation`.

The UAR persists outside `MemorySaver`'s checkpoint store (it's content-addressed on disk) but is keyed deterministically off the same inputs, so checkpoint replay produces cache hits.

## Goal

Translate validated intents into real, layered imagery via Replicate. Establish the Universal Asset Registry (UAR) so locked elements survive iteration without regeneration cost.

## Deliverables

### D1. CreativeIntent schema
- `packages/schemas/python/cvc_schemas/creative.py`:
  ```python
  CreativeIntentKind = Literal[
      "generate_subject", "generate_background", "generate_foreground_fx",
      "apply_warm_lighting", "apply_cool_lighting", "apply_lens_blur",
      "stylize_palette", "regenerate_layer",
  ]
  class CreativeIntent(BaseModel):
      kind: CreativeIntentKind
      target_path: str            # e.g. "scene.layers.subject"
      parameters: dict[str, Any]  # validated per-kind by a discriminated union in Plan4
      seed: int
      adapter_hint: str | None    # "replicate.sdxl" by default
  ```
- A discriminated-union parameter model per `kind` (e.g. `GenerateSubjectParams`, `ApplyWarmLightingParams`). Strict so the LLM can target it via structured output.

### D2. Adapter pattern
- `apps/api/src/adapters/base.py`:
  ```python
  class CreativeAdapter(Protocol):
      name: str
      def supports(self, intent: CreativeIntent) -> bool: ...
      def translate(self, intent: CreativeIntent, ctx: ProjectCtx) -> ProviderPayload: ...
      async def execute(self, payload: ProviderPayload) -> AssetRef: ...
      def cost_estimate(self, payload: ProviderPayload) -> Tokens: ...
  ```
- `apps/api/src/adapters/replicate_adapter.py` — first concrete implementation.
  - SDXL for `generate_subject` / `generate_background`.
  - SDXL + ControlNet (depth/canny) for layer-consistent regeneration.
  - rembg or `bria-rmbg` model for alpha extraction.
  - MiDaS or depth-anything for depth maps.
- `apps/api/src/adapters/comfyui_adapter.py` — stub only (`raises NotImplementedError`). Locks the interface so Plan6+ can swap in.

### D3. Layer compositing
- Every generation produces a `LayerAsset`:
  ```python
  class LayerAsset(BaseModel):
      id: str                  # sha256 of inputs (deterministic)
      kind: Literal["subject", "background", "fx"]
      rgba_path: str           # PNG with alpha
      alpha_mask_path: str     # 8-bit grayscale
      depth_map_path: str      # 16-bit grayscale
      bbox_px: tuple[int, int, int, int]
      adapter: str
      adapter_version: str
      created_at: float
  ```
- Foreground (subject) + background + optional FX are produced as separate assets, never as a flattened composite. Composition happens later in the Three.js viewport (Plan5) and in Blender (Plan4) as plane-cards.

### D4. Universal Asset Registry (UAR)
- `apps/api/src/uar/store.py`:
  - Table `assets(id TEXT PK, kind TEXT, paths JSON, adapter TEXT, adapter_version TEXT, prompt_hash TEXT, created_at REAL)`.
  - Content-addressed blob layout: `projects/{id}/assets/{sha256[:2]}/{sha256}.{ext}`.
  - `get_or_create(intent, adapter) -> (LayerAsset, was_cached: bool)`:
    1. Compute `prompt_hash = sha256(canonical_json(intent_payload) + adapter_version)`.
    2. If `prompt_hash` exists in `assets`, return cached.
    3. Else, call `adapter.execute`, write all three files atomically (write to `.tmp`, then `os.rename`), insert row, return.
- Locked-layer behavior: when a `CreativeIntent` targets a locked `target_path`, the UAR returns the existing asset for that path and emits `LockedAssetReused` instead of regenerating.

### D5. Cost guard
- `apps/api/src/orchestrator/budget.py`:
  - `BudgetLedger` keyed by `project_id` — per-project token cap, persisted in SQLite, decremented on every `adapter.execute` based on `cost_estimate`.
  - Over-budget → emit `BudgetExceeded` + require fresh `ApprovalEvent(mode="budget_topup")` before further `execute` calls.
- All adapter calls go through `BudgetLedger.spend(estimate, fn)` — fn does not run if the ledger refuses.

### D6. New routes
- `POST /projects/{id}/creative-intents` accepts a `CreativeIntent` list (storyboard → list of intents is produced by the orchestrator router added in Plan2).
- `GET /projects/{id}/assets/{asset_id}/{layer_type}` serves PNG bytes for FE.

## Critical files to create

```
apps/api/src/adapters/__init__.py
apps/api/src/adapters/base.py
apps/api/src/adapters/replicate_adapter.py
apps/api/src/adapters/comfyui_adapter.py        # stub
apps/api/src/uar/store.py
apps/api/src/uar/paths.py
apps/api/src/orchestrator/budget.py
apps/api/src/orchestrator/creative_dispatch.py   # storyboard → list[CreativeIntent]
apps/api/src/routes/creative.py
apps/api/src/routes/assets.py
apps/api/tests/test_uar_cache.py
apps/api/tests/test_replicate_adapter_translate.py   # no network — only payload shape
apps/web/components/RenderStudio/LayerPreview.tsx
```

Extend:
- `packages/schemas/python/cvc_schemas/models.py` — add `CreativeIntent`, `LayerAsset`, `AssetRef`, `BudgetLedger`, all per-kind parameter models. Regenerate TS.
- `apps/api/src/dag/reducers.py` — add `CreativeIntentDispatched`, `LayerGenerated`, `LockedAssetReused`, `BudgetExceeded`, `BudgetReplenished`.
- `apps/api/src/orchestrator/router.py` — register `generate_subject`, `generate_background`, `apply_warm_lighting`, etc.

## Verification

1. **Cache hit**: post the same `CreativeIntent` twice → second is `LockedAssetReused`-equivalent (UAR cache hit), zero Replicate calls. Confirm via mocked HTTP client in tests; confirm via real run in dev.
2. **Locked layer**: lock `scene.layers.subject`, edit only the background description, dispatch → only `generate_background` runs, subject asset reused.
3. **Provider failure**: monkeypatch the Replicate client to raise `httpx.ConnectError` → adapter raises `ProviderUnavailable` → `LayerGenerationFailed` event in DAG → DAG remains replayable (no half-written assets — confirm `.tmp` files are cleaned up).
4. **Budget**: set token cap = 100, dispatch an intent estimated at 150 → `BudgetExceeded`, no execute call made. Approve top-up → resume.
5. **Layer separation**: open any `LayerAsset` in macOS Preview — RGBA PNG has true alpha (transparent background), depth map looks like a depth map.

## Out of scope

- Blender / DSL (Plan4).
- Real-time R3F viewport rendering of layers (Plan5 — Plan3 ships only `LayerPreview.tsx` as a 2D <img> grid).
- Embedding-based asset retrieval (Plan7).
