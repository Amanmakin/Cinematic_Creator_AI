"""OpenAI text-embedding-3-small wrapper with an in-process LRU cache.

Embeddings are deterministic for a given text, so caching aggressively is safe.
"""

from __future__ import annotations

import hashlib
import struct
from functools import lru_cache

import numpy as np

_EMBEDDING_MODEL = "text-embedding-3-small"
_DIM = 1536


@lru_cache(maxsize=4096)
def _cached_embed(text: str) -> tuple[float, ...]:
    """Inner function so lru_cache key is just the text string."""
    from openai import OpenAI

    from api.settings import settings

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=_EMBEDDING_MODEL, input=text)
    return tuple(resp.data[0].embedding)


def embed(text: str) -> list[float]:
    """Return a 1536-d embedding for *text*, using the in-process cache."""
    return list(_cached_embed(text.strip()))


def embed_to_blob(text: str) -> bytes:
    """Return the embedding serialised as little-endian float32 bytes for SQLite BLOB storage."""
    vec = embed(text)
    return struct.pack(f"<{len(vec)}f", *vec)


def blob_to_array(blob: bytes) -> np.ndarray:
    n = len(blob) // 4
    return np.array(struct.unpack(f"<{n}f", blob), dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
