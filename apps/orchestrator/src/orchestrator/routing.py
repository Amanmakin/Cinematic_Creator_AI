"""Conditional-edge routing functions for the StateGraph."""

from orchestrator.state import AgentState

HUMAN_APPROVAL_THRESHOLD = 0.8
MAX_RETRIES = 1


def route_after_intent(state: AgentState) -> str:
    if state.execution_status == "failed":
        return "fail"
    if state.ambiguity_score > HUMAN_APPROVAL_THRESHOLD:
        return "human_approval"
    return "proceed"


def route_after_validation(state: AgentState) -> str:
    has_error = any(f.severity == "error" for f in state.validation_findings)
    if not has_error:
        return "success"
    if state.retry_count >= MAX_RETRIES:
        return "fail"
    return "retry"


def route_after_mesh_dispatch(state: AgentState) -> str:
    """Plan10/B: object & landscape go to mesh_generator pre-wireframe; abstract skips it."""
    subj_class = state.subject_class or "object"
    if subj_class in ("object", "landscape"):
        return "mesh_generator"
    return "wireframe_previs_generator"
