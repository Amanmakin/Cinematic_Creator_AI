"""Test ReplicateAdapter.translate() payload shape — no network calls."""

import pytest

from orchestrator.schemas.creative import CreativeIntent, ProviderPayload


class _Ctx:
    project_id = "proj-test"
    uar_root = "/tmp/uar"


def _adapter():
    from api.adapters.replicate_adapter import ReplicateAdapter
    return ReplicateAdapter(api_key="sk-test-fake")


def test_generate_subject_payload():
    adapter = _adapter()
    intent = CreativeIntent(
        kind="generate_subject",
        target_path="scene.subjects[0]",
        parameters={"prompt": "a warrior queen", "width": 1024, "height": 1024},
        seed=7,
    )
    payload = adapter.translate(intent, _Ctx())

    assert "sdxl" in payload.model
    assert payload.inputs["prompt"] == "a warrior queen"
    assert payload.inputs["width"] == 1024
    assert payload.inputs["seed"] == 7
    assert payload.estimated_tokens > 0


def test_generate_background_payload():
    adapter = _adapter()
    intent = CreativeIntent(
        kind="generate_background",
        target_path="scene.background",
        parameters={"prompt": "misty forest", "width": 1920, "height": 1080},
        seed=99,
    )
    payload = adapter.translate(intent, _Ctx())

    assert "sdxl" in payload.model
    assert payload.inputs["prompt"] == "misty forest"
    assert payload.inputs["width"] == 1920
    assert payload.inputs["height"] == 1080


def test_regenerate_layer_uses_controlnet():
    adapter = _adapter()
    intent = CreativeIntent(
        kind="regenerate_layer",
        target_path="scene.subjects[0]",
        parameters={
            "original_asset_id": "abc123",
            "modification_prompt": "make her angrier",
            "use_controlnet": True,
        },
        seed=3,
    )
    payload = adapter.translate(intent, _Ctx())

    assert "controlnet" in payload.model.lower()
    assert payload.inputs["prompt"] == "make her angrier"


def test_noop_intents_return_noop_payload():
    adapter = _adapter()
    for kind in ("apply_warm_lighting", "apply_cool_lighting", "apply_lens_blur", "stylize_palette"):
        intent = CreativeIntent(
            kind=kind,  # type: ignore[arg-type]
            target_path="scene.subjects[0]",
            parameters={},
            seed=0,
        )
        payload = adapter.translate(intent, _Ctx())
        assert payload.model == "noop"
        assert payload.estimated_tokens == 0


def test_cost_estimate_proportional_to_resolution():
    adapter = _adapter()

    small = CreativeIntent(
        kind="generate_subject",
        target_path="scene.subjects[0]",
        parameters={"prompt": "test", "width": 512, "height": 512},
        seed=0,
    )
    large = CreativeIntent(
        kind="generate_subject",
        target_path="scene.subjects[0]",
        parameters={"prompt": "test", "width": 2048, "height": 2048},
        seed=0,
    )

    p_small = adapter.translate(small, _Ctx())
    p_large = adapter.translate(large, _Ctx())

    assert adapter.cost_estimate(p_large) > adapter.cost_estimate(p_small)
