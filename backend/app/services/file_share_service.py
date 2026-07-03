from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFound
from app.models.file import File
from app.models.file_share import FileShare
from app.models.user import User


async def check_file_access(db: AsyncSession, file_id: int, user_id: int) -> dict:
    """Check if a user can access a file. Returns access info."""
    file = await db.get(File, file_id)
    if not file or file.deleted:
        return {"accessible": False, "permission": None}

    if file.owner_id == user_id:
        return {"accessible": True, "permission": "owner"}

    share = await db.execute(
        select(FileShare).where(
            FileShare.file_id == file_id,
            FileShare.shared_with_user_id == user_id,
        )
    )
    share_record = share.scalar_one_or_none()
    if share_record:
        return {"accessible": True, "permission": share_record.permission}

    return {"accessible": False, "permission": None}


async def check_file_write_access(db: AsyncSession, file_id: int, user_id: int) -> dict:
    """Check if a user can write a file. Owner or edit share only."""
    access = await check_file_access(db, file_id, user_id)
    if access["permission"] in ("owner", "edit"):
        return {"accessible": True, "permission": access["permission"]}
    return {"accessible": False, "permission": access["permission"]}


async def create_share(
    db: AsyncSession,
    file_id: int,
    shared_by_user_id: int,
    shared_with_user_id: int,
    permission: str,
) -> FileShare:
    """Share a file with another user. Reuses existing share if already shared."""
    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")
    if file.owner_id != shared_by_user_id:
        raise AppException("Only the file owner can share", status_code=403)

    target_user = await db.get(User, shared_with_user_id)
    if not target_user:
        raise NotFound("Target user not found")

    if shared_by_user_id == shared_with_user_id:
        raise AppException("Cannot share a file with yourself", status_code=400)

    if permission not in ("read", "edit"):
        raise AppException("Permission must be 'read' or 'edit'", status_code=400)

    # Check if already shared — update existing
    existing = await db.execute(
        select(FileShare).where(
            FileShare.file_id == file_id,
            FileShare.shared_by_owner_id == shared_by_user_id,
            FileShare.shared_with_user_id == shared_with_user_id,
        )
    )
    share = existing.scalar_one_or_none()
    if share:
        share.permission = permission
        await db.commit()
        await db.refresh(share)
        return share

    share = FileShare(
        file_id=file_id,
        shared_by_owner_id=shared_by_user_id,
        shared_with_user_id=shared_with_user_id,
        permission=permission,
        publish=False,
        reshare=False,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


async def delete_share(db: AsyncSession, share_id: int, user_id: int) -> None:
    """Cancel a share. Only the original sharer can cancel."""
    share = await db.get(FileShare, share_id)
    if not share:
        raise NotFound("Share not found")
    if share.shared_by_owner_id != user_id:
        raise AppException("Only the sharer can cancel the share", status_code=403)
    await db.delete(share)
    await db.commit()


async def get_received_shares(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    keyword: str = "",
) -> dict:
    """Get files shared with a user."""
    query = (
        select(FileShare, File, User.display_name.label("shared_by_name"))
        .join(File, FileShare.file_id == File.id)
        .join(User, FileShare.shared_by_owner_id == User.id)
        .where(
            FileShare.shared_with_user_id == user_id,
            File.deleted.is_(False),
        )
    )
    if keyword:
        query = query.where(File.name.ilike(f"%{keyword}%"))

    query = query.order_by(FileShare.created_at.desc())
    # Count with same filters (deleted=False, keyword)
    count_q = select(FileShare).join(File, FileShare.file_id == File.id).where(
        FileShare.shared_with_user_id == user_id,
        File.deleted.is_(False),
    )
    if keyword:
        count_q = count_q.where(File.name.ilike(f"%{keyword}%"))
    total = len((await db.execute(count_q)).scalars().all())

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    items = []
    for share, file, shared_by_name in result.all():
        items.append({
            "id": share.id,
            "file_id": file.id,
            "file_name": file.name,
            "extension": file.extension,
            "size": file.size,
            "permission": share.permission,
            "shared_by_name": shared_by_name,
            "created_at": share.created_at.isoformat() if share.created_at else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_sent_shares(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get files shared by a user."""
    query = (
        select(FileShare, File, User.display_name.label("shared_with_name"))
        .join(File, FileShare.file_id == File.id)
        .join(User, FileShare.shared_with_user_id == User.id)
        .where(
            FileShare.shared_by_owner_id == user_id,
            File.deleted.is_(False),
        )
        .order_by(FileShare.created_at.desc())
    )
    total = len((await db.execute(
        select(FileShare).join(File, FileShare.file_id == File.id).where(
            FileShare.shared_by_owner_id == user_id,
            File.deleted.is_(False),
        )
    )).scalars().all())

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    items = []
    for share, file, shared_with_name in result.all():
        items.append({
            "id": share.id,
            "file_id": file.id,
            "file_name": file.name,
            "extension": file.extension,
            "permission": share.permission,
            "shared_with_name": shared_with_name,
            "created_at": share.created_at.isoformat() if share.created_at else None,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_accessible_file_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Get all file IDs accessible to a user (owned + shared)."""
    owned = await db.execute(
        select(File.id).where(File.owner_id == user_id, File.deleted.is_(False))
    )
    owned_ids = set(r for (r,) in owned.all())
    shared = await db.execute(
        select(FileShare.file_id).where(
            FileShare.shared_with_user_id == user_id,
        )
    )
    shared_ids = set(r for (r,) in shared.all())
    return owned_ids | shared_ids
