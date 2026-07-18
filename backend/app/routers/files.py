import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.file import File, Folder
from app.models.recycle import RecycleItem
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.file import (
    CreateFolderRequest,
    DeleteRequest,
    FolderResponse,
    MoveRequest,
    RenameRequest,
)
from app.services import file_compress_service, file_ops_service, file_service, file_tag_service
from app.services.system_service import create_log

router = APIRouter(prefix="/api/files", tags=["files"])
logger = logging.getLogger("v2.files")


async def _emit_file_event(event_name: str, file_id: int, user: User) -> None:
    """Best-effort module lifecycle event; file operations remain authoritative."""
    try:
        from app.services.module_events import emit_module_event

        await emit_module_event(
            event_name,
            {"file_id": file_id, "owner_id": user.id},
            caller=f"user:{user.id}",
            caller_role=user.role,
        )
    except Exception as exc:
        logger.warning("%s event emission failed for file_id=%d: %s", event_name, file_id, exc)


async def _collect_folder_file_ids(
    db: AsyncSession,
    folder_id: int,
    owner_id: int,
    *,
    deleted: bool,
) -> list[int]:
    file_rows = await db.execute(
        select(File.id).where(
            File.folder_id == folder_id,
            File.owner_id == owner_id,
            File.deleted.is_(deleted),
        )
    )
    file_ids = [int(file_id) for file_id in file_rows.scalars().all()]
    folder_rows = await db.execute(
        select(Folder.id).where(
            Folder.parent_id == folder_id,
            Folder.owner_id == owner_id,
            Folder.deleted.is_(deleted),
        )
    )
    for child_folder_id in folder_rows.scalars().all():
        file_ids.extend(
            await _collect_folder_file_ids(db, int(child_folder_id), owner_id, deleted=deleted)
        )
    return file_ids


