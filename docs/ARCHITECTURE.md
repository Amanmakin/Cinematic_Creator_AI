# AI Creative Studio — Architecture (V2)

> This document is the canonical, versioned reflection of the original vision. The phased build plans under [`plans/`](../plans/) translate this architecture into executable milestones. Whenever the vision changes, update this file first and then reconcile the affected plan(s).

## Vision

Build a highly structured, AI-native cinematic production pipeline that transforms user intent into deterministic, high-quality visual outputs. The system prioritizes creative throughput, iteration fluidity, and absolute state consistency. It behaves not as a chatbot or a theatrical OS, but as a centralized, specialized production orchestrator.

## Core Principles

1. **Constrained Execution.** The system initially focuses on a sharply constrained workflow (10–15s commercial advertising content for social media) to guarantee reliability before scaling complexity.
2. **Deterministic State.** Every stage is stateful, using an event-sourced DAG for instant reversibility without re-reasoning LLM costs.
3. **Adaptive Approvals & Predictive Batching.** The system batches decisions and uses reversible generation to maintain creative momentum. It asks for hard approvals before expensive GPU executions, while running low-cost, low-res speculative batches to resolve ambiguity early.
4. **Failure-First Design.** Built-in partial pipeline recovery, automatic fallback for invalid JSONs, and strict render budgeting prevent cascade failures and cost blowouts.

## Core User Flow

1. User provides a prompt (e.g., "A modern, cinematic ad for a new kurti collection, slow-motion, warm tones").
2. Central Orchestrator parses intent and validates against cinematic heuristics.
3. Structured scene plan and storyboard wireframes generated.
4. **Adaptive Approval Checkpoint.** Pauses on high semantic ambiguity. On medium ambiguity, triggers predictive speculative batching (2–3 concurrent low-res variations). On low ambiguity, proceeds.
5. Visual generation via the Creative Abstraction Layer (translating intent into provider-specific payloads).
6. Scene composition via Unified Scene Graph (frontend/backend parity).
7. Execution via strictly typed Blender DSL.
8. Preview render (streamed) → **Hard Approval Checkpoint**.
9. Final render & asset export.

## System Architecture Separation

### 1. Centralized Orchestration & Reasoning Layer

Implemented as a **LangGraph `StateGraph`** — a single authoritative state machine, not a chat of agents. State is a Pydantic `AgentState` model passed between typed nodes. Time-travel and instant rollback come from LangGraph's `MemorySaver` (in-process) / `SqliteSaver` (persistent) checkpointers.

Graph nodes:
- **IntentValidator.** Uses `langchain-openai` `with_structured_output()` to extract a typed `IntentSpec` from the raw prompt, then re-validates against hard Python rules (aspect ratio, duration cap, banned terms). Computes an `ambiguity_score`.
- **SemanticLocker.** Pure Python. Compares current intent to prior checkpoint and emits `SemanticLock`s to freeze stable elements (garment, character) across iterations.
- **SceneGraphGenerator.** Structured-output LLM call producing the typed `BlenderDsl`. Lock violations trigger a capped retry edge.
- **PhysicalValidationEngine.** Pure Python (zero LLM). Strict geometric/spatial checks — focal length, camera-vs-AABB collisions, light sanity, duration caps. Fails fast.
- **SpeculativeBatcher.** Triggered on medium ambiguity; generates 2–3 alternative `BlenderDsl`s for user selection at a `human_approval` breakpoint.

Conditional edges out of `IntentValidator` route to **human approval** (`score > 0.8`), **speculative batching** (`0.4 < score <= 0.8`), or **proceed**. Validation failures route back to the generator up to a strict retry limit, then terminate.

### 2. Creative Intent Abstraction Layer (Visual Stack)

Never binds directly to raw ComfyUI/ControlNet graphs.

- Maintains an internal schema of "Creative Intents" (e.g., `apply_warm_lighting`, `generate_background`).
- Adapters translate these intents into execution graphs for specific endpoints (Replicate, local SDXL, ComfyUI API).
- **Layer Compositing Strategy.** Generates isolated assets (Subject, Background, Foreground FX) rather than single flattened frames, enabling seamless semantic locking without heavy inpainting latency or edge-blend artifacts.
- Protects the core system from external node-ecosystem updates and breakages.

### 3. Dedicated GPU & Render Orchestrator

- Manages queue prioritization, cancellation, and concurrency isolation.
- Implements token and compute budgeting (hard limits on retries and speculative execution).
- Handles failed-render rollbacks and stale-dependency invalidation.

### 4. Deterministic Execution & Synchronization Layer (Blender DSL)

Blender operates as a 2.5D cinematic virtual-production engine.

