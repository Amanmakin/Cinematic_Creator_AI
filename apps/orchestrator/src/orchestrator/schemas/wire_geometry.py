from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MaterialHint = Literal["wood", "metal", "plastic", "fabric", "glass", "stone", "default"]


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
    material_hint: MaterialHint = Field(
        default="default",
        description="Dominant material of this part — used to tint the wireframe colour.",
    )
    color_hex: str | None = Field(
        default=None,
        description=(
            "Optional CSS hex color override e.g. '#C8A06E'. Overrides the material_hint tint. "
            "Use this for precise product colors (wood grain tones, brand colors, etc.)."
        ),
    )
    gradient_bottom_hex: str | None = Field(
        default=None,
        description=(
            "If set, a vertical gradient is applied: color_hex at the top, gradient_bottom_hex "
            "at the bottom. Ideal for gradient-painted bottles, ombre finishes, etc. "
            "Requires color_hex to also be set."
        ),
    )


class WireframeGeometry(BaseModel):
    subject: str = Field(description="Short name of the object being described")
    primitives: list[WirePrimitive] = Field(
        min_length=3,
        max_length=40,
        description="Geometric primitives that together form a recognisable wireframe of the subject",
    )
