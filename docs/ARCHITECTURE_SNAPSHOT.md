# Architecture Snapshot

> Auto-maintained reference. Update this file whenever nodes, state fields, routing conditions,
> schemas, routes, or infrastructure change. See `CLAUDE.md` for the update rule.
>
> Last synced: 2026-05-22 (Plan10 — text→3D pipeline)

---

## Graph Stats (as of last sync)

| Metric | Value |
|---|---|
| Files | 5 353 |
| Total nodes | 57 347 |
| Total edges | 270 747 |
| Languages | Python, TypeScript, JavaScript, TSX, C |
| Last graph update | 2026-05-19 |

---

## Repo Layout

```
.
├── apps/
│   ├── api/          FastAPI surface layer (Plan2+)
│   │   └── src/api/
│   │       ├── adapters/         Visual-generation adapters
│   │       ├── dag/              OT reducers
│   │       ├── memory/           Five-tier hierarchical memory
│   │       ├── orchestrator/     Budget, creative dispatch, gltf assembly, OT
│   │       ├── persistence/      SQLite project DB
│   │       ├── queue/            arq + Redis render queue
│   │       ├── render/           glTF builder, scene compiler
│   │       ├── routes/           FastAPI route modules
│   │       ├── uar/              Universal Asset Registry
│   │       ├── validation/       Finding helpers
│   │       ├── main.py           FastAPI app entrypoint
│   │       └── settings.py
│   ├── orchestrator/ LangGraph engine (Plan1)
│   │   └── src/orchestrator/
│   │       ├── cinematics/       camera_planner
│   │       ├── nodes/            All graph node functions
│   │       ├── rendering/        blender_runtime, previs_renderer, sheet_composer
│   │       ├── schemas/          Pydantic schema definitions
│   │       ├── graph.py          StateGraph assembly
│   │       ├── routing.py        Conditional-edge functions
│   │       ├── state.py          AgentState + enums
│   │       └── llm.py
│   └── web/          Next.js 14 App Router frontend
│       ├── app/(workspace)/page.tsx
│       ├── components/
│       │   ├── ControlPanel/     Left-panel UI components
│       │   └── RenderStudio/     Right-panel Three.js viewport
│       ├── state/projectStore.ts Zustand store
│       └── lib/api.ts, ws.ts
├── packages/
│   ├── dsl/          JSON schema for Blender DSL
│   └── schemas/      Shared schema package
├── workers/
│   └── render/       Headless Blender worker
├── docker/
│   ├── diffusers/    Local diffusers Docker image (SD 1.5 / SDXL)
│   ├── triposr/      Plan10. TripoSR image→3D service (port 8002)
│   └── shap_e/       Plan10. Shap-E text→3D service (port 8003)
├── data/
│   └── poly_haven_cache/   Plan10. Local cache for Poly Haven glb/hdri downloads
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md           Canonical vision doc (source of truth)
│   └── ARCHITECTURE_SNAPSHOT.md  ← this file
└── plans/            PlanN.md versioned build contracts
```

---

## Why LangChain + LangGraph

- **LangGraph** — the pipeline is a cyclic graph with conditional routing (ambiguity, validation retries, wireframe→model→video, feedback loops) and human-in-the-loop interrupts. `StateGraph` gives us typed `AgentState`, reducer-based merging, and free checkpointing (`MemorySaver` / `SqliteSaver`) that powers `/checkpoints`, `/forks`, and `/approvals` without us building it.
- **LangChain** — provides the LLM I/O surface: `with_structured_output` enforces Pydantic contracts (`IntentSpec`, `BlenderDsl`) so OpenAI is only ever called for typed JSON, and `BaseChatModel` lets `llm_settings.py` swap providers per-node without touching node code.

---

## LangGraph State Machine

### AgentState fields (`apps/orchestrator/src/orchestrator/state.py`)

