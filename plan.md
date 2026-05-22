# Accurate Text→3D Generation (Claude blender-mcp parity)

## Context

Today, typing `watch`, `mountain`, `people`, `bottle`, `house` into this project produces a stack of 10–20 primitives (box/cylinder/sphere/cone/mountain/terrain) — by design. The LLM is constrained to those six kinds by [apps/orchestrator/src/orchestrator/schemas/wire_geometry.py](apps/orchestrator/src/orchestrator/schemas/wire_geometry.py) and the system prompt at [apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md](apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md). That ceiling is why a "watch" reads as boxes-and-cylinders, not a watch.

Claude Desktop's blender-mcp gets accurate output by combining three pathways and routing per subject: (1) ML mesh generation, (2) asset libraries, (3) richer procedural code. This plan brings the same three pathways into this project, sized to its local-first constraints.

**User direction (confirmed):**
- Primary path: **Local ML mesh** (TripoSR/Shap-E on the M4).
- Landscapes: **Replace `mountain`/`terrain` primitives with Poly Haven** asset lookups.
- Quality bar: **Game-asset / stylised** (PBR-grade, recognisable details, not photoreal).
- Budget: **OpenAI + Local combined** — use DALL-E 3 (already wired in [openai_dalle_adapter.py](apps/api/src/api/adapters/openai_dalle_adapter.py)) as the reference-image step feeding local TripoSR.

---

## Architecture decisions

### 1. Pipeline: text → reference image → mesh (the key insight)

TripoSR is image-to-3D, not text-to-3D. The cleanest local-first pipeline is:

```
prompt ──► DALL-E 3 ──► front-facing reference PNG ──► TripoSR (local Docker) ──► .glb ──► Blender import
                                                  └► Shap-E (local, text-direct) as offline fallback
```

This composes two adapters that already match the project's hybrid pattern: a cloud LLM/image step + a local inference container. Shap-E (text→3D directly) provides a fully-offline fallback when DALL-E is unavailable, matching Plan8 philosophy.

### 2. Subject classifier decides which pathway

New tiny LLM-structured-output classifier node before `creative_dispatcher`:

| Class | Pathway | Output |
|---|---|---|
| `object` (watch, bottle, person, car, chair, house, animal…) | DALL-E → TripoSR | `MeshAsset` (.glb) |
| `landscape` (mountain, valley, forest, ocean, dunes) | Poly Haven lookup | `MeshAsset` + HDRI |
| `abstract` / unmatched | Existing wireframe primitives (unchanged) | `WireframeGeometry` |

Classifier returns `Literal["object", "landscape", "abstract"]` — no hand-rolled keyword matching.

### 3. New `MeshAsset` schema joins `LayerAsset` in UAR

Today UAR stores `LayerAsset` (PNG + alpha + depth — image-only). Add `MeshAsset` for triangle meshes. Both share UAR's content-addressed hash storage.

### 4. Blender runtime gains a `mesh_imports` code path

[blender_runtime.py](apps/orchestrator/src/orchestrator/rendering/blender_runtime.py) currently emits primitives from `WirePrimitive`. Add a second branch: when given `MeshAsset` records, call `bpy.ops.import_scene.gltf(filepath=...)`, normalise scale to metric, and place by position/rotation from the asset's bounds. The two paths can coexist — a scene can mix imported meshes (subject) with primitive ground.

---

## File-level changes

### New files

| Path | Purpose |
|---|---|
| `apps/api/src/api/adapters/text_to_3d_adapter.py` | Orchestrates the DALL-E → TripoSR pipeline. Mirrors `hybrid_adapter.py` shape — same `translate` / `execute` / `cost_estimate` contract. Strategies: `local_only` (Shap-E direct), `local_fallback` (DALL-E→TripoSR with Shap-E fallback), `openai_assisted` (always DALL-E→TripoSR). |
| `apps/api/src/api/adapters/triposr_client.py` | Thin HTTP client to local TripoSR service on `localhost:8002`. POST `/generate` { image_url } → `.glb` bytes + bounds JSON. |
| `apps/api/src/api/adapters/shap_e_client.py` | Thin HTTP client to local Shap-E service on `localhost:8003`. POST `/generate` { prompt } → `.glb`. |
| `apps/api/src/api/adapters/poly_haven_adapter.py` | Queries the public Poly Haven JSON API (`https://api.polyhaven.com/assets?t=models`), maps subject text → asset slug via tag intersection + name similarity, downloads the .glb and HDRI, caches under `data/poly_haven_cache/`. |
| `apps/orchestrator/src/orchestrator/schemas/mesh_asset.py` | `MeshAsset(BaseModel)` — fields: `asset_id`, `glb_path`, `bounds_m: BBox3`, `material_summary: Literal["pbr","stylised","wire"]`, `source: Literal["triposr","shap_e","poly_haven"]`, `position`, `rotation`, `scale`. |
| `apps/orchestrator/src/orchestrator/nodes/subject_classifier.py` | LLM structured-output node returning `{class, confidence, suggested_path}`. Mirrors `intent_validator.py` shape. |
| `apps/orchestrator/src/orchestrator/nodes/mesh_generator.py` | LangGraph node injected via `build_graph` (parallel to `visual_generator`). Walks `CreativeIntent[]`, calls the right adapter, returns `MeshAsset[]`. |
| `apps/api/src/api/queue/tasks/mesh.py` | arq task that runs the pipeline async; parallels `tasks/visual.py`. |
| `docker/triposr/Dockerfile` + `app.py` | FastAPI service wrapping TripoSR inference on Metal/CPU. Single endpoint. |
| `docker/shap_e/Dockerfile` + `app.py` | FastAPI service wrapping Shap-E (text→3D direct). |

