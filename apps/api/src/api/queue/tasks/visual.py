"""arq task: visual asset generation via the configured adapter."""

from __future__ import annotations

from typing import Any

from api.dag.reducers import record_event
from api.orchestrator.budget import BudgetLedger
from api.queue.cancellation import inflight_decrement, inflight_increment
from api.settings import settings


async def generate_visual(
    ctx: dict,
    *,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
    budget_id: str,
    budget_amount: int,
) -> dict:
    """Generate a visual asset via the adapter and commit/refund the budget token."""
    from api.adapters.hybrid_adapter import HybridAdapter

    ledger = BudgetLedger(db_path=settings.db_path)
    from api.routes.generation_settings import _fetch_config, _DEFAULTS
    cfg = await _fetch_config(project_id) or _DEFAULTS
    adapter = HybridAdapter(
        strategy=cfg.strategy,
        docker_base_url=settings.docker_diffusers_url,
        timeout_local=float(cfg.timeout_local_sec),
        use_smaller_model=cfg.use_smaller_models,
        openai_api_key=settings.openai_api_key,
    )

    await inflight_increment(project_id)
    await record_event(
        project_id, "TaskStarted", {"task": "generate_visual"}, dag_node_id=dag_node_id
    )
    try:
        result = await adapter.execute(payload)
        await ledger.commit(project_id, budget_id, budget_amount)
        return {"status": "ok", "result": result}
    except Exception as exc:
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id,
            "RenderFailed",
            {
                "cause": "provider_unavailable",
                "details": str(exc),
            },
            dag_node_id=dag_node_id,
        )
        raise
    finally:
        await inflight_decrement(project_id)