| Field | Type | Description |
|---|---|---|
| `project_id` | `str` | Unique project identifier |
| `user_prompt` | `str` | Raw user input |
| `project_canon` | `ProjectCanon` | Hard-locked project rules (aspect ratio, aesthetic) |
| `intent` | `IntentSpec \| None` | Typed intent extracted by IntentValidator |
| `ambiguity_score` | `float` | 0.0–1.0 score driving routing |
| `semantic_locks` | `list[SemanticLock]` | Frozen elements across iterations |
| `scene_graph` | `BlenderDsl \| None` | Current validated Blender DSL |
| `speculative_variants` | `list[BlenderDsl]` | 2–3 low-res alternatives (speculative batch) |
| `validation_findings` | `list[ValidationFinding]` | Physical validation errors/warnings |
| `execution_status` | `ExecutionStage` | Current pipeline stage |
| `retry_count` | `int` | Validation retry counter |
| `error_log` | `list[str]` | Accumulated error messages |
| `creative_intents` | `list[CreativeIntent]` | Translated visual generation intents |
| `generated_assets` | `list[LayerAsset]` | Subject / Background / FX layer assets |
| `creative_events` | `list[CreativeEvent]` | Audit log of creative dispatch events |
| `generation_mode` | `str` (GenerationMode enum) | `wireframe` \| `model` \| `video` |
| `previsualization` | `Previsualization \| None` | Wireframe previs renders |
| `previsualization_feedback` | `str \| None` | User feedback on wireframe |
| `model_renders` | `list[str] \| None` | URLs to 2D model renders |
| `model_feedback` | `str \| None` | User feedback on model renders |
| `gltf_assembled_path` | `str \| None` | API URL path to assembled .glb |
| `subject_class` | `Literal["object","landscape","abstract"] \| None` | Plan10 routing key (text→3D vs wireframe) |
| `subject_class_confidence` | `float` | LLM confidence on `subject_class` (0–1) |
| `mesh_assets` | `list[MeshAsset]` | Plan10 mesh outputs (TripoSR / Shap-E / Poly Haven) |

### ExecutionStage values

```
idle → intent_validated → awaiting_human_approval
                        → speculative_batching
                        → semantic_lock_applied → scene_graph_generated
                             → previsualization_generated
                               ├─ previsualization_approved
                               └─ previsualization_feedback
                             → model_generated
                               ├─ model_approved
                               └─ model_feedback
                             → creative_dispatching → visual_generating
                             → budget_exceeded
                             → physical_validation_failed
                             → dsl_compiled → dsl_validation_failed
                             → gltf_assembled
                             → render_progress → render_timed_out
                             → render_completed → completed
                             → subject_classified           (Plan10)
                             → mesh_generating → mesh_generated / mesh_generation_failed
failed
```

---

## Graph Nodes (`apps/orchestrator/src/orchestrator/nodes/`)

| Node | File | Kind | Responsibility |
|---|---|---|---|
| `intent_validator` | `intent_validator.py` | LLM (structured output) | Extracts `IntentSpec`, computes `ambiguity_score`, hard-validates against rules |
| `generation_mode_parser` | `generation_mode_parser.py` | Pure Python | Sets `generation_mode` from intent/prompt |
| `semantic_locker` | `semantic_locker.py` | Pure Python | Diffs current vs prior checkpoint, emits `SemanticLock`s |
| `scene_graph_generator` | `scene_graph_generator.py` | LLM (structured output) | Produces typed `BlenderDsl`; lock violations → capped retry |
| `wireframe_previs_generator` | `wireframe_previs_generator.py` | Deterministic | Renders camera-frustum wireframes from DSL via `camera_planner` + `previs_renderer` |
| `creative_dispatcher` | `creative_dispatcher.py` | Pure Python | Translates DSL into `CreativeIntent` list; emits `CreativeIntentDispatched` events |
| `physical_validation` | `physical_validation.py` | Pure Python (zero LLM) | Strict geometry checks: focal length, camera-AABB collision, light sanity, duration cap |
| `dsl_compiler` | `dsl_compiler.py` | Pure Python | Compiles validated DSL to Blender-executable form |
| `speculative_batcher` | `speculative_batcher.py` | LLM | Generates 2–3 `BlenderDsl` variants on medium ambiguity |
| `visual_generator` | _(injected via `build_graph`)_ | Adapter call | Calls `HybridAdapter` / `ReplicateAdapter` for image generation |
| `gltf_assembler` | _(injected via `build_graph`)_ | Pure Python | Assembles glTF/glb from layer assets; sets `gltf_assembled_path` |
| `subject_classifier` | `subject_classifier.py` | LLM (structured output) | Plan10. Labels prompt as `object` / `landscape` / `abstract`; sets `subject_class` |
| `mesh_generator` | `mesh_generator.py` + `api/orchestrator/mesh_dispatch.py` | Adapter call | Plan10. Resolves mesh intents via `TextTo3DAdapter` (DALL-E+TripoSR or Shap-E) or `PolyHavenAdapter` |

