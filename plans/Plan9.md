# Plan: Add Deterministic Wireframe Previsualization Node to Orchestrator Pipeline

## Context

The current orchestration pipeline lacks a true visual approval phase before expensive image/video generation begins. The original storyboard concept relied on LLM-generated textual descriptions, which introduces:

- hallucinations
- framing inconsistencies
- nondeterministic regeneration
- weak spatial validation
- unreliable approval workflows

This implementation introduces a brand-new deterministic orchestration node:

```text
wireframe_previs_generator
```

The node generates actual viewport wireframe renders directly from the canonical Scene Graph / Blender DSL instead of generating natural-language storyboards.

This transforms the approval phase into a real cinematic previsualization system.

---

# Target Pipeline

```text
intent_validator
  ├─ human_approval → END
  ├─ fail → END
  ├─ speculative → speculative_batcher → [INTERRUPT] → END
  └─ proceed → semantic_locker
                  ↓
          scene_graph_generator
                  ↓
       wireframe_previs_generator
                  ↓
          [INTERRUPT/APPROVAL]
                  ├─ accept → creative_dispatcher → visual_generator → physical_validation
                  ├─ modify → wireframe_previs_generator
                  └─ reject → scene_graph_generator
```

---

# Architectural Goal

Replace text-based storyboard generation with:

```text
Scene Graph
   ↓
Blender DSL Compiler
   ↓
Deterministic Camera Planner
   ↓
Viewport/OpenGL Renderer
   ↓
Wireframe Thumbnails
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

```text
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

    render_engine: Literal[
        "blender_eevee",
        "opengl"
    ]
```

---

# D2 — State Changes

## Modify

```text
apps/orchestrator/src/orchestrator/state.py
```

---

## Add Execution Stages

Add:

```python
"previsualization_generated"
"previsualization_approved"
```

to `ExecutionStage`.

---

## Add State Fields

```python
previsualization: Previsualization | None = None

previsualization_feedback: str | None = None
```

---

# D3 — New Wireframe Previsualization Node

## New File

```text
apps/orchestrator/src/orchestrator/nodes/wireframe_previs_generator.py
```

This is a completely new orchestration node.

The node is responsible for generating deterministic cinematic wireframe previews directly from the Scene Graph.

---

# Node Responsibilities

---

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

# Responsibilities

---

## 1. Compile Scene Graph → Blender DSL

Convert canonical scene graph into executable Blender scene instructions.

Example:

```python
scene = BlenderSceneCompiler().compile(
    scene_graph=state.scene_graph
)
```

---

## 2. Deterministic Camera Planning

Generate cinematic camera framing procedurally.

No LLM usage permitted.

Camera placement derives from:

- subject positions
- action timing
- pacing
- emotional intensity
- environment scale
- motion vectors

---

## Example Shot Rules

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

Generate:

- key lights
- fill lights
- rim lights
- environment lighting

based on:

- scene mood
- time of day
- emotional tone
- environment metadata

---

## 4. Viewport Rendering

Generate:

- OpenGL viewport renders
- Blender Eevee previews
- thumbnail images

Example outputs:

```text
/tmp/previs/frame_001.png
/tmp/previs/frame_002.png
```

---

## 5. Construct Previsualization Object

Build deterministic `Previsualization` schema object.

---

## Return

```python
return {
    "previsualization": result,
    "execution_status": "previsualization_generated"
}
```

---

# D4 — Rendering Layer

## New File

```text
apps/orchestrator/src/orchestrator/rendering/previs_renderer.py
```

Encapsulates rendering logic.

---

## Responsibilities

```python
class PrevisRenderer:
    def render_frame(...)
    def render_sequence(...)
```

---

## Rendering Modes

### Blender Eevee

Fast physically-aware previews.

### OpenGL Viewport

Ultra-fast iteration previews.

---

# D5 — Deterministic Camera Planning Engine

## New File

```text
apps/orchestrator/src/orchestrator/cinematics/camera_planner.py
```

Generate deterministic cinematic shots.

---

## Responsibilities

```python
planner.generate_shots(
    scene_graph=...,
    pacing="slow",
    tone="tense"
)
```

---

## Rules

```python
if action_type == "conversation":
    use_over_shoulder_pattern()

if environment.scale == "epic":
    use_wide_establishing()

