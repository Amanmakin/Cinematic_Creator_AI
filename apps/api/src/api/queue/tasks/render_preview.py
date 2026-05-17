"""arq task: preview render — low-res frame sequence streamed via WS events."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).parents[7])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from api.dag.reducers import record_event
from api.orchestrator.budget import BudgetLedger
from api.queue.cancellation import (
    inflight_decrement,
    inflight_increment,
    register_blender_pid,
    unregister_blender_pid,
)
from api.render.gltf_builder import build_glb, scene_hash
from api.settings import settings
from api.ws.broadcaster import broadcast


async def render_preview(
    ctx: dict,
    *,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
    budget_id: str,
    budget_amount: int,
) -> dict:
    """Render a low-res preview frame sequence and stream PreviewFrameReady events."""
    from orchestrator.schemas.canon import ProjectCanon
    from orchestrator.schemas.dsl import BlenderDsl
    from workers.render.blender_runner import (
        RenderCompleted,
        RenderFailed as BRFailed,
        RenderTimedOut,
        run_render_sequence,
    )

    ledger = BudgetLedger(db_path=settings.db_path)
    dsl = BlenderDsl.model_validate(payload["dsl"])
    canon = ProjectCanon.model_validate(payload["canon"])
    blender_bin = payload.get("blender_bin", "blender")
    timeout_s = float(payload.get("timeout_s", 600.0))

    sha = scene_hash(dsl)
    out_dir = str(Path(settings.renders_root) / project_id / sha / "preview")
    extras_path = str(Path(settings.renders_root) / project_id / sha / f"{sha}.extras.json")

    try:
        glb_path = build_glb(dsl, uar_root=settings.uar_root, out_dir=str(Path(out_dir).parent))
    except Exception as exc:
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id,
            "RenderFailed",
            {"cause": "subprocess_error", "details": f"glTF assembly failed: {exc}"},
            dag_node_id=dag_node_id,
            scene_hash=sha,
        )
        raise

    await inflight_increment(project_id)
    await record_event(
        project_id, "TaskStarted", {"task": "render_preview", "scene_hash": sha},
        dag_node_id=dag_node_id, scene_hash=sha
    )

    frame_count = int(dsl.scene.fps * getattr(dsl.scene, "duration_seconds", 1))
    frame_count = max(1, frame_count)

    pid_holder: list[int] = []

    def _on_pid(pid: int) -> None:
        pid_holder.append(pid)
        register_blender_pid(project_id, dag_node_id, pid)

    async def _frame_cb(frame_index: int, total: int, path: str) -> None:
        await record_event(
            project_id,
            "PreviewFrameReady",
            {"frame_index": frame_index, "total": total, "path": path},
            dag_node_id=dag_node_id,
            scene_hash=sha,
        )
        await broadcast(project_id, {
            "kind": "PreviewFrameReady",
            "frame_index": frame_index,
            "total": total,
            "scene_hash": sha,
            "path": path,
        })

    loop = asyncio.get_event_loop()

    def _render() -> Any:
        return run_render_sequence(
            glb_path=glb_path,
            extras_path=extras_path,
            out_dir=out_dir,
            blender_bin=blender_bin,
            timeout_s=timeout_s,
            frame_count=frame_count,
            resolution=(480, 854),
            on_pid=_on_pid,
            on_frame=lambda fi, tot, path: asyncio.run_coroutine_threadsafe(
                _frame_cb(fi, tot, path), loop
            ).result(),
        )

    try:
        result = await loop.run_in_executor(None, _render)
    finally:
        unregister_blender_pid(project_id, dag_node_id)
        await inflight_decrement(project_id)

    if isinstance(result, RenderCompleted):
        await ledger.commit(project_id, budget_id, budget_amount)
        await record_event(
            project_id, "PreviewCompleted",
            {"output_dir": result.output_dir, "frame_count": frame_count},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        await broadcast(project_id, {"kind": "PreviewCompleted", "scene_hash": sha})
        return {"status": "completed", "scene_hash": sha, "output_dir": result.output_dir}

    elif isinstance(result, RenderTimedOut):
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "RenderFailed",
            {"cause": "timeout", "details": f"timed out after {result.timeout_s}s"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        raise TimeoutError(f"Blender preview timed out after {result.timeout_s}s")

    else:
        rc = result.returncode if isinstance(result, BRFailed) else -1
        tail = result.stderr_tail if isinstance(result, BRFailed) else ""
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "RenderFailed",
            {"cause": "subprocess_error", "details": f"exit {rc}: {tail[:300]}"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        raise RuntimeError(f"Blender preview failed (exit {rc})")
