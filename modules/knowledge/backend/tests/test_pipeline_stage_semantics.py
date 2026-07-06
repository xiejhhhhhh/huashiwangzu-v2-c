import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
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
analysis_artifact_service = _load_service("analysis_artifact_service")
document_service = _load_service("document_service")
fusion_service = _load_service("fusion_service")
raw_collection_service = _load_service("raw_collection_service")
llm_diagnostics_stream = _load_service("llm_diagnostics_stream")
StageDef = pipeline_orchestrator.StageDef
classify_fusion_status = fusion_service.classify_fusion_status
classify_raw_collection_status = raw_collection_service.classify_raw_collection_status
completed_raw_pages = raw_collection_service.completed_raw_pages
summarize_raw_content_quality = raw_collection_service.summarize_raw_content_quality


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarList:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarList(self._values)


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


class _LazyTrapDocument(_EmptyParseDocument):
    def __init__(self):
        self._expired = False

    def __getattribute__(self, name):
        if name in {"file_id", "extension", "content_package_id"}:
            if object.__getattribute__(self, "_expired"):
                raise AssertionError(f"lazy access after commit: {name}")
        return super().__getattribute__(name)


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
        if hasattr(obj, "_expired"):
            obj._expired = False


class _SnapshotParseDb(_EmptyParseDb):
    def __init__(self):
        super().__init__()
        self.doc = _LazyTrapDocument()

    async def commit(self):
        self.commits += 1
        self.doc._expired = True


class _StaleParseDocument(_EmptyParseDocument):
    id = 987
    file_id = 654
    filename = "stale.txt"
    extension = "txt"
    parse_status = "parsing"
    vector_status = "indexing"
    parse_worker_id = "user:1"
    parse_started_at = datetime.now(timezone.utc) - timedelta(hours=2)


class _StaleParseDb(_EmptyParseDb):
    def __init__(self):
        super().__init__()
        self.doc = _StaleParseDocument()
        self.executes = 0

    async def execute(self, _stmt):
        self.executes += 1
        if self.executes == 1:
            return _ScalarResult(self.doc)
        if self.executes == 2:
            return _ListResult([])
        return _ScalarResult(None)


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


def test_raw_collection_classifies_page_covered_empty_rounds_as_done():
    assert classify_raw_collection_status(
        total_rounds=18,
        valid_rounds=16,
        failed_rounds=0,
        task_count=18,
        total_pages=6,
        valid_pages=6,
    ) == "done"


def test_raw_collection_classifies_missing_page_as_degraded():
    assert classify_raw_collection_status(
        total_rounds=18,
        valid_rounds=15,
        failed_rounds=0,
        task_count=18,
        total_pages=6,
        valid_pages=5,
    ) == "degraded"


def test_raw_quality_treats_empty_visual_ocr_as_optional():
    rows = [
        (1, 1, "text", "local image description", "done", 120, {}),
        (1, 2, "ocr", "", "degraded", 35, {"method": "tesseract_boxes", "words": []}),
        (1, 3, "vision", "poster layout and text", "done", 18000, {}),
    ]

    quality = summarize_raw_content_quality(
        rows,
        total_pages=1,
        expected_rounds=3,
        visual_document=True,
    )

    assert quality["valid_rounds"] == 2
    assert quality["empty_rounds"] == 1
    assert quality["optional_empty_rounds"] == 1
    assert quality["primary_valid_pages"] == 1
    assert quality["primary_empty_pages"] == 0
    assert classify_raw_collection_status(
        total_rounds=quality["total_rounds"],
        valid_rounds=quality["valid_rounds"],
        failed_rounds=0,
        task_count=3,
        total_pages=1,
        valid_pages=quality["valid_pages"],
        primary_valid_pages=quality["primary_valid_pages"],
    ) == "done"


def test_raw_quality_degrades_when_visual_page_lacks_primary_content():
    rows = [
        (1, 1, "text", "", "degraded", 120, {}),
        (1, 2, "ocr", "only ocr text", "done", 35, {"method": "tesseract_boxes"}),
        (1, 3, "vision", "", "degraded", 18000, {}),
    ]

    quality = summarize_raw_content_quality(
        rows,
        total_pages=1,
        expected_rounds=3,
        visual_document=True,
    )

    assert quality["valid_rounds"] == 1
    assert quality["primary_empty_pages"] == 1
    assert classify_raw_collection_status(
        total_rounds=quality["total_rounds"],
        valid_rounds=quality["valid_rounds"],
        failed_rounds=0,
        task_count=3,
        total_pages=1,
        valid_pages=quality["valid_pages"],
        primary_valid_pages=quality["primary_valid_pages"],
    ) == "degraded"


