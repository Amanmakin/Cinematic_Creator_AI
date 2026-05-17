"""Conditional-edge routing functions for the StateGraph."""

from orchestrator.state import AgentState

HUMAN_APPROVAL_THRESHOLD = 0.8
SPECULATIVE_THRESHOLD = 0.4
MAX_RETRIES = 2


def route_after_intent(state: AgentState) -> str:
    if state.execution_status == "failed":
        return "fail"
    if state.ambiguity_score > HUMAN_APPROVAL_THRESHOLD:
        return "human_approval"
    if state.ambiguity_score > SPECULATIVE_THRESHOLD:
        return "speculative"
    return "proceed"


def route_after_validation(state: AgentState) -> str:
    has_error = any(f.severity == "error" for f in state.validation_findings)
    if not has_error:
        return "success"
    if state.retry_count >= MAX_RETRIES:
        return "fail"
    return "retry"
