"""LLM-driven scene graph generator with lock enforcement."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.state import AgentState


class LockViolation(RuntimeError):
    pass


def scene_graph_generator_node(state: AgentState) -> dict:
    assert state.intent is not None, "scene_graph_generator requires a validated intent"

    system = SystemMessage(content=llm_module.load_prompt("scene_system.md"))
    user = HumanMessage(
        content=(
            "PROJECT CANON:\n"
            f"{state.project_canon.model_dump_json(indent=2)}\n\n"
            "VALIDATED INTENT:\n"
            f"{state.intent.model_dump_json(indent=2)}\n\n"
            "ACTIVE SEMANTIC LOCKS (do not modify these subtrees):\n"
            + (
                "\n".join(f"- {l.path}: {l.reason}" for l in state.semantic_locks)
                or "(none)"
            )
        )
    )

    llm = llm_module.make_llm()
    structured = llm.with_structured_output(BlenderDsl)
    dsl: BlenderDsl = structured.invoke([system, user])

    return {
        "scene_graph": dsl,
        "execution_status": "scene_graph_generated",
    }
