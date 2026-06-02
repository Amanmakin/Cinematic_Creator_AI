"""Plan 11 T1 — reference_vision: analyze (mocked OpenAI) + crop_to_object."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

from PIL import Image

from api import reference_vision
from api.reference_vision import (
    ReferenceAnalysis,
    analyze_reference_image,
    crop_to_object,
)


def _png_bytes(w: int = 100, h: int = 80, color=(120, 30, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _mock_openai(content: str):
    """Build a MagicMock standing in for ``openai.OpenAI`` returning ``content``."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    factory = MagicMock(return_value=client)
    return factory


def setup_function(_fn):
    reference_vision._ANALYSIS_CACHE.clear()


def test_analyze_parses_label_and_bbox():
    payload = json.dumps({"label": "water bottle", "bbox": [0.2, 0.1, 0.6, 0.9]})
    factory = _mock_openai(payload)
    with patch("openai.OpenAI", factory):
        result = analyze_reference_image(_png_bytes(), "sk-test", hint="bottle")
    assert result.label == "water bottle"
    assert result.bbox_norm == (0.2, 0.1, 0.6, 0.9)


def test_analyze_empty_key_returns_nulls():
    # No key → no network call attempted at all.
    with patch("openai.OpenAI") as factory:
        result = analyze_reference_image(_png_bytes(), "")
    assert result == ReferenceAnalysis(None, None)
    factory.assert_not_called()


def test_analyze_openai_error_returns_nulls():
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("boom")
    with patch("openai.OpenAI", MagicMock(return_value=client)):
        result = analyze_reference_image(_png_bytes(), "sk-test")
    assert result == ReferenceAnalysis(None, None)


def test_analyze_caches_per_image():
    payload = json.dumps({"label": "mug", "bbox": [0.1, 0.1, 0.5, 0.5]})
    factory = _mock_openai(payload)
    img = _png_bytes()
    with patch("openai.OpenAI", factory):
        analyze_reference_image(img, "sk-test")
        analyze_reference_image(img, "sk-test")
    # Two calls, one image → one network round-trip.
    factory.return_value.chat.completions.create.assert_called_once()


def test_analyze_rejects_degenerate_bbox():
    payload = json.dumps({"label": "thing", "bbox": [0.5, 0.5, 0.5, 0.9]})
    with patch("openai.OpenAI", _mock_openai(payload)):
        result = analyze_reference_image(_png_bytes(), "sk-test")
    assert result.label == "thing"
    assert result.bbox_norm is None


def test_crop_to_object_crops_padded_box_and_roundtrips_png():
    src = _png_bytes(200, 200)
    out = crop_to_object(src, (0.25, 0.25, 0.75, 0.75), padding=0.10)
    assert out != src
    cropped = Image.open(io.BytesIO(out))
    cropped.load()  # valid PNG
    # 0.5-wide box + 10% padding each side ≈ 0.6 of 200 = ~120px.
    assert 110 <= cropped.size[0] <= 130
    assert 110 <= cropped.size[1] <= 130


def test_crop_to_object_passthrough_when_no_bbox():
    src = _png_bytes()
    assert crop_to_object(src, None) is src