def test_raw_collection_only_skips_pages_with_all_rounds_done():
    rows = [
        (1, "done"),
        (1, "done"),
        (1, "failed"),
        (2, "done"),
        (2, "done"),
        (2, "done"),
    ]

    assert completed_raw_pages(rows, expected_rounds=3) == {2}


def test_stage_assessment_allows_optional_raw_empty_rounds():
    assessment = pipeline_orchestrator.assess_stage_result(
        "raw",
        {
            "status": "done",
            "total_rounds": 3,
            "valid_rounds": 2,
            "empty_rounds": 1,
            "optional_empty_rounds": 1,
            "empty_pages": 0,
            "primary_empty_pages": 0,
        },
        required=True,
    )

    assert assessment.status == "done"
    assert assessment.complete_for_dependencies is True


def test_stage_assessment_degrades_raw_missing_primary_page():
    assessment = pipeline_orchestrator.assess_stage_result(
        "raw",
        {
            "status": "done",
            "total_rounds": 3,
            "valid_rounds": 1,
            "empty_rounds": 2,
            "empty_pages": 0,
            "primary_empty_pages": 1,
        },
        required=True,
    )

    assert assessment.status == "degraded"
    assert assessment.complete_for_dependencies is True
    assert assessment.reason == "raw_content_partial"


def test_fusion_classifies_all_empty_and_index_failure():
    assert classify_fusion_status(total_pages=2, valid_pages=0) == "degraded"
    assert classify_fusion_status(total_pages=2, valid_pages=0, error_pages=2) == "failed"
    assert classify_fusion_status(total_pages=2, valid_pages=2, index_error="embed down") == "degraded"


def test_analysis_artifact_stable_hash_ignores_dict_order():
    left = {"stage": "fusion", "payload": {"b": [2, 1], "a": "文本"}}
    right = {"payload": {"a": "文本", "b": [2, 1]}, "stage": "fusion"}

    assert analysis_artifact_service.stable_hash(left) == analysis_artifact_service.stable_hash(right)
    assert analysis_artifact_service.stable_hash(left) != analysis_artifact_service.stable_hash({
        "stage": "fusion",
        "payload": {"b": [1, 2], "a": "文本"},
    })


