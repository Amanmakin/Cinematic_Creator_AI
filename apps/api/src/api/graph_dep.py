"""Singleton compiled graph shared across all requests."""

from functools import lru_cache

from langgraph.graph.state import CompiledStateGraph

from api.adapters.hybrid_adapter import HybridAdapter
from api.orchestrator.budget import BudgetLedger
from api.orchestrator.creative_dispatch import make_visual_generator_node
from api.persistence.projects_db import get_sqlite_checkpointer
from api.settings import settings
from api.uar.store import UARStore
from orchestrator.graph import build_graph


@lru_cache(maxsize=1)
def get_uar() -> UARStore:
    return UARStore(db_path=settings.db_path, uar_root=settings.uar_root)


@lru_cache(maxsize=1)
def get_ledger() -> BudgetLedger:
    return BudgetLedger(db_path=settings.db_path)


@lru_cache(maxsize=1)
def get_adapter() -> HybridAdapter:
    return HybridAdapter(
        api_key=settings.replicate_api_key,
        strategy=settings.generation_strategy,
        docker_base_url=settings.docker_diffusers_url,
        timeout_local=float(settings.generation_timeout_local),
        timeout_replicate=float(settings.generation_timeout_replicate),
        use_smaller_model=settings.use_smaller_models_locally,
    )


@lru_cache(maxsize=1)
def get_graph() -> CompiledStateGraph:
    checkpointer = get_sqlite_checkpointer()
    visual_node = make_visual_generator_node(
        adapter=get_adapter(),
        uar=get_uar(),
        ledger=get_ledger(),
    )
    return build_graph(checkpointer=checkpointer, visual_generator_node=visual_node)
