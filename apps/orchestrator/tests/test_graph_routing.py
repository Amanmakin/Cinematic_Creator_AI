"""Routing-function unit tests — pure inputs, no LLM, no graph wiring."""

from __future__ import annotations

from orchestrator.routing import (
    MAX_RETRIES,
    route_after_intent,
    route_after_validation,
)
from orchestrator.state import AgentState, ValidationFinding


def _state(canon, **kwargs) -> AgentState:
    return AgentState(user_prompt="p", project_canon=canon, **kwargs)


def test_route_after_intent_proceed(canon) -> None:
    assert route_after_intent(_state(canon, ambiguity_score=0.1)) == "proceed"


def test_route_after_intent_speculative(canon) -> None:
    assert route_after_intent(_state(canon, ambiguity_score=0.5)) == "speculative"


def test_route_after_intent_human(canon) -> None:
    assert route_after_intent(_state(canon, ambiguity_score=0.9)) == "human_approval"


def test_route_after_intent_failed_short_circuits(canon) -> None:
    s = _state(canon, ambiguity_score=0.5, execution_status="failed")
    assert route_after_intent(s) == "fail"


def test_route_after_validation_success(canon) -> None:
    assert route_after_validation(_state(canon, validation_findings=[])) == "success"


def test_route_after_validation_retry(canon) -> None:
    s = _state(
        canon,
        retry_count=0,
        validation_findings=[
            ValidationFinding(severity="error", code="x", message="m", path=None)
        ],
    )
    assert route_after_validation(s) == "retry"


def test_route_after_validation_fail_when_retries_exhausted(canon) -> None:
    s = _state(
        canon,
        retry_count=MAX_RETRIES,
        validation_findings=[
            ValidationFinding(severity="error", code="x", message="m", path=None)
        ],
    )
    assert route_after_validation(s) == "fail"


def test_route_after_validation_warning_only_passes(canon) -> None:
    s = _state(
        canon,
        validation_findings=[
            ValidationFinding(severity="warning", code="x", message="m", path=None)
        ],
    )
    assert route_after_validation(s) == "success"
