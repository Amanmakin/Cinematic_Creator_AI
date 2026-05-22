"""Poly Haven adapter — fetch landscape-class glb models by subject text.

Workflow
--------
1. Read (or download once) the model index from
   ``{POLY_HAVEN_API_URL}/assets?t=models``.
2. Map a subject string → asset slug via tag intersection + name similarity.
3. Download the model's glb (1k variant) and HDRI environment into the cache
   directory; subsequent hits read from disk.

Cache layout (managed in :func:`_manifest_path`):

    data/poly_haven_cache/
    ├── manifest.json     # { slug: { glb_path, hdri_path, tags } }
    ├── models_index.json # snapshot of /assets?t=models
    ├── models/<slug>.glb
    └── hdri/<slug>.hdr

The adapter raises :class:`ProviderUnavailable` only on transport failures —
"no model matched" returns ``None`` so callers can choose a fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any

import httpx

from api.adapters.base import ProviderUnavailable

logger = logging.getLogger(__name__)


class PolyHavenMatch:
    """A resolved Poly Haven asset on disk."""

    def __init__(self, slug: str, glb_path: str, hdri_path: str | None, tags: list[str]) -> None:
        self.slug = slug
        self.glb_path = glb_path
        self.hdri_path = hdri_path
        self.tags = tags


class PolyHavenAdapter:
    name = "poly_haven"
    version = "1.0.0"

    def __init__(
        self,
        api_url: str = "https://api.polyhaven.com",
        cache_dir: str = "data/poly_haven_cache",
        timeout_sec: float = 60.0,
    ) -> None:
        self._api = api_url.rstrip("/")
        self._cache = cache_dir
        self._timeout = timeout_sec
        os.makedirs(os.path.join(cache_dir, "models"), exist_ok=True)
        os.makedirs(os.path.join(cache_dir, "hdri"), exist_ok=True)

    # ------------------------------------------------------------------
    # Index + manifest
    # ------------------------------------------------------------------

    async def _load_index(self) -> dict[str, Any]:
        idx_path = os.path.join(self._cache, "models_index.json")
        if os.path.exists(idx_path):
            try:
                with open(idx_path) as f:
                    return json.load(f)
            except Exception:
                pass
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._api}/assets", params={"t": "models"})
                resp.raise_for_status()
                data = resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(f"Poly Haven index unreachable: {exc}") from exc

        with open(idx_path, "w") as f:
            json.dump(data, f)
        return data

    def _manifest(self) -> dict[str, Any]:
        p = os.path.join(self._cache, "manifest.json")
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _write_manifest(self, m: dict[str, Any]) -> None:
        p = os.path.join(self._cache, "manifest.json")
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(m, f, indent=2)
        os.replace(tmp, p)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(text: str) -> list[str]:
        return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]

    def _score(self, query_tokens: list[str], slug: str, tags: list[str]) -> float:
        slug_tokens = self._normalise(slug)
        tag_tokens = [t.lower() for t in tags]

        # Tag intersection (0..1)
        if query_tokens:
            shared = sum(1 for q in query_tokens if q in tag_tokens)
            tag_score = shared / len(query_tokens)
        else:
            tag_score = 0.0

        # Slug similarity (0..1)
        slug_score = SequenceMatcher(
            None, " ".join(query_tokens), " ".join(slug_tokens)
        ).ratio()

        return 0.6 * tag_score + 0.4 * slug_score

    def _pick_slug(self, query: str, index: dict[str, Any]) -> str | None:
        tokens = self._normalise(query)
        if not tokens:
            return None
        best_slug: str | None = None
        best_score = 0.0
        for slug, meta in index.items():
            tags = meta.get("tags", []) if isinstance(meta, dict) else []
            score = self._score(tokens, slug, tags)
            if score > best_score:
                best_score = score
                best_slug = slug
        if best_score < 0.15:
            return None
        return best_slug

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def _download_glb(self, slug: str) -> str:
        dest = os.path.join(self._cache, "models", f"{slug}.glb")
        if os.path.exists(dest):
            return dest
        # Poly Haven returns per-asset files via /files/{slug}; pick the gltf 1k variant.
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                meta = await client.get(f"{self._api}/files/{slug}")
                meta.raise_for_status()
                files = meta.json()
                glb_node = (
                    files.get("gltf", {}).get("1k", {}).get("gltf")
                    or files.get("glb", {}).get("1k", {}).get("glb")
                )
                if not glb_node or "url" not in glb_node:
                    raise ProviderUnavailable(f"Poly Haven: no glb/gltf 1k variant for {slug}")
                url = glb_node["url"]
                blob = await client.get(url)
                blob.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Poly Haven download failed for {slug}: {exc}") from exc

        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob.content)
        os.replace(tmp, dest)
        return dest

    async def resolve(self, subject: str) -> PolyHavenMatch | None:
        """Map a subject string → on-disk Poly Haven asset, or None if nothing matched."""
        manifest = self._manifest()
        if subject in manifest:
            m = manifest[subject]
            if os.path.exists(m.get("glb_path", "")):
                return PolyHavenMatch(
                    slug=m["slug"],
                    glb_path=m["glb_path"],
                    hdri_path=m.get("hdri_path"),
                    tags=m.get("tags", []),
                )

        index = await self._load_index()
        slug = self._pick_slug(subject, index)
        if slug is None:
            return None

        glb_path = await self._download_glb(slug)
        tags = index.get(slug, {}).get("tags", []) if isinstance(index, dict) else []
        manifest[subject] = {"slug": slug, "glb_path": glb_path, "hdri_path": None, "tags": tags}
        self._write_manifest(manifest)
        return PolyHavenMatch(slug=slug, glb_path=glb_path, hdri_path=None, tags=tags)