---

## Routing Conditions (`apps/orchestrator/src/orchestrator/routing.py`)

### After `intent_validator`

| Condition | Destination |
|---|---|
| `execution_status == "failed"` | `END` (fail) |
| `ambiguity_score > 0.8` | `END` (human_approval interrupt) |
| `0.4 < ambiguity_score <= 0.8` | `speculative_batcher` |
| `ambiguity_score <= 0.4` | `subject_classifier` → `generation_mode_parser` (proceed) |

### After `creative_dispatcher` (Plan10)

| Condition | Destination |
|---|---|
| Any intent has `output_kind == "mesh"` | `mesh_generator` |
| Otherwise | `visual_generator` |

### After `wireframe_previs_generator`

| Condition | Destination |
|---|---|
| `status == "previsualization_approved"` AND `mode == "wireframe"` | `END` |
| `status == "previsualization_approved"` AND `mode in {model, video}` | `creative_dispatcher` |
| `status == "previsualization_feedback"` | `wireframe_previs_generator` (loop) |
| _(reject)_ | `scene_graph_generator` (rewind) |

### After `visual_generator`

| Condition | Destination |
|---|---|
| `status == "model_approved"` AND `mode == "model"` | `END` |
| `status == "model_approved"` AND `mode == "video"` | `physical_validation` |
| `status == "model_feedback"` | `visual_generator` (loop) |
| _(reject)_ | `wireframe_previs_generator` (rewind) |

### After `physical_validation`

| Condition | Destination |
|---|---|
| No errors | `dsl_compiler` (success) |
| Has errors AND `retry_count < 1` | `scene_graph_generator` (retry) |
| Has errors AND `retry_count >= 1` | `END` (fail) |

### Interrupt points (human-in-the-loop)

- `speculative_batcher` — presents variants; user selects or rejects
- `wireframe_previs_generator` — user approves / gives feedback / rejects wireframe
- `visual_generator` (when wired) — user approves / gives feedback / rejects model renders

---

## Schema Definitions (`apps/orchestrator/src/orchestrator/schemas/`)

| Schema | File | Description |
|---|---|---|
| `IntentSpec` | `intent.py` | Typed structured output from LLM intent extraction |
| `BlenderDsl` | `dsl.py` | Versioned Blender execution DSL (strict JSON contract) |
| `ProjectCanon` | `canon.py` | Immutable project rules (aspect ratio, aesthetic, duration cap) |
| `CreativeIntent` | `creative.py` | Provider-agnostic visual generation intent |
| `LayerAsset` | `creative.py` | Subject / Background / FX asset with alpha + depth |
| `Previsualization` | `previsualization.py` | Wireframe render set with metadata |
| `WireGeometry` | `wire_geometry.py` | Camera-frustum wireframe geometry primitives |
| `MeshAsset` | `mesh_asset.py` | Plan10. Content-addressed glb + bounds + transform |

---

## API Routes (`apps/api/src/api/routes/`)

| Module | Prefix | Purpose |
|---|---|---|
| `projects.py` | `/projects` | CRUD for projects |
| `runs.py` | `/runs` | Stream LangGraph run state via SSE |
| `approvals.py` | `/approvals` | Resume graph at human-approval breakpoints |
| `checkpoints.py` | `/checkpoints` | Time-travel / rollback via MemorySaver |
| `forks.py` | `/forks` | Fork a project state into a new branch |
| `locks.py` | `/locks` | Read / clear semantic locks |
| `ot.py` | `/ot` | Apply OT mutations to active scene graph |
| `creative.py` | `/creative` | Trigger creative dispatch |
| `assets.py` | `/assets` | Read / download UAR assets |
| `render.py` | `/render` | Enqueue preview and final renders |
| `cancel.py` | `/cancel` | Cancel in-flight render jobs |
| `style.py` | `/style` | Style pin management |
| `generation_settings.py` | `/generation-settings` | Read / update generation settings |
| `llm_settings.py` | `/llm-settings` | Override LLM model/temperature at runtime |

