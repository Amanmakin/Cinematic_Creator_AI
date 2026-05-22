"""POST /projects/{id}/sample-images — upload reference images for a project run."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.persistence.projects_db import project_exists

router = APIRouter()

_UPLOADS_DIR = Path(os.environ.get("SAMPLE_IMAGES_DIR", "sample_images"))
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per file


@router.post("/{project_id}/sample-images")
async def upload_sample_images(project_id: str, files: list[UploadFile]):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = _UPLOADS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    urls: list[str] = []
    for f in files:
        if f.content_type not in _ALLOWED_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {f.content_type}. Allowed: jpeg, png, webp, gif",
            )

        data = await f.read()
        if len(data) > _MAX_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"{f.filename} exceeds 10 MB limit")

        ext = (f.filename or "image").rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "png"
        filename = f"{uuid.uuid4().hex}.{ext}"
        (project_dir / filename).write_bytes(data)
        urls.append(f"/sample-images/{project_id}/{filename}")

    return JSONResponse({"urls": urls})
