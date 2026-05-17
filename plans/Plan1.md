# Plan 1 — LangGraph Orchestration Engine (Backend Brain)

> Status: **Not started**
> Depends on: nothing (this is the first phase)
> Unblocks: Plan2, Plan3, Plan4, Plan5, Plan6, Plan7

## Goal

Build the deterministic, event-sourced **State Machine** that transforms a user prompt into a strictly typed Blender DSL JSON. This phase is **backend-only Python** — no FastAPI, no frontend, no Replicate, no Blender execution. The output is a runnable `main.py` that takes a prompt, drives the graph, and prints the final `AgentState`.

LangGraph + `MemorySaver()` replaces the custom event-sourced DAG idea from the original sketch — checkpointing, replay, and time-travel come from the framework instead of hand-rolled SQLite.

## Tech stack

- Python 3.11+
- [`langgraph`](https://github.com/langchain-ai/langgraph) — `StateGraph`, conditional edges, `MemorySaver`, breakpoints
- [`langchain-core`](https://python.langchain.com/) + [`langchain-openai`](https://python.langchain.com/) — `with_structured_output()` for typed LLM calls
- Pydantic v2 — `AgentState`, intent schemas, Blender DSL
- `uv` for dependency management

## Project structure

```
CinematicVideoCreator/
├── apps/
│   └── orchestrator/
│       ├── src/
│       │   └── orchestrator/
│       │       ├── __init__.py
│       │       ├── state.py                  # AgentState + sub-models
│       │       ├── schemas/
│       │       │   ├── __init__.py
│       │       │   ├── intent.py             # IntentSpec, AmbiguityHints
│       │       │   ├── dsl.py                # BlenderDsl, Scene, Camera, Light, ...
│       │       │   └── canon.py              # ProjectCanon
│       │       ├── nodes/
│       │       │   ├── __init__.py
│       │       │   ├── intent_validator.py
│       │       │   ├── semantic_locker.py
│       │       │   ├── scene_graph_generator.py
│       │       │   ├── physical_validation.py
│       │       │   └── speculative_batcher.py
│       │       ├── routing.py                # conditional edge functions
│       │       ├── graph.py                  # StateGraph construction + compile
│       │       ├── prompts/
│       │       │   ├── intent_system.md
│       │       │   ├── scene_system.md
│       │       │   └── speculative_system.md
│       │       └── llm.py                    # ChatOpenAI factory w/ structured output helpers
│       ├── tests/
│       │   ├── test_intent_validator.py
│       │   ├── test_physical_validation.py
│       │   ├── test_graph_routing.py
│       │   └── test_main_e2e.py              # full graph run with mocked LLM
│       ├── main.py                            # demo runner
│       ├── pyproject.toml
│       └── README.md
├── plans/
├── docs/
└── .env.example                               # OPENAI_API_KEY=
```

## Deliverables

### D1. `AgentState` (Pydantic v2 model used as the LangGraph state)

`apps/orchestrator/src/orchestrator/state.py`:

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field
import operator

ExecutionStage = Literal[
    "idle",
    "intent_validated",
    "awaiting_human_approval",
    "speculative_batching",
    "semantic_lock_applied",
    "scene_graph_generated",
    "physical_validation_failed",
    "completed",
]

class SemanticLock(BaseModel):
    path: str                  # e.g. "scene.subject.garment"
    asset_id: str | None       # UAR id once Plan3 lands; nullable for Plan1
    reason: str

class ValidationFinding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    path: str | None

class AgentState(BaseModel):
    user_prompt: str
    project_canon: ProjectCanon                    # required, supplied at graph entry
    intent: IntentSpec | None = None
    ambiguity_score: float = 0.0                   # 0..1
    semantic_locks: list[SemanticLock] = Field(default_factory=list)
    scene_graph: BlenderDsl | None = None
    speculative_variants: list[BlenderDsl] = Field(default_factory=list)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    execution_status: ExecutionStage = "idle"
    retry_count: int = 0                            # cap regeneration loop
    error_log: list[str] = Field(default_factory=list)
```

Notes:
- Using a Pydantic model (not TypedDict) so we get strict v2 validation on every state transition.
- Append-style fields (`error_log`, `validation_findings`) are replaced wholesale by node returns — LangGraph's default merge — which is fine because nodes always emit the full intended state slice. (If we later need append-merge, switch to `Annotated[list, operator.add]`.)
- `retry_count` exists to enforce the strict regeneration cap on the validation → generator back-edge.

### D2. Schemas

#### `IntentSpec` (`schemas/intent.py`)
```python
class IntentSpec(BaseModel):
    subject: str                        # e.g. "woman wearing a modern kurti"
    setting: str                        # e.g. "warm-lit minimal studio"
    mood_tags: list[str]                # ["warm", "slow-motion", "cinematic"]
    duration_seconds: float             # validated against canon max
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    motion_hints: list[str]             # ["slow_motion", "dolly_in"]
    camera_hint: CameraHint | None
    ambiguity_hints: AmbiguityHints     # nested, so the LLM can self-report uncertainty
class AmbiguityHints(BaseModel):
    underspecified_fields: list[str]    # ["lighting_direction", "background_detail"]
    conflicting_directives: list[str]
    confidence: float                   # 0..1, LLM's own confidence
```

#### `BlenderDsl` (`schemas/dsl.py`)
Versioned (`dsl_version: Literal["1.0.0"]`). Minimal viable shape for Plan1 — full DSL with animation tracks lands in Plan4:
```python
class Vec3(BaseModel): x: float; y: float; z: float
class Camera(BaseModel):
    focal_mm: float       # validated 1..1000
    sensor_mm: float = 36.0
    position: Vec3
    look_at: Vec3
    f_stop: float = 2.8
class Light(BaseModel):
    kind: Literal["key", "fill", "rim", "ambient"]
    position: Vec3
    intensity: float      # 0..10000
    color_kelvin: int     # 1000..20000
class SubjectPlaceholder(BaseModel):
    kind: Literal["subject_placeholder"]
    aabb_min: Vec3
    aabb_max: Vec3
    description: str
class Scene(BaseModel):
    duration_s: float
    fps: int                              # 24/30/60
    resolution: tuple[int, int]
    camera: Camera
    lights: list[Light]
    subjects: list[SubjectPlaceholder]    # real meshes/plane-cards in Plan4
class BlenderDsl(BaseModel):
    dsl_version: Literal["1.0.0"] = "1.0.0"
    scene: Scene
```

#### `ProjectCanon` (`schemas/canon.py`)
```python
class ProjectCanon(BaseModel):
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    duration_seconds_max: float
    aesthetic_tags: list[str]
    style_guide: str                      # free text
```

### D3. Nodes

Each node is a **pure function** `(state: AgentState) -> dict` returning the slice to merge.

#### Node 1: `IntentValidator` (`nodes/intent_validator.py`)
- Builds messages: system (canon + extraction rules) + user (raw prompt).
- `llm.with_structured_output(IntentSpec)` → `IntentSpec`.
- Hard-rule re-validation in Python:
  - `intent.aspect_ratio == canon.aspect_ratio` (or override allowed list)
  - `intent.duration_seconds <= canon.duration_seconds_max`
  - banned-term scan over mood_tags + subject + setting
- Compute `ambiguity_score`:
  ```python
  ambiguity_score = clip(
      0.5 * (1 - intent.ambiguity_hints.confidence)
      + 0.1 * len(intent.ambiguity_hints.underspecified_fields)
      + 0.2 * len(intent.ambiguity_hints.conflicting_directives),
      0.0, 1.0,
  )
  ```
- Returns `{"intent": ..., "ambiguity_score": ..., "execution_status": "intent_validated"}`.

#### Node 2: `SemanticLocker` (`nodes/semantic_locker.py`)
- Pure Python (no LLM). Diffs the incoming `IntentSpec` against any persisted prior locks for the same checkpoint thread (read via the `RunnableConfig`'s `configurable.thread_id` — `MemorySaver` carries the prior state). On first run, no prior state → no new locks.
- Heuristics: if `intent.subject` is unchanged from the prior run, emit a `SemanticLock(path="scene.subjects[0]", reason="subject unchanged across iterations")`. (Asset-ID locks land in Plan3 once UAR exists.)
- Returns `{"semantic_locks": [...], "execution_status": "semantic_lock_applied"}`.

#### Node 3: `SceneGraphGenerator` (`nodes/scene_graph_generator.py`)
- System prompt includes canon, validated intent, and any active `semantic_locks` (locks are emitted as "do not modify these subtrees" directives).
- `llm.with_structured_output(BlenderDsl)` → `BlenderDsl`.
- Enforce locks in Python after the LLM returns: if a locked path's payload changed from the prior checkpoint's value, raise `LockViolation` → bump retry, route back via the failure edge.
- Returns `{"scene_graph": ..., "execution_status": "scene_graph_generated"}`.

#### Node 4: `PhysicalValidationEngine` (`nodes/physical_validation.py`)
- **No LLM calls.** Pure Python checks against `state.scene_graph`:
  1. `1.0 <= camera.focal_mm <= 1000.0`
  2. `camera.position != camera.look_at`
  3. Camera position not inside any `SubjectPlaceholder` AABB
  4. Each light intensity in `[0, 10000]`, color_kelvin in `[1000, 20000]`
  5. `scene.duration_s <= canon.duration_seconds_max`
  6. `scene.resolution` aspect matches canon (tolerance 0.01)
  7. At least one `Light` of kind `"key"`
- Builds `list[ValidationFinding]`. If any `severity=="error"` → returns `{"validation_findings": [...], "execution_status": "physical_validation_failed", "retry_count": state.retry_count + 1}`.
- Else → `{"validation_findings": [...], "execution_status": "completed"}`.

#### Node 5: `SpeculativeBatcher` (`nodes/speculative_batcher.py`)
- Triggered on medium ambiguity. Generates 2–3 alternative `BlenderDsl`s by varying high-signal fields the LLM flagged as underspecified (lighting direction, camera lens, color palette).
- Implementation: three sequential `with_structured_output(BlenderDsl)` calls with distinct system-prompt nudges (e.g. "Variation A: cool key light from camera-left; Variation B: warm key light from camera-right; Variation C: top-down soft key").
- Returns `{"speculative_variants": [...], "execution_status": "speculative_batching"}`.
- The graph then routes to a `HumanApproval` interrupt for variant selection (Plan2 ships the actual UI; Plan1 just halts via `interrupt_before=["speculative_batcher"]`-style breakpoints and the test surfaces the variants).

### D4. Graph topology (`graph.py`)

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def build_graph() -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("intent_validator", intent_validator_node)
    g.add_node("semantic_locker", semantic_locker_node)
    g.add_node("scene_graph_generator", scene_graph_generator_node)
    g.add_node("physical_validation", physical_validation_node)
    g.add_node("speculative_batcher", speculative_batcher_node)

    g.set_entry_point("intent_validator")

    g.add_conditional_edges("intent_validator", route_after_intent, {
        "human_approval": END,           # interrupted via breakpoints
        "speculative":    "speculative_batcher",
        "proceed":        "semantic_locker",
    })

    g.add_edge("semantic_locker", "scene_graph_generator")
    g.add_edge("scene_graph_generator", "physical_validation")

    g.add_conditional_edges("physical_validation", route_after_validation, {
        "retry":   "scene_graph_generator",   # capped at retry_count >= 2
        "fail":    END,
        "success": END,
    })

    g.add_edge("speculative_batcher", END)    # human selects variant out-of-band

    return g.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["speculative_batcher"],   # hard-stop for human approval before speculative variants render
    )
```

Routing functions in `routing.py`:
```python
HUMAN_APPROVAL_THRESHOLD = 0.8
SPECULATIVE_THRESHOLD = 0.4
MAX_RETRIES = 2

def route_after_intent(state: AgentState) -> str:
    if state.ambiguity_score > HUMAN_APPROVAL_THRESHOLD:
        return "human_approval"
    if state.ambiguity_score > SPECULATIVE_THRESHOLD:
        return "speculative"
    return "proceed"

def route_after_validation(state: AgentState) -> str:
    has_error = any(f.severity == "error" for f in state.validation_findings)
    if not has_error:
        return "success"
    if state.retry_count >= MAX_RETRIES:
        return "fail"
    return "retry"
```

### D5. LLM factory (`llm.py`)
```python
from langchain_openai import ChatOpenAI
def make_llm(model: str = "gpt-4o-mini", temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=temperature, timeout=60)
```
Each node gets its LLM from this factory so tests can monkeypatch a single seam.

### D6. `main.py`
```python
from orchestrator.graph import build_graph
from orchestrator.state import AgentState
from orchestrator.schemas.canon import ProjectCanon

def run():
    canon = ProjectCanon(
        aspect_ratio="9:16",
        duration_seconds_max=15,
        aesthetic_tags=["modern", "natural", "cinematic"],
        style_guide="Warm tones, soft natural light, minimal background clutter.",
    )
    state = AgentState(
        user_prompt="A modern, cinematic advertisement for a new kurti collection, "
                    "focusing on slow-motion movement and warm tones.",
        project_canon=canon,
    )
    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-1"}}
    final = graph.invoke(state, config=config)
    print(AgentState.model_validate(final).model_dump_json(indent=2))

if __name__ == "__main__":
    run()
```

### D7. Tests
- `test_intent_validator.py` — mocks `make_llm` to return a fixed `IntentSpec`; asserts ambiguity score formula and hard-rule rejection.
- `test_physical_validation.py` — table-driven; one row per check, validates pass/fail behavior. No LLM.
- `test_graph_routing.py` — feeds states with varying `ambiguity_score`/`retry_count`/`validation_findings` directly into the routing functions.
- `test_main_e2e.py` — monkeypatches `ChatOpenAI` to deterministic fakes, runs `build_graph().invoke(...)`, asserts terminal `execution_status == "completed"` and a valid `BlenderDsl`.

## Verification

1. `uv run python apps/orchestrator/main.py` with a valid `OPENAI_API_KEY` prints a final `AgentState` whose `execution_status == "completed"` and whose `scene_graph` is a valid `BlenderDsl`.
2. Inject a bad-canon prompt (`duration_seconds_max=2`, prompt asks for "10 seconds") → graph terminates with `execution_status` reflecting failure and a clear `error_log` entry; **no** `bpy` or Replicate is ever touched (this phase doesn't even import them).
3. Run the same prompt twice with the same `thread_id` → second run starts from the `MemorySaver` checkpoint, **does not re-call the LLM** for nodes already past, and produces identical final state bytes.
4. Time-travel: `graph.update_state(config, values=..., as_node="semantic_locker")` lets a test rewind to before scene graph generation and resume with mutated locks; final state reflects the new locks.
5. Force `PhysicalValidationEngine` to fail (mock generator to emit `focal_mm=0`) → graph retries once, then routes to `END` with a fail status and a clear finding. `retry_count` is 2.
6. `pytest -q apps/orchestrator/tests` is green.

## Out of scope (deferred)

- FastAPI / HTTP surface around the engine → **Plan2**.
- Project canon persistence + lock CRUD endpoints → **Plan2**.
- Real human-approval UI (Plan1 surfaces interrupts via breakpoints; the UI lands in **Plan3**).
- Universal Asset Registry + Replicate adapters → **Plan3** (today's `SubjectPlaceholder` AABBs become real `PlaneCard` references then).
- Full Blender DSL with plane-cards, animation tracks, glTF assembly → **Plan4**.
- Three.js / R3F viewport → **Plan5**.
- arq queue + preview/final render → **Plan6**.
- Semantic retrieval / hierarchical memory beyond `MemorySaver` → **Plan7**.

## Amendment vs. original Plan1

The original Plan1 specified a custom event-sourced DAG in SQLite, a FastAPI surface, and a Next.js shell. Per updated requirements, that scope is split:
- **State machine, checkpointing, time-travel** now come from LangGraph + `MemorySaver` (this Plan1).
- **FastAPI surface + frontend shell** move to **Plan2**.

This is a net simplification — LangGraph already provides the spine we were going to hand-roll.