@router.get("/tree")
async def get_folder_tree(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    tree = await file_service.get_folder_tree(db, user.id)
    return ApiResponse(data=[FolderResponse.model_validate(f) for f in tree])


@router.get("/locations")
async def get_user_locations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Return Finder special locations; creates 文稿/下载 root folders if missing."""
    data = await file_service.ensure_user_locations(db, user.id)
    return ApiResponse(data=data)


class FileTagSetRequest(BaseModel):
    item_type: str
    item_id: int
    tags: list[str] = []


class FileTagToggleRequest(BaseModel):
    item_type: str
    item_id: int
    tag: str


@router.get("/tags")
async def list_file_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    """Return current user's file/folder tags map: { 'file:12': ['red'], ... }."""
    data = await file_tag_service.list_tags_map(db, user.id)
    return ApiResponse(data=data)


@router.get("/tags/{item_type}/{item_id}")
async def get_file_item_tags(
    item_type: str,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    tags = await file_tag_service.get_item_tags(
        db,
        owner_id=user.id,
        item_type=item_type,
        item_id=item_id,
    )
    return ApiResponse(data={"item_type": item_type, "item_id": item_id, "tags": tags})


@router.put("/tags")
async def set_file_item_tags(
    body: FileTagSetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    tags = await file_tag_service.set_item_tags(
        db,
        owner_id=user.id,
        item_type=body.item_type,
        item_id=body.item_id,
        tags=body.tags,
    )
    return ApiResponse(data={"item_type": body.item_type, "item_id": body.item_id, "tags": tags})


@router.post("/tags/toggle")
async def toggle_file_item_tag(
    body: FileTagToggleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    tags = await file_tag_service.toggle_item_tag(
        db,
        owner_id=user.id,
        item_type=body.item_type,
        item_id=body.item_id,
        tag=body.tag,
    )
    return ApiResponse(data={"item_type": body.item_type, "item_id": body.item_id, "tags": tags})


@router.post("/folder")
async def create_folder(body: CreateFolderRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
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
async def rename(body: RenameRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await file_service.rename_item(db, body.type, body.id, body.new_name, user.id)
    return ApiResponse(data={"message": "Renamed"})


@router.post("/move")
async def move(body: MoveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    await file_service.move_item(db, body.type, body.id, body.target_folder_id, user.id)
    return ApiResponse(data={"message": "Moved"})


@router.post("/copy")
async def copy(body: MoveRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    item = await file_ops_service.copy_item(db, body.type, body.id, body.target_folder_id, user.id)
    return ApiResponse(data={"id": item.id, "type": body.type, "message": "Copied"})


@router.post("/delete")
async def delete_item(body: DeleteRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    file_ids_to_emit = [body.id] if body.type == "file" else await _collect_folder_file_ids(
        db, body.id, user.id, deleted=False
    )
    item = await file_service.delete_to_trash(db, body.type, body.id, user.id)
    recycle_item = RecycleItem(origin_id=body.id, item_type=body.type, name=item.name, owner_id=user.id, deleted_at=datetime.now(timezone.utc))
    db.add(recycle_item)
    await db.commit()
    for file_id in file_ids_to_emit:
        await _emit_file_event("file.deleted", file_id, user)
    return ApiResponse(data={"message": "Deleted"})


@router.get("/search")
async def search(
    keyword: str = Query(""),
    extension: str = Query(None),
    folder_id: int | None = Query(None),
    recursive: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    result = await file_service.search_files(
        db,
        user.id,
        keyword,
        extension,
        page,
        page_size,
        folder_id=folder_id,
        recursive=recursive,
    )
    return ApiResponse(data=result)


# ── Batch operations ─────────────────────────────────────────────────


class BatchItem(BaseModel):
    id: int
    item_type: str = "file"


class BatchRequest(BaseModel):
    items: list[BatchItem]
    target_folder_id: int | None = None


@router.post("/batch-delete")
async def batch_delete(body: BatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    results = []
    success_count = 0
    failed_count = 0
    for item in body.items:
        try:
            file_ids_to_emit = [item.id] if item.item_type == "file" else await _collect_folder_file_ids(
                db, item.id, user.id, deleted=False
            )
            deleted = await file_service.delete_to_trash(db, item.item_type, item.id, user.id)
            recycle_item = RecycleItem(origin_id=item.id, item_type=item.item_type, name=deleted.name, owner_id=user.id, deleted_at=datetime.now(timezone.utc))
            db.add(recycle_item)
            await db.commit()
            for file_id in file_ids_to_emit:
                await _emit_file_event("file.deleted", file_id, user)
            results.append({"id": item.id, "type": item.item_type, "success": True, "error": None})
            success_count += 1
            await create_log(db, "info", "file_system", "delete_to_trash", f"Batch deleted {item.item_type} {item.id}", user_id=user.id)
        except Exception as e:
            await db.rollback()
            results.append({"id": item.id, "type": item.item_type, "success": False, "error": str(e)})
            failed_count += 1
    return ApiResponse(data={"items": results, "success_count": success_count, "failed_count": failed_count})


@router.post("/batch-move")
async def batch_move(body: BatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
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


@router.post("/batch-copy")
async def batch_copy(body: BatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    results = []
    success_count = 0
    failed_count = 0
    for item in body.items:
        try:
            copied = await file_ops_service.copy_item(db, item.item_type, item.id, body.target_folder_id, user.id)
            results.append({
                "id": item.id,
                "type": item.item_type,
                "success": True,
                "error": None,
                "new_id": getattr(copied, "id", None),
            })
            success_count += 1
            await create_log(
                db,
                "info",
                "file_system",
                "copy",
                f"Copied {item.item_type} {item.id} to folder {body.target_folder_id}",
                user_id=user.id,
            )
        except Exception as e:
            await db.rollback()
            results.append({"id": item.id, "type": item.item_type, "success": False, "error": str(e)})
            failed_count += 1
    return ApiResponse(data={"items": results, "success_count": success_count, "failed_count": failed_count})


class CompressRequest(BaseModel):
    items: list[BatchItem]


@router.post("/compress")
async def compress_items(
    body: CompressRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    payload = [{"id": i.id, "item_type": i.item_type} for i in body.items]
    data, filename = await file_compress_service.build_zip_bytes(db, owner_id=user.id, items=payload)
    await create_log(db, "info", "file_system", "compress", f"Compressed {len(payload)} items", user_id=user.id)
    # RFC 5987 filename*
    cd = f"attachment; filename=\"archive.zip\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": cd},
    )


@router.get("/path/{item_type}/{item_id}")
async def get_item_path(item_type: str, item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer"))):
    result = await file_service.get_item_path(db, item_type, item_id, user.id)
    return ApiResponse(data=result)
