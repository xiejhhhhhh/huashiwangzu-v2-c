"""Knowledge retrieval must not expose chunks from deleted or unavailable sources."""
# ruff: noqa: E402, I001

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal, engine, init_db
from app.models.file import File
from modules.knowledge.backend.models import KbChunk, KbDocument
from modules.knowledge.backend.services import search_service
from modules.knowledge.backend.services.embedding_service import get_chunk_by_id
from modules.knowledge.backend.services.search_service import (
    get_document_chunks,
    hybrid_search,
    keyword_search,
    vector_search,
)

OWNER_ID = 1
VECTOR_SIZE = 1024
_FRAMEWORK_READY = False


async def _ensure_framework_ready() -> None:
    global _FRAMEWORK_READY
    if _FRAMEWORK_READY:
        return
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await init_db()
    _FRAMEWORK_READY = True


async def _cleanup(doc_ids: list[int], file_ids: list[int]) -> None:
    async with AsyncSessionLocal() as db:
        for doc_id in doc_ids:
            await db.execute(text("DELETE FROM kb_chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_documents WHERE id = :doc_id"), {"doc_id": doc_id})
        for file_id in file_ids:
            await db.execute(text("DELETE FROM framework_file_items WHERE id = :file_id"), {"file_id": file_id})
        await db.commit()


async def _create_case(marker: str) -> tuple[dict[str, int], dict[str, int]]:
    await _ensure_framework_ready()
    vector = [1.0] + [0.0] * (VECTOR_SIZE - 1)
    async with AsyncSessionLocal() as db:
        live_file = File(
            name=f"k3_live_{marker}",
            extension="txt",
            size=1,
            owner_id=OWNER_ID,
            storage_path=f"tests/k3_live_{marker}.txt",
            mime_type="text/plain",
            deleted=False,
        )
        deleted_file = File(
            name=f"k3_deleted_source_{marker}",
            extension="txt",
            size=1,
            owner_id=OWNER_ID,
            storage_path=f"tests/k3_deleted_source_{marker}.txt",
            mime_type="text/plain",
            deleted=True,
        )
        db.add_all([live_file, deleted_file])
        await db.flush()

        live_doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=live_file.id,
            filename=f"k3_live_{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        deleted_doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=live_file.id,
            filename=f"k3_deleted_doc_{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=True,
        )
        source_deleted_doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=deleted_file.id,
            filename=f"k3_source_deleted_{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        missing_source_doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=900_000_000 + int(marker[:6], 16),
            filename=f"k3_source_missing_{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        db.add_all([live_doc, deleted_doc, source_deleted_doc, missing_source_doc])
        await db.flush()

        docs = {
            "live": live_doc.id,
            "deleted_doc": deleted_doc.id,
            "source_deleted": source_deleted_doc.id,
            "source_missing": missing_source_doc.id,
        }
        chunks: dict[str, int] = {}
        for key, doc_id in docs.items():
            chunk = KbChunk(
                document_id=doc_id,
                owner_id=OWNER_ID,
                page=1,
                chunk_index=0,
                block_type="paragraph",
                text=f"K3 live source filtering {marker} {key}",
                embedding=vector,
                keywords=f"K3 {marker} {key}",
            )
            db.add(chunk)
            await db.flush()
            chunks[key] = chunk.id

        await db.commit()
        return docs, {"live_file": live_file.id, "deleted_file": deleted_file.id, **chunks}


@pytest.mark.asyncio
async def test_search_filters_deleted_doc_and_unavailable_source(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = uuid.uuid4().hex[:8]
    docs, ids = await _create_case(marker)
    try:
        async def fake_embedding(_query: str) -> list[float]:
            return [1.0] + [0.0] * (VECTOR_SIZE - 1)

        monkeypatch.setattr(search_service, "get_embedding", fake_embedding)
        async with AsyncSessionLocal() as db:
            keyword_results = await keyword_search(db, marker, OWNER_ID, top_k=10)
            vector_results = await vector_search(db, marker, OWNER_ID, top_k=10)
            hybrid_results = await hybrid_search(db, marker, OWNER_ID, top_k=10)

        assert [item["document_id"] for item in keyword_results] == [docs["live"]]
        assert [item["document_id"] for item in hybrid_results] == [docs["live"]]
        vector_doc_ids = {item["document_id"] for item in vector_results}
        assert docs["live"] in vector_doc_ids
        assert docs["deleted_doc"] not in vector_doc_ids
        assert docs["source_deleted"] not in vector_doc_ids
        assert docs["source_missing"] not in vector_doc_ids
        for item in keyword_results + vector_results + hybrid_results:
            assert item["source_available"] is True
            assert item["source_state"] == "available"
    finally:
        await _cleanup(list(docs.values()), [ids["live_file"], ids["deleted_file"]])


@pytest.mark.asyncio
async def test_chunk_detail_filters_deleted_doc_and_unavailable_source() -> None:
    marker = uuid.uuid4().hex[:8]
    docs, ids = await _create_case(marker)
    try:
        async with AsyncSessionLocal() as db:
            live = await get_chunk_by_id(db, ids["live"], owner_id=OWNER_ID)
            assert live is not None
            assert marker in live["text"]

            assert await get_chunk_by_id(db, ids["deleted_doc"], owner_id=OWNER_ID) is None
            assert await get_chunk_by_id(db, ids["source_deleted"], owner_id=OWNER_ID) is None
            assert await get_chunk_by_id(db, ids["source_missing"], owner_id=OWNER_ID) is None
            assert await get_document_chunks(db, docs["source_deleted"], owner_id=OWNER_ID) == []
            assert await get_document_chunks(db, docs["source_missing"], owner_id=OWNER_ID) == []

    finally:
        await _cleanup(list(docs.values()), [ids["live_file"], ids["deleted_file"]])