if emotional_intensity > 0.8:
    use_closeup()
```

---

# D6 — Blender/OpenGL Runtime

## New File

```text
apps/orchestrator/src/orchestrator/rendering/blender_runtime.py
```

---

## Responsibilities

- launch headless Blender
- execute generated DSL
- render viewport previews
- export thumbnails
- manage temporary scenes

---

## Example Invocation

```bash
blender -b previs.blend -P render_sequence.py
```

---

# D7 — Export Node

## Modify

```text
apps/orchestrator/src/orchestrator/nodes/__init__.py
```

Add export:

```python
from .wireframe_previs_generator import (
    wireframe_previs_generator_node,
)
```

---

# D8 — Graph Wiring

## Modify

```text
apps/orchestrator/src/orchestrator/graph.py
```

---

# Add New Node

```python
g.add_node(
    "wireframe_previs_generator",
    wireframe_previs_generator_node
)
```

---

# Replace Existing Edge

Replace:

```text
scene_graph_generator → creative_dispatcher
```

with:

```text
scene_graph_generator → wireframe_previs_generator
wireframe_previs_generator → creative_dispatcher
```

---

# Interrupt Configuration

The graph must pause after previsualization generation.

```python
interrupt_after = [
    "speculative_batcher",
    "wireframe_previs_generator"
]
```

Previsualization approval is mandatory.

---

# D9 — Approval API

## Modify

```text
apps/api/src/api/routes/approvals.py
```

Add a new approval decision branch:

```python
decision == "previsualization_approve"
```

---

# Approval Actions

---

## Accept

```python
graph.update_state(
    config,
    {
        "execution_status": "previsualization_approved"
    },
    as_node="wireframe_previs_generator"
)
```

Resume graph execution.

---

## Modify

Accept revision notes:

```json
{
  "action": "modify",
  "notes": "camera framing too tight"
}
```

Update:

```python
previsualization_feedback = notes
```

Then regenerate previs from the same scene graph.

---

## Reject

Clear previs and rewind:

```python
previsualization = None
scene_graph = None
execution_status = "intent_validated"
```

Return pipeline to scene planning.

---

# D10 — Frontend Types

## Modify

```text
apps/web/src/lib/types/agentState.d.ts
```

Add:

```ts
interface CameraTransform { ... }

interface LightingInfo { ... }

interface WireframeFrame { ... }

interface Previsualization { ... }
```

Add to `AgentState`:

```ts
previsualization?: Previsualization
```

---

# D11 — Approval UI

## Modify

```text
apps/web/src/components/ControlPanel/ApprovalDialog.tsx
```

---

# Activation Condition

```ts
state.execution_status === "previsualization_generated";
```

---

# Render

Display:

- wireframe thumbnails
- viewport previews
- frame timeline
- camera metadata
- focal lengths
- lighting information

---

# Controls

### Approve

Continue generation pipeline.

### Modify

Submit revision notes and regenerate previs.

### Reject

Rewind to scene planning.

---

# D12 — Verification

---

## Unit Tests

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

### Interrupt Test

Validate graph pauses after:

```python
wireframe_previs_generator
```

---

## Approval Test

Validate approval resumes:

```python
creative_dispatcher
```

---

## Modify Test

Validate previs regenerates while preserving canonical scene graph.

---

## Reject Test

Validate pipeline rewinds correctly.

---

# Critical Constraints

---

## No LLM Camera Generation

Camera planning must remain deterministic.

LLMs may optionally:

- summarize mood
- annotate shots
- suggest alternates

but must never define canonical framing.

---

## Deterministic Output

Same scene graph must always produce:

- identical framing
- identical lighting
- identical shot layouts

unless revision feedback changes planning inputs.

---

## Approval Must Validate Physical Reality

Approval previews must reflect:

- actual geometry
- actual blocking
- actual composition
- actual camera physics

not textual interpretation.

---

# Expected Outcome

After implementation, the orchestration system gains a true cinematic previsualization layer with:

- deterministic wireframe rendering
- real viewport previews
- physically grounded composition
- approval-safe cinematic planning
- reproducible framing
- spatially accurate validation

This upgrades the orchestration pipeline from a text-based AI workflow into a production-grade cinematic previs system with real visual validation before expensive generation begins.
