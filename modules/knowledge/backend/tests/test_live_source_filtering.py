"""Knowledge retrieval must not expose chunks from deleted or unavailable sources."""
# ruff: noqa: E402, I001

from __future__ import annotations

import sys
import uuid
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-live-source-filtering")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal, engine, init_db
from app.core.exceptions import NotFound
from app.models.file import File
from modules.knowledge.backend.init_db import ensure_kb_indexes, ensure_kb_tables, ensure_migration_columns
from modules.knowledge.backend.models import KbChunk, KbDocument, KbPageFusion, KbRawData
from modules.knowledge.backend.services import document_service, pipeline_service
from modules.knowledge.backend.services import search_service
from modules.knowledge.backend.services.embedding_service import get_chunk_by_id
from modules.knowledge.backend.services.search_service import (
    get_document_chunks,
    hybrid_search,
    keyword_search,
    rrf_fusion,
    vector_search,
)

OWNER_ID = 1
VECTOR_SIZE = 1024
_FRAMEWORK_READY = False


def test_rrf_fusion_prioritizes_document_candidates_for_list_queries() -> None:
    query_plan = {
        "intent": "document_inventory",
        "need_document_level_results": True,
        "answer_shape": "list",
        "terms": ["Acme", "Report"],
        "entities": ["Acme"],
        "document_types": ["Report"],
        "constraints": [],
        "source": "test",
    }
    document_results = [
        {
            "chunk_id": None,
            "document_id": 101,
            "text": "Acme Safety Report\nDocument profile",
            "score": 18.0,
            "rank": 1,
            "source": "document_profile",
        }
    ]
    vector_results = [
        {
            "chunk_id": 9001,
            "document_id": 202,
            "text": "Acme customer survey",
            "score": 0.99,
            "rank": 1,
            "source": "vector",
        }
    ]

    results = rrf_fusion(
        [],
        vector_results,
        top_k=2,
        document_results=document_results,
        dedupe_by_document=True,
        query_plan=query_plan,
    )

    assert results[0]["document_id"] == 101
    assert results[0]["source"] == "document_profile"
    assert results[1]["document_id"] == 202
    assert results[1]["query_plan_matched"] is False


@pytest.mark.asyncio
async def test_brand_product_query_uses_local_fast_plan() -> None:
    plan = await search_service.plan_query("娇薇诗有什么产品")

    assert plan["source"] == "local_fast_product_query"
    assert plan["intent"] == "brand_product_lookup"
    assert plan["answer_shape"] == "list"
    assert plan["need_document_level_results"] is False
    assert plan["entities"] == ["娇薇诗"]
    assert "产品" not in plan["terms"]


@pytest.mark.asyncio
async def test_existence_query_uses_local_fast_plan() -> None:
    plan = await search_service.plan_query(
        "蔻诺，不是有轻颜和博泉吗？两个的。然后资料里面现在没有俏小喵对吧？",
    )

    assert plan["source"] == "local_fast_existence_query"
    assert plan["intent"] == "local_existence_lookup"
    assert plan["answer_shape"] == "qa"
    assert {"蔻诺", "轻颜", "博泉", "俏小喵"}.issubset(set(plan["terms"]))
    assert not any("，" in term for term in plan["terms"])


@pytest.mark.asyncio
async def test_fast_brand_product_query_skips_heavy_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    async def fail_document_candidate(*_args, **_kwargs):
        raise AssertionError("fast product lookup must not run document_candidate_search")

    async def fail_structured_signal(*_args, **_kwargs):
        raise AssertionError("fast product lookup must not run structured_signal_search")

    async def fake_keyword(_db, query: str, _owner_id: int, top_k: int = 20):
        calls["keyword_query"] = query
        calls["keyword_top_k"] = top_k
        return []

    async def fail_vector(*_args, **_kwargs):
        raise AssertionError("fast product lookup must not run vector_search")

    monkeypatch.setattr(search_service, "document_candidate_search", fail_document_candidate)
    monkeypatch.setattr(search_service, "structured_signal_search", fail_structured_signal)
    monkeypatch.setattr(search_service, "keyword_search", fake_keyword)
    monkeypatch.setattr(search_service, "vector_search", fail_vector)

    results = await hybrid_search(object(), "娇薇诗有什么产品", OWNER_ID, top_k=10)

    assert results == []
    assert calls["keyword_query"] == "娇薇诗 娇薇"
    assert calls["keyword_top_k"] == 20


