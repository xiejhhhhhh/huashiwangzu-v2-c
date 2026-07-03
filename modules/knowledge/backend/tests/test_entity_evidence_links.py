"""Tests for knowledge entity evidence and owner-scoped page fusion links."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, or_, select, text

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-entity-evidence-links")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal

from modules.knowledge.backend.init_db import ensure_kb_tables, ensure_migration_columns
from modules.knowledge.backend.models import (
    KbChunk,
    KbChunkEntity,
    KbDocument,
    KbEvidence,
    KbPageFusion,
)
from modules.knowledge.backend.services import entity_service

OWNER_ID = 1
TEST_FILE_IDS = (900_000_000, 900_000_001)


async def _ensure_schema() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.commit()
        await ensure_kb_tables(db)
        await ensure_migration_columns(db)
        await _cleanup_stale_test_documents(db)


def _marker_from_test_filename(filename: str | None) -> str:
    stem = (filename or "").rsplit(".", 1)[0]
    for prefix in ("entity-link-", "fusion-owner-"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return ""


async def _delete_document_rows(db, document_id: int, marker: str) -> None:
    if marker:
        await db.execute(
            text(
                "DELETE FROM kb_graph_edges WHERE source_node_id IN "
                "(SELECT id FROM kb_graph_nodes WHERE label LIKE :marker) "
                "OR target_node_id IN (SELECT id FROM kb_graph_nodes WHERE label LIKE :marker)"
            ),
            {"marker": f"%{marker}%"},
        )
        await db.execute(text("DELETE FROM kb_graph_nodes WHERE label LIKE :marker"), {"marker": f"%{marker}%"})
        await db.execute(text("DELETE FROM kb_entity_dictionary WHERE name LIKE :marker"), {"marker": f"%{marker}%"})

    for table in (
        "kb_chunk_entities",
        "kb_evidence",
        "kb_governance_candidates",
        "kb_page_fusions",
        "kb_chunks",
    ):
        await db.execute(text(f"DELETE FROM {table} WHERE document_id = :document_id"), {"document_id": document_id})
    await db.execute(text("DELETE FROM kb_documents WHERE id = :document_id"), {"document_id": document_id})


async def _cleanup_stale_test_documents(db) -> None:
    result = await db.execute(
        select(KbDocument.id, KbDocument.filename).where(
            or_(
                KbDocument.file_id.in_(TEST_FILE_IDS),
                KbDocument.filename.like("entity-link-%"),
                KbDocument.filename.like("fusion-owner-%"),
            )
        )
    )
    for document_id, filename in result.all():
        await _delete_document_rows(db, int(document_id), _marker_from_test_filename(filename))
    await db.commit()

async def _cleanup(document_id: int, marker: str) -> None:
    async with AsyncSessionLocal() as db:
        await _delete_document_rows(db, document_id, marker)
        await db.commit()


@pytest.mark.asyncio
async def test_process_document_entities_links_evidence_to_real_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = uuid.uuid4().hex[:8]
    document_id = 0

    async def fake_extract(_text: str, **_kwargs) -> dict:
        return {
            "entities": [
                {
                    "name": f"Entity-{marker}",
                    "category": "test",
                    "description": f"Evidence for Entity-{marker}",
                }
            ],
            "relationships": [],
        }

    monkeypatch.setattr(entity_service, "extract_entities_from_text", fake_extract)
    await _ensure_schema()

    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=900_000_000,
            filename=f"entity-link-{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="pending",
            fusion_status="pending",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        db.add(doc)
        await db.flush()
        document_id = int(doc.id)
        chunk = KbChunk(
            document_id=document_id,
            owner_id=OWNER_ID,
            page=1,
            chunk_index=0,
            block_type="paragraph",
            text=f"Entity-{marker} appears on this page.",
            keywords=marker,
        )
        db.add(chunk)
        await db.commit()

    try:
        blocks = [{"type": "paragraph", "text": f"Entity-{marker} appears on this page.", "page": 1}]
        async with AsyncSessionLocal() as db:
            result = await entity_service.process_document_entities(db, document_id, OWNER_ID, blocks)
            assert result["entities_found"] == 1

            chunk_entity_count = await db.scalar(
                select(func.count(KbChunkEntity.id)).where(KbChunkEntity.document_id == document_id)
            )
            evidence = await db.scalar(
                select(KbEvidence).where(KbEvidence.document_id == document_id)
            )

        assert chunk_entity_count == 1
        assert evidence is not None
        assert evidence.chunk_id > 0
        assert evidence.page == 1
    finally:
        if document_id:
            await _cleanup(document_id, marker)


@pytest.mark.asyncio
async def test_get_page_fusion_is_owner_scoped() -> None:
    marker = uuid.uuid4().hex[:8]
    document_id = 0
    await _ensure_schema()
    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=900_000_001,
            filename=f"fusion-owner-{marker}.txt",
            extension="txt",
            file_size=1,
            mime_type="text/plain",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=0,
            total_pages=1,
            deleted=False,
        )
        db.add(doc)
        await db.flush()
        document_id = int(doc.id)
        db.add(KbPageFusion(
            document_id=document_id,
            owner_id=OWNER_ID,
            page=1,
            fused_text=f"fusion {marker}",
            fusion_version=1,
            fusion_status="done",
        ))
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            visible = await entity_service.get_page_fusion(db, document_id, 1, owner_id=OWNER_ID)
            hidden = await entity_service.get_page_fusion(db, document_id, 1, owner_id=OWNER_ID + 999)

        assert visible is not None
        assert visible["fused_text"] == f"fusion {marker}"
        assert hidden is None
    finally:
        if document_id:
            await _cleanup(document_id, marker)
