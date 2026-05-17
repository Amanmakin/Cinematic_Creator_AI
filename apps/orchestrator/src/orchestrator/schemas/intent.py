from typing import Literal

from pydantic import BaseModel, Field

from orchestrator.schemas.canon import AspectRatio


class CameraHint(BaseModel):
    """Optional camera intent extracted from the prompt."""

    focal_mm: float | None = None
    movement: str | None = None  # e.g. "dolly_in", "static", "handheld"


class AmbiguityHints(BaseModel):
    """LLM self-reported uncertainty about the extracted intent."""

    underspecified_fields: list[str] = Field(default_factory=list)
    conflicting_directives: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class IntentSpec(BaseModel):
    """Typed extraction of the user prompt."""

    subject: str
    setting: str
    mood_tags: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(gt=0)
    aspect_ratio: AspectRatio
    motion_hints: list[str] = Field(default_factory=list)
    camera_hint: CameraHint | None = None
    ambiguity_hints: AmbiguityHints = Field(default_factory=AmbiguityHints)
