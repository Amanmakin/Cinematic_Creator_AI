from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.persistence.projects_db import add_lock, delete_lock, get_locks, project_exists

router = APIRouter()


class AddLockRequest(BaseModel):
    path: str
    asset_id: str | None = None
    reason: str


@router.get("/{project_id}/locks")
async def list_locks(project_id: str):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return await get_locks(project_id)


@router.post("/{project_id}/locks", status_code=201)
async def create_lock(project_id: str, body: AddLockRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    lock = await add_lock(project_id, body.path, body.asset_id, body.reason)
    return lock


@router.delete("/{project_id}/locks/{lock_path:path}", status_code=204)
async def remove_lock(project_id: str, lock_path: str):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    deleted = await delete_lock(project_id, lock_path)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lock not found")
