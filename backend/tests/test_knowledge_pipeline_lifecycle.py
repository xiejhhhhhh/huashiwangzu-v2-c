import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_STORAGE_PATH = "_knowledge_tests/lifecycle-live.txt"


@pytest.fixture(autouse=True)
def _live_upload_fixture():
    marker = REPO_ROOT / "data" / "uploads" / TEST_STORAGE_PATH
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("knowledge pipeline lifecycle source", encoding="utf-8")
    try:
        yield
    finally:
        marker.unlink(missing_ok=True)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeDocument:
    id = 7
    owner_id = 4
    file_id = 99
    deleted = False
    extension = "txt"
    total_pages = 1
    parse_status = "parsing"
    vector_status = "indexing"
    raw_status = "collecting"
    fusion_status = "running"
    profile_status = "pending"
    graph_status = "pending"
    relation_status = "pending"
    parse_error = None


class _FakeDb:
    def __init__(self, doc):
        self.doc = doc
        self.commits = 0
        self.added = []
        self._next_id = 1000

    async def scalar(self, _stmt):
        return self.doc

    async def execute(self, _stmt):
        return _ScalarResult(self.doc)

    async def get(self, model, item_id):
        for item in self.added:
            if model.__name__ == item.__class__.__name__ and getattr(item, "id", None) == item_id:
                return item
        return None

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = self._next_id
            self._next_id += 1
        self.added.append(item)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.commits += 1


class _FakeSessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


