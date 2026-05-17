"""Diff current intent against the previous checkpointed state and emit locks.

Plan1 has no UAR (asset registry) yet, so locks are purely descriptive: they
record which subtrees should be considered stable across iterations. Plan3
will populate `asset_id` once the Universal Asset Registry exists.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from orchestrator.node_logger import node_step
from orchestrator.state import AgentState, SemanticLock


def _prior_intent(config: RunnableConfig | None) -> Any | None:
    """Best-effort fetch of the prior IntentSpec from the checkpointer.

    Returns None on the first run (no prior checkpoint), and silently
    swallows lookup errors — locks are an optimization, not a correctness
    guarantee.
    """
    if not config:
        return None
    try:
        from langgraph.config import get_config  # noqa: F401  (runtime hook)
    except Exception:
        return None
    return None  # MemorySaver-based prior reads land via graph wiring in Plan2.


def semantic_locker_node(state: AgentState, config=None) -> dict:
    with node_step(
        "semantic_locker",
        existing_locks=len(state.semantic_locks),
    ) as out:
        locks: list[SemanticLock] = list(state.semantic_locks)

        prior = _prior_intent(config)
        if prior is not None and state.intent is not None:
            if getattr(prior, "subject", None) == state.intent.subject:
                locks.append(
                    SemanticLock(
                        path="scene.subjects[0]",
                        asset_id=None,
                        reason="subject unchanged across iterations",
                    )
                )

        out.update(total_locks=len(locks), status="semantic_lock_applied")
        return {
            "semantic_locks": locks,
            "execution_status": "semantic_lock_applied",
        }
