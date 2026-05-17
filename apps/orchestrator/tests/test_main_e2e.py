"""End-to-end graph runs with a mocked LLM — no network, no OpenAI key."""

from __future__ import annotations

import pytest

from orchestrator import llm as llm_module
from orchestrator.graph import build_graph
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.schemas.intent import IntentSpec
from orchestrator.state import AgentState

from conftest import FakeLLM, make_valid_dsl


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm_module, "make_llm", lambda *a, **k: fake)
    return fake


def test_low_ambiguity_happy_path(fake_llm, canon, low_ambiguity_intent) -> None:
    fake_llm.enqueue(IntentSpec, low_ambiguity_intent)
    fake_llm.enqueue(BlenderDsl, make_valid_dsl())

    graph = build_graph()
    config = {"configurable": {"thread_id": "t-happy"}}
    final = graph.invoke(
        AgentState(user_prompt="prompt", project_canon=canon),
        config=config,
    )

    final_state = AgentState.model_validate(final)
    assert final_state.execution_status == "completed"
    assert isinstance(final_state.scene_graph, BlenderDsl)
    assert final_state.scene_graph.dsl_version == "1.0.0"
    assert final_state.validation_findings == []


def test_retry_then_fail_on_invalid_dsl(fake_llm, canon, low_ambiguity_intent) -> None:
    bad_one = make_valid_dsl()
    bad_one.scene.camera.focal_mm = 0.1  # under-range
    bad_two = make_valid_dsl()
    bad_two.scene.camera.focal_mm = 0.2  # still under-range
    bad_three = make_valid_dsl()
    bad_three.scene.camera.focal_mm = 0.3  # still under-range

    fake_llm.enqueue(IntentSpec, low_ambiguity_intent)
    fake_llm.enqueue(BlenderDsl, bad_one)
    fake_llm.enqueue(BlenderDsl, bad_two)
    fake_llm.enqueue(BlenderDsl, bad_three)

    graph = build_graph()
    config = {"configurable": {"thread_id": "t-retry"}}
    final = graph.invoke(
        AgentState(user_prompt="prompt", project_canon=canon),
        config=config,
    )

    final_state = AgentState.model_validate(final)
    assert final_state.execution_status == "physical_validation_failed"
    assert final_state.retry_count == 2
    assert any(
        f.code == "camera.focal_mm_out_of_range"
        for f in final_state.validation_findings
    )


def test_intent_failure_short_circuits(fake_llm, canon) -> None:
    bad = IntentSpec(
        subject="x",
        setting="y",
        duration_seconds=999,
        aspect_ratio="9:16",
    )
    fake_llm.enqueue(IntentSpec, bad)

    graph = build_graph()
    config = {"configurable": {"thread_id": "t-intent-fail"}}
    final = graph.invoke(
        AgentState(user_prompt="prompt", project_canon=canon),
        config=config,
    )

    final_state = AgentState.model_validate(final)
    assert final_state.execution_status == "failed"
    assert final_state.scene_graph is None
    assert any("duration_exceeds_canon" in m for m in final_state.error_log)


def test_speculative_branch_interrupts_before_batcher(
    fake_llm, canon, low_ambiguity_intent
) -> None:
    """Medium-ambiguity intent routes to the speculative batcher, which is
    breakpointed — invoke() should return *before* the batcher runs."""
    medium = low_ambiguity_intent.model_copy(update={
        "ambiguity_hints": low_ambiguity_intent.ambiguity_hints.model_copy(
            update={"confidence": 0.0, "underspecified_fields": ["lighting"]}
        )
    })
    fake_llm.enqueue(IntentSpec, medium)
    # No BlenderDsl queued — the batcher must not be invoked.

    graph = build_graph(interrupt_before_speculative=True)
    config = {"configurable": {"thread_id": "t-spec"}}
    graph.invoke(
        AgentState(user_prompt="prompt", project_canon=canon),
        config=config,
    )

    snapshot = graph.get_state(config)
    # Halted before speculative_batcher — it should still be a "next" task.
    assert "speculative_batcher" in snapshot.next
