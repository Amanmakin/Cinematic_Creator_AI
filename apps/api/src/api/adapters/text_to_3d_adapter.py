"""text→3D adapter — orchestrates DALL-E + TripoSR (default) or Shap-E (offline).

Strategies (set via ``MESH_PIPELINE_STRATEGY`` env):

- ``openai_assisted``  — DALL-E 3 reference image → TripoSR. Highest quality.
- ``local_fallback``   — same as ``openai_assisted``; on DALL-E or TripoSR
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
from orchestrator.schemas.mesh_asset import BBox3, MeshAsset

logger = logging.getLogger(__name__)

_STRATEGIES = {"openai_assisted", "local_fallback", "local_only"}

DALLE_PROMPT_TEMPLATE = (
    "studio product photo, isolated white background, orthographic front view, {subject}"
)


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
    ) -> TextTo3DResult:
        if not subject.strip():
            raise ProviderUnavailable("text_to_3d requires a non-empty subject")

        if self._strategy == "local_only":
            return await self._shap_e_only(subject, seed=seed)

        try:
            return await self._openai_assisted(subject)
        except ProviderUnavailable as exc:
            if self._strategy != "local_fallback":
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
        ref_url = await _dalle_generate(self._openai_api_key, prompt)
        img_bytes = await _fetch_bytes(ref_url)
        glb, bounds = await self._triposr.generate(img_bytes, filename=f"{_slug(subject)}.png")
        return TextTo3DResult(
            glb_bytes=glb,
            bounds=bounds,
            source="triposr",
            reference_image_url=ref_url,
        )

    async def _shap_e_only(self, subject: str, *, seed: int | None = None) -> TextTo3DResult:
        glb, bounds = await self._shap_e.generate(subject, seed=seed)
        return TextTo3DResult(glb_bytes=glb, bounds=bounds, source="shap_e")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in text.strip().lower())
    return cleaned[:48] or "subject"


async def _dalle_generate(api_key: str, prompt: str) -> str:
    """Call DALL-E 3 and return the URL of the generated image."""
    try:
        import openai
    except ImportError as exc:
        raise ProviderUnavailable("openai package not installed") from exc

    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
    except openai.AuthenticationError as exc:
        raise ProviderUnavailable(f"OpenAI auth failed — check OPENAI_API_KEY: {exc}") from exc
    except openai.OpenAIError as exc:
        raise ProviderUnavailable(f"OpenAI error: {exc}") from exc

    url = resp.data[0].url
    if not url:
        raise ProviderUnavailable("OpenAI returned no image URL")
    return url


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
