# Plan: Add Deterministic Wireframe Previsualization Node to Orchestrator Pipeline

## Context

The current orchestration pipeline lacks a true visual approval phase before expensive image/video generation begins. The original storyboard concept relied on LLM-generated textual descriptions, which introduces:

- hallucinations
- framing inconsistencies
- nondeterministic regeneration
- weak spatial validation
- unreliable approval workflows

This implementation introduces a brand-new deterministic orchestration node:

```
wireframe_previs_generator
```

The node generates actual viewport wireframe renders directly from the canonical Scene Graph / Blender DSL instead of generating natural-language storyboards.

This transforms the approval phase into a real cinematic previsualization system.

---

## Staged Generation Principle

The pipeline supports three explicit generation depths determined by what the user requested:

| User Request | Pipeline Stops At | What Is Returned | Offered Next Action |
|---|---|---|---|
| wireframes | after `wireframe_previs_generator` | wireframe renders only | "Proceed to Model Generation" |
| models | after `visual_generator` | wireframes + 2D/2.5D model renders | "Proceed to Video Generation" |
| video (default) | after full pipeline | wireframes + models + final video | — |

The system never auto-advances past a stage boundary without explicit user action. Each boundary surfaces a clearly labelled proceed option in the UI.

---

# Target Pipeline

```
intent_validator
  ├─ human_approval → END
  ├─ fail → END
  ├─ speculative → speculative_batcher → [INTERRUPT] → END
  └─ proceed → generation_mode_parser → semantic_locker
                                                ↓
                                      scene_graph_generator
                                                ↓
                                   wireframe_previs_generator
                                                ↓
                                 [INTERRUPT — wireframe_generated]
                                                ├─ accept + mode=="wireframe" → END
                                                │          (UI offers "Proceed to Model Generation")
                                                ├─ accept + mode in {"model","video"} → creative_dispatcher
                                                │                                              ↓
                                                │                                      visual_generator
                                                │                                              ↓
                                                │                             [INTERRUPT — model_generated]
                                                │                                              ├─ accept + mode=="model" → END
                                                │                                              │          (UI offers "Proceed to Video Generation")
                                                │                                              ├─ accept + mode=="video" → physical_validation → END
                                                │                                              ├─ modify → visual_generator
                                                │                                              └─ reject → wireframe_previs_generator
                                                ├─ modify → wireframe_previs_generator
                                                └─ reject → scene_graph_generator
```

---

# Architectural Goal

Replace text-based storyboard generation with:

```
Scene Graph
   ↓
Blender DSL Compiler
   ↓
Deterministic Camera Planner
   ↓
Viewport/OpenGL Renderer
   ↓
Wireframe Thumbnails
   ↓
[stage gate — wireframe mode stops here]
   ↓
2D / 2.5D Model Renders
   ↓
[stage gate — model mode stops here]
   ↓
Final Video
```

This ensures previews are:

- physically accurate
- spatially correct
- compositionally accurate
- lighting-aware
- deterministic
- reproducible

---

# Core Principle

The approval phase must validate:

- actual framing
- actual spacing
- actual blocking
- actual camera placement
- actual lighting direction
- actual scene geometry

using real rendered previews rather than prose descriptions.

---

# Deliverables

---

# D1 — Wireframe Previsualization Schema

## New File

```
apps/orchestrator/src/orchestrator/schemas/previsualization.py
```

Define deterministic previsualization schemas.

```python
class CameraTransform(BaseModel):
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    focal_length_mm: float

class LightingInfo(BaseModel):
    key_light_direction: tuple[float, float, float]
    fill_intensity: float
    rim_enabled: bool

class WireframeFrame(BaseModel):
    frame_index: int
    time_start_s: float
    time_end_s: float
    camera: CameraTransform
    lighting: LightingInfo
    viewport_image_path: str
    viewport_thumbnail_path: str
    notes: str | None = None

class Previsualization(BaseModel):
    frames: list[WireframeFrame]
    mood: str
    palette_hint: str
    render_engine: Literal["blender_eevee", "opengl"]
```

---

# D2 — State Changes

## Modify

```
apps/orchestrator/src/orchestrator/state.py
```

## Add Execution Stages

Add to `ExecutionStage`:

```python
"previsualization_generated"
"previsualization_approved"
"previsualization_feedback"
"model_generated"
"model_approved"
"model_feedback"
```

## Add Generation Mode Enum

```python
class GenerationMode(str, Enum):
    wireframe = "wireframe"
    model = "model"
    video = "video"
```

## Add State Fields

