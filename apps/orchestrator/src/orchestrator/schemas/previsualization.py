from typing import Literal

from pydantic import BaseModel


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
    wireframe_sheet_path: str | None = None
    wireframe_glb_path: str | None = None
