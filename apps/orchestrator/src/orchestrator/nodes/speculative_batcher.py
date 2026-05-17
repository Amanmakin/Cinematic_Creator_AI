"""Generate 2-3 alternative BlenderDsl variants for medium-ambiguity intents."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.state import AgentState

VARIATION_DIRECTIVES = [
    "Variation A: cool key light from camera-left, slight wide lens (28mm), desaturated palette.",
    "Variation B: warm key light from camera-right, classic portrait lens (50mm), saturated palette.",
    "Variation C: top-down soft key light, telephoto compression (85mm), pastel palette.",
]


def speculative_batcher_node(state: AgentState) -> dict:
    assert state.intent is not None, "speculative_batcher requires a validated intent"

    system = SystemMessage(content=llm_module.load_prompt("speculative_system.md"))
    llm = llm_module.make_llm()
    structured = llm.with_structured_output(BlenderDsl)

    variants: list[BlenderDsl] = []
    for directive in VARIATION_DIRECTIVES:
        user = HumanMessage(
            content=(
                "PROJECT CANON:\n"
                f"{state.project_canon.model_dump_json(indent=2)}\n\n"
                "VALIDATED INTENT:\n"
                f"{state.intent.model_dump_json(indent=2)}\n\n"
                f"VARIATION DIRECTIVE:\n{directive}"
            )
        )
        variant: BlenderDsl = structured.invoke([system, user])
        variants.append(variant)

    return {
        "speculative_variants": variants,
        "execution_status": "speculative_batching",
    }