```python
generation_mode: GenerationMode = GenerationMode.video

previsualization: Previsualization | None = None
previsualization_feedback: str | None = None

model_renders: list[str] | None = None   # paths to 2D/2.5D renders
model_feedback: str | None = None
```

---

# D3 — Generation Mode Parser Node

## New File

```
apps/orchestrator/src/orchestrator/nodes/generation_mode_parser.py
```

Runs immediately after `intent_validator`, before `semantic_locker`. Reads `state.intent` and sets `generation_mode`.

## Responsibilities

Parse the user's natural-language request to determine generation depth. No LLM call — pure keyword heuristic so the mode is deterministic and free.

```python
def parse_generation_mode(intent: str) -> GenerationMode:
    intent_lower = intent.lower()
    if any(kw in intent_lower for kw in ["wireframe", "layout", "blocking", "previs"]):
        return GenerationMode.wireframe
    if any(kw in intent_lower for kw in ["model", "render", "2d", "2.5d", "scene"]):
        return GenerationMode.model
    return GenerationMode.video
```

## Return

```python
return {"generation_mode": parse_generation_mode(state.intent)}
```

---

# D4 — Wireframe Previsualization Node

## New File

```
apps/orchestrator/src/orchestrator/nodes/wireframe_previs_generator.py
```

This is a completely new orchestration node responsible for generating deterministic cinematic wireframe previews directly from the Scene Graph.

## Inputs

Read:

```python
state.intent
state.scene_graph
state.project_canon
state.previsualization_feedback
```

Assert required fields exist.

---

## 1. Compile Scene Graph → Blender DSL

Convert canonical scene graph into executable Blender scene instructions.

```python
scene = BlenderSceneCompiler().compile(scene_graph=state.scene_graph)
```

---

## 2. Deterministic Camera Planning

Generate cinematic camera framing procedurally. No LLM usage permitted.

Camera placement derives from:

- subject positions
- action timing
- pacing
- emotional intensity
- environment scale
- motion vectors

```python
if environment.scale == "large":
    use_establishing_shot()

if emotion.intensity > 0.8:
    use_closeup()

if dialogue_between_two_subjects:
    use_ots_pattern()
```

---

## 3. Procedural Lighting Setup

Generate key lights, fill lights, rim lights, and environment lighting based on scene mood, time of day, emotional tone, and environment metadata.

---

## 4. Viewport Rendering

Generate OpenGL viewport renders, Blender Eevee previews, and thumbnail images.

```
/tmp/previs/frame_001.png
/tmp/previs/frame_002.png
```

---

## 5. Construct Previsualization Object

Build deterministic `Previsualization` schema object.

## Return

```python
return {
    "previsualization": result,
    "execution_status": "previsualization_generated"
}
```

The graph then interrupts. Routing after the interrupt is determined by `generation_mode` (see D7).

---

# D5 — Rendering Layer

## New File

```
apps/orchestrator/src/orchestrator/rendering/previs_renderer.py
```

```python
class PrevisRenderer:
    def render_frame(...): ...
    def render_sequence(...): ...
```

### Rendering Modes

**Blender Eevee** — fast physically-aware previews.

**OpenGL Viewport** — ultra-fast iteration previews.

---

# D6 — Deterministic Camera Planning Engine

## New File

```
apps/orchestrator/src/orchestrator/cinematics/camera_planner.py
```

```python
planner.generate_shots(
    scene_graph=...,
    pacing="slow",
    tone="tense"
)
```

### Rules

```python
if action_type == "conversation":
    use_over_shoulder_pattern()

if environment.scale == "epic":
    use_wide_establishing()

if emotional_intensity > 0.8:
    use_closeup()
```

---

# D7 — Blender/OpenGL Runtime

## New File

```
apps/orchestrator/src/orchestrator/rendering/blender_runtime.py
```

Responsibilities:

- launch headless Blender
- execute generated DSL
- render viewport previews
- export thumbnails
- manage temporary scenes

```bash
blender -b previs.blend -P render_sequence.py
```

---

# D8 — Export Nodes

## Modify

```
apps/orchestrator/src/orchestrator/nodes/__init__.py
```

```python
from .generation_mode_parser import generation_mode_parser_node
from .wireframe_previs_generator import wireframe_previs_generator_node
```

---

# D9 — Graph Wiring

## Modify

```
apps/orchestrator/src/orchestrator/graph.py
```

## Add New Nodes

```python
g.add_node("generation_mode_parser", generation_mode_parser_node)
g.add_node("wireframe_previs_generator", wireframe_previs_generator_node)
```