@pytest.mark.asyncio
async def test_record_analysis_artifact_uses_session_factory():
    diagnostics_db = _DiagnosticDb()

    artifact_id = await analysis_artifact_service.record_analysis_artifact(
        owner_id=1,
        document_id=123,
        file_id=456,
        task_id=777,
        pipeline_run_id=1000,
        stage="fusion",
        status="done",
        input_hash="input-hash",
        output_hash="output-hash",
        prompt_hash_value="prompt-hash",
        model_profile="gpt-5.5-knowledge",
        model_used="gpt-5.5",
        reason="done",
        diagnostics={"model_diagnostics": {"selected_profile": "gpt-5.5"}},
        metrics={"valid_pages": 1},
        session_factory=_SessionFactory(diagnostics_db),
    )

    artifact_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_analysis_artifacts"
    ]
    assert artifact_id == artifact_rows[0].id
    assert artifact_rows[0].stage == "fusion"
    assert artifact_rows[0].status == "done"
    assert artifact_rows[0].prompt_hash == "prompt-hash"
    assert artifact_rows[0].model_profile == "gpt-5.5-knowledge"
    assert artifact_rows[0].model_used == "gpt-5.5"
    assert artifact_rows[0].metrics_json["valid_pages"] == 1


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
async def test_orchestrator_updates_document_status_fields(monkeypatch):
    async def profile_stage(**_kwargs):
        return {"subject": "检验报告", "doc_summary": "检测结论"}

    async def graph_stage(**_kwargs):
        return {"status": "done", "entities": 3}

    async def relations_stage(**_kwargs):
        return {"status": "done", "relations": 1}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("profile", ["fusion"], True, profile_stage),
            StageDef("graph", ["fusion"], True, graph_stage),
            StageDef("relations", ["profile", "graph"], True, relations_stage, requires=["profile", "graph"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)

    db = _FakeDb()
    result = await pipeline_orchestrator.run_pipeline(db, 123, 1, 456, 1)

    assert result["status"] == "done"
    assert db.doc.profile_status == "done"
    assert db.doc.graph_status == "done"
    assert db.doc.relation_status == "done"


@pytest.mark.asyncio
async def test_orchestrator_skips_done_deep_stages_when_not_stale(monkeypatch):
    async def stale_none(*_args, **_kwargs):
        return []

    async def should_not_run(**_kwargs):
        raise AssertionError("done stage should be resumed as skipped")

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("profile", ["fusion"], False, should_not_run),
            StageDef("graph", ["fusion"], False, should_not_run),
            StageDef("relations", ["profile", "graph"], False, should_not_run, requires=["profile", "graph"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", stale_none)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)

    db = _FakeDb()
    db.doc.profile_status = "done"
    db.doc.graph_status = "done"
    db.doc.relation_status = "done"

    result = await pipeline_orchestrator.run_pipeline(db, 123, 1, 456, 1)

    assert result["status"] == "done"
    assert result["steps"]["profile"]["reason"] == "already done"
    assert result["steps"]["graph"]["reason"] == "already done"
    assert result["steps"]["relations"]["reason"] == "already done"


@pytest.mark.asyncio
async def test_orchestrator_force_fusion_reruns_downstream(monkeypatch):
    calls: list[str] = []

    async def stale_none(*_args, **_kwargs):
        return []

    async def stage_fn(**_kwargs):
        calls.append(_kwargs["document_id"] and "called")
        return {"status": "done"}

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [
            StageDef("fusion", ["raw"], False, stage_fn, requires=[]),
            StageDef("profile", ["fusion"], False, stage_fn, requires=["fusion"]),
            StageDef("relations", ["profile"], False, stage_fn, requires=["profile"]),
        ],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", stale_none)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)
    monkeypatch.setattr(pipeline_orchestrator, "mark_stale", _noop)

    db = _FakeDb()
    db.doc.fusion_status = "done"
    db.doc.profile_status = "done"
    db.doc.relation_status = "done"

    result = await pipeline_orchestrator.run_pipeline(db, 123, 1, 456, 1, force_fusion=True)

    assert result["status"] == "done"
    assert len(calls) == 3


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
async def test_orchestrator_persists_analysis_artifacts(monkeypatch):
    async def done_raw(**_kwargs):
        return {
            "status": "done",
            "total_rounds": 1,
            "valid_rounds": 1,
            "empty_rounds": 0,
            "model_diagnostics": [
                {
                    "requested_profile": "gpt-5.5-knowledge",
                    "selected_profile": "gpt-5.5",
                }
            ],
        }

    async def prompt_hash_stub(_db, stage):
        return f"prompt:{stage}"

    monkeypatch.setattr(
        pipeline_orchestrator,
        "STAGE_REGISTRY",
        [StageDef("raw", ["source_file"], False, done_raw)],
    )
    monkeypatch.setattr(pipeline_orchestrator, "detect_stale_stages", _always_stale)
    monkeypatch.setattr(pipeline_orchestrator, "record_artifact_hash", _hash_stage)
    monkeypatch.setattr(pipeline_orchestrator, "resolve_stage_prompt_hash", prompt_hash_stub)

    diagnostics_db = _DiagnosticDb()
    monkeypatch.setattr(pipeline_orchestrator, "AsyncSessionLocal", _SessionFactory(diagnostics_db))

    result = await pipeline_orchestrator.run_pipeline(_FakeDb(), 123, 1, 456, 1, task_id=777)

    artifact_rows = [
        item for item in diagnostics_db.added
        if getattr(item, "__tablename__", "") == "kb_analysis_artifacts"
    ]
    assert result["status"] == "done"
    assert [row.stage for row in artifact_rows] == ["source_file", "raw"]
    raw_artifact = artifact_rows[1]
    assert raw_artifact.task_id == 777
    assert raw_artifact.pipeline_run_id == 1000
    assert raw_artifact.status == "done"
    assert raw_artifact.prompt_hash == "prompt:raw"
    assert raw_artifact.model_profile == "gpt-5.5-knowledge"
    assert raw_artifact.model_used == "gpt-5.5"
    assert raw_artifact.input_hash
    assert raw_artifact.output_hash
    assert raw_artifact.diagnostics_json["model_diagnostics"][0]["selected_profile"] == "gpt-5.5"
    assert raw_artifact.metrics_json["valid_rounds"] == 1


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
async def test_parse_uses_document_snapshot_after_initial_commit(monkeypatch):
    calls = []

    async def empty_parse_document(file_id, extension, caller):
        calls.append((file_id, extension, caller))
        return _ParsedIr()

    monkeypatch.setattr(document_service, "parse_document", empty_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {"blocks": []})

    db = _SnapshotParseDb()
    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
    )

    assert calls == [(654, "docx", "user:1")]
    assert result["status"] == "degraded"
    assert result["document"]["file_id"] == 654


@pytest.mark.asyncio
async def test_parse_releases_stale_lock_without_inflight_task(monkeypatch):
    async def empty_parse_document(*_args, **_kwargs):
        return _ParsedIr()

    monkeypatch.setattr(document_service, "parse_document", empty_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {"blocks": []})

    db = _StaleParseDb()
    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
    )

    assert result["status"] == "degraded"
    assert db.doc.parse_status == "degraded"
    assert db.doc.vector_status == "pending"
    assert db.doc.parse_worker_id == "user:1"


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
