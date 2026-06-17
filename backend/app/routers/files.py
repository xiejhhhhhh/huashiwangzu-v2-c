from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.file import (
    FolderResponse, FileResponse, CreateFolderRequest, RenameRequest, MoveRequest, DeleteRequest,
)
from app.middleware.auth import require_permission
from app.models.user import User
from app.models.recycle import RecycleItem
from app.services import file_service, file_ops_service
from app.services.system_service import create_log
from datetime import datetime, timezone
from pydantic import BaseModel

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/tree")
async def get_folder_tree(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    tree = await file_service.get_folder_tree(db, user.id)
    return ApiResponse(data=[FolderResponse.model_validate(f) for f in tree])


@router.post("/folder")
async def create_folder(body: CreateFolderRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    folder = await file_service.create_folder(db, body.name, body.parent_id, user.id)
    return ApiResponse(data=FolderResponse.model_validate(folder))


@router.get("/list")
async def get_file_list(folder_id: int = Query(0), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_service.get_file_list(db, folder_id, user.id, page, page_size)
    return ApiResponse(data=result)


@router.get("/detail/{file_id}")
async def get_file_detail(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await file_ops_service.get_file_detail(db, file_id, user.id)
    return ApiResponse(data=result)


@router.post("/rename")
async def rename(body: RenameRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    await file_service.rename_item(db, body.type, body.id, body.new_name, user.id)
    return ApiResponse(data={"message": "Renamed"})


@router.post("/move")
async def move(body: MoveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    await file_service.move_item(db, body.type, body.id, body.target_folder_id, user.id)
    return ApiResponse(data={"message": "Moved"})


@router.post("/copy")
async def copy(body: MoveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    item = await file_ops_service.copy_item(db, body.type, body.id, body.target_folder_id, user.id)
    return ApiResponse(data={"id": item.id, "message": "Copied"})


@router.post("/delete")
async def delete_item(body: DeleteRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    item = await file_service.delete_to_trash(db, body.type, body.id, user.id)
    recycle_item = RecycleItem(origin_id=body.id, item_type=body.type, name=item.name, owner_id=user.id, deleted_at=datetime.now(timezone.utc))
    db.add(recycle_item)
    await db.commit()
    return ApiResponse(data={"message": "Deleted"})


@router.get("/search")
async def search(keyword: str = Query(""), extension: str = Query(None), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_service.search_files(db, user.id, keyword, extension, page, page_size)
    return ApiResponse(data=result)


# ── Batch operations ─────────────────────────────────────────────────


class BatchItem(BaseModel):
    id: int
    item_type: str = "file"


class BatchRequest(BaseModel):
    items: list[BatchItem]
    target_folder_id: int | None = None


@router.post("/batch-delete")
async def batch_delete(body: BatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    results = []
    success_count = 0
    failed_count = 0
    for item in body.items:
        try:
            deleted = await file_service.delete_to_trash(db, item.item_type, item.id, user.id)
            recycle_item = RecycleItem(origin_id=item.id, item_type=item.item_type, name=deleted.name, owner_id=user.id, deleted_at=datetime.now(timezone.utc))
            db.add(recycle_item)
            await db.commit()
            results.append({"id": item.id, "type": item.item_type, "success": True, "error": None})
            success_count += 1
            await create_log(db, "info", "file_system", "delete_to_trash", f"Batch deleted {item.item_type} {item.id}", user_id=user.id)
        except Exception as e:
            await db.rollback()
            results.append({"id": item.id, "type": item.item_type, "success": False, "error": str(e)})
            failed_count += 1
    return ApiResponse(data={"items": results, "success_count": success_count, "failed_count": failed_count})


@router.post("/batch-move")
async def batch_move(body: BatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("editor"))):
    results = []
    success_count = 0
    failed_count = 0
    for item in body.items:
        try:
            await file_service.move_item(db, item.item_type, item.id, body.target_folder_id, user.id)
            results.append({"id": item.id, "type": item.item_type, "success": True, "error": None})
            success_count += 1
            await create_log(db, "info", "file_system", "move", f"Moved {item.item_type} {item.id} to folder {body.target_folder_id}", user_id=user.id)
        except Exception as e:
            await db.rollback()
            results.append({"id": item.id, "type": item.item_type, "success": False, "error": str(e)})
            failed_count += 1
    return ApiResponse(data={"items": results, "success_count": success_count, "failed_count": failed_count})


@router.get("/path/{item_type}/{item_id}")
async def get_item_path(item_type: str, item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_service.get_item_path(db, item_type, item_id, user.id)
    return ApiResponse(data=result)
