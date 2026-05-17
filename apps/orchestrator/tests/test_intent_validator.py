"""Unit tests for the IntentValidator node."""

from __future__ import annotations

import pytest

from orchestrator import llm as llm_module
from orchestrator.nodes.intent_validator import (
    compute_ambiguity_score,
    intent_validator_node,
)
from orchestrator.schemas.intent import AmbiguityHints, IntentSpec
from orchestrator.state import AgentState

from conftest import FakeLLM


def test_ambiguity_score_formula(low_ambiguity_intent: IntentSpec) -> None:
    score = compute_ambiguity_score(low_ambiguity_intent)
    # confidence=0.95, no underspec, no conflicts -> 0.5 * 0.05 = 0.025
    assert score == pytest.approx(0.025, abs=1e-6)


def test_ambiguity_score_clamped_to_one() -> None:
    intent = IntentSpec(
        subject="x",
        setting="y",
        duration_seconds=5,
        aspect_ratio="9:16",
        ambiguity_hints=AmbiguityHints(
            underspecified_fields=["a", "b", "c", "d", "e"],
            conflicting_directives=["x", "y", "z"],
            confidence=0.0,
        ),
    )
    # 0.5 + 0.1*5 + 0.2*3 = 1.6 -> clamped to 1.0
    assert compute_ambiguity_score(intent) == 1.0


def test_node_emits_intent_validated(monkeypatch, canon, low_ambiguity_intent) -> None:
    fake = FakeLLM()
    fake.enqueue(IntentSpec, low_ambiguity_intent)
    monkeypatch.setattr(llm_module, "make_llm", lambda *a, **k: fake)

    state = AgentState(user_prompt="prompt", project_canon=canon)
    out = intent_validator_node(state)

    assert out["execution_status"] == "intent_validated"
    assert out["intent"] == low_ambiguity_intent
    assert out["ambiguity_score"] == pytest.approx(0.025, abs=1e-6)


def test_node_rejects_duration_over_canon(monkeypatch, canon) -> None:
    bad = IntentSpec(
        subject="x",
        setting="y",
        duration_seconds=999,  # > canon.duration_seconds_max=15
        aspect_ratio="9:16",
    )
    fake = FakeLLM()
    fake.enqueue(IntentSpec, bad)
    monkeypatch.setattr(llm_module, "make_llm", lambda *a, **k: fake)

    out = intent_validator_node(AgentState(user_prompt="p", project_canon=canon))
    assert out["execution_status"] == "failed"
    assert any("duration_exceeds_canon" in m for m in out["error_log"])


def test_node_rejects_banned_term(monkeypatch, canon) -> None:
    bad = IntentSpec(
        subject="nsfw subject",
        setting="studio",
        duration_seconds=5,
        aspect_ratio="9:16",
    )
    fake = FakeLLM()
    fake.enqueue(IntentSpec, bad)
    monkeypatch.setattr(llm_module, "make_llm", lambda *a, **k: fake)

    out = intent_validator_node(AgentState(user_prompt="p", project_canon=canon))
    assert out["execution_status"] == "failed"
    assert any("banned_term" in m for m in out["error_log"])


def test_node_rejects_aspect_mismatch(monkeypatch, canon) -> None:
    bad = IntentSpec(
        subject="x",
        setting="y",
        duration_seconds=5,
        aspect_ratio="16:9",
    )
    fake = FakeLLM()
    fake.enqueue(IntentSpec, bad)
    monkeypatch.setattr(llm_module, "make_llm", lambda *a, **k: fake)

    out = intent_validator_node(AgentState(user_prompt="p", project_canon=canon))
    assert out["execution_status"] == "failed"
    assert any("aspect_ratio_mismatch" in m for m in out["error_log"])