---

## Visual Generation Adapters (`apps/api/src/api/adapters/`)

| Adapter | File | Description |
|---|---|---|
| `BaseAdapter` | `base.py` | Abstract interface: `generate(intent) → LayerAsset` |
| `HybridAdapter` | `hybrid_adapter.py` | Local-first (diffusers Docker) with Replicate fallback (Plan8) |
| `LocalDockerAdapter` | `local_docker_adapter.py` | Calls local diffusers service on `localhost:8001` |
| `ComfyUIAdapter` | `comfyui_adapter.py` | Translates `CreativeIntent` to ComfyUI workflow JSON |
| `TextTo3DAdapter` | `text_to_3d_adapter.py` | Plan10. DALL-E 3 reference → TripoSR (default) with Shap-E fallback |
| `TripoSRClient` | `triposr_client.py` | Plan10. HTTP client for the TripoSR Docker service on :8002 |
| `ShapEClient` | `shap_e_client.py` | Plan10. HTTP client for the Shap-E Docker service on :8003 |
| `PolyHavenAdapter` | `poly_haven_adapter.py` | Plan10. Text → Poly Haven glb landscape asset, locally cached |

---

## Five-Tier Hierarchical Memory (`apps/api/src/api/memory/`)

| Tier | File | Description |
|---|---|---|
| Project Canon | `canon.py` | Hard-locked rules; never mutated mid-session |
| UAR (Universal Asset Registry) | `uar.py` | Content-addressed locked assets (hash → alpha/depth) |
| Working Memory | `working.py` | Active scene graph + immediate context |
| Compressed Summaries | `compressed.py` | Lightweight logs of prior iterations |
| Semantic Retrieval Index | `retrieval.py` + `embeddings.py` | Rejected concepts / style overrides; vector search |
| Context Builder | `build_context.py` | Assembles memory tiers into LLM context window |

---

## Render Queue (`apps/api/src/api/queue/`)

| Component | File | Description |
|---|---|---|
| Dispatch | `dispatch.py` | Enqueue jobs to arq + Redis |
| Worker | `worker.py` | arq worker entrypoint |
| Cancellation | `cancellation.py` | Cascade-cancel dependents |
| Task: preview render | `tasks/render_preview.py` | Low-res streamed preview |
| Task: final render | `tasks/render_final.py` | Hard-gated mp4 export |
| Task: DSL validation | `tasks/validate_dsl.py` | Pre-queue schema check |
| Task: visual generation | `tasks/visual.py` | Image layer generation task |
| Task: mesh generation | `tasks/mesh.py` | Plan10. Runs text→3D pipeline and persists `MeshAsset` |
| Task: compress history | `tasks/compress_history.py` | Periodic memory compression |

---

## Orchestrator Subsystems (`apps/api/src/api/orchestrator/`)

| Module | Description |
|---|---|
| `budget.py` | Token + compute budget ledger; hard limits on retries / speculative spend |
| `creative_dispatch.py` | Maps `BlenderDsl` → `CreativeIntent` list |
| `gltf_assembly.py` | Assembles layer assets into a single glTF/glb |
| `ot.py` | Operational Transformations — transactional scene graph mutations |
| `scene_graph_path.py` | Path helpers for scene graph traversal |
| `mesh_dispatch.py` | Plan10. Builds the `mesh_generator` node with text→3D and Poly Haven adapters |

---

## Frontend (`apps/web/`)

