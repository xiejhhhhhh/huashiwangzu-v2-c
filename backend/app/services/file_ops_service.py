from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFound
from app.models.file import File, Folder
from app.services.file_service import get_file_record
from app.services.file_share_service import check_file_access


async def _unique_file_name(
    db: AsyncSession,
    *,
    owner_id: int,
    folder_id: int | None,
    base_name: str,
    extension: str,
) -> str:
    copied_name = base_name
    copy_idx = 1
    while True:
        existing = await db.execute(
            select(File).where(
                File.name == copied_name,
                File.extension == extension,
                File.folder_id == folder_id,
                File.owner_id == owner_id,
                File.deleted.is_(False),
            )
        )
        if not existing.scalar_one_or_none():
            return copied_name
        copy_idx += 1
        copied_name = f"{base_name} {copy_idx}"


async def _unique_folder_name(
    db: AsyncSession,
    *,
    owner_id: int,
    parent_id: int | None,
    base_name: str,
) -> str:
    copied_name = base_name
    copy_idx = 1
    while True:
        existing = await db.execute(
            select(Folder).where(
                Folder.name == copied_name,
                Folder.parent_id == parent_id,
                Folder.owner_id == owner_id,
                Folder.deleted.is_(False),
            )
        )
        if not existing.scalar_one_or_none():
            return copied_name
        copy_idx += 1
        copied_name = f"{base_name} {copy_idx}"


async def _copy_file_row(
    db: AsyncSession,
    *,
    source: File,
    dest_folder_id: int | None,
    owner_id: int,
    name_override: str | None = None,
) -> File:
    base_name = name_override or f"{source.name} copy"
    copied_name = await _unique_file_name(
        db,
        owner_id=owner_id,
        folder_id=dest_folder_id,
        base_name=base_name,
        extension=source.extension or "",
    )
    copied = File(
        name=copied_name,
        extension=source.extension,
        size=source.size,
        folder_id=dest_folder_id,
        owner_id=owner_id,
        storage_path=source.storage_path,  # content-addressed share
        mime_type=source.mime_type,
        md5_hash=source.md5_hash,
        deleted=False,
    )
    db.add(copied)
    await db.flush()
    return copied


async def _copy_folder_recursive(
    db: AsyncSession,
    *,
    source_folder: Folder,
    dest_parent_id: int | None,
    owner_id: int,
    name_override: str | None = None,
) -> Folder:
    """Deep-copy folder tree under dest_parent_id. Caller commits."""
    if dest_parent_id is not None and dest_parent_id == source_folder.id:
        raise AppException("Cannot copy folder into itself", status_code=400)

    # cycle: dest is descendant of source
    if dest_parent_id:
        current = dest_parent_id
        seen: set[int] = set()
        while current:
            if current == source_folder.id:
                raise AppException("Cannot copy folder into its subfolder", status_code=400)
            if current in seen:
                break
            seen.add(current)
            parent = await db.get(Folder, current)
            current = parent.parent_id if parent else None

    base_name = name_override or f"{source_folder.name} copy"
    folder_name = await _unique_folder_name(
        db,
        owner_id=owner_id,
        parent_id=dest_parent_id,
        base_name=base_name,
    )
    new_folder = Folder(name=folder_name, parent_id=dest_parent_id, owner_id=owner_id, deleted=False)
    db.add(new_folder)
    await db.flush()

    # copy files in this folder (keep original names inside new tree)
    files = await db.execute(
        select(File).where(
            File.folder_id == source_folder.id,
            File.owner_id == owner_id,
            File.deleted.is_(False),
        )
    )
    for src_file in files.scalars().all():
        await _copy_file_row(
            db,
            source=src_file,
            dest_folder_id=new_folder.id,
            owner_id=owner_id,
            name_override=src_file.name,
        )

    # copy subfolders
    subfolders = await db.execute(
        select(Folder).where(
            Folder.parent_id == source_folder.id,
            Folder.owner_id == owner_id,
            Folder.deleted.is_(False),
        )
    )
    for sub in subfolders.scalars().all():
        await _copy_folder_recursive(
            db,
            source_folder=sub,
            dest_parent_id=new_folder.id,
            owner_id=owner_id,
            name_override=sub.name,
        )

    return new_folder


async def copy_item(
    db: AsyncSession,
    item_type: str,
    item_id: int,
    target_folder_id: int | None,
    owner_id: int,
) -> File | Folder:
    dest_folder_id = target_folder_id if target_folder_id and target_folder_id > 0 else None
    if dest_folder_id:
        target = await db.get(Folder, dest_folder_id)
        if not target or target.deleted:
            raise NotFound("Target folder not found")
        if target.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)

    if item_type == "file":
        source = await db.get(File, item_id)
        if not source or source.owner_id != owner_id or source.deleted:
            raise NotFound("File not found")
        copied = await _copy_file_row(
            db,
            source=source,
            dest_folder_id=dest_folder_id,
            owner_id=owner_id,
        )
        await db.commit()
        await db.refresh(copied)
        return copied

    if item_type == "folder":
        source_folder = await db.get(Folder, item_id)
        if not source_folder or source_folder.owner_id != owner_id or source_folder.deleted:
            raise NotFound("Folder not found")
        copied_folder = await _copy_folder_recursive(
            db,
            source_folder=source_folder,
            dest_parent_id=dest_folder_id,
            owner_id=owner_id,
        )
        await db.commit()
        await db.refresh(copied_folder)
        return copied_folder

    raise AppException("Unsupported item type", status_code=400)


async def get_file_detail(db: AsyncSession, file_id: int, user_id: int) -> dict:
    file = await get_file_record(db, file_id)
    if not file:
        raise NotFound("File not found")
    access = await check_file_access(db, file_id, user_id)
    if not access["accessible"]:
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
        "access_permission": access["permission"],
    }
