# Plan 10 — Accurate Text→3D Generation (Parallel Execution)

> Status: **Not started**
> Depends on: Plan3 (UAR / adapters), Plan4 (Blender DSL + runtime), Plan8 (hybrid-adapter pattern, local Docker discipline)
> Unblocks: subject-accurate previs; retires today's primitive-stack output for object/landscape prompts
> Source: [/plan.md](../plan.md) — same scope, reorganized for concurrent tracks

## Goal

Replace the 6-primitive ceiling in [wire_geometry.py](../apps/orchestrator/src/orchestrator/schemas/wire_geometry.py) with subject-accurate meshes via three routed pathways: **DALL-E 3 → TripoSR** (objects), **Poly Haven** (landscapes), and existing **wire primitives** (abstract only). Add **Shap-E** as the offline-only fallback. Final output: typing `watch` returns a watch mesh, not a stack of cylinders.

## Why parallel execution

The work splits cleanly into four independent surface areas — schema/state, Docker/ML infra, adapters, and graph wiring — each of which can be developed against a stable seam. Dependencies form a shallow DAG, not a long chain. A single sequential pass would stall on Docker image builds (slow) and model downloads (slower) while leaving easy schema work idle. Waves below maximise throughput by running the slow infra tracks in parallel with the fast code tracks.

## Dependency DAG

```
Wave A (foundation, all parallel)
├── A1  MeshAsset schema + UAR + state          ─┐
├── A2  TripoSR Docker service                  ─┤
├── A3  Shap-E Docker service                   ─┤
└── A4  Poly Haven cache scaffold + API recon   ─┤
                                                  │
Wave B (depends on A; tracks parallel within B)   ▼
├── B1  subject_classifier node           (← A1)
├── B2  triposr_client.py                 (← A2)
├── B3  shap_e_client.py                  (← A3)
├── B4  poly_haven_adapter.py             (← A1, A4)
└── B5  Blender runtime glTF branch       (← A1)

Wave C (depends on B; two tracks parallel)
├── C1  text_to_3d_adapter.py             (← B2, B3 optional)
└── C2  mesh_generator node               (← B1, A1; stubs C1 if needed)

Wave D (integration, serial within wave)
├── D1  creative_dispatcher → emit mesh intents
├── D2  graph.py wiring of new nodes
├── D3  routing.py route_after_creative_dispatch
├── D4  queue/tasks/mesh.py
└── D5  End-to-end verification (5 test prompts)

Wave E (cleanup, after D)
├── E1  Trim wire_geometry_system.md to abstract-only
├── E2  Update docs/ARCHITECTURE_SNAPSHOT.md
└── E3  Side-by-side wireframe + mesh visual regression
```

Critical insight: **Waves A, B run with 4–5 concurrent tracks**. Only Wave D is forced-serial (graph wiring touches the same files). A and B together can finish in roughly the time of their slowest task (Docker image builds), not the sum.

## Wave A — Foundation (4 parallel tracks)

### A1 — `MeshAsset` schema + UAR storage + state
- New: `apps/orchestrator/src/orchestrator/schemas/mesh_asset.py` — `MeshAsset(asset_id, glb_path, bounds_m: BBox3, material_summary: Literal["pbr","stylised","wire"], source: Literal["triposr","shap_e","poly_haven"], position, rotation, scale)`.
- Modify: [state.py](../apps/orchestrator/src/orchestrator/state.py) — add `mesh_assets: list[MeshAsset]` and `subject_class: Literal["object","landscape","abstract"] | None`; extend `ExecutionStage` with `mesh_generating`, `mesh_generated`.
- Modify: [schemas/creative.py](../apps/orchestrator/src/orchestrator/schemas/creative.py) — `CreativeIntent.layer_kind` gains `"mesh"`; add optional `target_path: Literal["mesh","image","wire"]`.
- Modify: [apps/api/src/api/uar/__init__.py](../apps/api/src/api/uar) — add `store_mesh(MeshAsset)` / `load_mesh(asset_id)`, content-addressed by `sha256(glb_bytes)`.
- Verification: unit test round-trips a fake `.glb` through `store_mesh`/`load_mesh`; state serialises to JSON without loss.