def _load_knowledge_module(module_suffix: str):
    module_names = (
        f"modules.knowledge.backend.{module_suffix}",
        f"huashiwangzu_modules.knowledge.{module_suffix}",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is not None:
            return module
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except Exception:
            continue
    raise AssertionError(f"Cannot load knowledge module {module_suffix}")


def _load_pipeline_modules():
    return (
        _load_knowledge_module("services.pipeline_service"),
        _load_knowledge_module("services.source_file_state"),
    )


@pytest.mark.asyncio
async def test_kb_pipeline_stage_skips_when_document_row_is_missing(monkeypatch) -> None:
    pipeline_service, _source_state = _load_pipeline_modules()
    db = _FakeDb(None)

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", _FakeSessionFactory(db))

    result = await pipeline_service._pipeline_stage_handler({
        "document_id": 404,
        "user_id": 4,
        "stage": "source_validate",
    })

    assert result["status"] == "skipped"
    assert result["reason"] == "doc_missing"
    assert result["classification"] == "obsolete"
    assert result["document_id"] == 404
    assert db.commits == 0


@pytest.mark.asyncio
async def test_kb_pipeline_stage_skips_when_source_file_is_deleted(monkeypatch) -> None:
    pipeline_service, source_state = _load_pipeline_modules()
    doc = _FakeDocument()
    db = _FakeDb(doc)

    async def fake_raise_if_source_unavailable(_db, _file_id):
        raise source_state.SourceFileUnavailable(99, "source_file_deleted")

    async def fake_get_source_file_availability(_db, _file_id):
        return source_state.SourceFileAvailability(False, "source_file_deleted")

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", _FakeSessionFactory(db))
    monkeypatch.setattr(
        pipeline_service,
        "raise_if_source_unavailable",
        fake_raise_if_source_unavailable,
    )
    monkeypatch.setattr(
        pipeline_service,
        "get_source_file_availability",
        fake_get_source_file_availability,
    )
    monkeypatch.setattr(pipeline_service, "record_analysis_artifact", _noop_record_analysis_artifact)
    monkeypatch.setattr(pipeline_service, "resolve_stage_prompt_hash", _noop_prompt_hash)

    result = await pipeline_service._pipeline_stage_handler({
        "document_id": doc.id,
        "user_id": doc.owner_id,
        "stage": "source_validate",
    })

    assert result["status"] == "skipped"
    assert result["reason"] == "source_file_deleted"
    assert doc.parse_error == "source_file_deleted"
    assert doc.raw_status == "pending"
    assert doc.fusion_status == "pending"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_kb_pipeline_stage_skips_when_source_file_is_missing(monkeypatch) -> None:
    pipeline_service, source_state = _load_pipeline_modules()
    doc = _FakeDocument()
    db = _FakeDb(doc)

    async def fake_raise_if_source_unavailable(_db, _file_id):
        raise source_state.SourceFileUnavailable(99, "source_file_missing")

    async def fake_get_source_file_availability(_db, _file_id):
        return source_state.SourceFileAvailability(False, "source_file_missing")

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", _FakeSessionFactory(db))
    monkeypatch.setattr(
        pipeline_service,
        "raise_if_source_unavailable",
        fake_raise_if_source_unavailable,
    )
    monkeypatch.setattr(
        pipeline_service,
        "get_source_file_availability",
        fake_get_source_file_availability,
    )
    monkeypatch.setattr(pipeline_service, "record_analysis_artifact", _noop_record_analysis_artifact)
    monkeypatch.setattr(pipeline_service, "resolve_stage_prompt_hash", _noop_prompt_hash)

    result = await pipeline_service._pipeline_stage_handler({
        "document_id": doc.id,
        "user_id": doc.owner_id,
        "stage": "source_validate",
    })

    assert result["status"] == "skipped"
    assert result["reason"] == "source_file_missing"
    assert doc.parse_error == "source_file_missing"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_kb_pipeline_stage_still_fails_when_active_source_content_is_broken(monkeypatch) -> None:
    pipeline_service, source_state = _load_pipeline_modules()
    doc = _FakeDocument()
    db = _FakeDb(doc)

    async def fake_raise_if_source_unavailable(_db, _file_id):
        return None

    async def fake_run_stage(*_args, **_kwargs):
        raise RuntimeError("File content is missing on disk")

    async def fake_get_source_file_availability(_db, _file_id):
        return source_state.SourceFileAvailability(True, "")

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", _FakeSessionFactory(db))
    monkeypatch.setattr(
        pipeline_service,
        "raise_if_source_unavailable",
        fake_raise_if_source_unavailable,
    )
    monkeypatch.setattr(pipeline_service, "_run_stage", fake_run_stage)
    monkeypatch.setattr(
        pipeline_service,
        "get_source_file_availability",
        fake_get_source_file_availability,
    )
    monkeypatch.setattr(pipeline_service, "record_analysis_artifact", _noop_record_analysis_artifact)
    monkeypatch.setattr(pipeline_service, "resolve_stage_prompt_hash", _noop_prompt_hash)

    result = await pipeline_service._pipeline_stage_handler({
        "document_id": doc.id,
        "user_id": doc.owner_id,
        "stage": "raw_text",
    })

    assert result["status"] == "failed"
    assert result["reason"] == "File content is missing on disk"


async def _noop_record_analysis_artifact(**_kwargs):
    return None


async def _noop_prompt_hash(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_enqueue_pipeline_task_dedupes_existing_inflight_task() -> None:
    document_service = _load_knowledge_module("services.document_service")
    from app.models.system import SystemTaskQueue

    existing = SystemTaskQueue(
        id=42,
        task_type="kb_pipeline_stage",
        module="knowledge",
        parameters='{"document_id": 7, "user_id": 4, "stage": "source_validate"}',
        status="running",
        creator_id=4,
    )

    class FakeDb:
        def __init__(self):
            self.added = []
            self.execute_calls = 0

        async def execute(self, _stmt, _params=None):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return _ScalarResult(None)
            return _ScalarListResult([existing])

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            raise AssertionError("flush should not run when a task is already in flight")

    db = FakeDb()
    result = await document_service.enqueue_pipeline_task(db, _FakeDocument(), 4)

    assert result == {
        "task_id": 42,
        "enqueued": False,
        "reason": "already_in_flight",
        "stage": "source_validate",
        "next_task": "kb_pipeline_stage",
    }
    assert db.added == []


def test_parser_empty_degraded_document_can_still_be_search_ready() -> None:
    document_service = _load_knowledge_module("services.document_service")
    doc = _FakeDocument()
    doc.parse_status = "degraded"
    doc.parse_error = "Parser returned no content blocks: empty_result"
    doc.vector_status = "done"
    doc.raw_status = "done"
    doc.fusion_status = "done"
    doc.profile_status = "done"
    doc.graph_status = "done"
    doc.relation_status = "done"
    doc.total_chunks = 3
    doc.total_pages = 1
    doc.catalog_id = None
    doc.filename = "scan.pdf"
    doc.extension = "pdf"
    doc.file_size = 128
    doc.mime_type = "application/pdf"
    doc.summary = None
    doc.content_package_id = None
    doc.created_at = None
    doc.updated_at = None

    payload = document_service.document_registration_payload(
        doc,
        {"task_id": None, "enqueued": False, "reason": "existing_completed"},
    )

    assert document_service.document_parse_allows_search(doc) is True
    assert payload["search_ready"] is True
    assert payload["deep_ready"] is True


@pytest.mark.asyncio
async def test_pipeline_debt_dry_run_keeps_live_file_for_retry_or_parser_investigation() -> None:
    debt_service = _load_knowledge_module("services.pipeline_debt_service")
    from app.models.system import SystemTaskQueue

    task = SystemTaskQueue(
        id=100,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 7}',
        status="failed",
        error_message="File not found",
    )
    doc = _FakeDocument()
    file_row = type("LiveFile", (), {"id": 99, "deleted": False, "storage_path": TEST_STORAGE_PATH})()

    class FakeDb:
        async def execute(self, _stmt):
            return _ScalarListResult([task])

        async def get(self, model, item_id):
            if model.__name__ == "KbDocument" and item_id == 7:
                return doc
            if model.__name__ == "File" and item_id == 99:
                return file_row
            return None

    result = await debt_service.classify_pipeline_lifecycle_debt(FakeDb())

    assert result["summary"] == {"file_row_live": 1}
    assert result["items"][0]["category"] == "file_row_live"
    assert result["items"][0]["suggested_action"] == "retry_or_parser_investigation"
    assert result["items"][0]["would_set_parse_error"] is None


@pytest.mark.asyncio
async def test_pipeline_debt_dry_run_includes_document_not_found_debt() -> None:
    debt_service = _load_knowledge_module("services.pipeline_debt_service")
    from app.models.system import SystemTaskQueue

    task = SystemTaskQueue(
        id=101,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 404}',
        status="failed",
        error_message="Document 404 not found",
    )

    class FakeDb:
        async def execute(self, _stmt):
            return _ScalarListResult([task])

        async def get(self, model, item_id):
            if model.__name__ == "KbDocument" and item_id == 404:
                return None
            raise AssertionError(f"unexpected lookup: {model.__name__} {item_id}")

    result = await debt_service.classify_pipeline_lifecycle_debt(FakeDb())

    assert result["summary"] == {"doc_missing": 1}
    assert result["items"][0]["category"] == "doc_missing"
    assert result["items"][0]["suggested_action"] == "archive_obsolete"
    assert result["items"][0]["archiveable"] is True
    assert result["items"][0]["retryable"] is False