| Component | Path | Description |
|---|---|---|
| Workspace page | `app/(workspace)/page.tsx` | Root two-panel layout |
| Project store | `state/projectStore.ts` | Zustand global state |
| Prompt Composer | `components/ControlPanel/PromptComposer.tsx` | Left-panel prompt input |
| Phase Status Bar | `components/ControlPanel/PhaseStatusBar.tsx` | Current execution stage |
| State Timeline | `components/ControlPanel/StateTimeline.tsx` | Checkpoint history |
| Lock Manager | `components/ControlPanel/LockManager.tsx` | Semantic lock UI |
| Budget Indicator | `components/ControlPanel/BudgetIndicator.tsx` | Spend / remaining budget |
| Render Queue | `components/ControlPanel/RenderQueue.tsx` | Job status |
| Timeline | `components/ControlPanel/Timeline.tsx` | Scene timeline |
| Style Pin Button | `components/ControlPanel/StylePinButton.tsx` | Lock style elements |
| Wireframe Viewer | `components/WireframeViewer.tsx` | Renders `Previsualization` output |
| Viewport | `components/RenderStudio/Viewport.tsx` | Three.js / R3F 2.5D render studio |
| Settings Drawer | `components/SettingsDrawer.tsx` | LLM + generation settings |
| Generation Settings | `components/GenerationSettingsPanel.tsx` | Provider / model config |
| Generation Stats | `components/GenerationStatsPanel.tsx` | Token / cost stats |
| API client | `lib/api.ts` | REST wrappers |
| WS client | `lib/ws.ts` | SSE / WebSocket streaming |

---

## Infrastructure

### Docker services (`docker-compose.yml`)

| Service | Image | Port | Purpose |
|---|---|---|---|
| `redis` | `redis:7-alpine` | 6379 | arq job queue + pub/sub |
| `diffusers` | `./docker/diffusers` | 8001 | Local SD 1.5 / SDXL inference (Mac M-series, CPU) |
| `triposr` | `./docker/triposr` | 8002 | Plan10. Image→3D mesh via TripoSR |
| `shap_e` | `./docker/shap_e` | 8003 | Plan10. Text→3D mesh via Shap-E (offline fallback) |

### Key environment variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for all LLM structured-output calls |
| `DOCKER_SMALLER_MODEL` | `true` | `true` = SD 1.5, `false` = SDXL |
| `DOCKER_DEVICE` | `cpu` | `cpu` for Mac M-series, `cuda` for GPU Linux |
| `TRIPOSR_URL` | `http://localhost:8002` | TripoSR service base URL (Plan10) |
| `SHAP_E_URL` | `http://localhost:8003` | Shap-E service base URL (Plan10) |
| `POLY_HAVEN_API_URL` | `https://api.polyhaven.com` | Poly Haven public API (Plan10) |
| `POLY_HAVEN_CACHE_DIR` | `data/poly_haven_cache` | Local glb/hdri cache (Plan10) |
| `MESH_PIPELINE_STRATEGY` | `openai_assisted` | `openai_assisted` / `local_fallback` / `local_only` (Plan10) |

---

## Core Constraints

- **Local-first, no local GPU.** Visual generation → Replicate fallback or local diffusers (CPU).
- **OpenAI only for typed structured JSON** (intent, scene graph, summaries). Never for image/video/raw bpy.
- **Max retries = 1** on physical validation failures before terminal fail.
- **Ambiguity thresholds**: human approval > 0.8 / speculative 0.4–0.8 / proceed ≤ 0.4.
- **Generation modes**: `wireframe` → `model` → `video`; never auto-advance across a boundary.
- **glTF/glb** is the universal exchange format ensuring spatial parity between Three.js and Blender.
- **MemorySaver** (in-process) / **SqliteSaver** (persistent) for LangGraph time-travel.

---

## Build Plans Index

| Plan | Focus | Status |
|---|---|---|
| Plan1 | LangGraph engine (AgentState, 5 nodes, routing, MemorySaver) | Complete |
| Plan2 | FastAPI surface + Next.js workspace + canon/lock persistence + approval-resume | Complete |
| Plan3 | Creative Abstraction Layer (adapters, UAR, BudgetLedger, creative_dispatcher) | Complete |
| Plan4 | Blender DSL expansion + glTF assembler + headless render worker | Complete |
| Plan5 | Three.js / R3F viewport + OT + reversibility timeline | — |
| Plan6 | Render orchestrator (arq + Redis, preview streaming, final render gate) | — |
| Plan7 | Memory hardening (five-tier hierarchical + semantic retrieval) | — |
| Plan8 | Hybrid Adapter: local diffusers + Replicate fallback (Mac M4) | In progress |
| Plan9 | Deterministic wireframe previsualization node + staged generation | In progress |
| Plan10 | Accurate text→3D pipeline (TripoSR / Shap-E / Poly Haven) | Complete |