## Replace Existing Edges

Replace:

```
intent_validator → semantic_locker
scene_graph_generator → creative_dispatcher
```

With:

```
intent_validator → generation_mode_parser → semantic_locker
scene_graph_generator → wireframe_previs_generator
```

## Stage-Gate Router: After Wireframe Interrupt

```python
def route_after_wireframe(state: AgentState) -> str:
    if state.execution_status == "previsualization_approved":
        if state.generation_mode == GenerationMode.wireframe:
            return END          # wireframe-only; pipeline halts
        return "creative_dispatcher"
    if state.execution_status == "previsualization_feedback":
        return "wireframe_previs_generator"
    return "scene_graph_generator"  # reject

g.add_conditional_edges("wireframe_previs_generator", route_after_wireframe)
```

## Stage-Gate Router: After Model Interrupt

```python
def route_after_model(state: AgentState) -> str:
    if state.execution_status == "model_approved":
        if state.generation_mode == GenerationMode.model:
            return END          # model-only; pipeline halts
        return "physical_validation"
    if state.execution_status == "model_feedback":
        return "visual_generator"
    return "wireframe_previs_generator"  # reject

g.add_conditional_edges("visual_generator", route_after_model)
```

## Interrupt Configuration

```python
interrupt_after = [
    "speculative_batcher",
    "wireframe_previs_generator",
    "visual_generator",          # catches model-mode stage gate
]
```

---

# D10 — Approval API

## Modify

```
apps/api/src/api/routes/approvals.py
```

## Wireframe Decision Branches

```python
decision == "previsualization_approve"    # accept; continue to model/video
decision == "previsualization_proceed"    # user clicked "Proceed to Model Generation" from wireframe-only halt
decision == "previsualization_modify"     # revision notes; regenerate previs
decision == "previsualization_reject"     # rewind to scene planning
```

## Model Decision Branches

```python
decision == "model_approve"               # accept; continue to video
decision == "model_proceed"               # user clicked "Proceed to Video Generation" from model-only halt
decision == "model_modify"                # revision notes; re-render model
decision == "model_reject"               # rewind to wireframe
```

## Accept — Wireframe

```python
graph.update_state(
    config,
    {"execution_status": "previsualization_approved"},
    as_node="wireframe_previs_generator"
)
```

Router reads `generation_mode` to decide whether to halt or continue.

## Proceed to Model — from Wireframe-Only Halt

Upgrade `generation_mode` then resume:

```python
graph.update_state(
    config,
    {
        "generation_mode": "model",
        "execution_status": "previsualization_approved",
    },
    as_node="wireframe_previs_generator"
)
```

## Modify — Wireframe

```json
{ "action": "modify", "notes": "camera framing too tight" }
```

```python
previsualization_feedback = notes
execution_status = "previsualization_feedback"
```

## Reject — Wireframe

```python
previsualization = None
scene_graph = None
execution_status = "intent_validated"
```

## Proceed to Video — from Model-Only Halt

```python
graph.update_state(
    config,
    {
        "generation_mode": "video",
        "execution_status": "model_approved",
    },
    as_node="visual_generator"
)
```

---

# D11 — Frontend Types

## Modify

```
apps/web/src/lib/types/agentState.d.ts
```

```ts
type GenerationMode = "wireframe" | "model" | "video"

interface CameraTransform {
    position: [number, number, number]
    rotation: [number, number, number]
    focal_length_mm: number
}

interface LightingInfo {
    key_light_direction: [number, number, number]
    fill_intensity: number
    rim_enabled: boolean
}

interface WireframeFrame {
    frame_index: number
    time_start_s: number
    time_end_s: number
    camera: CameraTransform
    lighting: LightingInfo
    viewport_image_path: string
    viewport_thumbnail_path: string
    notes?: string
}

interface Previsualization {
    frames: WireframeFrame[]
    mood: string
    palette_hint: string
    render_engine: "blender_eevee" | "opengl"
}
```

Add to `AgentState`:

```ts
generation_mode: GenerationMode
previsualization?: Previsualization
model_renders?: string[]
```

---

# D12 — Approval UI

## Modify

```
apps/web/src/components/ControlPanel/ApprovalDialog.tsx
```

---

## Wireframe Approval Panel

### Activation Condition

```ts
state.execution_status === "previsualization_generated"
```

### What to Render

- wireframe thumbnails
- viewport previews
- frame timeline
- camera metadata (focal length, position)
- lighting information

### Controls

