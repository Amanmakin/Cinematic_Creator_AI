"""LLM-driven scene graph generator with lock enforcement."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from orchestrator import llm as llm_module
from orchestrator.node_logger import llm_call, llm_response, node_step
from orchestrator.schemas.dsl import BlenderDsl
from orchestrator.state import AgentState


class LockViolation(RuntimeError):
    pass


def scene_graph_generator_node(state: AgentState) -> dict:
    assert state.intent is not None, "scene_graph_generator requires a validated intent"

    with node_step(
        "scene_graph_generator",
        subject=state.intent.subject,
        locks=len(state.semantic_locks),
    ) as out:
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

        model = llm_module.make_llm()
        llm_call(model.model_name, 2)
        structured = model.with_structured_output(BlenderDsl, include_raw=True, method="function_calling")
        result = structured.invoke([system, user])
        llm_response(result.get("raw"), result.get("parsing_error"))
        dsl: BlenderDsl = result["parsed"]

        out.update(
            status="scene_graph_generated",
            subjects=len(dsl.scene.subjects),
            lights=len(dsl.scene.lights),
            duration_s=dsl.scene.duration_s,
        )

        return {
            "scene_graph": dsl,
            "execution_status": "scene_graph_generated",
        }
