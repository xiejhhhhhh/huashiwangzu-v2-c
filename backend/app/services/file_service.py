from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.file import Folder, File
from app.core.exceptions import NotFound, AppException
from app.services.file_share_service import get_accessible_file_ids


async def get_folder_tree(db: AsyncSession, owner_id: int) -> list[Folder]:
    result = await db.execute(select(Folder).where(Folder.owner_id == owner_id, Folder.deleted == False).order_by(Folder.name))
    return result.scalars().all()


async def create_folder(db: AsyncSession, name: str, parent_id: int | None, owner_id: int) -> Folder:
    if parent_id:
        parent = await db.get(Folder, parent_id)
        if not parent or parent.deleted:
            raise NotFound("Parent folder not found")
        if parent.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)
    # Check name conflict in same directory
    existing = await db.execute(
        select(Folder).where(
            Folder.name == name,
            Folder.parent_id == parent_id,
            Folder.owner_id == owner_id,
            Folder.deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise AppException("A folder with the same name already exists", status_code=409)
    folder = Folder(name=name, parent_id=parent_id, owner_id=owner_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def get_file_list(db: AsyncSession, folder_id: int, owner_id: int, page: int = 1, page_size: int = 50):
    if folder_id == 0:
        subfolders = await db.execute(select(Folder).where(Folder.parent_id.is_(None), Folder.owner_id == owner_id, Folder.deleted == False).order_by(Folder.name))
    else:
        # Verify folder exists and belongs to user
        folder = await db.get(Folder, folder_id)
        if not folder or folder.deleted or folder.owner_id != owner_id:
            raise NotFound("Folder not found")
        subfolders = await db.execute(select(Folder).where(Folder.parent_id == folder_id, Folder.owner_id == owner_id, Folder.deleted == False).order_by(Folder.name))
    folder_list = [{"id": f.id, "name": f.name, "extension": None, "size": 0, "created_at": f.created_at, "storage_path": None, "is_folder": True, "parent_id": f.parent_id, "mime_type": None} for f in subfolders.scalars().all()]
    cond = File.folder_id.is_(None) if folder_id == 0 else File.folder_id == folder_id
    result = await db.execute(select(File).where(cond, File.owner_id == owner_id, File.deleted == False).order_by(File.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    file_list = [{"id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "created_at": f.created_at, "storage_path": f.storage_path, "is_folder": False, "parent_id": f.folder_id, "mime_type": f.mime_type} for f in result.scalars().all()]
    return {"items": folder_list + file_list, "total": len(folder_list) + len(file_list), "page": page, "page_size": page_size}


async def rename_item(db: AsyncSession, item_type: str, item_id: int, new_name: str, owner_id: int):
    item = await db.get(Folder, item_id) if item_type == "folder" else await db.get(File, item_id)
    if not item or (hasattr(item, "owner_id") and item.owner_id != owner_id) or getattr(item, "deleted", False):
        raise NotFound(f"{item_type} not found")
    # Check name conflict in the same directory
    if item_type == "folder":
        existing = await db.execute(
            select(Folder).where(Folder.name == new_name, Folder.parent_id == item.parent_id,
                                 Folder.owner_id == owner_id, Folder.deleted == False, Folder.id != item_id)
        )
    else:
        existing = await db.execute(
            select(File).where(File.name == new_name, File.extension == item.extension,
                               File.folder_id == item.folder_id, File.owner_id == owner_id,
                               File.deleted == False, File.id != item_id)
        )
    if existing.scalar_one_or_none():
        raise AppException("An item with the same name already exists in this directory", status_code=409)
    item.name = new_name
    await db.commit()
    return item


async def move_item(db: AsyncSession, item_type: str, item_id: int, target_folder_id: int | None, owner_id: int):
    item = await db.get(Folder, item_id) if item_type == "folder" else await db.get(File, item_id)
    if not item or item.owner_id != owner_id or (hasattr(item, "deleted") and item.deleted):
        raise NotFound(f"{item_type} not found")
    if target_folder_id:
        target = await db.get(Folder, target_folder_id)
        if not target or target.deleted:
            raise NotFound("Target folder not found")
        if target.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)
    if item_type == "folder":
        await _check_folder_cycle(db, item_id, target_folder_id)
        # Check name conflict in target directory
        existing = await db.execute(
            select(Folder).where(Folder.name == item.name, Folder.parent_id == target_folder_id,
                                 Folder.owner_id == owner_id, Folder.deleted == False, Folder.id != item_id)
        )
        if existing.scalar_one_or_none():
            raise AppException("A folder with the same name already exists in the target directory", status_code=409)
        item.parent_id = target_folder_id
    else:
        # Check name conflict in target directory
        existing = await db.execute(
            select(File).where(File.name == item.name, File.extension == item.extension,
                               File.folder_id == target_folder_id, File.owner_id == owner_id,
                               File.deleted == False, File.id != item_id)
        )
        if existing.scalar_one_or_none():
            raise AppException("A file with the same name already exists in the target directory", status_code=409)
        item.folder_id = target_folder_id
    await db.commit()
    return item


async def _check_folder_cycle(db: AsyncSession, folder_id: int, target_parent_id: int | None):
    if target_parent_id is None or target_parent_id == 0:
        return
    if folder_id == target_parent_id:
        raise AppException("Cannot move folder into itself", status_code=400)
    current = target_parent_id
    while current:
        if current == folder_id:
            raise AppException("Cannot move folder into itself or a subfolder", status_code=400)
        parent = await db.get(Folder, current)
        current = parent.parent_id if parent else None


async def delete_to_trash(db: AsyncSession, item_type: str, item_id: int, owner_id: int):
    if item_type == "file":
        item = await db.get(File, item_id)
        if not item or item.owner_id != owner_id or item.deleted:
            raise NotFound("File not found")
        item.deleted = True
        item.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return item
    if item_type == "folder":
        item = await db.get(Folder, item_id)
        if not item or item.owner_id != owner_id or item.deleted:
            raise NotFound("Folder not found")
        await _recursive_delete_folder(db, item_id)
        await db.commit()
        return item
    raise NotFound("Unsupported item type")


async def _recursive_delete_folder(db: AsyncSession, folder_id: int):
    now = datetime.now(timezone.utc)
    folder = await db.get(Folder, folder_id)
    if folder and not folder.deleted:
        folder.deleted = True
        folder.deleted_at = now
    files = await db.execute(select(File).where(File.folder_id == folder_id, File.deleted == False))
    for f in files.scalars():
        f.deleted = True
        f.deleted_at = now
    subfolders = await db.execute(select(Folder).where(Folder.parent_id == folder_id, Folder.deleted == False))
    for sf in subfolders.scalars():
        await _recursive_delete_folder(db, sf.id)


async def get_file_record(db: AsyncSession, file_id: int) -> File | None:
    result = await db.get(File, file_id)
    return result if result and not result.deleted else None


async def search_files(db: AsyncSession, owner_id: int, keyword: str = "", extension: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    # Get all accessible file IDs (owned + shared)
    accessible_ids = await get_accessible_file_ids(db, owner_id)
    base = File.deleted == False
    fq = select(File).where(base, File.id.in_(accessible_ids))
    if keyword:
        fq = fq.where(File.name.ilike(f"%{keyword}%"))
    if extension:
        fq = fq.where(File.extension == extension)
    total = len((await db.execute(fq.with_only_columns(File.id))).scalars().all())
    result = await db.execute(fq.order_by(File.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    file_list = [{"id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "folder_id": f.folder_id, "created_at": f.created_at, "is_folder": False} for f in result.scalars().all()]
    if extension:
        return {"items": file_list, "total": total, "page": page, "page_size": page_size}
    fld_q = select(Folder).where(Folder.deleted == False, Folder.owner_id == owner_id)
    if keyword:
        fld_q = fld_q.where(Folder.name.ilike(f"%{keyword}%"))
    fld_total = len((await db.execute(fld_q.with_only_columns(Folder.id))).scalars().all())
    fld_result = await db.execute(fld_q.order_by(Folder.name).offset((page - 1) * page_size).limit(page_size))
    folder_list = [{"id": f.id, "name": f.name, "extension": None, "size": 0, "folder_id": f.parent_id, "created_at": None, "is_folder": True} for f in fld_result.scalars().all()]
    return {"items": folder_list + file_list, "total": fld_total + total, "page": page, "page_size": page_size}


async def get_item_path(db: AsyncSession, item_type: str, item_id: int, user_id: int) -> dict:
    """Return breadcrumb path from root to the given file or folder."""
    items = [{"id": None, "name": "Desktop", "type": "root"}]

    if item_type == "file":
        item = await db.get(File, item_id)
        if not item or item.deleted:
            raise NotFound("File not found")
        if item.owner_id != user_id:
            # Check shared access
            from app.services.file_share_service import check_file_access
            access = await check_file_access(db, item_id, user_id)
            if not access["accessible"]:
                raise NotFound("File not found")
        current_folder_id = item.folder_id
    elif item_type == "folder":
        item = await db.get(Folder, item_id)
        if not item or item.deleted or item.owner_id != user_id:
            raise NotFound("Folder not found")
        items.append({"id": item.id, "name": item.name, "type": "folder"})
        current_folder_id = item.parent_id
    else:
        raise AppException("Invalid item_type", status_code=400)

    # Walk up the folder hierarchy
    visited_ids = set()
    while current_folder_id:
        if current_folder_id in visited_ids:
            break  # Prevent infinite loop
        visited_ids.add(current_folder_id)
        folder = await db.get(Folder, current_folder_id)
        if not folder or folder.deleted or folder.owner_id != user_id:
            break
        items.insert(1, {"id": folder.id, "name": folder.name, "type": "folder"})
        current_folder_id = folder.parent_id

    return {"items": items}
