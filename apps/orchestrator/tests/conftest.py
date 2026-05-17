"""Shared test fixtures: fake LLM, canonical sample DSL, canonical canon."""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import (
    BlenderDsl,
    Camera,
    Light,
    Scene,
    SubjectPlaceholder,
    Vec3,
)
from orchestrator.schemas.intent import AmbiguityHints, IntentSpec


class _StructuredStub:
    """Stand-in for `llm.with_structured_output(Schema)` — pops from a queue."""

    def __init__(self, schema: type, queue: deque, include_raw: bool = False):
        self._schema = schema
        self._queue = queue
        self._include_raw = include_raw

    def invoke(self, _messages: Any) -> Any:
        if not self._queue:
            raise RuntimeError(f"FakeLLM has no queued response for {self._schema.__name__}")
        item = self._queue.popleft()
        if isinstance(item, Exception):
            raise item
        parsed = item if isinstance(item, self._schema) else self._schema.model_validate(item)
        if self._include_raw:
            return {"parsed": parsed, "raw": None, "parsing_error": None}
        return parsed


class FakeLLM:
    """Replaces `make_llm()` — routes structured calls to a per-schema queue."""

    def __init__(self) -> None:
        self._queues: dict[type, deque] = {}
        self.model_name = "fake-llm"

    def enqueue(self, schema: type, value: Any) -> None:
        self._queues.setdefault(schema, deque()).append(value)

    def with_structured_output(self, schema: type, **kwargs: Any) -> _StructuredStub:
        include_raw = kwargs.get("include_raw", False)
        return _StructuredStub(schema, self._queues.setdefault(schema, deque()), include_raw=include_raw)


@pytest.fixture
def canon() -> ProjectCanon:
    return ProjectCanon(
        aspect_ratio="9:16",
        duration_seconds_max=15.0,
        aesthetic_tags=["modern", "natural"],
        style_guide="Warm tones.",
        banned_terms=["nsfw"],
    )


@pytest.fixture
def low_ambiguity_intent() -> IntentSpec:
    return IntentSpec(
        subject="woman wearing a modern kurti",
        setting="warm-lit minimal studio",
        mood_tags=["warm", "slow-motion", "cinematic"],
        duration_seconds=12.0,
        aspect_ratio="9:16",
        motion_hints=["slow_motion"],
        camera_hint=None,
        ambiguity_hints=AmbiguityHints(
            underspecified_fields=[],
            conflicting_directives=[],
            confidence=0.95,
        ),
    )


def make_valid_dsl(focal_mm: float = 50.0, duration_s: float = 10.0) -> BlenderDsl:
    return BlenderDsl(
        scene=Scene(
            duration_s=duration_s,
            fps=24,
            resolution=(1080, 1920),
            camera=Camera(
                focal_mm=focal_mm,
                sensor_mm=36.0,
                position=Vec3(x=0.0, y=-3.0, z=1.6),
                look_at=Vec3(x=0.0, y=0.0, z=1.5),
                f_stop=2.8,
            ),
            lights=[
                Light(kind="key", position=Vec3(x=2.0, y=-2.0, z=2.5), intensity=800.0, color_kelvin=4200),
                Light(kind="fill", position=Vec3(x=-2.0, y=-1.0, z=2.0), intensity=300.0, color_kelvin=5600),
            ],
            subjects=[
                SubjectPlaceholder(
                    aabb_min=Vec3(x=-0.4, y=-0.4, z=0.0),
                    aabb_max=Vec3(x=0.4, y=0.4, z=1.8),
                    description="primary subject standing",
                )
            ],
        )
    )


@pytest.fixture
def valid_dsl() -> BlenderDsl:
    return make_valid_dsl()
