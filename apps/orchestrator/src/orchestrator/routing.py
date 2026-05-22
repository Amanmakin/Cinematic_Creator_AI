"""Conditional-edge routing functions for the StateGraph."""

from orchestrator.state import AgentState

HUMAN_APPROVAL_THRESHOLD = 0.8
SPECULATIVE_THRESHOLD = 0.4
MAX_RETRIES = 1


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


def route_after_creative_dispatch(state: AgentState) -> str:
    """Plan10: route mesh intents to mesh_generator, others to visual_generator."""
    for intent in state.creative_intents:
        if intent.output_kind == "mesh" or intent.kind == "generate_mesh":
            return "mesh"
    return "image"
