import asyncio
import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.file import File
from app.models.system import SystemTaskQueue
from sqlalchemy import delete, func, select

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _knowledge_attr(module_suffix: str, attr_name: str):
    """Return Knowledge symbols without re-registering SQLAlchemy tables.

    The app imports module routers under huashiwangzu_modules.*; importing the
    same models again as modules.* in a full test run creates duplicate Table
    objects on shared Base.metadata.
    """
    module_names = (
        f"huashiwangzu_modules.knowledge.{module_suffix}",
        f"modules.knowledge.backend.{module_suffix}",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, attr_name):
            return getattr(module, attr_name)
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, attr_name):
            return getattr(module, attr_name)
    raise AssertionError(f"Cannot load Knowledge symbol {module_suffix}.{attr_name}")


@pytest.mark.asyncio
async def test_concurrent_register_document_reuses_document_and_pipeline_task() -> None:
    KbDocument = _knowledge_attr("models", "KbDocument")
    register_document = _knowledge_attr("services.document_service", "register_document")

    owner_id = 1
    marker = f"knowledge-idempotency-{uuid4().hex}"
    storage_rel = f"test/{marker}.txt"
    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    storage_path = upload_root / storage_rel
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text(marker, encoding="utf-8")
    file_id: int | None = None
    document_id: int | None = None

    try:
        async with AsyncSessionLocal() as db:
            file = File(
                name=marker,
                extension="txt",
                size=len(marker.encode()),
                folder_id=None,
                owner_id=owner_id,
                storage_path=storage_rel,
                mime_type="text/plain",
                md5_hash=uuid4().hex,
                ref_count=1,
                deleted=False,
            )
            db.add(file)
            await db.commit()
            file_id = file.id

        async def register_once() -> dict:
            async with AsyncSessionLocal() as db:
                return await register_document(db, file_id or 0, owner_id)

        first, second = await asyncio.gather(register_once(), register_once())
        document_id = first["id"]

        async with AsyncSessionLocal() as db:
            document_count = await db.scalar(
                select(func.count(KbDocument.id)).where(
                    KbDocument.owner_id == owner_id,
                    KbDocument.file_id == file_id,
                    KbDocument.deleted.is_(False),
                )
            )
            task_count = await db.scalar(
                select(func.count(SystemTaskQueue.id)).where(
                    SystemTaskQueue.task_type == "kb_pipeline_stage",
                    SystemTaskQueue.parameters.ilike(f'%"document_id": {document_id}%'),
                )
            )

        assert first["id"] == second["id"]
        assert document_count == 1
        assert task_count == 1
    finally:
        async with AsyncSessionLocal() as db:
            if document_id is not None:
                await db.execute(
                    delete(SystemTaskQueue).where(
                        SystemTaskQueue.task_type == "kb_pipeline_stage",
                        SystemTaskQueue.parameters.ilike(f'%"document_id": {document_id}%'),
                    )
                )
                await db.execute(delete(KbDocument).where(KbDocument.id == document_id))
            if file_id is not None:
                await db.execute(delete(File).where(File.id == file_id))
            await db.commit()
        storage_path.unlink(missing_ok=True)
