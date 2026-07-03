"""Regression tests for backend foundation sweep fixes."""

from uuid import uuid4

import pytest
from app.core.exceptions import PermissionDenied
from app.database import AsyncSessionLocal
from app.models.file import File
from app.models.file_share import FileShare
from app.services.content.adapter import call_export_adapter
from app.services.file_share_service import get_sent_shares
from sqlalchemy import delete


async def _delete_files(file_ids: list[int]) -> None:
    if not file_ids:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(FileShare).where(FileShare.file_id.in_(file_ids)))
        await db.execute(delete(File).where(File.id.in_(file_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_export_adapter_checks_returned_file_access(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id = 4
    intruder_id = 5
    file_id = None
    async with AsyncSessionLocal() as db:
        file_rec = File(
            name=f"adapter-cross-owner-{uuid4().hex}",
            extension="docx",
            size=4,
            owner_id=owner_id,
            storage_path="adapter-cross-owner.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            deleted=False,
        )
        db.add(file_rec)
        await db.commit()
        await db.refresh(file_rec)
        file_id = file_rec.id

    async def fake_call_capability(*_args, **_kwargs):
        return {"file_id": file_id}

    monkeypatch.setattr("app.services.content.adapter.call_capability", fake_call_capability)

    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(PermissionDenied):
                await call_export_adapter(db, "docx", {"filename": "x"}, intruder_id)
    finally:
        if file_id is not None:
            await _delete_files([file_id])


@pytest.mark.asyncio
async def test_get_sent_shares_excludes_deleted_files() -> None:
    owner_id = 4
    shared_with_user_id = 5
    file_id = None
    async with AsyncSessionLocal() as db:
        file_rec = File(
            name=f"deleted-share-{uuid4().hex}",
            extension="txt",
            size=0,
            owner_id=owner_id,
            storage_path="deleted-share.txt",
            mime_type="text/plain",
            deleted=True,
        )
        db.add(file_rec)
        await db.flush()
        share = FileShare(
            file_id=file_rec.id,
            shared_by_owner_id=owner_id,
            shared_with_user_id=shared_with_user_id,
            permission="read",
        )
        db.add(share)
        await db.commit()
        file_id = file_rec.id

    try:
        async with AsyncSessionLocal() as db:
            result = await get_sent_shares(db, owner_id, page=1, page_size=50)
        assert all(item["file_id"] != file_id for item in result["items"])
    finally:
        if file_id is not None:
            await _delete_files([file_id])
