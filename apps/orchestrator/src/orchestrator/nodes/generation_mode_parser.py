"""Deterministic keyword-heuristic node that sets generation_mode from the user intent."""

from __future__ import annotations

from orchestrator.state import AgentState, GenerationMode


def parse_generation_mode(intent: str) -> GenerationMode:
    intent_lower = intent.lower()
    if any(kw in intent_lower for kw in ["wireframe", "layout", "blocking", "previs"]):
        return GenerationMode.wireframe
    if any(kw in intent_lower for kw in ["model", "render", "2d", "2.5d", "scene"]):
        return GenerationMode.model
    return GenerationMode.video


def generation_mode_parser_node(state: AgentState) -> dict:
    assert state.intent is not None, "generation_mode_parser requires a validated intent"
    prompt = state.user_prompt
    mode = parse_generation_mode(prompt)
    return {"generation_mode": mode}
