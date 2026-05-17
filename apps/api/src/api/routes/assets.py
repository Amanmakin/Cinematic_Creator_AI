"""GET /projects/{id}/assets/{asset_id}/{layer_type} — serve PNG bytes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.graph_dep import get_uar

router = APIRouter()

LayerType = Literal["rgba", "alpha", "depth"]


@router.get("/{project_id}/assets/{asset_id}/{layer_type}")
async def get_asset_layer(
    project_id: str,
    asset_id: str,
    layer_type: LayerType,
):
    uar = get_uar()
    asset = await uar.get_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    path_map = {
        "rgba": asset.rgba_path,
        "alpha": asset.alpha_mask_path,
        "depth": asset.depth_map_path,
    }
    file_path = path_map[layer_type]

    import os
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Asset file not found on disk")

    return FileResponse(file_path, media_type="image/png")
