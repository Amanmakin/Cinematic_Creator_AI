"""Single seam for LLM construction so tests can monkeypatch one place."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Type

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = os.getenv("ORCHESTRATOR_LLM_MODEL", "gpt-4o-mini")

# Fixture file written by RECORD_LLM=true and read by DUMMY_LLM=true.
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wooden_chair.json"

# Runtime-overridable config — set via configure_llm() from the API layer.
_config: dict[str, str | None] = {
    "model": None,
    "base_url": None,
}


def configure_llm(*, model: str | None = None, base_url: str | None = None) -> None:
    """Override LLM model/endpoint at runtime (takes effect on the next make_llm() call)."""
    _config["model"] = model
    _config["base_url"] = base_url


# ---------------------------------------------------------------------------
# Dummy LLM — activated by DUMMY_LLM=true (no OpenAI key required)
# Loads responses from fixtures/wooden_chair.json (written by RECORD_LLM=true).
# Falls back to hard-coded shapes when the fixture file is absent.
# ---------------------------------------------------------------------------

def _load_fixture(schema_name: str) -> Any | None:
    """Return a parsed Pydantic object from the saved fixture file, or None."""
    if not _FIXTURE_PATH.exists():
        return None
    try:
        data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        raw = data.get(schema_name)
        if raw is None:
            return None
        if schema_name == "IntentSpec":
            from orchestrator.schemas.intent import IntentSpec
            return IntentSpec.model_validate(raw)
        if schema_name == "BlenderDsl":
            from orchestrator.schemas.dsl import BlenderDsl
            return BlenderDsl.model_validate(raw)
        if schema_name == "_SpeculativeBatch":
            from orchestrator.nodes.speculative_batcher import _SpeculativeBatch
            return _SpeculativeBatch.model_validate(raw)
    except Exception:
        pass
    return None


def _wooden_chair_intent():
    from orchestrator.schemas.intent import AmbiguityHints, CameraHint, IntentSpec
    return IntentSpec(
        subject="wooden chair",
        setting="neutral studio backdrop",
        mood_tags=["clean", "product-shot", "natural"],
        duration_seconds=5.0,
        aspect_ratio="16:9",
        motion_hints=["static"],
        camera_hint=CameraHint(focal_mm=50.0, movement="static"),
        ambiguity_hints=AmbiguityHints(confidence=0.95),
    )


def _wooden_chair_dsl():
    from orchestrator.schemas.dsl import (
        BlenderDsl, Camera, Light, Scene, SubjectPlaceholder, Vec3, WorldEnv,
    )
    return BlenderDsl(
        dsl_version="1.0.0",
        scene=Scene(
            duration_s=5.0,
            fps=24,
            resolution=[1920, 1080],
            camera=Camera(
                focal_mm=50.0,
                sensor_mm=36.0,
                position=Vec3(x=0.0, y=-3.0, z=1.2),
                look_at=Vec3(x=0.0, y=0.0, z=0.5),
                f_stop=5.6,
            ),
            lights=[
                Light(
                    kind="key",
                    position=Vec3(x=-2.0, y=-1.0, z=3.0),
                    intensity=800.0,
                    color_kelvin=5500,
                ),
                Light(
                    kind="fill",
                    position=Vec3(x=2.0, y=-1.0, z=2.0),
                    intensity=300.0,
                    color_kelvin=6000,
                ),
            ],
            subjects=[
                SubjectPlaceholder(
                    aabb_min=Vec3(x=-0.35, y=-0.35, z=0.0),
                    aabb_max=Vec3(x=0.35, y=0.35, z=0.9),
                    description="wooden chair — oak finish, four legs, slatted back",
                    asset_ref=None,
                )
            ],
            world=WorldEnv(background_color=[0.9, 0.9, 0.88]),
        ),
    )


class _StructuredChain:
    """Stand-in for LangChain's structured-output chain used by _DummyLLM."""

    def __init__(self, schema: Type) -> None:
        self._schema = schema

    def invoke(self, _messages: Any) -> dict:
        from langchain_core.messages import AIMessage

        schema_name = self._schema.__name__

        # Prefer saved fixture over hardcoded fallbacks.
        parsed = _load_fixture(schema_name)
        if parsed is None:
            if schema_name == "IntentSpec":
                parsed = _wooden_chair_intent()
            elif schema_name == "BlenderDsl":
                parsed = _wooden_chair_dsl()
            elif schema_name == "_SpeculativeBatch":
                from orchestrator.nodes.speculative_batcher import _SpeculativeBatch
                parsed = _SpeculativeBatch(variants=[_wooden_chair_dsl(), _wooden_chair_dsl(), _wooden_chair_dsl()])
            else:
                raise ValueError(f"DummyLLM: no fixture for schema '{schema_name}'")

        return {
            "raw": AIMessage(content="[dummy]"),
            "parsed": parsed,
            "parsing_error": None,
        }


class _DummyLLM:
    model_name: str = "dummy-llm"

    def with_structured_output(self, schema: Type, *, include_raw: bool = False, **_kwargs: Any) -> _StructuredChain:
        return _StructuredChain(schema)


# ---------------------------------------------------------------------------
# Recording LLM — activated by RECORD_LLM=true
# Makes real OpenAI calls and saves each parsed response to the fixture file.
# Run once for "Create a wooden chair"; subsequent runs can use DUMMY_LLM=true.
# ---------------------------------------------------------------------------

class _RecordingStructuredChain:
    """Wraps a real structured-output chain and saves the parsed result to disk."""

    def __init__(self, real_chain: Any, schema: Type) -> None:
        self._chain = real_chain
        self._schema = schema

    def invoke(self, messages: Any) -> dict:
        result = self._chain.invoke(messages)
        parsed = result.get("parsed")
        if parsed is not None:
            _save_fixture(self._schema.__name__, parsed)
        return result


def _save_fixture(schema_name: str, parsed: Any) -> None:
    _FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if _FIXTURE_PATH.exists():
        try:
            existing = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing[schema_name] = parsed.model_dump(mode="json")
    _FIXTURE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


class _RecordingLLM:
    """Real ChatOpenAI that records every structured-output response to the fixture file."""

    def __init__(self, real_llm: Any) -> None:
        self._llm = real_llm
        self.model_name: str = getattr(real_llm, "model_name", "recording-llm")

    def with_structured_output(self, schema: Type, *, include_raw: bool = False, **kwargs: Any) -> _RecordingStructuredChain:
        real_chain = self._llm.with_structured_output(schema, include_raw=include_raw, **kwargs)
        return _RecordingStructuredChain(real_chain, schema)


def make_llm(model: str | None = None, temperature: float = 0.2):
    if os.getenv("DUMMY_LLM", "").lower() in ("1", "true", "yes"):
        return _DummyLLM()

    resolved_model = model or _config["model"] or DEFAULT_MODEL
    base_url = _config["base_url"] or None
    kwargs: dict = {"model": resolved_model, "temperature": temperature, "timeout": 600}
    if base_url:
        kwargs["base_url"] = base_url
        # Local endpoints (Ollama etc.) don't need a real key but the client requires one.
        kwargs.setdefault("api_key", os.getenv("OPENAI_API_KEY", "ollama"))
    real = ChatOpenAI(**kwargs)

    if os.getenv("RECORD_LLM", "").lower() in ("1", "true", "yes"):
        return _RecordingLLM(real)

    return real


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    """Read a system prompt file shipped alongside the package."""
    path = Path(__file__).parent / "prompts" / name
    return path.read_text(encoding="utf-8")