@pytest.mark.asyncio
async def test_fast_existence_query_skips_heavy_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    async def fail_document_candidate(*_args, **_kwargs):
        raise AssertionError("fast existence lookup must not run document_candidate_search")

    async def fail_structured_signal(*_args, **_kwargs):
        raise AssertionError("fast existence lookup must not run structured_signal_search")

    async def fake_keyword(_db, query: str, _owner_id: int, top_k: int = 20):
        calls["keyword_query"] = query
        calls["keyword_top_k"] = top_k
        return []

    async def fail_vector(*_args, **_kwargs):
        raise AssertionError("fast existence lookup must not run vector_search")

    monkeypatch.setattr(search_service, "document_candidate_search", fail_document_candidate)
    monkeypatch.setattr(search_service, "structured_signal_search", fail_structured_signal)
    monkeypatch.setattr(search_service, "keyword_search", fake_keyword)
    monkeypatch.setattr(search_service, "vector_search", fail_vector)

    results = await hybrid_search(object(), "资料里面现在没有俏小喵对吧", OWNER_ID, top_k=10)

    assert results == []
    assert calls["keyword_query"] == "俏小喵"
    assert calls["keyword_top_k"] == 20


def _upload_path(storage_path: str) -> Path:
    return REPO_ROOT / "data" / "uploads" / storage_path


