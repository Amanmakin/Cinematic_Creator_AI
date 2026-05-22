from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

CreativeIntentKind = Literal[
    "generate_subject",
    "generate_background",
    "generate_foreground_fx",
    "apply_warm_lighting",
    "apply_cool_lighting",
    "apply_lens_blur",
    "stylize_palette",
    "regenerate_layer",
    # Plan10 text→3D
    "generate_mesh",
]

OutputKind = Literal["mesh", "image", "wire"]


class GenerateSubjectParams(BaseModel):
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    remove_background: bool = True


class GenerateBackgroundParams(BaseModel):
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    style: str = "photorealistic"


class GenerateForegroundFxParams(BaseModel):
    fx_type: str
    prompt: str
    width: int = 1024
    height: int = 1024


class ApplyWarmLightingParams(BaseModel):
    intensity: float = Field(default=1.0, ge=0.0, le=10.0)
    temperature_kelvin: int = Field(default=3200, ge=1000, le=20000)


class ApplyCoolLightingParams(BaseModel):
    intensity: float = Field(default=1.0, ge=0.0, le=10.0)
    temperature_kelvin: int = Field(default=6500, ge=1000, le=20000)


class ApplyLensBlurParams(BaseModel):
    amount: float = Field(default=1.0, ge=0.0, le=10.0)
    focal_distance: float = Field(default=0.5, ge=0.0, le=1.0)


class StylizePaletteParams(BaseModel):
    palette: list[str]
    strength: float = Field(default=0.8, ge=0.0, le=1.0)


class RegenerateLayerParams(BaseModel):
    original_asset_id: str
    modification_prompt: str
    use_controlnet: bool = True


class GenerateMeshParams(BaseModel):
    prompt: str
    subject_class: Literal["object", "landscape"] = "object"
    negative_prompt: str = ""
    reference_image_url: str | None = None
    style_hint: str = "studio product photo, isolated white background, orthographic front view"


class CreativeIntent(BaseModel):
    kind: CreativeIntentKind
    target_path: str
    parameters: dict[str, Any]
    seed: int
    adapter_hint: str | None = "local.sdxl"
    output_kind: OutputKind = "image"


class AssetRef(BaseModel):
    asset_id: str
    adapter: str
    adapter_version: str
    source_url: str | None = None  # file:// or http:// URL to the raw generated image


class LayerAsset(BaseModel):
    id: str
    kind: Literal["subject", "background", "fx"]
    rgba_path: str
    alpha_mask_path: str
    depth_map_path: str
    bbox_px: tuple[int, int, int, int]
    adapter: str
    adapter_version: str
    created_at: float = Field(default_factory=time.time)


class ProviderPayload(BaseModel):
    model: str
    inputs: dict[str, Any]
    adapter_hint: str
    estimated_tokens: int = 0
