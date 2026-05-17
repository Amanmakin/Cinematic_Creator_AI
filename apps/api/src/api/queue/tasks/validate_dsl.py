"""arq task: physical DSL validation (no subprocess)."""

from __future__ import annotations

from typing import Any

from api.dag.reducers import record_event
from api.orchestrator.budget import BudgetLedger
from api.queue.cancellation import inflight_decrement, inflight_increment
from api.settings import settings


async def validate_dsl(
    ctx: dict,
    *,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
    budget_id: str,
    budget_amount: int,
) -> dict:
    """Validate a BlenderDsl payload against canon rules."""
    from api.validation.physical import validate_dsl_full
    from orchestrator.schemas.canon import ProjectCanon
    from orchestrator.schemas.dsl import BlenderDsl

    ledger = BudgetLedger(db_path=settings.db_path)
    await inflight_increment(project_id)
    await record_event(
        project_id, "TaskStarted", {"task": "validate_dsl"}, dag_node_id=dag_node_id
    )
    try:
        dsl = BlenderDsl.model_validate(payload["dsl"])
        canon = ProjectCanon.model_validate(payload["canon"])
        report = validate_dsl_full(dsl, canon)
        await ledger.commit(project_id, budget_id, budget_amount)
        return {
            "ok": report.ok,
            "findings": [f.model_dump() for f in report.findings],
        }
    except Exception as exc:
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id,
            "RenderFailed",
            {"cause": "subprocess_error", "details": str(exc)},
            dag_node_id=dag_node_id,
        )
        raise
    finally:
        await inflight_decrement(project_id)