### A2 — TripoSR Docker service
- New: `docker/triposr/Dockerfile` + `docker/triposr/app.py` — FastAPI service on port 8002. Single endpoint: `POST /generate { image_url } → multipart (glb bytes, bounds JSON)`. Lazy-load model on first request; single-request queue.
- Modify: [docker-compose.yml](../docker-compose.yml) — add `triposr` service (port 8002), reuse the diffusers Dockerfile pattern.
- Verification: `docker compose up triposr` → `curl -F image=@front.png localhost:8002/generate` returns valid glb.

### A3 — Shap-E Docker service
- New: `docker/shap_e/Dockerfile` + `docker/shap_e/app.py` — FastAPI service on port 8003. `POST /generate { prompt } → glb bytes`. Same lazy-load + queue discipline as A2.
- Modify: [docker-compose.yml](../docker-compose.yml) — add `shap_e` service (port 8003).
- Verification: `curl -d '{"prompt":"a wristwatch"}' localhost:8003/generate` returns valid glb.

### A4 — Poly Haven cache scaffold
- New: `data/poly_haven_cache/` directory structure + cache index format (json manifest of slug → file paths).
- Spike: call `https://api.polyhaven.com/assets?t=models` once, dump JSON, eyeball the tag vocabulary so B4 can map subjects → slugs without surprises.
- Verification: cache directory exists; manifest schema documented inline in `poly_haven_adapter.py` docstring.

## Wave B — Component layer (5 parallel tracks)

### B1 — `subject_classifier` node ← A1
- New: `apps/orchestrator/src/orchestrator/nodes/subject_classifier.py` — LLM structured-output node returning `Literal["object", "landscape", "abstract"]` + confidence. Mirror [intent_validator.py](../apps/orchestrator/src/orchestrator/nodes/intent_validator.py) shape.
- Writes to `state.subject_class`. **Does not yet alter routing** — that lands in D2/D3.

### B2 — `triposr_client.py` ← A2
- New: `apps/api/src/api/adapters/triposr_client.py` — async HTTP client to `http://localhost:8002/generate`. Retries 0; bubbles errors to the adapter strategy switch.
- Modify: [apps/api/src/api/settings.py](../apps/api/src/api/settings.py) — `TRIPOSR_URL=http://localhost:8002`.

### B3 — `shap_e_client.py` ← A3
- New: `apps/api/src/api/adapters/shap_e_client.py` — async HTTP client to `http://localhost:8003/generate`.
- Modify: [apps/api/src/api/settings.py](../apps/api/src/api/settings.py) — `SHAP_E_URL=http://localhost:8003`.

### B4 — `poly_haven_adapter.py` ← A1, A4
- New: `apps/api/src/api/adapters/poly_haven_adapter.py` — subject text → asset slug via tag-intersection + name similarity over the recon dump; downloads `.glb` + HDRI; caches under `data/poly_haven_cache/`.
- Modify: [apps/api/src/api/settings.py](../apps/api/src/api/settings.py) — `POLY_HAVEN_API_URL=https://api.polyhaven.com`.

### B5 — Blender runtime glTF import branch ← A1
- Modify: [blender_runtime.py](../apps/orchestrator/src/orchestrator/rendering/blender_runtime.py) — accept `mesh_assets: list[MeshAsset]` alongside `primitives`; for each, emit `bpy.ops.import_scene.gltf(filepath=...)` plus transform block. The two paths coexist.
- Reuse camera/lighting from [previs_renderer.py](../apps/orchestrator/src/orchestrator/rendering/previs_renderer.py).
- Verification: feed a synthetic `MeshAsset` pointing at a checked-in test `.glb`; render produces a PNG visibly different from the wireframe path.

