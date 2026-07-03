import importlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-pipeline-stage-semantics")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_service(service_name: str):
    suffix = f".{service_name}"
    for module_name, module in sys.modules.items():
        if module_name.endswith(suffix):
            return module
    return importlib.import_module(f"modules.knowledge.backend.services.{service_name}")


pipeline_orchestrator = _load_service("pipeline_orchestrator")
document_service = _load_service("document_service")
fusion_service = _load_service("fusion_service")
raw_collection_service = _load_service("raw_collection_service")
llm_diagnostics_stream = _load_service("llm_diagnostics_stream")
StageDef = pipeline_orchestrator.StageDef
classify_fusion_status = fusion_service.classify_fusion_status
classify_raw_collection_status = raw_collection_service.classify_raw_collection_status


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDocument:
    id = 123
    raw_status = "pending"
    fusion_status = "pending"
    parse_error = None
    parse_status = "done"
    vector_status = "done"
    deleted = False


class _FakeDb:
    def __init__(self):
        self.doc = _FakeDocument()
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return _ScalarResult(self.doc)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _DiagnosticDb(_FakeDb):
    def __init__(self):
        super().__init__()
        self.added = []
        self.flushes = 0
        self.rollbacks = 0
        self._next_id = 1000

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = self._next_id
            self._next_id += 1
        self.added.append(item)

    async def get(self, _model, item_id):
        for item in self.added:
            if getattr(item, "id", None) == item_id:
                return item
        return None

    async def flush(self):
        self.flushes += 1

    async def rollback(self):
        self.rollbacks += 1


class _FailingDiagnosticDb(_DiagnosticDb):
    async def flush(self):
        self.flushes += 1
        raise RuntimeError("diagnostics table unavailable")

    async def commit(self):
        self.commits += 1
        raise RuntimeError("diagnostics table unavailable")


class _SessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


class _Availability:
    def __init__(self, available: bool, reason: str = ""):
        self.available = available
        self.reason = reason


class _EmptyParseDocument:
    id = 321
    owner_id = 1
    catalog_id = None
    file_id = 654
    filename = "empty.docx"
    extension = "docx"
    file_size = 100
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    content_package_id = None
    parse_status = "pending"
    vector_status = "pending"
    raw_status = "pending"
    fusion_status = "pending"
    parse_error = None
    total_chunks = 0
    total_pages = 0
    summary = None
    created_at = None
    updated_at = None
    deleted = False


class _EmptyParseDb:
    def __init__(self):
        self.doc = _EmptyParseDocument()
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _stmt):
        return _ScalarResult(self.doc)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        assert obj is self.doc
        self.refreshes += 1


class _ParsedIr:
    parse_errors = ["empty_result"]
    parse_status = "ok"
    resource_diagnostics = []


def test_raw_collection_classifies_all_empty_as_degraded_or_failed():
    assert classify_raw_collection_status(
        total_rounds=3,
        valid_rounds=0,
        failed_rounds=0,
        task_count=3,
    ) == "degraded"
    assert classify_raw_collection_status(
        total_rounds=3,
        valid_rounds=0,
        failed_rounds=3,
        task_count=3,
    ) == "failed"


def test_raw_collection_classifies_partial_empty_as_degraded():
    assert classify_raw_collection_status(
        total_rounds=3,
        valid_rounds=1,
        failed_rounds=0,
        task_count=3,
    ) == "degraded"


def test_fusion_classifies_all_empty_and_index_failure():
    assert classify_fusion_status(total_pages=2, valid_pages=0) == "degraded"
    assert classify_fusion_status(total_pages=2, valid_pages=0, error_pages=2) == "failed"
    assert classify_fusion_status(total_pages=2, valid_pages=2, index_error="embed down") == "degraded"