### Modified files

| Path | Change |
|---|---|
| [apps/orchestrator/src/orchestrator/state.py](apps/orchestrator/src/orchestrator/state.py) | Add `mesh_assets: list[MeshAsset]` and `subject_class: Literal["object","landscape","abstract"] \| None` to `AgentState`. Extend `ExecutionStage` with `mesh_generating`, `mesh_generated`. |
| [apps/orchestrator/src/orchestrator/schemas/creative.py](apps/orchestrator/src/orchestrator/schemas/creative.py) | `CreativeIntent.layer_kind` gains `"mesh"`. Add optional `target_path: Literal["mesh","image","wire"]`. |
| [apps/orchestrator/src/orchestrator/nodes/creative_dispatcher.py](apps/orchestrator/src/orchestrator/nodes/creative_dispatcher.py) | Read `subject_class`; emit `CreativeIntent(layer_kind="mesh")` for object/landscape, leave abstract on the existing image+wire path. |
| [apps/orchestrator/src/orchestrator/graph.py](apps/orchestrator/src/orchestrator/graph.py) | Insert `subject_classifier` between `intent_validator` and `generation_mode_parser`; wire `mesh_generator` parallel to `visual_generator`; add conditional edge. |
| [apps/orchestrator/src/orchestrator/routing.py](apps/orchestrator/src/orchestrator/routing.py) | New `route_after_creative_dispatch`: if any intent is `layer_kind="mesh"` → `mesh_generator`, else current → `visual_generator`. |
| [apps/orchestrator/src/orchestrator/rendering/blender_runtime.py](apps/orchestrator/src/orchestrator/rendering/blender_runtime.py) | Accept `mesh_assets: list[MeshAsset]` alongside `primitives`. For each mesh asset, emit `bpy.ops.import_scene.gltf(filepath=...)` plus a transform block. Reuse existing camera/lighting setup. |
| [apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md](apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md) | Trim — only runs now for `subject_class == "abstract"` (and small props the mesh path doesn't cover). Remove the mountain/terrain sections (Poly Haven owns landscape now). |
| [apps/api/src/api/adapters/__init__.py](apps/api/src/api/adapters/__init__.py) | Export new adapters. |
| [apps/api/src/api/uar/__init__.py](apps/api/src/api/uar/) | Add `store_mesh(MeshAsset)` / `load_mesh(asset_id)` next to existing image helpers. Content-addressed by `sha256(glb_bytes)`. |
| [docker-compose.yml](docker-compose.yml) | Add `triposr` (port 8002) and `shap_e` (port 8003) services. Reuse the diffusers Dockerfile pattern. |
| [apps/api/src/api/settings.py](apps/api/src/api/settings.py) | New env vars: `TRIPOSR_URL=http://localhost:8002`, `SHAP_E_URL=http://localhost:8003`, `POLY_HAVEN_API_URL=https://api.polyhaven.com`, `MESH_PIPELINE_STRATEGY=openai_assisted`. |
| [docs/ARCHITECTURE_SNAPSHOT.md](docs/ARCHITECTURE_SNAPSHOT.md) | Update with new nodes, schemas, adapters, Docker services, env vars. Mark `Last synced`. |

### Reused (do not rewrite)

- [apps/api/src/api/adapters/openai_dalle_adapter.py](apps/api/src/api/adapters/openai_dalle_adapter.py) — reference image generation step.
- [apps/api/src/api/adapters/hybrid_adapter.py](apps/api/src/api/adapters/hybrid_adapter.py) — pattern template for `text_to_3d_adapter.py` (strategies, `_record_generation`, project context plumbing).
- [apps/api/src/api/queue/tasks/visual.py](apps/api/src/api/queue/tasks/visual.py) — pattern template for `tasks/mesh.py`.
- [apps/orchestrator/src/orchestrator/nodes/intent_validator.py](apps/orchestrator/src/orchestrator/nodes/intent_validator.py) — pattern template for `subject_classifier.py` (structured-output LLM node).
- [apps/orchestrator/src/orchestrator/rendering/previs_renderer.py](apps/orchestrator/src/orchestrator/rendering/previs_renderer.py) — camera setup logic to reuse when rendering imported meshes.

---

## Why this gets us "type 'watch' → get a watch"

| Subject | Today | After this plan |
|---|---|---|
| `watch` | 20 stacked cylinders/boxes (current `wire_geometry_system.md` example) | DALL-E 3 renders a clean reference photo → TripoSR returns a real watch mesh with case, bezel, dial, strap topology |
| `mountain` | `mountain` primitive (cone + noise) | Poly Haven `rocky_terrain_02` or similar — actual sculpted geometry |
| `bottle` | Stacked cylinders | TripoSR mesh from DALL-E reference — curved profile, neck shoulders |
| `house` | Box + cone roof | TripoSR mesh — windows, eaves, porch |
| `people` | (Today: refuses or stacks ellipsoids) | TripoSR character mesh from DALL-E figure render |

The "accuracy" Claude blender-mcp shows comes from neural mesh inference, not better LLM prompts. This plan adds that inference layer.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| TripoSR quality for small/intricate subjects (watches, jewellery) | DALL-E 3 reference image is the lever — prompt it with "studio product photo, isolated white background, orthographic front view" for clean input. |
| TripoSR memory footprint on M4 (~6–8GB) | Lazy-load model, single-request queue inside the Docker service. Already a Plan8 pattern. |
| Poly Haven catalogue is small (~120 models) | Fallback chain: Poly Haven → TripoSR with DALL-E landscape image → existing primitive `terrain` (kept as floor-of-last-resort). |
| OpenAI key unavailable / offline | `MESH_PIPELINE_STRATEGY=local_only` switches to Shap-E direct. |
| MeshAsset import collides with existing wireframe path | The two paths are gated by `subject_class` — only `abstract` continues through the primitive path. No mixed rendering of the same subject. |

---

## Verification (end-to-end)

1. **Unit**: pytest covers `subject_classifier` (object/landscape/abstract for 12 sample prompts), `text_to_3d_adapter` (strategy routing), `poly_haven_adapter` (tag lookup, cache hit/miss).
2. **Integration — local only**:
   - `docker compose up triposr shap_e` (+ existing redis/diffusers)
   - `MESH_PIPELINE_STRATEGY=local_only python -m apps.api …`
   - POST `/projects/.../prompt` with `"a wristwatch"` — expect `MeshAsset` with `source=shap_e` in the resulting `AgentState`.
3. **Integration — OpenAI assisted**:
   - Set `OPENAI_API_KEY`, `MESH_PIPELINE_STRATEGY=openai_assisted`.
   - Run the five test prompts: `watch`, `mountain`, `people`, `bottle`, `house`.
   - Confirm `mountain` is routed to `poly_haven` (not TripoSR), others to `triposr`.
   - Inspect the rendered glb in the Three.js viewport at [Viewport.tsx](apps/web/components/RenderStudio/Viewport.tsx) — meshes should visibly read as the subject from any angle.
4. **Visual regression**: render the wireframe preview AND the new mesh-imported render side-by-side from `blender_runtime.py` — store both PNGs in the run output for inspection.
5. **Graph health**: `uvx code-review-graph detect-changes --brief` to confirm no broken imports / risk-scored review of the new adapter wiring.
6. **Architecture snapshot**: update `docs/ARCHITECTURE_SNAPSHOT.md` and verify all new nodes/schemas/services appear.

---

## Suggested implementation order

1. `MeshAsset` schema + UAR storage + `mesh_assets` state field (smallest seam, no behaviour change).
2. `subject_classifier` node + routing (still produces today's output — only adds classification metadata).
3. `triposr` Docker service stood up + `triposr_client.py` smoke test (independent of LangGraph wiring).
4. `text_to_3d_adapter.py` (DALL-E reuse + TripoSR call).
5. `mesh_generator` node + `creative_dispatcher` routing of `layer_kind="mesh"`.
6. `blender_runtime.py` glTF import branch + viewport verification.
7. `poly_haven_adapter.py` for landscape replacement.
8. `shap_e` Docker service + offline fallback wiring.
9. Trim `wire_geometry_system.md` to abstract-only; update `ARCHITECTURE_SNAPSHOT.md`.

Each step is independently testable and leaves the existing pipeline functional.
