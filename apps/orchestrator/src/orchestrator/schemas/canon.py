from typing import Literal

from pydantic import BaseModel, Field

AspectRatio = Literal["9:16", "16:9", "1:1", "4:5"]


class ProjectCanon(BaseModel):
    """Project-level constraints the orchestrator must honour."""

    aspect_ratio: AspectRatio
    duration_seconds_max: float = Field(gt=0)
    aesthetic_tags: list[str] = Field(default_factory=list)
    style_guide: str = ""
    banned_terms: list[str] = Field(default_factory=list)

    def aspect_value(self) -> float:
        w, h = self.aspect_ratio.split(":")
        return float(w) / float(h)
