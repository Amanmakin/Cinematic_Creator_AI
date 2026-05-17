"""Build the LangGraph StateGraph that drives prompt -> validated BlenderDsl."""

from __future__ import annotations

from typing import Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from orchestrator.nodes import (
    creative_dispatcher_node,
    intent_validator_node,
    physical_validation_node,
    scene_graph_generator_node,
    semantic_locker_node,
    speculative_batcher_node,
)
from orchestrator.routing import route_after_intent, route_after_validation
from orchestrator.state import AgentState


def build_graph(
    *,
    checkpointer: MemorySaver | None = None,
    interrupt_before_speculative: bool = True,
    visual_generator_node: Callable[[AgentState], dict] | None = None,
) -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("intent_validator", intent_validator_node)
    g.add_node("semantic_locker", semantic_locker_node)
    g.add_node("scene_graph_generator", scene_graph_generator_node)
    g.add_node("creative_dispatcher", creative_dispatcher_node)

    if visual_generator_node is not None:
        g.add_node("visual_generator", visual_generator_node)

    g.add_node("physical_validation", physical_validation_node)
    g.add_node("speculative_batcher", speculative_batcher_node)

    g.set_entry_point("intent_validator")

    g.add_conditional_edges(
        "intent_validator",
        route_after_intent,
        {
            "human_approval": END,
            "speculative": "speculative_batcher",
            "proceed": "semantic_locker",
            "fail": END,
        },
    )

    g.add_edge("semantic_locker", "scene_graph_generator")
    g.add_edge("scene_graph_generator", "creative_dispatcher")

    if visual_generator_node is not None:
        g.add_edge("creative_dispatcher", "visual_generator")
        g.add_edge("visual_generator", "physical_validation")
    else:
        g.add_edge("creative_dispatcher", "physical_validation")

    g.add_conditional_edges(
        "physical_validation",
        route_after_validation,
        {
            "retry": "scene_graph_generator",
            "fail": END,
            "success": END,
        },
    )

    g.add_edge("speculative_batcher", END)

    interrupt_before = ["speculative_batcher"] if interrupt_before_speculative else []
    return g.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=interrupt_before,
    )
