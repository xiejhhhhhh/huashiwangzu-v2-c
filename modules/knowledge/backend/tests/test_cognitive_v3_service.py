"""Tests for Knowledge V3 cognitive substrate helpers."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-cognitive-v3")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.database import AsyncSessionLocal

from modules.knowledge.backend.init_db import ensure_kb_indexes, ensure_kb_tables, ensure_migration_columns
from modules.knowledge.backend.models import (
    KbAnalysisArtifact,
    KbArtifactLineage,
    KbCausalCandidate,
    KbConclusionEvidence,
    KbContentObject,
    KbDisambiguation,
    KbDocument,
    KbDocumentProfile,
    KbEntityAlias,
    KbEntityDictionary,
    KbEvidence,
    KbFactCandidate,
    KbFileKnowledgeLink,
    KbPageFusion,
    KbQueryContext,
    KbRetrievalLearningEvent,
    KbTermOccurrence,
)
from modules.knowledge.backend.services.cognitive_v3_service import (
    backfill_cognitive_v3,
    build_query_context_payload,
    derive_document_cognitive_index,
    extract_terms,
    link_payload,
    persist_query_context,
    term_hash_parts,
    upsert_file_knowledge_link,
)
from modules.knowledge.backend.services.derived_governance_service import (
    backfill_derived_governance,
    derived_governance_counts,
)
from modules.knowledge.backend.services.retrieval_learning_service import (
    get_learning_priors_for_documents,
    record_retrieval_learning_events,
)

OWNER_ID = 910_000_300


async def _ensure_schema() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.commit()
        await ensure_kb_tables(db)
        await ensure_migration_columns(db)
        await ensure_kb_indexes(db)
        await _cleanup_owner(db)


async def _cleanup_owner(db) -> None:
    for table in (
        "kb_disambiguation",
        "kb_entity_aliases",
        "kb_entity_dictionary",
        "kb_conclusion_evidence",
        "kb_evidence",
        "kb_artifact_lineage",
        "kb_analysis_artifacts",
        "kb_retrieval_learning_events",
        "kb_query_contexts",
        "kb_causal_candidates",
        "kb_fact_candidates",
        "kb_term_occurrences",
        "kb_term_edges",
        "kb_terms",
        "kb_file_knowledge_links",
        "kb_content_objects",
        "kb_validation_reports",
        "kb_ingest_batches",
        "kb_page_fusions",
        "kb_document_profiles",
        "kb_documents",
    ):
        await db.execute(text(f"DELETE FROM {table} WHERE owner_id = :owner_id"), {"owner_id": OWNER_ID})
    await db.commit()


def test_term_extraction_and_hash_are_stable() -> None:
    terms = extract_terms("苏蜜雅 菁纯精华水 GF03632025102615 MESOULYER 苏蜜雅")
    assert "苏蜜雅" in terms
    assert "MESOULYER" in terms

    first = term_hash_parts("苏蜜雅")
    second = term_hash_parts(" 苏 蜜 雅 ")
    assert first["normalized"] == second["normalized"]
    assert first["exact_hash"] == second["exact_hash"]
    assert first["language"] == "zh"


def test_query_context_payload_keeps_evidence_refs() -> None:
    diagnostics = {
        "schema_version": "kb_retrieval_diagnostics_v1",
        "total_duration_ms": 42.0,
        "stages": [
            {"name": "query_plan", "status": "done", "duration_ms": 3.0},
            {"name": "vector_search", "status": "skipped", "duration_ms": 0.0, "reason": "fast_local_plan"},
        ],
        "model_nodes": [
            {
                "name": "embedding",
                "used": False,
                "status": "skipped",
                "warm_state": "not_used",
                "basis": "not_called",
            }
        ],
    }
    payload = build_query_context_payload(
        "精华水 备案报告",
        [
            {"document_id": 1, "chunk_id": 10, "page": 1, "text": "备案报告正文", "score": 0.9},
            {
                "document_id": 2,
                "chunk_id": 11,
                "page": 2,
                "text": "精华水说明",
                "score": 0.8,
                "document_candidate": {"filename": "精华水检测报告.pdf", "extension": "pdf"},
            },
        ],
        diagnostics=diagnostics,
    )

    assert payload["result_document_ids"] == [1, 2]
    assert payload["evidence_refs"][0]["chunk_id"] == 10
    assert payload["facts"][0]["text"] == "备案报告正文"
    assert payload["diagnostics"]["schema_version"] == "kb_query_context_v1"
    snapshots = payload["diagnostics"]["candidate_snapshots"]
    assert snapshots[1]["filename"] == "精华水检测报告.pdf"
    assert snapshots[1]["text"] == "精华水说明"
    assert payload["diagnostics"]["retrieval_diagnostics"] == diagnostics
    assert any(node["node_type"] == "retrieval_stage" for node in payload["diagnostics"]["nodes"])
    assert any(node["node_type"] == "model_residency" for node in payload["diagnostics"]["nodes"])


@pytest.mark.asyncio
async def test_file_knowledge_link_marks_duplicate_reuse() -> None:
    await _ensure_schema()
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=910_000_301,
            filename=f"cognitive-v3-{marker}.pdf",
            extension="pdf",
            file_size=100,
            mime_type="application/pdf",
            parse_status="done",
            vector_status="done",
            raw_status="done",
            fusion_status="done",
            total_chunks=1,
            total_pages=1,
            deleted=False,
        )
        db.add(doc)
        await db.flush()
        duplicate_file = SimpleNamespace(
            id=910_000_302,
            name=f"cognitive-v3-copy-{marker}",
            extension="pdf",
            folder_id=123,
            storage_path=f"test/{marker}/copy.pdf",
            md5_hash=f"{marker:0<32}"[:32],
            size=100,
            mime_type="application/pdf",
        )
        link = await upsert_file_knowledge_link(
            db,
            owner_id=OWNER_ID,
            file=duplicate_file,
            document=doc,
            link_role="duplicate",
            reuse_reason="md5_duplicate",
        )
        await db.commit()

        payload = link_payload(link)
        content_count = await db.scalar(
            select(func.count(KbContentObject.id)).where(KbContentObject.owner_id == OWNER_ID)
        )
        link_count = await db.scalar(
            select(func.count(KbFileKnowledgeLink.id)).where(KbFileKnowledgeLink.owner_id == OWNER_ID)
        )

    assert payload is not None
    assert payload["link_role"] == "duplicate"
    assert payload["canonical_document_id"] == int(doc.id)
    assert content_count == 1
    assert link_count == 1


@pytest.mark.asyncio
async def test_derive_document_cognitive_index_is_rerunnable() -> None:
    await _ensure_schema()
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=910_000_303,
            filename=f"cognitive-v3-{marker}.txt",
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
        db.add(doc)
        await db.flush()
        document_id = int(doc.id)
        db.add(KbPageFusion(
            owner_id=OWNER_ID,
            document_id=document_id,
            page=1,
            page_title=f"苏蜜雅测试页 {marker}",
            page_summary="因为配方升级所以需要更新备案说明。",
            fused_text="苏蜜雅精华水包含测试成分，备案报告用于合规备查。",
            tags_json=["备案报告", "精华水"],
        ))
        db.add(KbDocumentProfile(
            owner_id=OWNER_ID,
            document_id=document_id,
            subject="苏蜜雅精华水备案资料",
            doc_type="备案报告",
            core_conclusions="该资料用于合规备查。",
            doc_summary="苏蜜雅精华水相关备案说明。",
            searchable_phrases=["苏蜜雅精华水", "备案报告"],
            key_entities=[{"name": "苏蜜雅", "type": "品牌"}],
            confidence=0.8,
        ))
        await db.commit()

        first = await derive_document_cognitive_index(db, owner_id=OWNER_ID, document_id=document_id, limit=40)
        await db.commit()
        first_occurrences = await db.scalar(
            select(func.count(KbTermOccurrence.id)).where(KbTermOccurrence.document_id == document_id)
        )
        second = await derive_document_cognitive_index(db, owner_id=OWNER_ID, document_id=document_id, limit=40)
        await db.commit()
        second_occurrences = await db.scalar(
            select(func.count(KbTermOccurrence.id)).where(KbTermOccurrence.document_id == document_id)
        )
        fact_count = await db.scalar(
            select(func.count(KbFactCandidate.id)).where(KbFactCandidate.document_id == document_id)
        )
        causal_count = await db.scalar(
            select(func.count(KbCausalCandidate.id)).where(KbCausalCandidate.document_id == document_id)
        )

    assert first["terms"] > 0
    assert second["terms"] > 0
    assert first_occurrences == second_occurrences
    assert fact_count and fact_count >= 1
    assert causal_count and causal_count >= 1


@pytest.mark.asyncio
async def test_persist_query_context_records_enrichment() -> None:
    await _ensure_schema()
    async with AsyncSessionLocal() as db:
        payload = await persist_query_context(
            db,
            owner_id=OWNER_ID,
            query="苏蜜雅 精华水",
            results=[{"document_id": 1, "chunk_id": 2, "page": 1, "text": "苏蜜雅精华水", "score": 0.9}],
            diagnostics={
                "schema_version": "kb_retrieval_diagnostics_v1",
                "model_nodes": [{"name": "embedding", "used": False, "warm_state": "not_used"}],
                "stages": [{"name": "vector_search", "status": "skipped", "reason": "fast_local_plan"}],
            },
        )
        await db.commit()
        row_count = await db.scalar(
            select(func.count(KbQueryContext.id)).where(KbQueryContext.owner_id == OWNER_ID)
        )
        row = await db.scalar(select(KbQueryContext).where(KbQueryContext.owner_id == OWNER_ID))

    assert payload["query_context_id"] > 0
    assert payload["result_document_ids"] == [1]
    assert row_count == 1
    assert row is not None
    assert row.diagnostics_json["retrieval_diagnostics"]["schema_version"] == "kb_retrieval_diagnostics_v1"


@pytest.mark.asyncio
async def test_retrieval_learning_events_feed_document_priors() -> None:
    await _ensure_schema()
    async with AsyncSessionLocal() as db:
        payload = await persist_query_context(
            db,
            owner_id=OWNER_ID,
            query="苏蜜雅 检测报告",
            results=[
                {"document_id": 101, "chunk_id": 201, "page": 1, "text": "苏蜜雅检测报告", "score": 0.9},
                {"document_id": 102, "chunk_id": 202, "page": 1, "text": "苏蜜雅宣传图", "score": 0.7},
            ],
            query_plan={
                "query": "苏蜜雅 检测报告",
                "terms": ["苏蜜雅", "检测报告"],
                "entities": ["苏蜜雅"],
                "document_types": ["检测报告"],
                "constraints": [],
            },
        )
        first = await record_retrieval_learning_events(
            db,
            owner_id=OWNER_ID,
            query_context_id=payload["query_context_id"],
            query="苏蜜雅 检测报告",
            events=[
                {
                    "document_id": 101,
                    "chunk_id": 201,
                    "signal_type": "helpful",
                    "signal_score": 0.9,
                    "confidence": 0.8,
                    "reason": "用户继续沿用该检测报告名单",
                    "evidence": {"excerpt": "这个名单可以"},
                },
                {
                    "document_id": 102,
                    "chunk_id": 202,
                    "signal_type": "wrong_result",
                    "signal_score": -0.6,
                    "confidence": 0.7,
                    "reason": "用户要求不要混入宣传图",
                    "evidence": {"excerpt": "不是宣传图"},
                },
            ],
        )
        second = await record_retrieval_learning_events(
            db,
            owner_id=OWNER_ID,
            query_context_id=payload["query_context_id"],
            query="苏蜜雅 检测报告",
            events=[
                {
                    "document_id": 101,
                    "chunk_id": 201,
                    "signal_type": "helpful",
                    "signal_score": 0.9,
                    "confidence": 0.8,
                    "reason": "用户继续沿用该检测报告名单",
                    "evidence": {"excerpt": "这个名单可以"},
                },
            ],
        )
        priors = await get_learning_priors_for_documents(
            db,
            owner_id=OWNER_ID,
            query_plan={"query": "苏蜜雅 检测报告", "terms": ["苏蜜雅", "检测报告"]},
            document_ids=[101, 102],
        )
        event_count = await db.scalar(
            select(func.count(KbRetrievalLearningEvent.id)).where(
                KbRetrievalLearningEvent.owner_id == OWNER_ID
            )
        )

    assert first["inserted"] == 2
    assert second["updated"] == 1
    assert event_count == 2
    assert priors[101]["prior"] > 0
    assert priors[102]["prior"] < 0


@pytest.mark.asyncio
async def test_backfill_cognitive_v3_dry_run_does_not_mutate() -> None:
    await _ensure_schema()
    async with AsyncSessionLocal() as db:
        before_links = await db.scalar(
            select(func.count(KbFileKnowledgeLink.id)).where(KbFileKnowledgeLink.owner_id == OWNER_ID)
        )
        result = await backfill_cognitive_v3(db, owner_id=OWNER_ID, dry_run=True, limit=5)
        after_links = await db.scalar(
            select(func.count(KbFileKnowledgeLink.id)).where(KbFileKnowledgeLink.owner_id == OWNER_ID)
        )

    assert result["dry_run"] is True
    assert result["will_mutate"] is False
    assert before_links == after_links == 0


@pytest.mark.asyncio
async def test_backfill_derived_governance_is_dry_run_and_rerunnable() -> None:
    await _ensure_schema()
    marker = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        doc = KbDocument(
            owner_id=OWNER_ID,
            file_id=910_000_401,
            filename=f"derived-governance-{marker}.txt",
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
        db.add(doc)
        await db.flush()
        document_id = int(doc.id)
        db.add(KbAnalysisArtifact(
            owner_id=OWNER_ID,
            document_id=document_id,
            file_id=doc.file_id,
            stage="profile",
            unit_type="document",
            unit_key="document",
            source_artifact_ids=[],
            input_hash=f"input-{marker}",
            output_hash=f"output-{marker}",
            schema_version="test",
            status="done",
        ))
        db.add(KbFactCandidate(
            owner_id=OWNER_ID,
            document_id=document_id,
            page=1,
            claim_text="蔻诺同时覆盖清颜与博泉相关资料。",
            evidence_ids=None,
            source_type="test",
            source_hash=f"fact-{marker}",
            confidence=0.91,
        ))
        db.add(KbEvidence(
            owner_id=OWNER_ID,
            entity_id=1,
            document_id=document_id,
            chunk_id=1,
            page=1,
            excerpt="蔻诺同时覆盖清颜与博泉相关资料，可用于产品线归属确认。",
            confidence=0.88,
            status="confirmed",
        ))
        db.add(KbEntityDictionary(
            owner_id=OWNER_ID,
            name="蔻诺（KRNOBQUE/清颜）",
            category="品牌",
            status="confirmed",
            source="test",
        ))
        db.add(KbEntityDictionary(
            owner_id=OWNER_ID,
            name="清颜",
            category="品牌",
            status="confirmed",
            source="test",
        ))
        await db.commit()

        dry_run = await backfill_derived_governance(db, owner_id=OWNER_ID, dry_run=True, limit=20)
        counts_after_dry_run = await derived_governance_counts(db, owner_id=OWNER_ID)
        applied = await backfill_derived_governance(db, owner_id=OWNER_ID, dry_run=False, limit=20)
        counts_after_apply = await derived_governance_counts(db, owner_id=OWNER_ID)
        second = await backfill_derived_governance(db, owner_id=OWNER_ID, dry_run=False, limit=20)
        counts_after_second = await derived_governance_counts(db, owner_id=OWNER_ID)
        alias_rows = (
            await db.execute(select(KbEntityAlias.alias).where(KbEntityAlias.owner_id == OWNER_ID))
        ).scalars().all()
        disambiguation = await db.scalar(
            select(KbDisambiguation).where(KbDisambiguation.owner_id == OWNER_ID)
        )
        lineage_count = await db.scalar(
            select(func.count(KbArtifactLineage.id)).where(KbArtifactLineage.owner_id == OWNER_ID)
        )
        conclusion_count = await db.scalar(
            select(func.count(KbConclusionEvidence.id)).where(KbConclusionEvidence.owner_id == OWNER_ID)
        )

    assert dry_run["dry_run"] is True
    assert dry_run["will_mutate"] is False
    assert dry_run["counts"]["artifact_lineage"] == 1
    assert counts_after_dry_run == {
        "artifact_lineage": 0,
        "conclusion_evidence": 0,
        "entity_aliases": 0,
        "disambiguation": 0,
    }
    assert applied["will_mutate"] is True
    assert counts_after_apply["artifact_lineage"] == 1
    assert counts_after_apply["conclusion_evidence"] == 1
    assert counts_after_apply["entity_aliases"] >= 2
    assert counts_after_apply["disambiguation"] >= 1
    assert counts_after_second == counts_after_apply
    assert second["counts"]["artifact_lineage"] == 0
    assert "KRNOBQUE" in alias_rows
    assert "清颜" in alias_rows
    assert disambiguation is not None
    assert lineage_count == 1
    assert conclusion_count == 1

    async with AsyncSessionLocal() as db:
        await _cleanup_owner(db)
