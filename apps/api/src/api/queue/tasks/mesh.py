"""arq task: text→3D mesh generation via the configured pipeline."""

from __future__ import annotations

from typing import Any

from api.dag.reducers import record_event
from api.queue.cancellation import inflight_decrement, inflight_increment
from api.settings import settings


async def generate_mesh(
    ctx: dict,
    *,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
) -> dict:
    """Run the mesh pipeline for a single subject and persist the asset.

    Payload shape:
        {
          "subject": str,
          "subject_class": "object" | "landscape",
          "target_path": str,
          "seed": int | None,
        }
    """
    from api.adapters.poly_haven_adapter import PolyHavenAdapter
    from api.adapters.text_to_3d_adapter import TextTo3DAdapter
    from api.uar.store import UARStore
    from orchestrator.schemas.mesh_asset import BBox3

    subject: str = payload["subject"]
    subject_class: str = payload.get("subject_class", "object")
    target_path: str = payload.get("target_path", "")
    seed = payload.get("seed")

    uar = UARStore(db_path=settings.db_path, uar_root=settings.uar_root)
    await uar.init()

    text_to_3d = TextTo3DAdapter(
        strategy=settings.mesh_pipeline_strategy,
        triposr_url=settings.triposr_url,
        shap_e_url=settings.shap_e_url,
        openai_api_key=settings.openai_api_key,
        timeout_sec=float(settings.generation_timeout_local),
    )
    poly_haven = PolyHavenAdapter(
        api_url=settings.poly_haven_api_url,
        cache_dir=settings.poly_haven_cache_dir,
    )

    await inflight_increment(project_id)
    await record_event(
        project_id, "TaskStarted", {"task": "generate_mesh"}, dag_node_id=dag_node_id
    )
    try:
        if subject_class == "landscape":
            match = await poly_haven.resolve(subject)
            if match is not None:
                with open(match.glb_path, "rb") as f:
                    glb_bytes = f.read()
                mesh = await uar.store_mesh(
                    project_id=project_id,
                    glb_bytes=glb_bytes,
                    bounds_m=BBox3(min_x=-1, min_y=-1, min_z=0, max_x=1, max_y=1, max_z=2),
                    source="poly_haven",
                    target_path=target_path,
                    adapter=poly_haven.name,
                    adapter_version=poly_haven.version,
                )
                await record_event(
                    project_id,
                    "AssetGenerated",
                    {"asset_id": mesh.asset_id, "provider": "poly_haven"},
                    dag_node_id=dag_node_id,
                )
                return {"status": "ok", "asset_id": mesh.asset_id, "source": "poly_haven"}

        result = await text_to_3d.generate(subject, seed=seed)
        mesh = await uar.store_mesh(
            project_id=project_id,
            glb_bytes=result.glb_bytes,
            bounds_m=result.bounds,
            source=result.source,  # type: ignore[arg-type]
            target_path=target_path,
            adapter=text_to_3d.name,
            adapter_version=text_to_3d.version,
        )
        await record_event(
            project_id,
            "AssetGenerated",
            {"asset_id": mesh.asset_id, "provider": result.source},
            dag_node_id=dag_node_id,
        )
        return {"status": "ok", "asset_id": mesh.asset_id, "source": result.source}
    except Exception as exc:
        await record_event(
            project_id,
            "RenderFailed",
            {"cause": "mesh_pipeline", "details": str(exc)},
            dag_node_id=dag_node_id,
        )
        raise
    finally:
        await inflight_decrement(project_id)
