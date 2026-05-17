"""arq task: final render — hard-gated, high-quality, ffmpeg-encoded mp4."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).parents[7])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from api.dag.reducers import has_event, record_event
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


async def render_final(
    ctx: dict,
    *,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
    budget_id: str,
    budget_amount: int,
) -> dict:
    """Final render: check approval gate, render full-res, encode to mp4."""
    from orchestrator.schemas.canon import ProjectCanon
    from orchestrator.schemas.dsl import BlenderDsl
    from workers.render.blender_runner import (
        RenderCompleted,
        RenderFailed as BRFailed,
        RenderTimedOut,
        run_render_final,
    )

    ledger = BudgetLedger(db_path=settings.db_path)
    dsl = BlenderDsl.model_validate(payload["dsl"])
    canon = ProjectCanon.model_validate(payload["canon"])
    blender_bin = payload.get("blender_bin", "blender")
    timeout_s = float(payload.get("timeout_s", 3600.0))

    sha = scene_hash(dsl)

    approved = await has_event(project_id, "FinalRenderApproved", scene_hash=sha)
    if not approved:
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "FinalRenderBlocked",
            {"reason": "no FinalRenderApproved event for this scene_hash"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        await broadcast(project_id, {"kind": "FinalRenderBlocked", "scene_hash": sha})
        return {"status": "blocked", "scene_hash": sha}

    out_dir = str(Path(settings.renders_root) / project_id / sha / "final")
    extras_path = str(Path(settings.renders_root) / project_id / sha / f"{sha}.extras.json")

    try:
        glb_path = build_glb(dsl, uar_root=settings.uar_root, out_dir=str(Path(out_dir).parent))
    except Exception as exc:
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "RenderFailed",
            {"cause": "subprocess_error", "details": f"glTF assembly failed: {exc}"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        raise

    await inflight_increment(project_id)
    await record_event(
        project_id, "TaskStarted", {"task": "render_final", "scene_hash": sha},
        dag_node_id=dag_node_id, scene_hash=sha,
    )

    scene = dsl.scene
    resolution = (scene.width if hasattr(scene, "width") else 1920,
                  scene.height if hasattr(scene, "height") else 1080)
    fps = scene.fps if hasattr(scene, "fps") else 24
    use_cycles = canon.aesthetic_tags and "high_quality" in canon.aesthetic_tags

    pid_holder: list[int] = []

    def _on_pid(pid: int) -> None:
        pid_holder.append(pid)
        register_blender_pid(project_id, dag_node_id, pid)

    loop = asyncio.get_event_loop()

    def _render() -> Any:
        return run_render_final(
            glb_path=glb_path,
            extras_path=extras_path,
            out_dir=out_dir,
            blender_bin=blender_bin,
            timeout_s=timeout_s,
            resolution=resolution,
            fps=fps,
            use_cycles=use_cycles,
            on_pid=_on_pid,
        )

    try:
        result = await loop.run_in_executor(None, _render)
    finally:
        unregister_blender_pid(project_id, dag_node_id)
        await inflight_decrement(project_id)

    if isinstance(result, RenderCompleted):
        mp4_dir = Path(settings.renders_root) / project_id / "out"
        mp4_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = str(mp4_dir / f"{sha}.mp4")

        encode_ok, encode_err = await loop.run_in_executor(
            None, _ffmpeg_encode, result.output_dir, mp4_path, fps
        )

        if not encode_ok:
            await ledger.refund(project_id, budget_id)
            await record_event(
                project_id, "EncodingFailed",
                {"cause": "encoding_failed", "details": encode_err},
                dag_node_id=dag_node_id, scene_hash=sha,
            )
            raise RuntimeError(f"ffmpeg encoding failed: {encode_err}")

        await ledger.commit(project_id, budget_id, budget_amount)
        await record_event(
            project_id, "FinalRenderCompleted",
            {"mp4_path": mp4_path, "scene_hash": sha},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        await broadcast(project_id, {
            "kind": "FinalRenderCompleted",
            "scene_hash": sha,
            "mp4_path": mp4_path,
        })
        return {"status": "completed", "mp4_path": mp4_path, "scene_hash": sha}

    elif isinstance(result, RenderTimedOut):
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "RenderFailed",
            {"cause": "timeout", "details": f"timed out after {result.timeout_s}s"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        raise TimeoutError(f"Blender final render timed out after {result.timeout_s}s")

    else:
        rc = result.returncode if isinstance(result, BRFailed) else -1
        tail = result.stderr_tail if isinstance(result, BRFailed) else ""
        await ledger.refund(project_id, budget_id)
        await record_event(
            project_id, "RenderFailed",
            {"cause": "subprocess_error", "details": f"exit {rc}: {tail[:300]}"},
            dag_node_id=dag_node_id, scene_hash=sha,
        )
        raise RuntimeError(f"Blender final render failed (exit {rc})")


def _ffmpeg_encode(frame_dir: str, mp4_path: str, fps: int) -> tuple[bool, str]:
    import subprocess
    frame_pattern = str(Path(frame_dir) / "frame_%04d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", frame_pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        mp4_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return False, result.stderr[-500:]
        return True, ""
    except FileNotFoundError:
        return False, "ffmpeg not found — install with: brew install ffmpeg"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timed out"
