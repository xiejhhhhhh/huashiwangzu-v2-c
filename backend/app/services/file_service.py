import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFound, PermissionDenied
from app.models.file import File, Folder
from app.models.file_share import FileShare
from app.services.file_share_service import active_share_conditions, get_accessible_file_ids

SHARED_ROOT_GROUP_OFFSET = 1_000_000_000_000


async def _lock_folder_namespace(db: AsyncSession, owner_id: int, parent_id: int | None) -> None:
    bind = db.get_bind()
    if not bind or bind.dialect.name != "postgresql":
        return
    key = f"framework_file_folders:{owner_id}:{parent_id or 0}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})


async def _folder_name_exists(
    db: AsyncSession,
    *,
    owner_id: int,
    parent_id: int | None,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(Folder.id).where(
        Folder.name == name,
        Folder.parent_id == parent_id,
        Folder.owner_id == owner_id,
        Folder.deleted.is_(False),
    )
    if exclude_id is not None:
        stmt = stmt.where(Folder.id != exclude_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def next_available_folder_name(
    db: AsyncSession,
    *,
    owner_id: int,
    parent_id: int | None,
    requested_name: str,
    exclude_id: int | None = None,
) -> str:
    base = requested_name.strip()
    if not base:
        raise AppException("Folder name cannot be empty", status_code=400)
    if not await _folder_name_exists(
        db,
        owner_id=owner_id,
        parent_id=parent_id,
        name=base,
        exclude_id=exclude_id,
    ):
        return base
    index = 1
    while True:
        candidate = f"{base}({index})"
        if not await _folder_name_exists(
            db,
            owner_id=owner_id,
            parent_id=parent_id,
            name=candidate,
            exclude_id=exclude_id,
        ):
            return candidate
        index += 1


def _shared_group_token(owner_id: int, path: str) -> int:
    digest = hashlib.sha1(f"{owner_id}:{path}".encode("utf-8")).hexdigest()[:12]
    return SHARED_ROOT_GROUP_OFFSET + int(digest, 16)


async def get_folder_tree(db: AsyncSession, owner_id: int) -> list[Folder]:
    result = await db.execute(select(Folder).where(Folder.owner_id == owner_id, Folder.deleted.is_(False)).order_by(Folder.name))
    return result.scalars().all()


async def create_folder(db: AsyncSession, name: str, parent_id: int | None, owner_id: int) -> Folder:
    if parent_id:
        parent = await db.get(Folder, parent_id)
        if not parent or parent.deleted:
            raise NotFound("Parent folder not found")
        if parent.owner_id != owner_id:
            raise AppException("Access denied: target folder does not belong to current user", status_code=403)
    await _lock_folder_namespace(db, owner_id, parent_id)
    final_name = await next_available_folder_name(
        db,
        owner_id=owner_id,
        parent_id=parent_id,
        requested_name=name,
    )
    folder = Folder(name=final_name, parent_id=parent_id, owner_id=owner_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


# Finder special locations (user-scoped real folders under desktop root parent_id=NULL)
USER_LOCATION_SPECS: tuple[tuple[str, str], ...] = (
    ("documents", "文稿"),
    ("downloads", "下载"),
)


async def _get_or_create_root_folder_by_name(
    db: AsyncSession,
    *,
    owner_id: int,
    name: str,
) -> Folder:
    """Idempotently ensure a root folder with exact name exists for the user."""
    existing = await db.execute(
        select(Folder)
        .where(
            Folder.owner_id == owner_id,
            Folder.parent_id.is_(None),
            Folder.deleted.is_(False),
            Folder.name == name,
        )
        .limit(1)
    )
    folder = existing.scalar_one_or_none()
    if folder is not None:
        return folder

    await _lock_folder_namespace(db, owner_id, None)
    existing = await db.execute(
        select(Folder)
        .where(
            Folder.owner_id == owner_id,
            Folder.parent_id.is_(None),
            Folder.deleted.is_(False),
            Folder.name == name,
        )
        .limit(1)
    )
    folder = existing.scalar_one_or_none()
    if folder is not None:
        return folder

    folder = Folder(name=name, parent_id=None, owner_id=owner_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def ensure_user_locations(db: AsyncSession, owner_id: int) -> dict:
    """Ensure Finder locations (文稿/下载) exist; desktop remains virtual id 0."""
    locations: dict[str, dict] = {
        "desktop": {"key": "desktop", "id": 0, "name": "桌面"},
    }
    for key, name in USER_LOCATION_SPECS:
        folder = await _get_or_create_root_folder_by_name(db, owner_id=owner_id, name=name)
        locations[key] = {"key": key, "id": int(folder.id), "name": name}
    return locations


async def get_file_list(db: AsyncSession, folder_id: int, owner_id: int, page: int = 1, page_size: int = 50):
    if folder_id < 0:
        source_id = abs(folder_id)
        if source_id >= SHARED_ROOT_GROUP_OFFSET:
            source_ids = await _resolve_shared_root_group_source_ids(db, owner_id, source_id)
            return await _get_shared_folder_file_list(db, source_ids, owner_id, page, page_size)
        return await _get_shared_folder_file_list(db, [source_id], owner_id, page, page_size)

    if folder_id == 0:
        subfolders = await db.execute(select(Folder).where(Folder.parent_id.is_(None), Folder.owner_id == owner_id, Folder.deleted.is_(False)).order_by(Folder.name))
    else:
        # Verify folder exists and belongs to user
        folder = await db.get(Folder, folder_id)
        if not folder or folder.deleted or folder.owner_id != owner_id:
            raise NotFound("Folder not found")
        subfolders = await db.execute(select(Folder).where(Folder.parent_id == folder_id, Folder.owner_id == owner_id, Folder.deleted.is_(False)).order_by(Folder.name))
    folder_list = [{"id": f.id, "name": f.name, "extension": None, "size": 0, "created_at": f.created_at, "updated_at": f.updated_at, "storage_path": None, "is_folder": True, "parent_id": f.parent_id, "mime_type": None} for f in subfolders.scalars().all()]
    if folder_id == 0:
        folder_list.extend(await _get_shared_root_folders(db, owner_id))
    cond = File.folder_id.is_(None) if folder_id == 0 else File.folder_id == folder_id
    result = await db.execute(select(File).where(cond, File.owner_id == owner_id, File.deleted.is_(False)).order_by(File.updated_at.desc(), File.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    file_list = [{"id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "created_at": f.created_at, "updated_at": f.updated_at, "storage_path": f.storage_path, "is_folder": False, "parent_id": f.folder_id, "mime_type": f.mime_type} for f in result.scalars().all()]
    return {"items": folder_list + file_list, "total": len(folder_list) + len(file_list), "page": page, "page_size": page_size}


async def _get_shared_root_folders(db: AsyncSession, user_id: int) -> list[dict]:
    """Return top-level shared folders as virtual folders for the desktop root.

    Shared folders are projected from file shares. The negative id keeps them
    distinct from folders owned by the current user while preserving navigation.
    """
    rows = [row for row in await _shared_folder_path_rows(db, user_id) if row.parent_id is None]
    groups: dict[tuple[int, str], list] = defaultdict(list)
    for row in rows:
        groups[(int(row.owner_id), str(row.path))].append(row)

    folders: list[dict] = []
    for (source_owner_id, path), group_rows in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0], min(int(row.id) for row in item[1]))):
        first = min(group_rows, key=lambda row: int(row.id))
        created_values = [row.created_at for row in group_rows if row.created_at is not None]
        folders.append({
            "id": -_shared_group_token(source_owner_id, path),
            "name": first.name,
            "extension": None,
            "size": 0,
            "created_at": min(created_values) if created_values else first.created_at,
            "storage_path": None,
            "is_folder": True,
            "parent_id": None,
            "mime_type": None,
            "source_folder_ids": [int(row.id) for row in group_rows],
        })
    return folders


async def _shared_folder_path_rows(db: AsyncSession, user_id: int) -> list:
    result = await db.execute(text("""
        WITH RECURSIVE ancestors AS (
            SELECT folder.id, folder.name, folder.parent_id, folder.owner_id, folder.created_at
            FROM framework_file_folders folder
            JOIN framework_file_items file ON file.folder_id = folder.id
            JOIN framework_file_shares share ON share.file_id = file.id
            WHERE share.shared_with_user_id = :user_id
              AND file.deleted = false
              AND folder.deleted = false
              AND (share.expiry IS NULL OR share.expiry > now())

            UNION

            SELECT parent.id, parent.name, parent.parent_id, parent.owner_id, parent.created_at
            FROM framework_file_folders parent
            JOIN ancestors child ON child.parent_id = parent.id
            WHERE parent.deleted = false
        ),
        paths AS (
            SELECT
                id,
                name,
                parent_id,
                owner_id,
                created_at,
                name::text AS path
            FROM ancestors
            WHERE parent_id IS NULL AND owner_id != :user_id

            UNION ALL

            SELECT
                child.id,
                child.name,
                child.parent_id,
                child.owner_id,
                child.created_at,
                paths.path || '/' || child.name AS path
            FROM ancestors child
            JOIN paths ON child.parent_id = paths.id
        )
        SELECT DISTINCT id, name, parent_id, owner_id, created_at, path
        FROM paths
        ORDER BY path, id
    """), {"user_id": user_id})
    return list(result)


async def _resolve_shared_root_group_source_ids(db: AsyncSession, user_id: int, group_token: int) -> list[int]:
    rows = await _shared_folder_path_rows(db, user_id)
    groups: dict[tuple[int, str], list] = defaultdict(list)
    for row in rows:
        groups[(int(row.owner_id), str(row.path))].append(row)
    for (source_owner_id, path), group_rows in groups.items():
        if _shared_group_token(source_owner_id, path) == group_token:
            return [int(row.id) for row in group_rows]
    raise NotFound("Folder not found")


async def _get_shared_folder_file_list(
    db: AsyncSession,
    source_folder_ids: list[int],
    user_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    source_folder_ids = [int(folder_id) for folder_id in source_folder_ids if int(folder_id) > 0]
    if not source_folder_ids:
        raise NotFound("Folder not found")
    folder_rows = await db.execute(
        select(Folder).where(
            Folder.id.in_(source_folder_ids),
            Folder.deleted.is_(False),
        )
    )
    found_folder_ids = {int(folder.id) for folder in folder_rows.scalars().all()}
    if found_folder_ids != set(source_folder_ids):
        raise NotFound("Folder not found")

    has_shared_file = await db.scalar(text("""
        WITH RECURSIVE folder_tree AS (
            SELECT id
            FROM framework_file_folders
            WHERE id = ANY(:folder_ids) AND deleted = false

            UNION ALL

            SELECT child.id
            FROM framework_file_folders child
            JOIN folder_tree parent ON child.parent_id = parent.id
            WHERE child.deleted = false
        )
        SELECT EXISTS (
            SELECT 1
            FROM folder_tree tree
            JOIN framework_file_items file ON file.folder_id = tree.id
            JOIN framework_file_shares share ON share.file_id = file.id
            WHERE share.shared_with_user_id = :user_id
              AND file.deleted = false
              AND (share.expiry IS NULL OR share.expiry > now())
        )
    """), {"folder_ids": source_folder_ids, "user_id": user_id})
    if not has_shared_file:
        raise NotFound("Folder not found")

    child_groups: dict[tuple[int, str], list] = defaultdict(list)
    for row in await _shared_folder_path_rows(db, user_id):
        if row.parent_id and int(row.parent_id) in source_folder_ids:
            child_groups[(int(row.owner_id), str(row.path))].append(row)
    folder_list = [
        {
            "id": -_shared_group_token(source_owner_id, path),
            "name": min(group_rows, key=lambda item: int(item.id)).name,
            "extension": None,
            "size": 0,
            "created_at": min(
                (row.created_at for row in group_rows if row.created_at is not None),
                default=min(group_rows, key=lambda item: int(item.id)).created_at,
            ),
            "storage_path": None,
            "is_folder": True,
            "parent_id": None,
            "mime_type": None,
            "source_folder_ids": [int(row.id) for row in group_rows],
        }
        for (source_owner_id, path), group_rows in sorted(
            child_groups.items(),
            key=lambda item: (min(row.name for row in item[1]), min(int(row.id) for row in item[1])),
        )
    ]

    offset = (page - 1) * page_size
    folder_limit = max(0, min(page_size, len(folder_list) - offset))
    paged_folders = folder_list[offset:offset + folder_limit]

    file_offset = max(0, offset - len(folder_list))
    file_limit = page_size - len(paged_folders)
    file_total = await db.scalar(
        select(func.count(File.id))
        .select_from(FileShare)
        .join(File, File.id == FileShare.file_id)
        .where(
            File.folder_id.in_(source_folder_ids),
            File.deleted.is_(False),
            FileShare.shared_with_user_id == user_id,
            *active_share_conditions(),
        )
    ) or 0
    files = []
    if file_limit:
        files_result = await db.execute(
            select(File)
            .join(FileShare, File.id == FileShare.file_id)
            .where(
                File.folder_id.in_(source_folder_ids),
                File.deleted.is_(False),
                FileShare.shared_with_user_id == user_id,
                *active_share_conditions(),
            )
            .order_by(File.created_at.desc())
            .offset(file_offset)
            .limit(file_limit)
        )
        files = files_result.scalars().all()
    file_list = [{"id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "created_at": f.created_at, "updated_at": f.updated_at, "storage_path": f.storage_path, "is_folder": False, "parent_id": -int(f.folder_id) if f.folder_id else None, "mime_type": f.mime_type} for f in files]
    return {
        "items": paged_folders + file_list,
        "total": len(folder_list) + file_total,
        "page": page,
        "page_size": page_size,
    }


async def rename_item(db: AsyncSession, item_type: str, item_id: int, new_name: str, owner_id: int):
    item = await db.get(Folder, item_id) if item_type == "folder" else await db.get(File, item_id)
    if not item or (hasattr(item, "owner_id") and item.owner_id != owner_id) or getattr(item, "deleted", False):
        raise NotFound(f"{item_type} not found")
    # Check name conflict in the same directory
    if item_type == "folder":
        existing = await db.execute(
            select(Folder).where(Folder.name == new_name, Folder.parent_id == item.parent_id,
                                 Folder.owner_id == owner_id, Folder.deleted.is_(False), Folder.id != item_id)
        )
    else:
        existing = await db.execute(
            select(File).where(File.name == new_name, File.extension == item.extension,
                               File.folder_id == item.folder_id, File.owner_id == owner_id,
                               File.deleted.is_(False), File.id != item_id)
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
                                 Folder.owner_id == owner_id, Folder.deleted.is_(False), Folder.id != item_id)
        )
        if existing.scalar_one_or_none():
            raise AppException("A folder with the same name already exists in the target directory", status_code=409)
        item.parent_id = target_folder_id
    else:
        # Check name conflict in target directory
        existing = await db.execute(
            select(File).where(File.name == item.name, File.extension == item.extension,
                               File.folder_id == target_folder_id, File.owner_id == owner_id,
                               File.deleted.is_(False), File.id != item_id)
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
    files = await db.execute(select(File).where(File.folder_id == folder_id, File.deleted.is_(False)))
    for f in files.scalars():
        f.deleted = True
        f.deleted_at = now
    subfolders = await db.execute(select(Folder).where(Folder.parent_id == folder_id, Folder.deleted.is_(False)))
    for sf in subfolders.scalars():
        await _recursive_delete_folder(db, sf.id)


async def get_file_record(db: AsyncSession, file_id: int) -> File | None:
    result = await db.get(File, file_id)
    return result if result and not result.deleted else None


async def check_file_access(db: AsyncSession, file_id: int, user_id: int) -> File:
    """Return an accessible file record or raise a framework API exception."""
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    if file.owner_id == user_id:
        return file

    from app.services.file_share_service import check_file_access as check_shared_file_access

    access = await check_shared_file_access(db, file_id, user_id)
    if not access["accessible"]:
        raise PermissionDenied("Permission denied")
    return file


async def check_file_write_access(db: AsyncSession, file_id: int, user_id: int) -> File:
    """Return a writable file record or raise a framework API exception."""
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    if file.owner_id == user_id:
        return file

    from app.services.file_share_service import check_file_write_access as check_shared_file_write_access

    access = await check_shared_file_write_access(db, file_id, user_id)
    if not access["accessible"]:
        raise PermissionDenied("Write permission denied")
    return file


async def _collect_owned_folder_ids(
    db: AsyncSession,
    *,
    owner_id: int,
    root_folder_id: int,
    recursive: bool,
) -> list[int]:
    """Return folder ids in scope. root itself is included."""
    root = await db.get(Folder, root_folder_id)
    if not root or root.deleted or root.owner_id != owner_id:
        raise NotFound("Folder not found")
    if not recursive:
        return [root_folder_id]

    ids: list[int] = []
    stack = [root_folder_id]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        ids.append(current)
        children = await db.execute(
            select(Folder.id).where(
                Folder.parent_id == current,
                Folder.owner_id == owner_id,
                Folder.deleted.is_(False),
            )
        )
        for child_id in children.scalars().all():
            stack.append(int(child_id))
    return ids


async def search_files(
    db: AsyncSession,
    owner_id: int,
    keyword: str = "",
    extension: str | None = None,
    page: int = 1,
    page_size: int = 50,
    folder_id: int | None = None,
    recursive: bool = True,
) -> dict:
    """Search files/folders by name.

    - folder_id is None: global (owned + shared files; owned folders)
    - folder_id set + recursive=False: only that folder's direct children
    - folder_id set + recursive=True: that folder subtree
    Desktop root uses folder_id=0 → treated as parent_id/folder_id IS NULL scope.
    """
    scope_folder_ids: list[int] | None = None
    root_scope = False
    if folder_id is not None:
        if int(folder_id) == 0:
            root_scope = True
            if recursive:
                # all owned folders + root files
                owned = await db.execute(
                    select(Folder.id).where(Folder.owner_id == owner_id, Folder.deleted.is_(False))
                )
                scope_folder_ids = [int(i) for i in owned.scalars().all()]
            else:
                scope_folder_ids = []
        else:
            scope_folder_ids = await _collect_owned_folder_ids(
                db, owner_id=owner_id, root_folder_id=int(folder_id), recursive=recursive
            )

    if scope_folder_ids is None:
        accessible_ids = await get_accessible_file_ids(db, owner_id)
        base = File.deleted.is_(False)
        fq = select(File).where(base, File.id.in_(accessible_ids))
    else:
        base = File.deleted.is_(False)
        if root_scope and not recursive:
            fq = select(File).where(base, File.owner_id == owner_id, File.folder_id.is_(None))
        elif root_scope and recursive:
            # root files + files in any owned folder
            fq = select(File).where(
                base,
                File.owner_id == owner_id,
                or_(File.folder_id.is_(None), File.folder_id.in_(scope_folder_ids or [-1])),
            )
        else:
            # non-root: files whose folder is in scope; for non-recursive only direct folder_id
            if recursive:
                fq = select(File).where(base, File.owner_id == owner_id, File.folder_id.in_(scope_folder_ids or [-1]))
            else:
                fq = select(File).where(base, File.owner_id == owner_id, File.folder_id == int(folder_id))

    if keyword:
        fq = fq.where(File.name.ilike(f"%{keyword}%"))
    if extension:
        fq = fq.where(File.extension == extension)
    total = len((await db.execute(fq.with_only_columns(File.id))).scalars().all())
    result = await db.execute(fq.order_by(File.updated_at.desc(), File.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    file_list = [{"id": f.id, "name": f.name, "extension": f.extension, "size": f.size, "folder_id": f.folder_id, "created_at": f.created_at, "updated_at": f.updated_at, "is_folder": False} for f in result.scalars().all()]
    if extension:
        return {"items": file_list, "total": total, "page": page, "page_size": page_size}

    if scope_folder_ids is None:
        fld_q = select(Folder).where(Folder.deleted.is_(False), Folder.owner_id == owner_id)
    elif root_scope and not recursive:
        fld_q = select(Folder).where(
            Folder.deleted.is_(False),
            Folder.owner_id == owner_id,
            Folder.parent_id.is_(None),
        )
    elif root_scope and recursive:
        fld_q = select(Folder).where(Folder.deleted.is_(False), Folder.owner_id == owner_id)
    else:
        if recursive:
            # folders in subtree except the root itself (search hits children)
            child_ids = [i for i in (scope_folder_ids or []) if i != int(folder_id)]
            if not child_ids:
                return {"items": file_list, "total": total, "page": page, "page_size": page_size}
            fld_q = select(Folder).where(
                Folder.deleted.is_(False),
                Folder.owner_id == owner_id,
                Folder.id.in_(child_ids),
            )
        else:
            fld_q = select(Folder).where(
                Folder.deleted.is_(False),
                Folder.owner_id == owner_id,
                Folder.parent_id == int(folder_id),
            )

    if keyword:
        fld_q = fld_q.where(Folder.name.ilike(f"%{keyword}%"))
    fld_total = len((await db.execute(fld_q.with_only_columns(Folder.id))).scalars().all())
    fld_result = await db.execute(fld_q.order_by(Folder.name).offset((page - 1) * page_size).limit(page_size))
    folder_list = [{"id": f.id, "name": f.name, "extension": None, "size": 0, "folder_id": f.parent_id, "created_at": f.created_at, "updated_at": f.updated_at, "is_folder": True} for f in fld_result.scalars().all()]
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
