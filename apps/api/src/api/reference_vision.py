"""Reference-image vision helper — pick the single main product, crop to it.

One OpenAI-vision call per reference image answers two needs (Plan 11):

1. **Object isolation** — return a normalized bounding box around the single
   product a user would want a 3D model of (excluding hands/arms/people/
   background) so the adapter can crop *before* TripoSR reconstructs.
2. **Auto-caption** — return a short ``label`` that seeds the pipeline when the
   user submits a reference image with no text prompt.

The call is memoized on ``sha256(image_bytes)`` so the route (caption) and the
adapter (crop) share a single network round-trip. Anything missing — no key, no
bytes, an OpenAI error, an unparseable reply — degrades to
``ReferenceAnalysis(None, None)``, which preserves today's behavior (no crop,
caption fallback handled by the caller).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Vision model. ``gpt-4o`` sees images and returns structured JSON; override via
# env for cheaper/newer models without a code change.
REFERENCE_VISION_MODEL = os.environ.get("REFERENCE_VISION_MODEL", "gpt-4o")

_SYSTEM_PROMPT = (
    "You are a vision assistant that isolates the single main product or object "
    "a user would want a 3D model of from a reference photo. Exclude hands, arms, "
    "people, and background. Respond ONLY with a JSON object of the form "
    '{"label": "<short noun phrase>", "bbox": [x0, y0, x1, y1]} where the bbox is '
    "the normalized bounding box of that object with each coordinate in 0..1 "
    "(x0,y0 = top-left, x1,y1 = bottom-right). If no clear object is present, use "
    "null for bbox."
)


@dataclass(frozen=True)
class ReferenceAnalysis:
    """Result of the vision pass. Both fields are ``None`` on any failure."""

    label: str | None = None
    bbox_norm: tuple[float, ...] | None = None


# sha256(image_bytes) -> ReferenceAnalysis. A plain dict (rather than
# functools.lru_cache) keeps the multi-megabyte image bytes out of the cache key
# while still guaranteeing one network call per image.
_ANALYSIS_CACHE: dict[str, ReferenceAnalysis] = {}


def analyze_reference_image(
    image_bytes: bytes,
    api_key: str,
    *,
    hint: str | None = None,
) -> ReferenceAnalysis:
    """Identify the main object in ``image_bytes``; cached per image content.

    ``hint`` (the user's prompt, if any) biases which object is selected. Returns
    ``ReferenceAnalysis(None, None)`` when bytes/key are empty or the call fails.
    """
    if not image_bytes or not api_key:
        return ReferenceAnalysis(None, None)

    digest = hashlib.sha256(image_bytes).hexdigest()
    cached = _ANALYSIS_CACHE.get(digest)
    if cached is not None:
        return cached

    result = _call_vision(image_bytes, api_key, hint)
    _ANALYSIS_CACHE[digest] = result
    return result


def _call_vision(image_bytes: bytes, api_key: str, hint: str | None) -> ReferenceAnalysis:
    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed; skipping reference analysis")
        return ReferenceAnalysis(None, None)

    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    user_text = "Identify the single main object in this reference photo."
    if hint and hint.strip():
        user_text += f" The user is interested in: {hint.strip()}."

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=REFERENCE_VISION_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
    except Exception as exc:  # openai errors, network, etc. — degrade gracefully
        logger.warning("reference vision call failed (%s); no crop/caption", exc)
        return ReferenceAnalysis(None, None)

    return _parse_analysis(content)


def _parse_analysis(content: str) -> ReferenceAnalysis:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("reference vision returned non-JSON content; ignoring")
        return ReferenceAnalysis(None, None)

    label = data.get("label")
    if isinstance(label, str):
        label = label.strip() or None
    else:
        label = None

    bbox = _coerce_bbox(data.get("bbox"))
    return ReferenceAnalysis(label=label, bbox_norm=bbox)


def _coerce_bbox(raw: object) -> tuple[float, ...] | None:
    """Validate a normalized ``[x0, y0, x1, y1]`` box; clamp to 0..1."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        coords = [min(1.0, max(0.0, float(v))) for v in raw]
    except (TypeError, ValueError):
        return None
    x0, y0, x1, y1 = coords
    # Degenerate / zero-area box → treat as no selection.
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def crop_to_object(
    image_bytes: bytes,
    bbox_norm: tuple[float, ...] | None,
    *,
    padding: float = 0.10,
) -> bytes:
    """Crop ``image_bytes`` to the padded ``bbox_norm``, re-encoded as PNG.

    Returns the input unchanged when ``bbox_norm`` is ``None`` or the image can't
    be opened. ``padding`` adds ~10% of the box size on each side so TripoSR sees
    a little context (its ``rembg`` pass cleans residual background).
    """
    if not bbox_norm:
        return image_bytes

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as exc:
        logger.warning("crop_to_object could not open image (%s); passthrough", exc)
        return image_bytes

    w, h = img.size
    x0, y0, x1, y1 = bbox_norm
    bw, bh = x1 - x0, y1 - y0
    x0 = max(0.0, x0 - bw * padding)
    y0 = max(0.0, y0 - bh * padding)
    x1 = min(1.0, x1 + bw * padding)
    y1 = min(1.0, y1 + bh * padding)

    px0, py0 = int(x0 * w), int(y0 * h)
    px1, py1 = int(round(x1 * w)), int(round(y1 * h))
    if px1 <= px0 or py1 <= py0:
        return image_bytes

    crop = img.crop((px0, py0, px1, py1))
    if crop.mode not in ("RGB", "RGBA"):
        crop = crop.convert("RGBA")
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()
