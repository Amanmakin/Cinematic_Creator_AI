# Plan 4 — Blender DSL Expansion + glTF Assembler + Headless Runner

> Status: **Not started**
> Depends on: Plan1 (engine), Plan3 (UAR textures)
> Unblocks: Plan5, Plan6

## Integration with the LangGraph orchestrator

The `BlenderDsl` Pydantic schema introduced in Plan1 stays — Plan4 **extends** it with `PlaneCard`, `AnimationTrack`, `WorldEnv`, full materials. The `PhysicalValidationEngine` node from Plan1 absorbs the broader rule set from this plan (camera-vs-AABB collisions, animation-time monotonicity, etc.).

Plan4 also adds two **post-engine** stages (not LangGraph nodes — they run after the graph terminates with `execution_status="completed"`):
- `gltf_builder` — assembles `.glb` from the finalized `BlenderDsl` + UAR textures.
- `blender_runner` — headless Blender subprocess wrapper.

Both are invoked from the FastAPI surface (Plan2) or from the render queue (Plan6).

## Goal

Define a versioned, strictly typed Blender DSL. Validate it against physical sanity rules in pure Python *before* spawning any subprocess. Assemble a `.glb` so frontend (R3F) and backend (Blender) consume the same geometry.

## Deliverables

### D1. DSL v1
- `packages/dsl/schema.json` — JSON Schema Draft 2020-12. Mirror as Pydantic in `packages/schemas/python/cvc_schemas/dsl.py`.
- Top-level shape:
  ```python
  class BlenderDsl(BaseModel):
      dsl_version: Literal["1.0.0"]
      scene: Scene
  class Scene(BaseModel):
      duration_s: float
      fps: int                       # 24 / 30 / 60
      resolution: tuple[int, int]    # locked to canon aspect ratio
      camera: Camera
      lights: list[Light]
      objects: list[SceneObject]     # PlaneCard | Mesh
      animations: list[AnimationTrack]
      world: WorldEnv                # background color, HDRI ref (asset id)
  class Camera(BaseModel):
      focal_mm: float                # validated 1..1000
      sensor_mm: float = 36.0
      position: Vec3
      rotation_euler: Vec3
      f_stop: float = 2.8
      clip_start: float = 0.01
      clip_end: float = 1000.0
  class PlaneCard(BaseModel):
      kind: Literal["plane_card"]
      asset_id: str                   # UAR LayerAsset id
      transform: Transform            # position, rotation, scale
      use_depth_map: bool             # extrude with depth if true
  class AnimationTrack(BaseModel):
      target_path: str                # JSONPath into the scene
      times: list[float]              # strictly monotonic
      values: list[Any]               # type must match target
      interp: Literal["linear","bezier","step"]
  ```

### D2. Physical Validation Engine
- `apps/api/src/validation/physical.py` — pure Python, **never** invokes the LLM.
- Checks (each emits a `ValidationFinding` with severity `error|warn`):
  1. `1.0 <= camera.focal_mm <= 1000.0`.
  2. `clip_start < clip_end`, both positive.
  3. Camera position not inside any object AABB (compute AABBs from plane-card transforms; treat plane-cards as 2D extruded by 0.01 along normal).
  4. Each light intensity ≤ 10000 (Blender EEVEE unit) and ≥ 0.
  5. Every `PlaneCard.asset_id` resolves in UAR; reject if missing.
  6. Animation tracks: `times` strictly monotonic, last `time` ≤ `scene.duration_s`, value count matches `times`.
  7. `scene.duration_s ≤ project_canon.duration_seconds_max`.
  8. `scene.resolution` matches project canon aspect ratio (within 0.01 tolerance).
- Returns `ValidationReport(ok: bool, findings: list[ValidationFinding])`. Orchestrator refuses to enqueue a render unless `ok == True`.

### D3. glTF/glb assembler
- `apps/api/src/render/gltf_builder.py` using `pygltflib`.
- Plane-cards → quads with embedded base-color textures (rgba PNG from UAR). If `use_depth_map`, displace vertices along normal using the depth map sampled on a 32×32 grid (Phase 4 keeps it cheap; finer subdivision in Plan6 if needed).
- Camera and lights serialized as glTF extras with vendor key `cvc_*`.
- Output: `projects/{id}/renders/{scene_hash}.glb`. `scene_hash = sha256(canonical_json(dsl))`.

### D4. Blender headless runner
- `workers/render/blender_runner.py` — orchestrator-side thin wrapper that:
  1. Writes `<scene_hash>.glb` and `<scene_hash>.extras.json` (camera/light/animation extras).
  2. Spawns `blender --background --python workers/render/render.py -- <glb> <extras> <out_dir>` with timeout (default 5 min, override per call).
  3. Streams stdout/stderr line-by-line and emits `RenderProgress` events to the DAG.
  4. On timeout: SIGTERM → 3s grace → SIGKILL. Emits `RenderTimedOut`.
- `workers/render/render.py` — the only place where `bpy` is imported. Reads the glb + extras, sets camera/lights/animation, configures EEVEE, renders one frame to PNG (Phase 4 ships single-frame; sequences come in Plan6).

### D5. Capability negotiation
- `workers/render/capabilities.py` — runs `blender --background --version` and a tiny `bpy` probe script that reports: Blender version, available engines (EEVEE/Cycles), GPU availability, `gltf` IO addon presence.
- Result cached in `apps/api/state/capabilities.json`, refreshed on api startup.
- DSL features gated on capabilities — e.g. Cycles-only nodes refused if only EEVEE is available.

## Critical files to create

```
packages/dsl/schema.json
packages/schemas/python/cvc_schemas/dsl.py
apps/api/src/validation/__init__.py
apps/api/src/validation/physical.py
apps/api/src/validation/findings.py
apps/api/src/render/gltf_builder.py
apps/api/src/render/scene_compiler.py        # SceneGraph + UAR → BlenderDsl
workers/render/blender_runner.py
workers/render/render.py                      # the ONLY bpy file
workers/render/capabilities.py
apps/api/tests/test_physical_validation.py
apps/api/tests/test_gltf_builder.py
```

Extend:
- `apps/api/src/dag/reducers.py` — `DslCompiled`, `DslValidationFailed`, `GltfAssembled`, `RenderProgress`, `RenderTimedOut`, `RenderCompleted`.
- `apps/api/src/orchestrator/router.py` — register `compile_dsl`, `validate_dsl`, `render_preview` (preview is just one frame in Plan4; full sequence in Plan6).

## Verification

1. **LLM nonsense rejected**: craft a `BlenderDsl` with `focal_mm = 0` → `validate` returns `ok=False` with a clear finding; no subprocess spawned.
2. **Happy path**: validated DSL → `.glb` written → `blender --background` renders a PNG under `projects/{id}/renders/{scene_hash}/frame_0000.png`.
3. **Parity probe**: open the same glb in a minimal Three.js sandbox (a temporary HTML file under `apps/web/public/_parity_probe/`) → camera coordinates and light positions visually match the Blender render.
4. **Timeout**: artificially set timeout to 1s for a render that needs 5s → `RenderTimedOut` event fires, no zombie `blender` process (`pgrep blender` returns empty).
5. **Capability gate**: rename `~/Applications/Blender.app` temporarily → capability probe fails gracefully, orchestrator refuses to enqueue renders with a clear error.

## Out of scope

- Cycles path tracing (treat as EEVEE-only for now).
- Multi-frame sequences (Plan6).
- R3F editing of the glb (Plan5).
