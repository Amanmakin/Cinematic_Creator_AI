"""Extract a typed IntentSpec from the raw prompt and re-validate in Python."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.intent import IntentSpec
from orchestrator.state import AgentState


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_ambiguity_score(intent: IntentSpec) -> float:
    hints = intent.ambiguity_hints
    raw = (
        0.5 * (1.0 - hints.confidence)
        + 0.1 * len(hints.underspecified_fields)
        + 0.2 * len(hints.conflicting_directives)
    )
    return _clip(raw, 0.0, 1.0)


def _hard_validate(intent: IntentSpec, canon: ProjectCanon) -> list[str]:
    errors: list[str] = []

    if intent.aspect_ratio != canon.aspect_ratio:
        errors.append(
            f"aspect_ratio_mismatch: intent={intent.aspect_ratio} canon={canon.aspect_ratio}"
        )
    if intent.duration_seconds <= 0:
        errors.append("duration_non_positive")
    if intent.duration_seconds > canon.duration_seconds_max:
        errors.append(
            f"duration_exceeds_canon: {intent.duration_seconds}>{canon.duration_seconds_max}"
        )

    banned = {t.lower() for t in canon.banned_terms}
    if banned:
        haystacks = [intent.subject, intent.setting, *intent.mood_tags]
        for token in haystacks:
            for b in banned:
                if b and b in token.lower():
                    errors.append(f"banned_term: {b!r} in {token!r}")
    return errors


def intent_validator_node(state: AgentState) -> dict:
    system = SystemMessage(content=llm_module.load_prompt("intent_system.md"))
    user = HumanMessage(
        content=(
            "PROJECT CANON:\n"
            f"{state.project_canon.model_dump_json(indent=2)}\n\n"
            "USER PROMPT:\n"
            f"{state.user_prompt}"
        )
    )

    llm = llm_module.make_llm()
    structured = llm.with_structured_output(IntentSpec)
    intent: IntentSpec = structured.invoke([system, user])

    errors = _hard_validate(intent, state.project_canon)
    if errors:
        return {
            "intent": intent,
            "execution_status": "failed",
            "error_log": state.error_log + errors,
        }

    return {
        "intent": intent,
        "ambiguity_score": compute_ambiguity_score(intent),
        "execution_status": "intent_validated",
    }