- **Strict Schema Contracts.** The JSON output is a versioned DSL with execution contracts, capability negotiation, and rollback support.
- **Physical Validation Engine.** Operates entirely outside the LLM layer. Acts as a strict physical compiler that fails fast on impossible spatial math (focal length of 0, camera inside a bounding box, etc.) before GPU queuing.
- **Cross-Environment Standardization.** glTF/glb is the universal exchange format, guaranteeing absolute spatial and material parity between the WebGL/Three.js frontend and the Blender backend.

## Architecture Data Flow

```
[User Input] ➔ [Intent Validator] ➔ [Pipeline Router] ➔ [Event-Sourced DAG]
                                                              │
                              ┌───────────────────────────────┴──────────────────────────────┐
                              ▼                                                              ▼
                  [Creative Abstraction Layer]                                 [Blender DSL Validation]
                              │                                                              │
                  (Adapters: ComfyUI/Replicate)                              (Camera, Space & Composition)
                              │                                                              │
                              └───────────────────────────────┬──────────────────────────────┘
                                                              ▼
                                                  [Unified Scene Graph JSON]
                                                              │
                              ┌───────────────────────────────┴──────────────────────────────┐
                              ▼                                                              ▼
                  [Frontend: Three.js Viewport]                              [Backend: Blender Render]
```

## Memory & State Management

**Hierarchical Project Memory.**

- **Immutable Project Canon.** Hard-locked project rules (e.g., aspect ratio 9:16, modern/natural aesthetic).
- **Universal Asset Registry (UAR).** Locked elements (garment, character) are hashed, converted to isolated asset IDs, and stored with alpha masks and depth maps to ensure identity preservation across iterations.
- **Active Working Memory.** Current scene graph and immediate context.
- **Compressed Historical Summaries.** Lightweight logs of previous iterations.
- **Semantic Retrieval Index.** Database of rejected concepts and style overrides.

**State Consistency Rules.**

- Authoritative state ownership belongs strictly to the backend DAG.
- Semantic diffing handled via **Operational Transformations** — changes are transactional mutations on individual nodes, not full-state regenerations.

## OpenAI Usage Policy

- **Allowed only for**: orchestration, structured creative specifications, logic translation, intent validation, typed JSON schema updates.
- **Strictly prohibited**: direct image/video generation, raw `bpy` scripting, executing unvalidated state changes.

## Frontend Architecture

- **Tech Stack**: Next.js, TailwindCSS, Zustand.
- **Render Engine**: Three.js / React Three Fiber.
- **Data Flow**: Streams only essential ephemeral updates (reasoning progress, wireframe previews). Heavy 3D state changes propagate as transactional OT commits to avoid WS race conditions and UI instability, maintaining coordinate parity with Blender.

## UI Layout (Two-Panel Workspace)

- **Left Panel — Control & Context**: AI conversation, semantic diffing history, targeted approval dialogs, budget/render status.
- **Right Panel — Render Studio**: Real-time 2.5D viewport powered by Three.js. Reads from the same validated Scene Graph JSON as the backend.

## Where each principle is implemented

| Principle | Phase | Key files |
|---|---|---|
| LangGraph `StateGraph` + `MemorySaver` checkpointing | Plan1 | `apps/orchestrator/src/orchestrator/graph.py`, `state.py` |
| Intent Validator (typed JSON only) | Plan1 | `apps/orchestrator/src/orchestrator/nodes/intent_validator.py` |
| Semantic Locker | Plan1 | `apps/orchestrator/src/orchestrator/nodes/semantic_locker.py` |
| Scene Graph Generator | Plan1 | `apps/orchestrator/src/orchestrator/nodes/scene_graph_generator.py` |
| Physical Validation Engine | Plan1 (+ extended in Plan4) | `apps/orchestrator/src/orchestrator/nodes/physical_validation.py` |
| Speculative Batcher + human-approval breakpoint | Plan1 | `apps/orchestrator/src/orchestrator/nodes/speculative_batcher.py`, `routing.py` |
| FastAPI surface + Next.js workspace shell | Plan2 | `apps/api/src/api/main.py`, `apps/web/app/(workspace)/page.tsx` |
| Creative Abstraction Layer | Plan3 | `apps/api/src/adapters/*` |
| UAR (layered, content-addressed) | Plan3 | `apps/api/src/uar/store.py` |
| Full Blender DSL + glTF parity + headless runner | Plan4 | `packages/dsl/schema.json`, `apps/api/src/render/gltf_builder.py`, `workers/render/render.py` |
| R3F viewport + OT against AgentState | Plan5 | `apps/web/components/RenderStudio/Viewport.tsx` |
| Render orchestrator (queue, budget, gates) | Plan6 | `apps/api/src/queue/*` |
| Hierarchical memory + retrieval (over LangGraph checkpoints) | Plan7 | `apps/api/src/memory/*` |
