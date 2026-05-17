"""Operational Transformation engine for scene graph mutations.

Per-project in-memory state:
  version        — monotonically increasing commit counter
  scene_graph    — current canonical scene graph dict
  op_history     — ops applied at each version: {version: [ops]}

Rebase policy: if base_version is stale, check whether any incoming op
path overlaps the paths mutated since base_version. Disjoint → rebased.
Overlap → OtConflict (FE must re-fetch and retry).
"""

import copy
from typing import Any

from api.orchestrator.scene_graph_path import (
    delete_value,
    get_value,
    insert_value,
    path_touches_lock,
    set_value,
)
from api.persistence.projects_db import get_locks

_ot_store: dict[str, dict] = {}
# schema: {version: int, scene_graph: dict, op_history: dict[int, list[dict]]}


class LockedPathViolation(Exception):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path is locked: {path}")


class OtConflict(Exception):
    pass


def _apply_ops(scene_graph: dict, ops: list[dict]) -> None:
    for op in ops:
        kind = op["op"]
        path = op["path"]
        if kind == "set":
            set_value(scene_graph, path, op["value"])
        elif kind == "insert":
            insert_value(scene_graph, path, op["index"], op["value"])
        elif kind == "delete":
            delete_value(scene_graph, path)
        else:
            raise ValueError(f"Unknown op kind: {kind!r}")


def _op_paths(ops: list[dict]) -> set[str]:
    return {op["path"] for op in ops}


def _init_store(project_id: str, graph: Any) -> None:
    config = {"configurable": {"thread_id": project_id}}
    state = graph.get_state(config)
    sg = state.values.get("scene_graph") or {}
    _ot_store[project_id] = {
        "version": 0,
        "scene_graph": copy.deepcopy(sg),
        "op_history": {},
    }


async def apply_commit(
    project_id: str,
    base_version: int,
    ops: list[dict],
    graph: Any,
) -> tuple[dict, int, str]:
    """Apply OT ops. Returns (new_scene_graph, new_version, status).
    status is 'accepted' | 'rebased'.
    Raises LockedPathViolation or OtConflict.
    """
    if project_id not in _ot_store:
        _init_store(project_id, graph)

    store = _ot_store[project_id]
    current_version: int = store["version"]

    # Lock check — reject before touching anything
    locks = await get_locks(project_id)
    locked_paths = {lock["path"] for lock in locks}
    for op in ops:
        for lp in locked_paths:
            if path_touches_lock(op["path"], lp):
                raise LockedPathViolation(op["path"])

    # Stale version: attempt rebase
    if base_version < current_version:
        intervening_paths: set[str] = set()
        for v in range(base_version + 1, current_version + 1):
            intervening_paths |= _op_paths(store["op_history"].get(v, []))

        incoming_paths = _op_paths(ops)
        if incoming_paths & intervening_paths:
            raise OtConflict()

        new_sg = copy.deepcopy(store["scene_graph"])
        _apply_ops(new_sg, ops)
        new_version = current_version + 1
        store["scene_graph"] = new_sg
        store["version"] = new_version
        store["op_history"][new_version] = ops
        _push_to_langgraph(project_id, new_sg, graph)
        return new_sg, new_version, "rebased"

    # Current version — standard apply
    new_sg = copy.deepcopy(store["scene_graph"])
    _apply_ops(new_sg, ops)
    new_version = current_version + 1
    store["scene_graph"] = new_sg
    store["version"] = new_version
    store["op_history"][new_version] = ops
    _push_to_langgraph(project_id, new_sg, graph)
    return new_sg, new_version, "accepted"


def _push_to_langgraph(project_id: str, scene_graph: dict, graph: Any) -> None:
    config = {"configurable": {"thread_id": project_id}}
    graph.update_state(config, {"scene_graph": scene_graph}, as_node="scene_graph_generator")


def get_current_version(project_id: str) -> int:
    return _ot_store.get(project_id, {}).get("version", 0)


def seed_scene_graph(project_id: str, scene_graph: dict) -> None:
    """Sync OT store when agent run produces a new scene_graph."""
    prev_version = _ot_store.get(project_id, {}).get("version", 0)
    _ot_store[project_id] = {
        "version": prev_version + 1,
        "scene_graph": copy.deepcopy(scene_graph),
        "op_history": _ot_store.get(project_id, {}).get("op_history", {}),
    }
