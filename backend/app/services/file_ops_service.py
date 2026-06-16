import shutil
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.core.exceptions import AppException, NotFound
from app.models.file import File, Folder
from app.services.file_service import get_file_record

UPLOAD_ROOT = Path(get_settings().UPLOAD_DIR)


async def copy_item(
    db: AsyncSession,
    item_type: str,
    item_id: int,
    target_folder_id: int | None,
    owner_id: int,
) -> File:
    if item_type != "file":
        raise AppException("Folder copy is not supported yet", status_code=400)
    source = await db.get(File, item_id)
    if not source or source.owner_id != owner_id or source.deleted:
        raise NotFound("File not found")
    if target_folder_id:
        target = await db.get(Folder, target_folder_id)
        if not target or target.deleted:
            raise NotFound("Target folder not found")
    copied = File(
        name=f"{source.name} copy", extension=source.extension, size=source.size,
        folder_id=target_folder_id, owner_id=owner_id, storage_path="",
        mime_type=source.mime_type, md5=source.md5, deleted=False,
    )
    db.add(copied)
    await db.flush()
    copied.storage_path = _copy_storage_file(source, copied)
    await db.commit()
    await db.refresh(copied)
    return copied


def _copy_storage_file(source: File, copied: File) -> str:
    if not source.storage_path:
        return ""
    source_path = UPLOAD_ROOT / source.storage_path
    if not source_path.exists():
        return ""
    suffix = f".{copied.extension}" if copied.extension else ""
    target_rel = f"source/{copied.id}{suffix}"
    target_path = UPLOAD_ROOT / target_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_rel


async def get_file_detail(db: AsyncSession, file_id: int, owner_id: int) -> dict:
    file = await get_file_record(db, file_id)
    if not file or file.owner_id != owner_id:
        raise NotFound("File not found")
    folder_name = ""
    if file.folder_id:
        folder = await db.get(Folder, file.folder_id)
        folder_name = folder.name if folder and not folder.deleted else ""
    return {
        "id": file.id, "name": file.name,
        "extension": file.extension, "size": file.size,
        "folder_id": file.folder_id, "folder_name": folder_name,
        "created_at": file.created_at, "updated_at": file.updated_at,
        "storage_path": file.storage_path, "deleted": file.deleted,
        "mime_type": file.mime_type,
    }