def _write_upload_file(storage_path: str, content: str) -> None:
    path = _upload_path(storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def _ensure_framework_ready() -> None:
    global _FRAMEWORK_READY
    if _FRAMEWORK_READY:
        return
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await init_db()
    async with AsyncSessionLocal() as db:
        await ensure_kb_tables(db)
        await ensure_migration_columns(db)
        await ensure_kb_indexes(db)
    _FRAMEWORK_READY = True


async def _cleanup(doc_ids: list[int], file_ids: list[int]) -> None:
    async with AsyncSessionLocal() as db:
        for doc_id in doc_ids:
            await db.execute(text("DELETE FROM kb_pipeline_stage_runs WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_pipeline_runs WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_raw_data WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_page_fusions WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})
            await db.execute(text("DELETE FROM kb_documents WHERE id = :doc_id"), {"doc_id": doc_id})
        for file_id in file_ids:
            await db.execute(text("DELETE FROM framework_file_items WHERE id = :file_id"), {"file_id": file_id})
        await db.commit()
    for path in (REPO_ROOT / "data" / "uploads" / "tests").glob("k3_*"):
        path.unlink(missing_ok=True)


async def _create_case(marker: str) -> tuple[dict[str, int], dict[str, int]]:
    await _ensure_framework_ready()
    vector = [1.0] + [0.0] * (VECTOR_SIZE - 1)
    live_storage_path = f"tests/k3_live_{marker}.txt"
    deleted_storage_path = f"tests/k3_deleted_source_{marker}.txt"
    _write_upload_file(live_storage_path, f"live source {marker}")
    _write_upload_file(deleted_storage_path, f"deleted source {marker}")
    async with AsyncSessionLocal() as db:
        live_file = File(
            name=f"k3_live_{marker}",
            extension="txt",
            size=1,
            owner_id=OWNER_ID,
            storage_path=live_storage_path,
            mime_type="text/plain",
            deleted=False,
        )
        deleted_file = File(
            name=f"k3_deleted_source_{marker}",
            extension="txt",
            size=1,
            owner_id=OWNER_ID,
            storage_path=deleted_storage_path,
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

        async def fake_query_plan(query: str) -> dict:
            return {
                "intent": "test_search",
                "need_document_level_results": False,
                "answer_shape": "mixed",
                "terms": [query],
                "entities": [],
                "document_types": [],
                "constraints": [],
                "source": "test",
            }

        monkeypatch.setattr(search_service, "get_embedding", fake_embedding)
        monkeypatch.setattr(search_service, "plan_query", fake_query_plan)
        async with AsyncSessionLocal() as db:
            keyword_results = await keyword_search(db, marker, OWNER_ID, top_k=10)
            vector_results = await vector_search(db, marker, OWNER_ID, top_k=10)
            hybrid_results = await hybrid_search(db, marker, OWNER_ID, top_k=10)

        assert [item["document_id"] for item in keyword_results] == [docs["live"]]
        hybrid_doc_ids = {item["document_id"] for item in hybrid_results}
        assert docs["live"] in hybrid_doc_ids
        assert docs["deleted_doc"] not in hybrid_doc_ids
        assert docs["source_deleted"] not in hybrid_doc_ids
        assert docs["source_missing"] not in hybrid_doc_ids
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
async def test_search_prefers_fusion_index_over_base_parse() -> None:
    marker = uuid.uuid4().hex[:8]
    docs, ids = await _create_case(marker)
    try:
        async with AsyncSessionLocal() as db:
            fusion_chunk = KbChunk(
                document_id=docs["live"],
                owner_id=OWNER_ID,
                page=1,
                chunk_index=1,
                block_type="fusion",
                text=f"K3 live source filtering {marker} fusion verified text",
                embedding=[1.0] + [0.0] * (VECTOR_SIZE - 1),
                keywords=f"K3 {marker} fusion",
                index_layer="fusion_verified",
                source_stage="fusion",
                source_ref_id=12345,
            )
            db.add(fusion_chunk)
            await db.commit()

            keyword_results = await keyword_search(db, marker, OWNER_ID, top_k=10)

        assert [item["document_id"] for item in keyword_results] == [docs["live"]]
        assert keyword_results[0]["index_layer"] == "fusion_verified"
        assert "fusion verified text" in keyword_results[0]["text"]
    finally:
        await _cleanup(list(docs.values()), [ids["live_file"], ids["deleted_file"]])


@pytest.mark.asyncio
async def test_document_list_and_detail_filter_unavailable_sources() -> None:
    marker = uuid.uuid4().hex[:8]
    docs, ids = await _create_case(marker)
    try:
        async with AsyncSessionLocal() as db:
            listed = await document_service.list_documents(db, OWNER_ID, keyword=marker, page=1, page_size=20)
            listed_ids = [item["id"] for item in listed["items"]]

            assert listed["total"] == 1
            assert listed_ids == [docs["live"]]
            assert listed["items"][0]["source_available"] is True
            assert listed["items"][0]["source_state"] == "available"

            live = await document_service.get_document(db, docs["live"], OWNER_ID)
            assert live["id"] == docs["live"]
            assert live["source_available"] is True
            assert live["source_state"] == "available"

            with pytest.raises(NotFound):
                await document_service.get_document(db, docs["source_deleted"], OWNER_ID)
            with pytest.raises(NotFound):
                await document_service.get_document(db, docs["source_missing"], OWNER_ID)
    finally:
        await _cleanup(list(docs.values()), [ids["live_file"], ids["deleted_file"]])


@pytest.mark.asyncio
async def test_pipeline_skips_unavailable_sources_before_parse_or_index() -> None:
    marker = uuid.uuid4().hex[:8]
    docs, ids = await _create_case(marker)
    try:
        async with AsyncSessionLocal() as db:
            deleted_doc = await db.get(KbDocument, docs["source_deleted"])
            missing_doc = await db.get(KbDocument, docs["source_missing"])
            assert deleted_doc is not None
            assert missing_doc is not None

            before = {
                key: {
                    "chunks": await db.scalar(select(func.count(KbChunk.id)).where(KbChunk.document_id == doc_id)) or 0,
                    "raw": await db.scalar(select(func.count(KbRawData.id)).where(KbRawData.document_id == doc_id)) or 0,
                    "fusion": await db.scalar(
                        select(func.count(KbPageFusion.id)).where(KbPageFusion.document_id == doc_id)
                    ) or 0,
                }
                for key, doc_id in (
                    ("source_deleted", docs["source_deleted"]),
                    ("source_missing", docs["source_missing"]),
                )
            }

            deleted_result = await pipeline_service._run_stage(
                db,
                doc=deleted_doc,
                user_id=OWNER_ID,
                stage=pipeline_service.ROOT_STAGE,
            )
            missing_result = await pipeline_service._run_stage(
                db,
                doc=missing_doc,
                user_id=OWNER_ID,
                stage=pipeline_service.ROOT_STAGE,
            )

            assert deleted_result["status"] == "skipped"
            assert deleted_result["reason"] == "source_file_deleted"
            assert missing_result["status"] == "skipped"
            assert missing_result["reason"] == "source_file_missing"

            await db.refresh(deleted_doc)
            await db.refresh(missing_doc)
            assert deleted_doc.parse_error == "source_file_deleted"
            assert missing_doc.parse_error == "source_file_missing"

            after = {
                key: {
                    "chunks": await db.scalar(select(func.count(KbChunk.id)).where(KbChunk.document_id == doc_id)) or 0,
                    "raw": await db.scalar(select(func.count(KbRawData.id)).where(KbRawData.document_id == doc_id)) or 0,
                    "fusion": await db.scalar(
                        select(func.count(KbPageFusion.id)).where(KbPageFusion.document_id == doc_id)
                    ) or 0,
                }
                for key, doc_id in (
                    ("source_deleted", docs["source_deleted"]),
                    ("source_missing", docs["source_missing"]),
                )
            }
            assert after == before
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
