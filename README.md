# Cinematic Video Creator

AI-native cinematic production pipeline. Turns a single text prompt into a finished short cinematic ad through a deterministic, schema-driven **LangGraph state machine** that produces strictly typed Blender DSL JSON, with downstream layers handling visual generation, render, and viewport.

> Status: **planning phase**. No code yet — only the architecture doc and the phased build plans.

## Read these in order

1. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the vision and the layered architecture (what we're building and why).
2. [`plans/Plan1.md`](plans/Plan1.md) — **LangGraph orchestration engine**: AgentState, five graph nodes (IntentValidator, SemanticLocker, SceneGraphGenerator, PhysicalValidationEngine, SpeculativeBatcher), conditional edges, `MemorySaver` checkpointing. Backend-only, runnable via `main.py`.
3. [`plans/Plan2.md`](plans/Plan2.md) — FastAPI surface + Next.js two-panel workspace shell + canon/lock persistence + approval-resume flow.
4. [`plans/Plan3.md`](plans/Plan3.md) — Creative Abstraction Layer: Replicate adapter, Universal Asset Registry, layered (subject/background/FX) generation.
5. [`plans/Plan4.md`](plans/Plan4.md) — Blender DSL + Physical Validation Engine + glTF/glb exchange.
6. [`plans/Plan5.md`](plans/Plan5.md) — Three.js / R3F viewport with Operational Transformations and reversibility timeline.
7. [`plans/Plan6.md`](plans/Plan6.md) — Render orchestrator: arq + Redis, preview streaming, hard-gated final render to mp4.
8. [`plans/Plan7.md`](plans/Plan7.md) — Memory hardening: five-tier hierarchical memory + semantic retrieval of rejections.

Each phase is independently shippable and has an end-to-end verification section at the bottom.

## Constraints

- **Local-first on macOS, no local GPU.** Visual generation routes to Replicate (or other remote providers via adapters). Blender runs locally headless.
- **Backend orchestrator**: Python 3.11+ + **LangGraph** (`StateGraph`, `MemorySaver` checkpointing for time-travel) + **LangChain Core / langchain-openai** (`with_structured_output()` for typed LLM calls) + **Pydantic v2** for state and DSL schemas.
- **HTTP surface (Plan2+)**: FastAPI wrapping the LangGraph engine; SSE/WS for state streaming.
- **Frontend**: Next.js 14 (App Router) + Tailwind + Zustand + React Three Fiber.
- **OpenAI is used only for typed structured JSON** (intent extraction, scene-graph generation, summaries). Never for image/video generation or for raw `bpy` scripting.

## Repo layout (target after Plan1)

```
.
├── apps/
│   └── orchestrator/        # Plan1 — LangGraph engine (state, nodes, graph, main.py)
│       ├── src/orchestrator/
│       │   ├── state.py
│       │   ├── schemas/     # intent, dsl, canon
│       │   ├── nodes/       # five graph nodes
│       │   ├── routing.py
│       │   ├── graph.py
│       │   └── llm.py
│       ├── tests/
│       └── main.py
├── plans/                   # Seven phase plans
├── docs/
│   └── ARCHITECTURE.md
└── .env.example             # OPENAI_API_KEY
```

After Plan2, this grows to include `apps/api/` (FastAPI) and `apps/web/` (Next.js).

## How to extend a plan

- Treat each `PlanN.md` as a versioned contract. If you change scope, add an "Amendments" section at the bottom rather than rewriting in place.
- The "Critical files to create" section is the canonical filename list — don't deviate without updating the plan.
- The "Verification" section is the acceptance criteria — a phase isn't done until every numbered item passes.
