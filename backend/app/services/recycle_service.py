from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.recycle import RecycleItem
from app.models.file import File, Folder
from app.core.exceptions import NotFound


async def get_recycle_list(db: AsyncSession, owner_id: int):
    result = await db.execute(
        select(RecycleItem).where(RecycleItem.owner_id == owner_id).order_by(RecycleItem.deleted_at.desc())
    )
    return result.scalars().all()


async def restore_item(db: AsyncSession, item_type: str, item_id: int, owner_id: int):
    recycle = await db.get(RecycleItem, item_id)
    if not recycle or recycle.owner_id != owner_id or recycle.item_type != item_type:
        raise NotFound("Recycle item not found")

    if recycle.item_type == "file":
        file = await db.get(File, recycle.origin_id)
        if not file or file.owner_id != owner_id:
            raise NotFound("Original file no longer accessible")
        file.deleted = False
        file.deleted_at = None
    elif recycle.item_type == "folder":
        folder = await db.get(Folder, recycle.origin_id)
        if not folder or folder.owner_id != owner_id:
            raise NotFound("Original folder no longer accessible")
        await _recursive_restore_folder(db, folder.id)

    await db.delete(recycle)
    await db.commit()


async def _recursive_restore_folder(db: AsyncSession, folder_id: int):
    folder = await db.get(Folder, folder_id)
    if folder and folder.deleted:
        folder.deleted = False
        folder.deleted_at = None

    files = await db.execute(
        select(File).where(File.folder_id == folder_id, File.deleted == True)
    )
    for f in files.scalars():
        f.deleted = False
        f.deleted_at = None

    subfolders = await db.execute(
        select(Folder).where(Folder.parent_id == folder_id, Folder.deleted == True)
    )
    for sf in subfolders.scalars():
        await _recursive_restore_folder(db, sf.id)


async def delete_permanently(db: AsyncSession, item_type: str, item_id: int, owner_id: int):
    recycle = await db.get(RecycleItem, item_id)
    if not recycle or recycle.owner_id != owner_id or recycle.item_type != item_type:
        raise NotFound("Recycle item not found")

    if recycle.item_type == "file":
        file = await db.get(File, recycle.origin_id)
        if file:
            path = _resolve_storage_path(file)
            if path and path.exists():
                path.unlink()
            await db.delete(file)
    elif recycle.item_type == "folder":
        folder = await db.get(Folder, recycle.origin_id)
        if folder:
            await _recursive_permanent_delete_folder(db, folder.id)
            if folder.deleted:
                await db.delete(folder)

    await db.delete(recycle)
    await db.commit()


async def _recursive_permanent_delete_folder(db: AsyncSession, folder_id: int):
    files = await db.execute(
        select(File).where(File.folder_id == folder_id, File.deleted == True)
    )
    for f in files.scalars():
        path = _resolve_storage_path(f)
        if path and path.exists():
            path.unlink()
        await db.delete(f)

    subfolders = await db.execute(
        select(Folder).where(Folder.parent_id == folder_id, Folder.deleted == True)
    )
    for sf in subfolders.scalars():
        await _recursive_permanent_delete_folder(db, sf.id)
        await db.delete(sf)


async def empty_trash(db: AsyncSession, owner_id: int):
    items = await db.execute(
        select(RecycleItem).where(RecycleItem.owner_id == owner_id)
    )
    for item in items.scalars():
        if item.item_type == "file":
            file = await db.get(File, item.origin_id)
            if file:
                path = _resolve_storage_path(file)
                if path and path.exists():
                    path.unlink()
                await db.delete(file)
        elif item.item_type == "folder":
            folder = await db.get(Folder, item.origin_id)
            if folder:
                await _recursive_permanent_delete_folder(db, folder.id)
                if folder.deleted:
                    await db.delete(folder)
        await db.delete(item)
    await db.commit()


def _resolve_storage_path(file: File):
    from pathlib import Path
    from app.config import get_settings
    settings = get_settings()
    upload_root = Path(settings.UPLOAD_DIR)
    if not file.storage_path:
        return None
    return upload_root / file.storage_path
