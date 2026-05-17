"""Extract a typed IntentSpec from the raw prompt and re-validate in Python."""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.intent import IntentSpec
from orchestrator.state import AgentState

log = logging.getLogger(__name__)


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


def _msgs_to_langchain(msgs: list[dict]) -> list[BaseMessage]:
    """Convert build_llm_context dicts to LangChain message objects."""
    out: list[BaseMessage] = []
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            from langchain_core.messages import AIMessage
            out.append(AIMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out


def _build_context_sync(state: AgentState) -> list[dict]:
    """Run build_llm_context synchronously, handling event-loop state."""
    try:
        from api.memory.build_context import build_llm_context
    except ImportError:
        # Orchestrator package may run without the api package in tests.
        return []

    async def _run():
        return await build_llm_context(
            state.project_id,
            state.user_prompt,
            state.project_canon,
            state.scene_graph,
        )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run())
            return future.result()
    else:
        return loop.run_until_complete(_run())


def intent_validator_node(state: AgentState) -> dict:
    system_prompt = llm_module.load_prompt("intent_system.md")

    # Try to load memory context; fall back gracefully to the original prompt construction.
    context_msgs: list[dict] = []
    if state.project_id:
        try:
            context_msgs = _build_context_sync(state)
        except Exception as exc:
            log.warning("build_llm_context failed, falling back to bare prompt: %s", exc)

    if context_msgs:
        # Prepend the system prompt and replace the last user message if needed.
        all_msgs = [{"role": "system", "content": system_prompt}] + context_msgs
    else:
        all_msgs = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "PROJECT CANON:\n"
                    f"{state.project_canon.model_dump_json(indent=2)}\n\n"
                    "USER PROMPT:\n"
                    f"{state.user_prompt}"
                ),
            },
        ]

    lc_msgs = _msgs_to_langchain(all_msgs)
    llm = llm_module.make_llm()
    structured = llm.with_structured_output(IntentSpec)
    intent: IntentSpec = structured.invoke(lc_msgs)

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
