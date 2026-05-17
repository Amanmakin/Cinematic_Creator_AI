"""Generate 2-3 alternative BlenderDsl variants for medium-ambiguity intents.

Uses a single LLM call returning all variants at once to avoid paying per-variation.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from orchestrator import llm as llm_module
from orchestrator.node_logger import llm_call, llm_response, node_step
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.state import AgentState

VARIATION_DIRECTIVES = [
    "Variation A: cool key light from camera-left, slight wide lens (28mm), desaturated palette.",
    "Variation B: warm key light from camera-right, classic portrait lens (50mm), saturated palette.",
    "Variation C: top-down soft key light, telephoto compression (85mm), pastel palette.",
]


class _SpeculativeBatch(BaseModel):
    """Wrapper so we get all variants in one structured-output call."""
    variants: list[BlenderDsl]


def speculative_batcher_node(state: AgentState) -> dict:
    assert state.intent is not None, "speculative_batcher requires a validated intent"

    with node_step(
        "speculative_batcher",
        subject=state.intent.subject,
        variations=len(VARIATION_DIRECTIVES),
    ) as out:
        system = SystemMessage(content=llm_module.load_prompt("speculative_system.md"))
        directives_block = "\n".join(VARIATION_DIRECTIVES)
        user = HumanMessage(
            content=(
                "PROJECT CANON:\n"
                f"{state.project_canon.model_dump_json(indent=2)}\n\n"
                "VALIDATED INTENT:\n"
                f"{state.intent.model_dump_json(indent=2)}\n\n"
                "VARIATION DIRECTIVES (produce one BlenderDsl variant per directive, "
                f"return all {len(VARIATION_DIRECTIVES)} in the `variants` list):\n"
                f"{directives_block}"
            )
        )

        model = llm_module.make_llm()
        llm_call(model.model_name, 2)
        structured = model.with_structured_output(_SpeculativeBatch, include_raw=True, method="function_calling")
        result = structured.invoke([system, user])
        llm_response(result.get("raw"), result.get("parsing_error"))
        variants: list[BlenderDsl] = result["parsed"].variants

        out.update(variants_generated=len(variants), status="speculative_batching")
        return {
            "speculative_variants": variants,
            "execution_status": "speculative_batching",
        }