## Wave C — Adapter + node assembly (2 parallel tracks)

### C1 — `text_to_3d_adapter.py` ← B2 (+ B3 optional)
- New: `apps/api/src/api/adapters/text_to_3d_adapter.py` — mirror [hybrid_adapter.py](../apps/api/src/api/adapters/hybrid_adapter.py). Strategies:
  - `openai_assisted` (default): DALL-E 3 reference → TripoSR.
  - `local_fallback`: openai_assisted with Shap-E on TripoSR/DALL-E failure.
  - `local_only`: Shap-E direct (text→3D, no DALL-E).
- Reuse [openai_dalle_adapter.py](../apps/api/src/api/adapters/openai_dalle_adapter.py) verbatim for the reference image step. DALL-E prompt template: `"studio product photo, isolated white background, orthographic front view, {subject}"`.
- Modify: [apps/api/src/api/adapters/__init__.py](../apps/api/src/api/adapters/__init__.py); [settings.py](../apps/api/src/api/settings.py) — `MESH_PIPELINE_STRATEGY=openai_assisted`.
- Until B3 lands, `local_only`/`local_fallback` strategies raise NotImplementedError — that does not block C2.

### C2 — `mesh_generator` node ← B1, A1 (stubs C1 if needed)
- New: `apps/orchestrator/src/orchestrator/nodes/mesh_generator.py` — LangGraph node parallel to `visual_generator`. Walks `CreativeIntent[]`, routes per `target_path`/`subject_class`:
  - `object` → `text_to_3d_adapter`
  - `landscape` → `poly_haven_adapter` (falls back to text_to_3d landscape image → terrain primitive on miss)
  - Returns `MeshAsset[]` into `state.mesh_assets`.
- If C1 still mid-flight, mock the adapter behind a Protocol; swap in real adapter when C1 merges.

## Wave D — Integration (serial)

These touch the same graph/routing files and must land in order on the same branch.

- **D1**: Modify [creative_dispatcher.py](../apps/orchestrator/src/orchestrator/nodes/creative_dispatcher.py) — read `subject_class`; emit `CreativeIntent(layer_kind="mesh")` for `object`/`landscape`; leave `abstract` on the existing image+wire path.
- **D2**: Modify [graph.py](../apps/orchestrator/src/orchestrator/graph.py) — insert `subject_classifier` between `intent_validator` and `generation_mode_parser`; wire `mesh_generator` parallel to `visual_generator`.
- **D3**: Modify [routing.py](../apps/orchestrator/src/orchestrator/routing.py) — new `route_after_creative_dispatch`: any `layer_kind="mesh"` → `mesh_generator`, else → `visual_generator`.
- **D4**: New `apps/api/src/api/queue/tasks/mesh.py` — arq task wrapping the pipeline async. Pattern from [tasks/visual.py](../apps/api/src/api/queue/tasks/visual.py).
- **D5**: End-to-end verification — five prompts:
  | Prompt | Expected route | Expected source |
  |---|---|---|
  | `watch` | mesh | `triposr` |
  | `mountain` | mesh | `poly_haven` |
  | `bottle` | mesh | `triposr` |
  | `house` | mesh | `triposr` |
  | `swirling dread` | abstract | wire primitives |

## Wave E — Cleanup (after D)

- **E1**: Trim [wire_geometry_system.md](../apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md) — drop the mountain/terrain sections; rewrite for `subject_class == "abstract"` only.
- **E2**: Update [docs/ARCHITECTURE_SNAPSHOT.md](../docs/ARCHITECTURE_SNAPSHOT.md) — new nodes (`subject_classifier`, `mesh_generator`), schemas (`MeshAsset`), adapters, Docker services, env vars. Set `Last synced` to merge date.
- **E3**: Visual regression — render wireframe AND mesh-imported render side-by-side from `blender_runtime.py`; store both PNGs per run for inspection in the [Viewport.tsx](../apps/web/components/RenderStudio/Viewport.tsx).

