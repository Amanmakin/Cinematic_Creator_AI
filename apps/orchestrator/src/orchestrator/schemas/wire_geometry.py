from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WirePrimitive(BaseModel):
    kind: Literal["box", "cylinder", "sphere"]
    label: str = Field(description="Human-readable part name, e.g. 'seat', 'front_left_leg'")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    width: float = Field(gt=0, description="X extent in metres (diameter for cylinder/sphere)")
    depth: float = Field(gt=0, description="Y extent in metres (same as width for cylinder/sphere)")
    height: float = Field(gt=0, description="Z extent in metres (height for cylinder)")
    rot_x: float = 0.0
    rot_y: float = 0.0
    rot_z: float = 0.0


class WireframeGeometry(BaseModel):
    subject: str = Field(description="Short name of the object being described")
    primitives: list[WirePrimitive] = Field(
        min_length=3,
        max_length=40,
        description="Geometric primitives that together form a recognisable wireframe of the subject",
    )
