"""Async HTTP client for the TripoSR Docker service.

Bubbles errors up as `ProviderUnavailable` so the text_to_3d adapter can
decide whether to fall back or fail.
"""

from __future__ import annotations

import email
import io
import json
import logging
from email.parser import BytesParser
from email.policy import default

import httpx

from api.adapters.base import ProviderUnavailable
from orchestrator.schemas.mesh_asset import BBox3

logger = logging.getLogger(__name__)


class TripoSRClient:
    name = "triposr"
    version = "1.0.0"

    def __init__(self, base_url: str = "http://localhost:8002", timeout_sec: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            return False

    async def generate(self, image_bytes: bytes, filename: str = "ref.png") -> tuple[bytes, BBox3]:
        """POST an image and return (glb_bytes, bounds)."""
        if not await self.health_check():
            raise ProviderUnavailable(
                f"TripoSR service unavailable at {self._base_url}. "
                "Run: docker compose up -d triposr"
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/generate",
                    files={"image": (filename, image_bytes, "image/png")},
                )
                resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"TripoSR unreachable: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"TripoSR timed out after {self._timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                f"TripoSR HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

        return _parse_mesh_multipart(resp.content, resp.headers.get("content-type", ""))


def _parse_mesh_multipart(body: bytes, content_type: str) -> tuple[bytes, BBox3]:
    """Parse the (glb, bounds.json) multipart body our docker services emit."""
    headers = f"Content-Type: {content_type}\r\n\r\n".encode()
    msg = BytesParser(policy=default).parsebytes(headers + body)
    glb_bytes: bytes | None = None
    bounds: BBox3 | None = None
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        payload = part.get_payload(decode=True)
        if name == "mesh.glb":
            glb_bytes = payload
        elif name == "bounds.json":
            bounds = BBox3.model_validate(json.loads(payload.decode()))
    if glb_bytes is None or bounds is None:
        raise ProviderUnavailable("TripoSR response missing mesh.glb or bounds.json")
    return glb_bytes, bounds