## Critical files (grouped by track for assignment)

```
A1   apps/orchestrator/src/orchestrator/schemas/mesh_asset.py        (new)
A1   apps/orchestrator/src/orchestrator/state.py                     (modify)
A1   apps/orchestrator/src/orchestrator/schemas/creative.py          (modify)
A1   apps/api/src/api/uar/__init__.py                                (modify)
A2   docker/triposr/{Dockerfile,app.py}                              (new)
A2   docker-compose.yml                                              (modify)
A3   docker/shap_e/{Dockerfile,app.py}                               (new)
A3   docker-compose.yml                                              (modify, coordinate with A2)
A4   data/poly_haven_cache/                                          (new scaffold)
B1   apps/orchestrator/src/orchestrator/nodes/subject_classifier.py  (new)
B2   apps/api/src/api/adapters/triposr_client.py                     (new)
B3   apps/api/src/api/adapters/shap_e_client.py                      (new)
B4   apps/api/src/api/adapters/poly_haven_adapter.py                 (new)
B5   apps/orchestrator/src/orchestrator/rendering/blender_runtime.py (modify)
C1   apps/api/src/api/adapters/text_to_3d_adapter.py                 (new)
C1   apps/api/src/api/adapters/__init__.py                           (modify)
C1   apps/api/src/api/settings.py                                    (modify)
C2   apps/orchestrator/src/orchestrator/nodes/mesh_generator.py      (new)
D1   apps/orchestrator/src/orchestrator/nodes/creative_dispatcher.py (modify)
D2   apps/orchestrator/src/orchestrator/graph.py                     (modify)
D3   apps/orchestrator/src/orchestrator/routing.py                   (modify)
D4   apps/api/src/api/queue/tasks/mesh.py                            (new)
E1   apps/orchestrator/src/orchestrator/prompts/wire_geometry_system.md (modify)
E2   docs/ARCHITECTURE_SNAPSHOT.md                                   (modify)
```

## Coordination notes

- **Shared file conflicts**: Three tracks (A2/A3, C1, B2/B3) all touch `docker-compose.yml` and `settings.py`. Land A1+A2+A3 first as a single foundation PR to avoid merge conflicts on those files; then run B1–B5 in parallel branches.
- **Adapter Protocol contract**: Before Wave B starts, freeze the adapter return type as `MeshAsset` (from A1) so C2 can stub against the type, not the implementation. This is the only API surface C1 and C2 share.
- **Docker model download time**: A2 and A3 will both pull multi-GB checkpoints on first build. Start those builds the moment Wave A kicks off — they run in the background while A1 / A4 finish.
- **Graph wiring is the merge point**: All Wave D edits land on one branch in the listed order; no parallelism inside Wave D.

## Risks & mitigations

| Risk | Mitigation | Owning track |
|---|---|---|
| TripoSR quality for intricate subjects | DALL-E reference template tuned in C1 | C1 |
| TripoSR memory (~6–8 GB on M4) | Lazy-load + single-request queue inside A2 container | A2 |
| Poly Haven catalogue small (~120 models) | Fallback in C2: Poly Haven → TripoSR landscape image → primitive terrain | B4 / C2 |
| OpenAI key unavailable / offline | `MESH_PIPELINE_STRATEGY=local_only` switches to Shap-E (B3+C1) | C1 |
| Mesh+primitive collision in renders | Gated by `subject_class` in D1; abstract is the only primitive consumer | D1 |
| Parallel branches conflicting on `settings.py` | Add all new env vars in A1's PR up front (empty defaults) so B/C tracks only fill values | A1 |

## Out of scope

- Texture upscaling / PBR material baking (TripoSR's untextured output is acceptable per the "game-asset / stylised" quality bar).
- Multi-image-to-3D refinement (single front-view reference only).
- Animation rigs on imported character meshes.
- Replacing the existing primitive path for `abstract` subjects — it stays.
