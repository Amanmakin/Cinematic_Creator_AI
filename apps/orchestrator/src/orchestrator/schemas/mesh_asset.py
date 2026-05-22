from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

MeshSource = Literal["triposr", "shap_e", "poly_haven"]
MaterialSummary = Literal["pbr", "stylised", "wire"]


class BBox3(BaseModel):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def size(self) -> tuple[float, float, float]:
        return (
            self.max_x - self.min_x,
            self.max_y - self.min_y,
            self.max_z - self.min_z,
        )

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
            (self.min_z + self.max_z) / 2.0,
        )


class MeshAsset(BaseModel):
    asset_id: str = Field(description="sha256(glb_bytes) — content address")
    glb_path: str = Field(description="Absolute path to the .glb file on local disk")
    bounds_m: BBox3 = Field(description="Axis-aligned bounding box in metres, model-space")
    material_summary: MaterialSummary = "stylised"
    source: MeshSource
    target_path: str = Field(
        default="",
        description="Scene-graph path the mesh should be placed under (e.g. 'subject', 'background')",
    )
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    adapter: str = ""
    adapter_version: str = ""
    created_at: float = Field(default_factory=time.time)
