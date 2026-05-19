from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.creative import CreativeIntent, LayerAsset
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.schemas.intent import IntentSpec
from orchestrator.schemas.previsualization import Previsualization

ExecutionStage = Literal[
    "idle",
    "intent_validated",
    "awaiting_human_approval",
    "speculative_batching",
    "semantic_lock_applied",
    "scene_graph_generated",
    # Plan9 previsualization stages
    "previsualization_generated",
    "previsualization_approved",
    "previsualization_feedback",
    "model_generated",
    "model_approved",
    "model_feedback",
    "creative_dispatching",
    "visual_generating",
    "budget_exceeded",
    "physical_validation_failed",
    # Plan4 render pipeline stages
    "dsl_compiled",
    "dsl_validation_failed",
    "gltf_assembled",
    "render_progress",
    "render_timed_out",
    "render_completed",
    "completed",
    "failed",
]


class GenerationMode(str, Enum):
    wireframe = "wireframe"
    model = "model"
    video = "video"

CreativeEventKind = Literal[
    "CreativeIntentDispatched",
    "LayerGenerated",
    "LockedAssetReused",
    "BudgetExceeded",
    "BudgetReplenished",
    "LayerGenerationFailed",
]


class CreativeEvent(BaseModel):
    kind: CreativeEventKind
    target_path: str
    asset_id: str | None = None
    detail: str = ""


class SemanticLock(BaseModel):
    path: str
    asset_id: str | None = None
    reason: str


class ValidationFinding(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    path: str | None = None


class AgentState(BaseModel):
    project_id: str = ""
    user_prompt: str
    project_canon: ProjectCanon
    intent: IntentSpec | None = None
    ambiguity_score: float = 0.0
    semantic_locks: list[SemanticLock] = Field(default_factory=list)
    scene_graph: BlenderDsl | None = None
    speculative_variants: list[BlenderDsl] = Field(default_factory=list)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    execution_status: ExecutionStage = "idle"
    retry_count: int = 0
    error_log: list[str] = Field(default_factory=list)
    # Plan3 creative fields
    creative_intents: list[CreativeIntent] = Field(default_factory=list)
    generated_assets: list[LayerAsset] = Field(default_factory=list)
    creative_events: list[CreativeEvent] = Field(default_factory=list)
    # Plan9 staged generation fields
    generation_mode: str = GenerationMode.video  # stored as plain str so SqliteSaver can serialize it
    previsualization: Previsualization | None = None
    previsualization_feedback: str | None = None
    model_renders: list[str] | None = None
    model_feedback: str | None = None
    gltf_assembled_path: str | None = None  # API URL path to the assembled .glb, set by gltf_assembler