@pytest.mark.asyncio
async def test_orchestrator_failed_stage_returns_failed(monkeypatch):
    async def fail_stage(**_kwargs):
        return {"status": "failed", "reason": "boom"}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [StageDef("raw", ["source_file"], False, fail_stage)],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _noop)

    main_db = _FakeDb()
    diagnostics_db = _DiagnosticDb()
    monkeypatch.setattr(pipeline_orchestrator, "AsyncSessionLocal", _SessionFactory(diagnostics_db))

    result = await pipeline_orchestrator.run_pipeline(main_db, 123, 1, 456, 1)

    run_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_pipeline_runs"
    ]
    stage_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_pipeline_stage_runs"
    ]

    assert run_rows[0].status == "failed"
    assert run_rows[0].reason == "boom"
    assert result["status"] == "failed"
    assert result["steps"]["raw"]["stage_status"] == "failed"
    assert stage_rows[-1].stage == "raw"
    assert stage_rows[-1].status == "failed"


@pytest.mark.asyncio
async def test_orchestrator_degraded_empty_required_stage_skips_downstream(monkeypatch):
    async def empty_raw(**_kwargs):
        return {
            "status": "degraded",
            "total_rounds": 1,
            "valid_rounds": 0,
            "empty_rounds": 1,
        }

    async def fusion_stage(**_kwargs):
        return {"status": "done", "valid_pages": 1, "total_pages": 1}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("raw", ["source_file"], False, empty_raw),
            StageDef("fusion", ["raw"], False, fusion_stage, requires=["raw"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _noop)

    result = await pipeline_orchestrator.run_pipeline(_FakeDb(), 123, 1, 456, 1)

    assert result["status"] == "degraded"
    assert result["steps"]["raw"]["stage_status"] == "degraded"
    assert result["steps"]["fusion"]["status"] == "skipped"
    assert result["steps"]["fusion"]["classification"] == "degraded_dependency"


@pytest.mark.asyncio
async def test_orchestrator_required_skipped_stage_degrades_pipeline(monkeypatch):
    async def skipped_raw(**_kwargs):
        return {"status": "skipped", "reason": "no usable raw"}

    async def fusion_stage(**_kwargs):
        return {"status": "done", "valid_pages": 1, "total_pages": 1}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("raw", ["source_file"], False, skipped_raw),
            StageDef("fusion", ["raw"], False, fusion_stage, requires=["raw"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _noop)

    result = await pipeline_orchestrator.run_pipeline(_FakeDb(), 123, 1, 456, 1)

    assert result["status"] == "degraded"
    assert result["steps"]["raw"]["stage_status"] == "degraded"
    assert result["steps"]["fusion"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_orchestrator_persists_stage_diagnostics(monkeypatch):
    async def partial_raw(**_kwargs):
        return {
            "status": "degraded",
            "total_rounds": 3,
            "valid_rounds": 2,
            "empty_rounds": 1,
        }

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [StageDef("raw", ["source_file"], False, partial_raw)],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)

    main_db = _FakeDb()
    diagnostics_db = _DiagnosticDb()
    monkeypatch.setattr(pipeline_orchestrator, "AsyncSessionLocal", _SessionFactory(diagnostics_db))
    result = await pipeline_orchestrator.run_pipeline(main_db, 123, 1, 456, 1)

    assert result["status"] == "degraded"
    stage_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_pipeline_stage_runs"
    ]
    assert [row.stage for row in stage_rows] == ["source_file", "raw"]
    assert stage_rows[1].status == "degraded"
    assert stage_rows[1].reason == "raw_content_partial"
    assert stage_rows[1].metrics_json["valid_rounds"] == 2


@pytest.mark.asyncio
async def test_orchestrator_persists_queue_task_id_on_pipeline_run(monkeypatch):
    async def done_raw(**_kwargs):
        return {
            "status": "done",
            "total_rounds": 1,
            "valid_rounds": 1,
            "empty_rounds": 0,
        }

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [StageDef("raw", ["source_file"], False, done_raw)],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)

    diagnostics_db = _DiagnosticDb()
    monkeypatch.setattr(pipeline_orchestrator, "AsyncSessionLocal", _SessionFactory(diagnostics_db))

    result = await pipeline_orchestrator.run_pipeline(_FakeDb(), 123, 1, 456, 1, task_id=777)

    run_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_pipeline_runs"
    ]
    assert result["status"] == "done"
    assert run_rows[0].task_id == 777


