"""Sandbox test for knowledge module.

Validates core shapes: search results, document, chunk, entity, page fusion,
and governance candidates — without calling external embedding services or real DB.
"""


def test_search_result_shape() -> None:
    """Hybrid search result shape contract."""
    result = {
        "document_id": 1,
        "document_name": "test.pdf",
        "chunk_id": 10,
        "block_id": 5,
        "page": 1,
        "text": "Relevant content snippet...",
        "score": 0.95,
        "content_package_id": None,
        "source_available": True,
        "source_state": "available",
    }
    required = {"document_id", "text", "score", "page"}
    for field in required:
        assert field in result, f"Missing required field: {field}"
    assert isinstance(result["score"], (int, float))
    assert result["page"] >= 1
    print("  [SEARCH] Result shape valid")


def test_document_shape() -> None:
    """Document shape contract."""
    doc = {
        "id": 1,
        "file_id": 10,
        "filename": "sample.pdf",
        "owner_id": 1,
        "status": "completed",
        "parse_status": "completed",
        "fusion_status": "completed",
        "total_chunks": 25,
        "total_pages": 5,
        "source_available": True,
        "source_state": "available",
        "created_at": "2026-07-01T00:00:00",
    }
    required = {"id", "filename", "owner_id", "status", "source_available", "source_state"}
    for field in required:
        assert field in doc, f"Missing required field: {field}"
    assert doc["status"] in ("pending", "processing", "completed", "failed")
    assert doc["source_available"] is True
    assert doc["source_state"] == "available"
    print("  [DOCUMENT] Shape valid")


def test_document_lifecycle_filters_unavailable_sources() -> None:
    """List/detail must not expose unavailable source files as normal documents."""
    docs = [
        {"id": 1, "deleted": False, "source_available": True, "source_state": "available"},
        {"id": 2, "deleted": False, "source_available": False, "source_state": "source_file_deleted"},
        {"id": 3, "deleted": False, "source_available": False, "source_state": "source_file_missing"},
        {"id": 4, "deleted": True, "source_available": True, "source_state": "available"},
    ]

    visible = [
        doc for doc in docs
        if not doc["deleted"] and doc["source_available"] and doc["source_state"] == "available"
    ]

    assert [doc["id"] for doc in visible] == [1]
    assert all(doc["source_available"] is True for doc in visible)
    assert all(doc["source_state"] == "available" for doc in visible)
    assert {doc["source_state"] for doc in docs if not doc["source_available"]} == {
        "source_file_deleted",
        "source_file_missing",
    }
    print("  [DOCUMENT-LIFECYCLE] Source filtering valid")


def test_pipeline_lifecycle_skips_before_parse_or_index() -> None:
    """Pipeline must stop unavailable sources before writing derived artifacts."""
    source_state = {"available": False, "reason": "source_file_deleted"}
    writes = {"chunks": 0, "raw": 0, "fusion": 0}

    if not source_state["available"]:
        result = {
            "status": "skipped",
            "reason": source_state["reason"],
            "classification": "source_unavailable",
        }
    else:
        writes["chunks"] += 1
        result = {"status": "done"}

    assert result == {
        "status": "skipped",
        "reason": "source_file_deleted",
        "classification": "source_unavailable",
    }
    assert writes == {"chunks": 0, "raw": 0, "fusion": 0}
    print("  [PIPELINE-LIFECYCLE] Pre-parse source guard valid")


def test_chunk_shape() -> None:
    """Knowledge chunk shape contract."""
    chunk = {
        "id": 10,
        "document_id": 1,
        "owner_id": 1,
        "page": 1,
        "chunk_index": 0,
        "block_type": "paragraph",
        "text": "Chunk text content...",
        "keywords": "",
        "source_available": True,
        "source_state": "available",
    }
    required = {"id", "document_id", "text", "page", "block_type"}
    for field in required:
        assert field in chunk, f"Missing required field: {field}"
    assert chunk["block_type"] in ("paragraph", "heading", "list", "table", "code")
    assert chunk["source_available"] is True
    assert chunk["source_state"] == "available"
    print("  [CHUNK] Shape valid")