| Button | Visible when | Action |
|---|---|---|
| **Approve** | `generation_mode !== "wireframe"` | Continue to model generation |
| **Proceed to Model Generation** | `generation_mode === "wireframe"` | Upgrades mode to `model`, resumes pipeline |
| **Modify** | always | Submit revision notes, regenerate previs |
| **Reject** | always | Rewind to scene planning |

When `generation_mode === "wireframe"`, Approve is hidden. The primary CTA is **Proceed to Model Generation** — the wireframe stage is terminal unless the user explicitly escalates.

---

## Model Approval Panel

### Activation Condition

```ts
state.execution_status === "model_generated"
```

### What to Render

- wireframe thumbnails (collapsible reference)
- 2D / 2.5D model renders (primary display)
- scene metadata

### Controls

| Button | Visible when | Action |
|---|---|---|
| **Approve** | `generation_mode !== "model"` | Continue to video generation |
| **Proceed to Video Generation** | `generation_mode === "model"` | Upgrades mode to `video`, resumes pipeline |
| **Modify** | always | Submit revision notes, re-render model |
| **Reject** | always | Rewind to wireframe approval |

When `generation_mode === "model"`, Approve is hidden. The primary CTA is **Proceed to Video Generation** — the model stage is terminal unless the user explicitly escalates.

---

# D13 — Verification

## Unit Tests

### Generation Mode Parser

Validate keyword → mode mapping for all three modes and edge cases (ambiguous input defaults to `video`).

### Camera Planner

Validate deterministic shot generation.

### Renderer

Validate viewport image export.

### Blender Runtime

Validate render execution.

### DSL Compiler

Validate scene graph compilation.

---

## Integration Tests

### Wireframe-Only Flow

1. User requests "wireframe"
2. `generation_mode_parser` sets `generation_mode = wireframe`
3. Pipeline stops at `wireframe_previs_generator`
4. UI shows wireframe thumbnails + **Proceed to Model Generation** button
5. Approve button is hidden
6. No model or video rendering triggered

### Model-Only Flow

1. User requests "model"
2. `generation_mode_parser` sets `generation_mode = model`
3. Pipeline continues through `visual_generator`
4. Stops at model interrupt
5. UI shows wireframes + model renders + **Proceed to Video Generation** button
6. Approve button is hidden
7. No video rendering triggered

### Full Video Flow

1. User requests video (default / no keyword match)
2. `generation_mode_parser` sets `generation_mode = video`
3. Pipeline runs to completion through both interrupts
4. No intermediate halts at wireframe or model stage gates

### Wireframe → Escalate to Model

1. User starts in wireframe mode, views wireframes
2. Clicks **Proceed to Model Generation**
3. API updates `generation_mode = model`, resumes graph
4. Pipeline continues, halts at model stage
5. UI transitions to model approval panel

### Model → Escalate to Video

1. User in model mode, views model renders
2. Clicks **Proceed to Video Generation**
3. API updates `generation_mode = video`, resumes graph
4. Pipeline continues to final video

### Wireframe Interrupt Test

Validate graph pauses after `wireframe_previs_generator`.

### Wireframe Approval Test

Validate approval resumes `creative_dispatcher` when mode is not wireframe.

### Wireframe Modify Test

Validate previs regenerates while preserving canonical scene graph.

### Wireframe Reject Test

Validate pipeline rewinds to scene planning.

### Model Approval Test

Validate model approval resumes `physical_validation` when mode is video.

### Model Reject Test

Validate pipeline rewinds to `wireframe_previs_generator`.

---

# Critical Constraints

## No LLM Camera Generation

Camera planning must remain deterministic. LLMs may optionally summarize mood, annotate shots, or suggest alternates — but must never define canonical framing.

## Deterministic Output

Same scene graph must always produce identical framing, identical lighting, and identical shot layouts unless revision feedback changes planning inputs.

## Approval Must Validate Physical Reality

Approval previews must reflect actual geometry, actual blocking, actual composition, and actual camera physics — not textual interpretation.

## Stage Gates Are Opt-In Escalation Only

The system must never auto-advance past a stage boundary. Escalation from wireframe → model → video requires explicit user action. Within a terminal mode, accepting/approving only submits approval feedback — it does not advance the pipeline depth.

---

# Expected Outcome

After implementation, the orchestration system gains a true cinematic previsualization layer with:

- deterministic wireframe rendering
- real viewport previews
- physically grounded composition
- approval-safe cinematic planning
- reproducible framing
- spatially accurate validation
- staged generation depth controlled by the user — wireframe-only, model-only, or full video — with explicit opt-in escalation at each boundary
