"""Build the LangGraph StateGraph that drives prompt -> validated BlenderDsl."""

from __future__ import annotations

from typing import Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from orchestrator.nodes import (
    creative_dispatcher_node,
    dsl_compiler_node,
    generation_mode_parser_node,
    intent_validator_node,
    physical_validation_node,
    scene_graph_generator_node,
    semantic_locker_node,
    speculative_batcher_node,
    subject_classifier_node,
    wireframe_previs_generator_node,
)
from orchestrator.routing import (
    route_after_creative_dispatch,
    route_after_intent,
    route_after_validation,
)
from orchestrator.state import AgentState, GenerationMode


def route_after_wireframe(state: AgentState) -> str:
    if state.execution_status == "previsualization_approved":
        if state.generation_mode == GenerationMode.wireframe:
            return END
        return "creative_dispatcher"
    if state.execution_status == "previsualization_feedback":
        return "wireframe_previs_generator"
    # reject — rewind to scene planning
    return "scene_graph_generator"


def route_after_model(state: AgentState) -> str:
    if state.execution_status == "model_approved":
        if state.generation_mode == GenerationMode.model:
            return END
        return "physical_validation"
    if state.execution_status == "model_feedback":
        return "visual_generator"
    # reject — rewind to wireframe
    return "wireframe_previs_generator"


def build_graph(
    *,
    checkpointer: MemorySaver | None = None,
    interrupt_after_speculative: bool = True,
    visual_generator_node: Callable[[AgentState], dict] | None = None,
    gltf_assembler_node: Callable[[AgentState], dict] | None = None,
    mesh_generator_node: Callable[[AgentState], dict] | None = None,
) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("intent_validator", intent_validator_node)
    g.add_node("subject_classifier", subject_classifier_node)
    g.add_node("generation_mode_parser", generation_mode_parser_node)
    g.add_node("semantic_locker", semantic_locker_node)
    g.add_node("scene_graph_generator", scene_graph_generator_node)
    g.add_node("wireframe_previs_generator", wireframe_previs_generator_node)
    g.add_node("creative_dispatcher", creative_dispatcher_node)

    if visual_generator_node is not None:
        g.add_node("visual_generator", visual_generator_node)

    if mesh_generator_node is not None:
        g.add_node("mesh_generator", mesh_generator_node)

    g.add_node("physical_validation", physical_validation_node)
    g.add_node("dsl_compiler", dsl_compiler_node)

    if gltf_assembler_node is not None:
        g.add_node("gltf_assembler", gltf_assembler_node)

    g.add_node("speculative_batcher", speculative_batcher_node)

    g.set_entry_point("intent_validator")

    g.add_conditional_edges(
        "intent_validator",
        route_after_intent,
        {
            "human_approval": END,
            "speculative": "speculative_batcher",
            "proceed": "subject_classifier",
            "fail": END,
        },
    )

    g.add_edge("subject_classifier", "generation_mode_parser")
    g.add_edge("generation_mode_parser", "semantic_locker")
    g.add_edge("semantic_locker", "scene_graph_generator")
    g.add_edge("scene_graph_generator", "wireframe_previs_generator")

    g.add_conditional_edges(
        "wireframe_previs_generator",
        route_after_wireframe,
        {
            END: END,
            "creative_dispatcher": "creative_dispatcher",
            "wireframe_previs_generator": "wireframe_previs_generator",
            "scene_graph_generator": "scene_graph_generator",
        },
    )

    have_visual = visual_generator_node is not None
    have_mesh = mesh_generator_node is not None

    if have_visual and have_mesh:
        g.add_conditional_edges(
            "creative_dispatcher",
            route_after_creative_dispatch,
            {
                "mesh": "mesh_generator",
                "image": "visual_generator",
            },
        )
        g.add_edge("mesh_generator", "physical_validation")
        g.add_conditional_edges(
            "visual_generator",
            route_after_model,
            {
                END: END,
                "physical_validation": "physical_validation",
                "visual_generator": "visual_generator",
                "wireframe_previs_generator": "wireframe_previs_generator",
            },
        )
    elif have_visual:
        g.add_edge("creative_dispatcher", "visual_generator")
        g.add_conditional_edges(
            "visual_generator",
            route_after_model,
            {
                END: END,
                "physical_validation": "physical_validation",
                "visual_generator": "visual_generator",
                "wireframe_previs_generator": "wireframe_previs_generator",
            },
        )
    elif have_mesh:
        g.add_edge("creative_dispatcher", "mesh_generator")
        g.add_edge("mesh_generator", "physical_validation")
    else:
        g.add_edge("creative_dispatcher", "physical_validation")

    # After validation passes: compile DSL then assemble GLB
    g.add_conditional_edges(
        "physical_validation",
        route_after_validation,
        {
            "retry": "scene_graph_generator",
            "fail": END,
            "success": "dsl_compiler",
        },
    )

    if gltf_assembler_node is not None:
        g.add_edge("dsl_compiler", "gltf_assembler")
        g.add_edge("gltf_assembler", END)
    else:
        g.add_edge("dsl_compiler", END)

    g.add_edge("speculative_batcher", END)

    interrupt_after = ["speculative_batcher", "wireframe_previs_generator"]
    if visual_generator_node is not None:
        interrupt_after.append("visual_generator")
    if not interrupt_after_speculative:
        interrupt_after = [n for n in interrupt_after if n != "speculative_batcher"]

    return g.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_after=interrupt_after,
    )