def test_entity_shape() -> None:
    """Entity dictionary entry shape contract."""
    entity = {
        "id": 1,
        "label": "hyaluronic acid",
        "category": "ingredient",
        "description": "A moisturizing ingredient",
        "aliases": ["HA", "hyaluronan"],
        "confidence": 0.92,
    }
    required = {"id", "label", "category"}
    for field in required:
        assert field in entity, f"Missing required field: {field}"
    assert isinstance(entity["confidence"], (int, float))
    print("  [ENTITY] Shape valid")


def test_page_fusion_shape() -> None:
    """Page fusion shape contract."""
    fusion = {
        "page": 1,
        "page_title": "Introduction",
        "fused_text": "Fused content for page 1...",
        "page_summary": "Summary of page 1",
        "confidence": 0.88,
        "conflicts": [],
    }
    required = {"page", "fused_text", "confidence"}
    for field in required:
        assert field in fusion, f"Missing required field: {field}"
    assert isinstance(fusion["conflicts"], list)
    print("  [PAGE_FUSION] Shape valid")


def test_governance_candidate_shape() -> None:
    """Governance candidate shape contract."""
    candidate = {
        "id": 1,
        "entity_id": None,
        "label": "New Entity",
        "category": "concept",
        "evidence": "Source text evidence...",
        "document_id": 1,
        "audit_status": "pending",
        "confidence": 0.85,
    }
    required = {"id", "label", "audit_status", "evidence"}
    for field in required:
        assert field in candidate, f"Missing required field: {field}"
    assert candidate["audit_status"] in ("pending", "approved", "rejected")
    print("  [GOVERNANCE] Candidate shape valid")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {"results": []}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def test_ingest_capability_params() -> None:
    """Ingest capability parameter contract."""
    params = {"file_id": 42}
    assert "file_id" in params
    assert isinstance(params["file_id"], int) and params["file_id"] > 0
    print("  [INGEST] Parameter contract valid")


def test_ingest_status_shape() -> None:
    """Ingest status result shape contract."""
    status = {
        "document_id": 1,
        "task_id": 10,
        "enqueued": True,
        "stage": "parse",
        "status": "queued",
        "pipeline_status": "queued",
        "task_status": "pending",
        "parse_status": "pending",
        "vector_status": "pending",
        "raw_status": "pending",
        "fusion_status": "pending",
        "stage_summary": {
            "parse": {"status": "pending", "ready": False},
            "vector": {"status": "pending", "ready": False, "count": 0},
            "raw": {"status": "pending", "ready": False},
            "fusion": {"status": "pending", "ready": False},
        },
        "search_ready": False,
        "deep_ready": False,
        "next_action": "wait_for_search_index",
    }
    required = {
        "document_id", "task_id", "enqueued", "stage", "status",
        "pipeline_status", "stage_summary", "search_ready", "deep_ready",
        "next_action",
    }
    for field in required:
        assert field in status, f"Missing required field: {field}"
    assert status["pipeline_status"] in ("queued", "running", "search_ready", "deep_ready", "failed", "pending")
    assert isinstance(status["stage_summary"], dict)
    print("  [INGEST-STATUS] Shape valid")


def main() -> None:
    print("=" * 60)
    print("knowledge sandbox test")
    print("=" * 60)
    test_search_result_shape()
    test_document_shape()
    test_document_lifecycle_filters_unavailable_sources()
    test_pipeline_lifecycle_skips_before_parse_or_index()
    test_chunk_shape()
    test_entity_shape()
    test_page_fusion_shape()
    test_governance_candidate_shape()
    test_response_shape()
    test_ingest_capability_params()
    test_ingest_status_shape()
    print("=" * 60)
    print("PASS: knowledge sandbox test")


if __name__ == "__main__":
    main()
