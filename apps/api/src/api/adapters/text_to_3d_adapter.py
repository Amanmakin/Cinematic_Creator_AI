"""text→3D adapter — orchestrates OpenAI image gen + TripoSR (default) or Shap-E (offline).

Strategies (set via ``MESH_PIPELINE_STRATEGY`` env):

- ``openai_assisted``  — OpenAI ``gpt-image-1`` reference image → TripoSR. Highest quality.
- ``local_fallback``   — same as ``openai_assisted``; on OpenAI or TripoSR
                         failure, falls back to Shap-E (text→3D directly).
- ``local_only``       — Shap-E only. No external network calls.

The adapter returns a `MeshAsset` already persisted in the UAR.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from api.adapters.base import ProviderUnavailable
from api.adapters.shap_e_client import ShapEClient
from api.adapters.triposr_client import TripoSRClient
from api.reference_vision import analyze_reference_image, crop_to_object
from orchestrator.schemas.mesh_asset import BBox3, MeshAsset

logger = logging.getLogger(__name__)

_STRATEGIES = {"openai_assisted", "local_fallback", "local_only"}

DALLE_PROMPT_TEMPLATE = (
    "studio product photo, isolated white background, orthographic front view, {subject}"
)

# OpenAI image model. ``dall-e-3`` was retired; ``gpt-image-1`` is the current
# successor and returns base64 directly (no URL hop required).
OPENAI_IMAGE_MODEL = "gpt-image-1"


@dataclass
class TextTo3DResult:
    glb_bytes: bytes
    bounds: BBox3
    source: str            # "triposr" | "shap_e"
    reference_image_url: str | None = None


class TextTo3DAdapter:
    name = "text_to_3d"
    version = "1.0.0"

    def __init__(
        self,
        strategy: str = "openai_assisted",
        *,
        triposr_url: str = "http://localhost:8002",
        shap_e_url: str = "http://localhost:8003",
        openai_api_key: str = "",
        timeout_sec: float = 600.0,
    ) -> None:
        if strategy not in _STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy!r}. Choose from {_STRATEGIES}")
        self._strategy = strategy
        self._triposr = TripoSRClient(base_url=triposr_url, timeout_sec=timeout_sec)
        self._shap_e = ShapEClient(base_url=shap_e_url, timeout_sec=timeout_sec)
        self._openai_api_key = openai_api_key

    @property
    def strategy(self) -> str:
        return self._strategy

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def generate(
        self,
        subject: str,
        *,
        seed: int | None = None,
        strategy: str | None = None,
        reference_image: bytes | None = None,
    ) -> TextTo3DResult:
        if not subject.strip():
            raise ProviderUnavailable("text_to_3d requires a non-empty subject")

        active = strategy or self._strategy
        if active not in _STRATEGIES:
            raise ValueError(f"Unknown strategy {active!r}. Choose from {_STRATEGIES}")

        # A user-supplied reference image is the strongest signal — reconstruct
        # directly from it via TripoSR (image→3D), skipping text→image generation.
        if reference_image is not None:
            try:
                return await self._triposr_from_image(reference_image, subject)
            except ProviderUnavailable as exc:
                # TripoSR is down (typically an OOM crash mid-inference). The
                # openai_assisted path below would route through the *same*
                # TripoSR service, so it can't succeed either — degrade straight
                # to Shap-E text→3D. A real (if generic) mesh beats a hard failure,
                # which renders downstream as a placeholder cube.
                logger.warning(
                    "TripoSR reconstruction from reference image failed (%s); "
                    "degrading to Shap-E text→3D",
                    exc,
                )
                return await self._shap_e_only(subject, seed=seed)

        if active == "local_only":
            return await self._shap_e_only(subject, seed=seed)

        try:
            return await self._openai_assisted(subject)
        except ProviderUnavailable as exc:
            if active != "local_fallback":
                raise
            logger.warning("openai_assisted failed (%s); falling back to Shap-E", exc)
            return await self._shap_e_only(subject, seed=seed)

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    async def _openai_assisted(self, subject: str) -> TextTo3DResult:
        if not self._openai_api_key:
            raise ProviderUnavailable("openai_assisted requires OPENAI_API_KEY")

        prompt = DALLE_PROMPT_TEMPLATE.format(subject=subject)
        img_bytes = await _openai_image_generate(self._openai_api_key, prompt)
        glb, bounds = await self._triposr.generate(img_bytes, filename=f"{_slug(subject)}.png")
        return TextTo3DResult(
            glb_bytes=glb,
            bounds=bounds,
            source="triposr",
            reference_image_url=None,
        )

    async def _triposr_from_image(self, image_bytes: bytes, subject: str) -> TextTo3DResult:
        # Isolate the single main product first: a raw reference (e.g. a hand
        # holding a bottle) would otherwise be reconstructed whole. The vision
        # pass returns a bbox we crop to; TripoSR's rembg cleans residual
        # background inside the crop. Cached per image (shared with the route's
        # caption call). No key / no bbox → passthrough = today's behavior.
        analysis = analyze_reference_image(image_bytes, self._openai_api_key, hint=subject)
        image_bytes = crop_to_object(image_bytes, analysis.bbox_norm)
        glb, bounds = await self._triposr.generate(image_bytes, filename=f"{_slug(subject)}.png")
        return TextTo3DResult(glb_bytes=glb, bounds=bounds, source="triposr")

    async def _shap_e_only(self, subject: str, *, seed: int | None = None) -> TextTo3DResult:
        glb, bounds = await self._shap_e.generate(subject, seed=seed)
        return TextTo3DResult(glb_bytes=glb, bounds=bounds, source="shap_e")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in text.strip().lower())
    return cleaned[:48] or "subject"


async def _openai_image_generate(api_key: str, prompt: str) -> bytes:
    """Call OpenAI's image API (gpt-image-1) and return the raw PNG bytes.

    gpt-image-1 returns base64 in `b64_json` rather than a hosted URL, so we
    decode in-process and hand bytes directly to TripoSR — no extra HTTP fetch.
    """
    try:
        import base64

        import openai
    except ImportError as exc:
        raise ProviderUnavailable("openai package not installed") from exc

    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
    except openai.AuthenticationError as exc:
        raise ProviderUnavailable(f"OpenAI auth failed — check OPENAI_API_KEY: {exc}") from exc
    except openai.OpenAIError as exc:
        raise ProviderUnavailable(f"OpenAI error: {exc}") from exc

    item = resp.data[0]
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)
    # Backwards compat: some deployments may still return a URL.
    url = getattr(item, "url", None)
    if url:
        return await _fetch_bytes(url)
    raise ProviderUnavailable("OpenAI returned neither b64_json nor url")


async def _fetch_bytes(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"Reference image fetch failed: {exc}") from exc


# Wall-clock timing helper used by callers that record events.
def now_sec() -> float:
    return time.monotonic()