@pytest.mark.asyncio
async def test_pipeline_debt_dry_run_classifies_parser_empty_as_quality_debt() -> None:
    debt_service = _load_knowledge_module("services.pipeline_debt_service")
    from app.models.system import SystemTaskQueue

    task = SystemTaskQueue(
        id=102,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 7}',
        status="failed",
        error_message="Parser returned no content blocks",
    )
    doc = _FakeDocument()
    file_row = type("LiveFile", (), {"id": 99, "deleted": False, "storage_path": TEST_STORAGE_PATH})()

    class FakeDb:
        async def execute(self, _stmt):
            return _ScalarListResult([task])

        async def get(self, model, item_id):
            if model.__name__ == "KbDocument" and item_id == 7:
                return doc
            if model.__name__ == "File" and item_id == 99:
                return file_row
            return None

    result = await debt_service.classify_pipeline_lifecycle_debt(FakeDb())

    assert result["summary"] == {"parser_no_content_blocks": 1}
    assert result["items"][0]["category"] == "parser_no_content_blocks"
    assert result["items"][0]["suggested_action"] == "parser_quality_investigation"
    assert result["items"][0]["archiveable"] is False
    assert result["items"][0]["retryable"] is False


@pytest.mark.asyncio
async def test_pipeline_debt_apply_archives_source_missing_as_skipped() -> None:
    debt_service = _load_knowledge_module("services.pipeline_debt_service")
    from app.models.system import SystemTaskQueue

    task = SystemTaskQueue(
        id=103,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 7}',
        status="failed",
        error_message="File not found",
    )
    doc = _FakeDocument()

    class FakeDb:
        def __init__(self):
            self.commits = 0

        async def execute(self, _stmt):
            return _ScalarListResult([task])

        async def get(self, model, item_id):
            if model.__name__ == "KbDocument" and item_id == 7:
                return doc
            if model.__name__ == "File" and item_id == 99:
                return None
            return None

        async def commit(self):
            self.commits += 1

    db = FakeDb()
    result = await debt_service.apply_pipeline_lifecycle_debt_action(
        db,
        action="archive_obsolete",
        dry_run=False,
    )

    assert result["changed"] == 1
    assert result["skipped"] == 0
    assert db.commits == 1
    assert task.status == "completed"
    assert task.error_message is None
    assert task.completed_at is not None
    assert '"status": "skipped"' in (task.result or "")
    assert '"classification": "source_file_missing"' in (task.result or "")
    assert doc.parse_error == "source_file_missing"
    assert doc.parse_status == "pending"
    assert doc.vector_status == "pending"
    assert doc.raw_status == "pending"
    assert doc.fusion_status == "pending"