@pytest.mark.asyncio
async def test_orchestrator_diagnostic_failure_rolls_back_and_does_not_break_pipeline(monkeypatch):
    async def done_raw(**_kwargs):
        return {
            "status": "done",
            "total_rounds": 1,
            "valid_rounds": 1,
            "empty_rounds": 0,
        }

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [StageDef("raw", ["source_file"], False, done_raw)],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)

    main_db = _FakeDb()
    diagnostics_db = _FailingDiagnosticDb()
    monkeypatch.setattr(pipeline_orchestrator, "AsyncSessionLocal", _SessionFactory(diagnostics_db))

    result = await pipeline_orchestrator.run_pipeline(main_db, 123, 1, 456, 1)

    assert result["status"] == "done"
    assert main_db.commits >= 1
    assert main_db.rollbacks == 0
    assert diagnostics_db.rollbacks >= 1


@pytest.mark.asyncio
async def test_orchestrator_stops_when_source_is_deleted_after_stage(monkeypatch):
    calls = {"source": 0, "fusion": 0}

    async def source_flips_after_raw(*_args, **_kwargs):
        calls["source"] += 1
        if calls["source"] >= 3:
            return _Availability(False, "source_file_deleted")
        return _Availability(True)

    async def done_raw(**_kwargs):
        return {
            "status": "done",
            "total_rounds": 1,
            "valid_rounds": 1,
            "empty_rounds": 0,
        }

    async def fusion_stage(**_kwargs):
        calls["fusion"] += 1
        return {"status": "done", "valid_pages": 1, "total_pages": 1}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("raw", ["source_file"], False, done_raw),
            StageDef("fusion", ["raw"], False, fusion_stage, requires=["raw"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)
    monkeypatch.setattr(pipeline_orchestrator, "get_source_file_availability", source_flips_after_raw)

    db = _FakeDb()
    result = await pipeline_orchestrator.run_pipeline(db, 123, 1, 456, 1)

    assert result["status"] == "skipped"
    assert result["reason"] == "source_file_deleted"
    assert result["steps"]["raw"]["classification"] == "source_unavailable"
    assert result["steps"]["raw"]["metrics"]["valid_rounds"] == 1
    assert db.doc.parse_error == "source_file_deleted"
    assert calls["fusion"] == 0


@pytest.mark.asyncio
async def test_parse_empty_degraded_branch_refreshes_before_payload(monkeypatch):
    async def empty_parse_document(*_args, **_kwargs):
        return _ParsedIr()

    monkeypatch.setattr(document_service, "parse_document", empty_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {"blocks": []})

    db = _EmptyParseDb()
    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
    )

    assert result["status"] == "degraded"
    assert result["parsed_blocks"] == 0
    assert result["document"]["parse_status"] == "degraded"
    assert result["document"]["parse_error"] == "Parser returned no content blocks: empty_result"
    assert db.refreshes == 1


@pytest.mark.asyncio
async def test_stream_llm_failure_without_fallback_raises():
    async def failing_stream(**_kwargs):
        yield {"type": "error", "content": "gateway unavailable"}

    with pytest.raises(RuntimeError, match="gateway unavailable"):
        await llm_diagnostics_stream.timed_llm_chat_stream(
            logger=llm_diagnostics_stream.logging.getLogger("test"),
            stage="fusion",
            profile_key="test-model",
            messages=[{"role": "user", "content": "hello"}],
            chat_stream_func=failing_stream,
        )


async def _always_stale(*_args, **_kwargs):
    return ["raw", "fusion"]


async def _noop(*_args, **_kwargs):
    return None


async def _hash_stage(*_args, **_kwargs):
    return "hash"