@pytest.mark.asyncio
async def test_pipeline_debt_apply_retries_only_live_file_rows() -> None:
    debt_service = _load_knowledge_module("services.pipeline_debt_service")
    from app.models.system import SystemTaskQueue

    live_task = SystemTaskQueue(
        id=104,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 7}',
        status="failed",
        retry_count=3,
        error_message="File not found",
    )
    deleted_doc_task = SystemTaskQueue(
        id=105,
        task_type="kb_pipeline",
        module="knowledge",
        parameters='{"document_id": 8}',
        status="failed",
        retry_count=3,
        error_message="File not found",
    )
    live_doc = _FakeDocument()
    deleted_doc = type(
        "DeletedDocument",
        (),
        {"id": 8, "owner_id": 4, "file_id": 100, "deleted": True},
    )()
    file_row = type("LiveFile", (), {"id": 99, "deleted": False, "storage_path": TEST_STORAGE_PATH})()

    class FakeDb:
        def __init__(self):
            self.commits = 0

        async def execute(self, _stmt):
            return _ScalarListResult([live_task, deleted_doc_task])

        async def get(self, model, item_id):
            if model.__name__ == "KbDocument" and item_id == 7:
                return live_doc
            if model.__name__ == "KbDocument" and item_id == 8:
                return deleted_doc
            if model.__name__ == "File" and item_id == 99:
                return file_row
            return None

        async def commit(self):
            self.commits += 1

    db = FakeDb()
    result = await debt_service.apply_pipeline_lifecycle_debt_action(
        db,
        action="retry_live",
        dry_run=False,
    )

    assert result["changed"] == 1
    assert result["skipped"] == 1
    assert result["skipped_items"][0]["category"] == "doc_deleted"
    assert db.commits == 1
    assert live_task.status == "pending"
    assert live_task.retry_count == 0
    assert live_task.error_message is None
    assert deleted_doc_task.status == "failed"
    assert deleted_doc_task.retry_count == 3
