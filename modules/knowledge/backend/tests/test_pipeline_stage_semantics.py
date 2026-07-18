import asyncio
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-pipeline-stage-semantics")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_service(service_name: str):
    module_names = (
        f"modules.knowledge.backend.services.{service_name}",
        f"huashiwangzu_modules.knowledge.services.{service_name}",
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
    raise AssertionError(f"Cannot load knowledge service {service_name}")


analysis_artifact_service = _load_service("analysis_artifact_service")
document_service = _load_service("document_service")
fusion_service = _load_service("fusion_service")
llm_diagnostics_stream = _load_service("llm_diagnostics_stream")
llm_diagnostics = _load_service("llm_diagnostics")
model_routing = _load_service("model_routing")
page_asset_service = _load_service("page_asset_service")
pipeline_service = _load_service("pipeline_service")
source_validate_stage = importlib.import_module(f"{pipeline_service.__package__}.pipeline_stages.source_validate")
raw_collection_service = _load_service("raw_collection_service")
source_file_state = _load_service("source_file_state")
stage_result_cache_service = _load_service("stage_result_cache_service")

classify_fusion_status = fusion_service.classify_fusion_status
classify_raw_collection_status = raw_collection_service.classify_raw_collection_status
completed_raw_pages = raw_collection_service.completed_raw_pages
summarize_raw_content_quality = raw_collection_service.summarize_raw_content_quality
TEST_STORAGE_PATH = "_knowledge_tests/stage-semantics-source.txt"


def test_pipeline_stage_lane_keys_match_resource_pools():
    assert pipeline_service.STAGE_LANE_KEYS["source_validate"] == "local_preprocess"
    assert pipeline_service.STAGE_LANE_KEYS["parse_index"] == "local_preprocess"
    assert pipeline_service.STAGE_LANE_KEYS["raw_text"] == "local_preprocess"
    assert pipeline_service.STAGE_LANE_KEYS["page_render"] == "local_preprocess"
    assert pipeline_service.STAGE_LANE_KEYS["raw_ocr"] == "vision_analysis"
    assert pipeline_service.STAGE_LANE_KEYS["raw_vision"] == "vision_analysis"
    assert pipeline_service.STAGE_LANE_KEYS["fusion"] == "llm_analysis"
    assert pipeline_service.STAGE_LANE_KEYS["profile"] == "llm_analysis"
    assert pipeline_service.STAGE_LANE_KEYS["graph"] == "llm_analysis"


def test_pipeline_failure_diagnostics_preserve_wrapped_conversion_details() -> None:
    from app.services.office_conversion import OfficeConversionError

    conversion_error = OfficeConversionError(
        "LibreOffice conversion failed",
        diagnostics={"exit_code": 1, "stderr": "missing export filter"},
    )
    try:
        raise RuntimeError("PPT parser conversion failed") from conversion_error
    except RuntimeError as wrapped:
        chain = pipeline_service._exception_chain_diagnostics(wrapped)

    assert chain[0]["exception_type"] == "RuntimeError"
    assert chain[1] == {
        "exception_type": "OfficeConversionError",
        "message": "LibreOffice conversion failed",
        "conversion": {"exit_code": 1, "stderr": "missing export filter"},
    }


@pytest.fixture(autouse=True)
def _live_upload_fixture():
    marker = REPO_ROOT / "data" / "uploads" / TEST_STORAGE_PATH
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("knowledge pipeline stage semantics source", encoding="utf-8")
    try:
        yield
    finally:
        marker.unlink(missing_ok=True)


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
    owner_id = 1
    file_id = 456
    filename = "stage-semantics-source.txt"
    extension = "pdf"
    storage_path = TEST_STORAGE_PATH
    total_pages = 2
    raw_status = "pending"
    fusion_status = "pending"
    profile_status = "pending"
    graph_status = "pending"
    relation_status = "pending"
    parse_error = None
    parse_status = "done"
    vector_status = "done"
    deleted = False


class _DiagnosticDb:
    def __init__(self):
        self.added = []
        self.flushes = 0
        self.commits = 0
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

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _SessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


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


class _RecentParseDocument(_StaleParseDocument):
    parse_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)


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


class _FakeQueueTask:
    def __init__(self, task_id: int, document_id: int, stage: str):
        self.id = task_id
        self.parameters = json.dumps({"document_id": document_id, "stage": stage})


class _StaleParseDbWithCurrentTask(_StaleParseDb):
    def __init__(self, task_id: int):
        super().__init__()
        self.task_id = task_id

    async def execute(self, _stmt):
        self.executes += 1
        if self.executes == 1:
            return _ScalarResult(self.doc)
        if self.executes == 2:
            return _ListResult([_FakeQueueTask(self.task_id, self.doc.id, "parse_index")])
        return _ScalarResult(None)


class _RecentParseDbWithCurrentTask(_StaleParseDbWithCurrentTask):
    def __init__(self, task_id: int):
        super().__init__(task_id)
        self.doc = _RecentParseDocument()


class _ParsedIr:
    parse_errors = ["empty_result"]
    parse_status = "ok"
    resource_diagnostics = []


class _FakePipelineRun:
    id = 99
    status = "running"
    reason = None
    diagnostics_json = {}
    completed_at = None


class _PipelineHandlerDb:
    def __init__(self, *, fail_commit: bool = False):
        self.doc = _FakeDocument()
        self.run = _FakePipelineRun()
        self.fail_commit = fail_commit
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0

    async def scalar(self, _stmt):
        return self.doc

    async def get(self, model, _item_id):
        if getattr(model, "__name__", "") == "KbPipelineRun":
            return self.run
        return None

    async def refresh(self, _obj):
        return None

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self):
        self.rollbacks += 1


class _PipelineHandlerSession:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


def test_raw_collection_classifies_all_empty_as_degraded_or_failed():
    assert classify_raw_collection_status(total_rounds=3, valid_rounds=0, failed_rounds=0, task_count=3) == "degraded"
    assert classify_raw_collection_status(total_rounds=3, valid_rounds=0, failed_rounds=3, task_count=3) == "failed"


def test_knowledge_concurrency_reads_models_json_between_batches(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    config_path.write_text(
        """
        {
          "module_routing": {
            "knowledge": {
              "pipeline_concurrency": {
                "raw_collect": 7,
                "entity_extract": 99,
                "page_fusion": "bad",
                "model_call_global": 12
              },
              "pipeline_priorities": {
                "source_validate": 10,
                "bad": "nope"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)
    monkeypatch.setattr(model_routing, "get_models_config", lambda: {})

    assert model_routing.resolve_knowledge_concurrency("raw_collect", 5) == 7
    assert model_routing.resolve_knowledge_concurrency("entity_extract", 6, maximum=16) == 16
    assert model_routing.resolve_knowledge_concurrency("page_fusion", 6) == 6
    assert model_routing.resolve_knowledge_model_call_concurrency() == 12
    assert model_routing.resolve_knowledge_pipeline_priority("source_validate", 5) == 10
    assert model_routing.resolve_knowledge_pipeline_priority("bad", 5) == 5


def test_model_stage_auto_pause_updates_worker_config(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text("{}", encoding="utf-8")
    worker_path.write_text(
        json.dumps(
            {
                "paused_task_types": ["kb_enterprise_import"],
                "paused_stages": {"kb_pipeline_stage": ["raw_text"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    result = model_routing.pause_model_stage_queue(
        "profile",
        reason="model_fallback_exhausted",
        error_message="all fallback profiles failed",
    )

    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert result["paused"] is True
    assert result["group"] == "llm"
    assert saved["paused_task_types"] == ["kb_enterprise_import"]
    assert saved["paused_stages"]["kb_pipeline_stage"] == ["fusion", "graph", "profile", "raw_text"]
    assert saved["model_auto_pause"]["stage"] == "profile"
    assert saved["model_auto_pause"]["group"] == "llm"


def test_model_stage_auto_pause_groups_vlm_stages(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text("{}", encoding="utf-8")
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    result = model_routing.pause_model_stage_queue(
        "raw_vision",
        reason="model_fallback_exhausted",
        error_message="vision relay failed",
    )

    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert result["paused"] is True
    assert result["group"] == "vlm"
    assert saved["paused_stages"]["kb_pipeline_stage"] == ["raw_ocr", "raw_vision"]


def test_model_rate_limit_auto_pause_after_threshold(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text(
        json.dumps(
            {
                "module_routing": {
                    "knowledge": {
                        "rate_limit_auto_pause": {
                            "enabled": True,
                            "threshold": 3,
                            "window_seconds": 300,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    first = model_routing.record_model_rate_limit("raw_vision", error_message="HTTP 429")
    second = model_routing.record_model_rate_limit("raw_vision", error_message="rate limit")
    third = model_routing.record_model_rate_limit("raw_vision", error_message="too many requests")

    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert first["reason"] == "below_threshold"
    assert second["reason"] == "below_threshold"
    assert third["paused"] is True
    assert third["count"] == 3
    assert third["group"] == "vlm"
    assert saved["paused_stages"]["kb_pipeline_stage"] == ["raw_ocr", "raw_vision"]
    assert saved["model_auto_pause"]["reason"] == "model_rate_limit_threshold"


def test_model_supply_unavailable_auto_pause_after_threshold(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text(
        json.dumps(
            {
                "module_routing": {
                    "knowledge": {
                        "rate_limit_auto_pause": {
                            "enabled": True,
                            "threshold": 2,
                            "window_seconds": 300,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    first = model_routing.record_model_rate_limit(
        "profile",
        error_message="HTTP 503 Service Unavailable: auth_unavailable: no auth available",
    )
    second = model_routing.record_model_rate_limit(
        "profile",
        error_message="upstream_error auth_unavailable: no auth available",
    )

    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert first["reason"] == "below_threshold"
    assert second["paused"] is True
    assert second["count"] == 2
    assert second["group"] == "llm"
    assert saved["paused_stages"]["kb_pipeline_stage"] == ["fusion", "graph", "profile"]


def test_model_rate_limit_stage_alias_pauses_llm_queue_group(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text(
        json.dumps(
            {
                "module_routing": {
                    "knowledge": {
                        "rate_limit_auto_pause": {
                            "enabled": True,
                            "threshold": 1,
                            "window_seconds": 300,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    result = model_routing.record_model_rate_limit("entity", error_message="HTTP 429")

    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert result["paused"] is True
    assert result["stage"] == "graph"
    assert result["group"] == "llm"
    assert saved["paused_stages"]["kb_pipeline_stage"] == ["fusion", "graph", "profile"]



def test_model_auto_pause_writes_resume_ttl_metadata(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text(
        json.dumps(
            {
                "module_routing": {
                    "knowledge": {
                        "rate_limit_auto_pause": {
                            "enabled": True,
                            "threshold": 1,
                            "window_seconds": 300,
                            "resume_ttl_seconds": 120,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    result = model_routing.pause_model_stage_queue(
        "profile",
        reason="model_fallback_exhausted",
        error_message="all fallback profiles failed",
    )
    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert result["paused"] is True
    assert result["resume_ttl_seconds"] == 120
    assert result["expires_at"]
    assert saved["model_auto_pause"]["enabled"] is True
    assert saved["model_auto_pause"]["resume_ttl_seconds"] == 120
    assert saved["model_auto_pause"]["expires_at"]


def test_model_auto_pause_self_heals_after_ttl(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text(
        json.dumps(
            {
                "module_routing": {
                    "knowledge": {
                        "rate_limit_auto_pause": {
                            "enabled": True,
                            "threshold": 1,
                            "window_seconds": 300,
                            "resume_ttl_seconds": 60,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    worker_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    paused = model_routing.pause_model_stage_queue(
        "raw_vision",
        reason="model_rate_limit_threshold",
        error_message="HTTP 429",
    )
    assert paused["paused"] is True
    mid = json.loads(worker_path.read_text(encoding="utf-8"))
    assert mid["paused_stages"]["kb_pipeline_stage"] == ["raw_ocr", "raw_vision"]

    # Force expiry into the past and clear.
    mid["model_auto_pause"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    worker_path.write_text(json.dumps(mid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cleared = model_routing.maybe_clear_expired_model_auto_pause()
    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert cleared["cleared"] is True
    assert saved["model_auto_pause"]["enabled"] is False
    assert "kb_pipeline_stage" not in (saved.get("paused_stages") or {})


def test_legacy_permanent_auto_pause_gets_ttl_backfill(tmp_path, monkeypatch):
    config_path = tmp_path / "models.json"
    worker_path = tmp_path / "task_worker.json"
    config_path.write_text("{}", encoding="utf-8")
    worker_path.write_text(
        json.dumps(
            {
                "paused_stages": {"kb_pipeline_stage": ["fusion", "profile", "graph"]},
                "model_auto_pause": {
                    "enabled": True,
                    "stage": "profile",
                    "group": "llm",
                    "paused_stages": ["fusion", "profile", "graph"],
                    "reason": "legacy_permanent",
                    "updated_at": "2000-01-01T00:00:00+00:00",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_routing, "get_models_config_path", lambda: config_path)

    cleared = model_routing.maybe_clear_expired_model_auto_pause()
    saved = json.loads(worker_path.read_text(encoding="utf-8"))
    assert cleared["cleared"] is True
    assert saved["model_auto_pause"]["enabled"] is False
    assert "kb_pipeline_stage" not in (saved.get("paused_stages") or {})


@pytest.mark.asyncio
async def test_timed_llm_chat_rejects_gateway_attempt_without_success(monkeypatch):
    calls: list[tuple[str, object]] = []

    def fake_record_model_rate_limit(stage: str, *, error_message: object = "") -> dict:
        calls.append((stage, error_message))
        return {"paused": False, "reason": "below_threshold", "stage": stage}

    async def fake_chat(**kwargs):
        return {
            "content": "placeholder gateway failure text",
            "diagnostics": {
                "attempts": [
                    {
                        "profile": "gpt-5.5-knowledge",
                        "provider": "gptstore-text",
                        "model": "gpt-5.5",
                        "stage": "chat",
                        "success": False,
                        "error": None,
                    }
                ]
            },
        }

    monkeypatch.setattr(llm_diagnostics, "record_model_rate_limit", fake_record_model_rate_limit)

    with pytest.raises(RuntimeError, match="gateway attempt failed without error"):
        await llm_diagnostics.timed_llm_chat(
            logger=llm_diagnostics.logging.getLogger("test.llm_diagnostics"),
            stage="entity",
            profile_key="gpt-5.5-knowledge",
            messages=[{"role": "user", "content": "ping"}],
            chat_func=fake_chat,
        )

    assert calls == [("entity", "gateway attempt failed without error")]


@pytest.mark.asyncio
async def test_knowledge_model_call_slot_limits_parallel_entries(monkeypatch):
    monkeypatch.setattr(model_routing, "resolve_knowledge_model_call_concurrency", lambda default=10: 1)
    active_counts: list[int] = []

    async def _worker() -> None:
        async with model_routing.knowledge_model_call_slot("test"):
            active_counts.append(model_routing.knowledge_model_call_active_count())
            await asyncio.sleep(0.01)

    await asyncio.gather(_worker(), _worker())

    assert active_counts == [1, 1]
    assert model_routing.knowledge_model_call_active_count() == 0


@pytest.mark.asyncio
async def test_raw_collection_builds_page_text_map_with_single_parse(monkeypatch):
    calls = 0

    async def _fake_parse_document(file_id: int, ext: str, caller: str):
        nonlocal calls
        calls += 1
        assert file_id == 42
        assert ext == "pdf"
        assert caller == "user:1"
        return {
            "blocks": [
                {"page": 1, "text": "第一页 A"},
                {"page": 1, "text": "第一页 B"},
                {"page": 2, "text": "第二页"},
                {"page": None, "text": "无页码默认第一页"},
            ]
        }

    monkeypatch.setattr(raw_collection_service, "parse_document", _fake_parse_document)
    monkeypatch.setattr(raw_collection_service, "to_legacy_dict", lambda value: value)

    page_text_map, error = await raw_collection_service._build_page_text_map(42, "pdf", "user:1")

    assert error == ""
    assert calls == 1
    assert page_text_map[1] == "第一页 A\n\n第一页 B\n\n无页码默认第一页"
    assert page_text_map[2] == "第二页"


@pytest.mark.asyncio
async def test_tesseract_ocr_runs_off_event_loop(monkeypatch):
    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return {"words": [{"t": "清颜"}], "img_w": 100, "img_h": 50}

    monkeypatch.setattr(raw_collection_service.asyncio, "to_thread", fake_to_thread)

    result = await raw_collection_service._ocr_words_tesseract_async(b"image")

    assert result["words"][0]["t"] == "清颜"
    assert calls == [(raw_collection_service._ocr_words_tesseract, (b"image",), {})]


def test_raw_collection_classifies_partial_and_page_coverage():
    assert classify_raw_collection_status(total_rounds=3, valid_rounds=1, failed_rounds=0, task_count=3) == "degraded"
    assert (
        classify_raw_collection_status(
            total_rounds=18,
            valid_rounds=16,
            failed_rounds=0,
            task_count=18,
            total_pages=6,
            valid_pages=6,
        )
        == "done"
    )
    assert (
        classify_raw_collection_status(
            total_rounds=18,
            valid_rounds=15,
            failed_rounds=0,
            task_count=18,
            total_pages=6,
            valid_pages=5,
        )
        == "degraded"
    )


def test_raw_stage_result_compaction_keeps_queue_payload_small():
    results = [
        {
            "round": 3,
            "page": page,
            "chars": 100,
            "status": "done",
            "duration_ms": 10,
            "processor": "vlm",
            "page_asset": {"storage_path": "x", "diagnostics": "large"},
        }
        for page in range(1, 101)
    ]

    compact = raw_collection_service._compact_raw_stage_results(results)

    assert len(compact) == 80
    assert compact[0] == {
        "round": 3,
        "page": 1,
        "chars": 100,
        "status": "done",
        "duration_ms": 10,
        "processor": "vlm",
        "error": None,
        "model_degraded": False,
    }
    assert "page_asset" not in compact[0]


def test_local_ocr_image_preprocess_resizes_oversized_images(monkeypatch):
    from io import BytesIO

    from PIL import Image

    monkeypatch.setattr(raw_collection_service, "TESSERACT_AVAILABLE", True)

    def fake_preprocess_int(key, default, *, minimum=1, maximum=100_000_000):
        if key == "raw_ocr_max_side":
            return 1000
        if key == "raw_ocr_max_bytes":
            return 512 * 1024
        return default

    monkeypatch.setattr(raw_collection_service, "resolve_knowledge_image_preprocess_int", fake_preprocess_int)

    source = BytesIO()
    Image.new("RGB", (4000, 1000), color="white").save(source, format="PNG")

    prepared, metadata = raw_collection_service._prepare_image_bytes_for_local_ocr(source.getvalue())

    assert metadata["resized"] is True
    assert metadata["reencoded"] is True
    assert metadata["original_size"] == [4000, 1000]
    assert metadata["prepared_size"] == [1000, 250]
    assert metadata["prepared_bytes"] == len(prepared)
    assert len(prepared) < len(source.getvalue())


def test_vlm_ready_image_materialization_uses_gateway_preprocess():
    from io import BytesIO

    from PIL import Image

    source = BytesIO()
    Image.new("RGB", (3600, 1200), color="white").save(source, format="PNG")

    prepared, prepared_mime, metadata = page_asset_service._prepare_page_asset_bytes(
        source.getvalue(),
        "image/png",
    )

    assert metadata["vlm_ready"] is True
    assert prepared_mime.startswith("image/")
    assert metadata["stage"] == "knowledge_page_render"
    assert metadata["preprocess_version"].startswith("vision_image_preprocess")
    assert metadata["resized"] is True
    assert metadata["reencoded"] is True
    assert metadata["source_original_md5"] != metadata["source_prepared_md5"]
    assert len(prepared) == metadata["prepared_bytes"]


@pytest.mark.asyncio
async def test_page_render_materializes_pages_with_independent_commits(monkeypatch):
    doc = _FakeDocument()
    doc.total_pages = 3

    class MainDb:
        def __init__(self):
            self.commits = 0

        async def scalar(self, _stmt):
            return doc

        async def commit(self):
            self.commits += 1

    class PageDb:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    class PageSession:
        def __init__(self, sessions: list[PageDb]):
            self.db = PageDb()
            sessions.append(self.db)

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *_exc_info):
            return None

    class Asset:
        id = 99
        width = 1600
        height = 900

    sessions: list[PageDb] = []
    active = 0
    max_active = 0

    async def fake_render(_file_id, page, _user_id):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return f"page-{page}".encode()

    async def fake_existing(*_args, **_kwargs):
        return None

    async def fake_upsert(*_args, **_kwargs):
        return Asset()

    monkeypatch.setattr(page_asset_service, "AsyncSessionLocal", lambda: PageSession(sessions))
    monkeypatch.setattr(page_asset_service, "get_pdf_page_count", AsyncMock(return_value=3))
    monkeypatch.setattr(page_asset_service, "render_page_to_image", fake_render)
    monkeypatch.setattr(page_asset_service, "_existing_page_asset", fake_existing)
    monkeypatch.setattr(page_asset_service, "_prepare_page_asset_bytes", lambda data, mime: (data, mime, {}))
    monkeypatch.setattr(page_asset_service, "_upsert_page_asset", fake_upsert)
    monkeypatch.setattr(
        page_asset_service,
        "resolve_knowledge_concurrency",
        lambda stage, default, **_kwargs: 3 if stage == "page_render_pages" else default,
    )

    db = MainDb()
    result = await page_asset_service.materialize_page_assets_stage(db, doc.id, doc.owner_id, doc.file_id, 1)

    assert result["status"] == "done"
    assert result["assets"] == 3
    assert result["materialized"] == 3
    assert result["page_concurrency"] == 3
    assert max_active == 3
    assert sum(session.commits for session in sessions) == 3
    assert db.commits == 2


@pytest.mark.asyncio
async def test_page_render_treats_image_zero_pages_as_one_page(monkeypatch):
    doc = _FakeDocument()
    doc.extension = "jpg"
    doc.total_pages = 0

    class MainDb:
        def __init__(self):
            self.commits = 0

        async def scalar(self, _stmt):
            return doc

        async def commit(self):
            self.commits += 1

    class PageDb:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    class PageSession:
        def __init__(self, sessions: list[PageDb]):
            self.db = PageDb()
            sessions.append(self.db)

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, *_exc_info):
            return None

    class Asset:
        id = 99
        width = 1600
        height = 900

    sessions: list[PageDb] = []
    read_pages: list[int] = []

    async def fake_read_image(_file_id, _user_id):
        read_pages.append(1)
        return b"image", "image/jpeg"

    async def fake_existing(*_args, **_kwargs):
        return None

    async def fake_upsert(*_args, **_kwargs):
        return Asset()

    monkeypatch.setattr(page_asset_service, "AsyncSessionLocal", lambda: PageSession(sessions))
    monkeypatch.setattr(page_asset_service, "_read_source_image_bytes", fake_read_image)
    monkeypatch.setattr(page_asset_service, "_existing_page_asset", fake_existing)
    monkeypatch.setattr(page_asset_service, "_prepare_page_asset_bytes", lambda data, mime: (data, mime, {}))
    monkeypatch.setattr(page_asset_service, "_upsert_page_asset", fake_upsert)

    db = MainDb()
    result = await page_asset_service.materialize_page_assets_stage(db, doc.id, doc.owner_id, doc.file_id, 1)

    assert result["status"] == "done"
    assert result["total_pages"] == 1
    assert result["assets"] == 1
    assert result["materialized"] == 1
    assert doc.total_pages == 1
    assert read_pages == [1]
    assert sum(session.commits for session in sessions) == 1
    assert db.commits == 2


def test_raw_quality_treats_empty_visual_ocr_as_optional():
    rows = [
        (1, 1, "text", "local image description", "done", 120, {}),
        (1, 2, "ocr", "", "degraded", 35, {"method": "tesseract_boxes", "words": []}),
        (1, 3, "vision", "poster layout and text", "done", 18000, {}),
    ]

    quality = summarize_raw_content_quality(rows, total_pages=1, expected_rounds=3, visual_document=True)

    assert quality["valid_rounds"] == 2
    assert quality["optional_empty_rounds"] == 1
    assert quality["primary_empty_pages"] == 0
    assert (
        classify_raw_collection_status(
            total_rounds=quality["total_rounds"],
            valid_rounds=quality["valid_rounds"],
            failed_rounds=0,
            task_count=3,
            total_pages=1,
            valid_pages=quality["valid_pages"],
            primary_valid_pages=quality["primary_valid_pages"],
        )
        == "done"
    )


def test_raw_quality_degrades_when_visual_page_lacks_primary_content():
    rows = [
        (1, 1, "text", "", "degraded", 120, {}),
        (1, 2, "ocr", "only ocr text", "done", 35, {"method": "tesseract_boxes"}),
        (1, 3, "vision", "", "degraded", 18000, {}),
    ]

    quality = summarize_raw_content_quality(rows, total_pages=1, expected_rounds=3, visual_document=True)

    assert quality["valid_rounds"] == 1
    assert quality["primary_empty_pages"] == 1
    assert (
        classify_raw_collection_status(
            total_rounds=quality["total_rounds"],
            valid_rounds=quality["valid_rounds"],
            failed_rounds=0,
            task_count=3,
            total_pages=1,
            valid_pages=quality["valid_pages"],
            primary_valid_pages=quality["primary_valid_pages"],
        )
        == "degraded"
    )


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


def test_pipeline_stage_result_status_contract():
    assert pipeline_service._stage_status_from_result({"status": "done"}) == ("done", "done")
    assert pipeline_service._stage_status_from_result({"status": "skipped", "reason": "already done"}) == (
        "skipped",
        "already done",
    )
    assert pipeline_service._stage_status_from_result({"model_degraded": True}) == ("degraded", "model_fallback")
    assert pipeline_service._stage_status_from_result({"error": "boom"}) == ("failed", "boom")


@pytest.mark.asyncio
async def test_pipeline_root_fans_out_parallelizable_stages(monkeypatch):
    doc = _FakeDocument()
    enqueued: list[str] = []

    async def fake_enqueue(_db, _doc, _user_id, stage, **_kwargs):
        enqueued.append(stage)
        return {"stage": stage, "enqueued": True}

    monkeypatch.setattr(pipeline_service, "enqueue_pipeline_stage_task", fake_enqueue)
    monkeypatch.setattr(pipeline_service, "page_assets_complete", AsyncMock(return_value=False))

    class Db:
        async def refresh(self, _doc):
            return None

    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage=pipeline_service.ROOT_STAGE,
        pipeline_run_id=10,
    )

    assert [item["stage"] for item in successors] == ["parse_index", "raw_text", "page_render"]
    assert enqueued == ["parse_index", "raw_text", "page_render"]


@pytest.mark.asyncio
async def test_pipeline_root_backfills_missing_page_assets_without_deep_rerun(monkeypatch):
    doc = _FakeDocument()
    doc.raw_status = "done"
    doc.fusion_status = "done"
    doc.profile_status = "done"
    doc.graph_status = "done"
    doc.relation_status = "done"
    enqueued: list[str] = []

    async def fake_enqueue(_db, _doc, _user_id, stage, **_kwargs):
        enqueued.append(stage)
        return {"stage": stage, "enqueued": True}

    monkeypatch.setattr(pipeline_service, "enqueue_pipeline_stage_task", fake_enqueue)
    monkeypatch.setattr(pipeline_service, "page_assets_complete", AsyncMock(return_value=False))

    class Db:
        async def refresh(self, _doc):
            return None

    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage=pipeline_service.ROOT_STAGE,
        pipeline_run_id=10,
    )

    assert [item["stage"] for item in successors] == ["page_render"]
    assert enqueued == ["page_render"]


@pytest.mark.asyncio
async def test_pipeline_page_render_fans_out_visual_consumers(monkeypatch):
    doc = _FakeDocument()
    enqueued: list[str] = []

    async def fake_enqueue(_db, _doc, _user_id, stage, **_kwargs):
        enqueued.append(stage)
        return {"stage": stage, "enqueued": True}

    monkeypatch.setattr(pipeline_service, "enqueue_pipeline_stage_task", fake_enqueue)

    class Db:
        async def refresh(self, _doc):
            return None

    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage="page_render",
        pipeline_run_id=10,
    )

    assert [item["stage"] for item in successors] == ["raw_ocr", "raw_vision"]
    assert enqueued == ["raw_ocr", "raw_vision"]


@pytest.mark.asyncio
async def test_pipeline_profile_graph_backfills_missing_peer_before_relations(monkeypatch):
    doc = _FakeDocument()
    doc.profile_status = "done"
    doc.graph_status = "pending"
    enqueued: list[str] = []

    async def fake_enqueue(_db, _doc, _user_id, stage, **_kwargs):
        enqueued.append(stage)
        return {"stage": stage, "enqueued": True}

    monkeypatch.setattr(pipeline_service, "enqueue_pipeline_stage_task", fake_enqueue)

    class Db:
        async def refresh(self, _doc):
            return None

    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage="profile",
        pipeline_run_id=10,
    )
    assert [item["stage"] for item in successors] == ["graph"]

    doc.graph_status = "done"
    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage="graph",
        pipeline_run_id=10,
    )
    assert [item["stage"] for item in successors] == ["relations"]

    doc.profile_status = "pending"
    doc.graph_status = "done"
    successors = await pipeline_service._enqueue_successors(
        Db(),
        doc=doc,
        user_id=1,
        completed_stage="graph",
        pipeline_run_id=10,
    )
    assert [item["stage"] for item in successors] == ["profile"]


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


def test_stage_result_cache_writes_recoverable_json_until_deleted(tmp_path):
    started_at = datetime.now(timezone.utc)

    cache_path = stage_result_cache_service.write_stage_result_cache(
        cache_dir=tmp_path,
        document_id=123,
        file_id=456,
        owner_id=1,
        stage="raw_vision",
        status="done",
        result={"text": "海报标题", "layout": {"blocks": 2}},
        task_id=777,
        pipeline_run_id=888,
        reason="done",
        started_at=started_at,
        duration_ms=321,
    )

    assert cache_path.exists()
    assert cache_path.suffix == ".json"
    assert not list(tmp_path.glob("*.tmp"))
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == stage_result_cache_service.CACHE_SCHEMA_VERSION
    assert payload["document_id"] == 123
    assert payload["stage"] == "raw_vision"
    assert payload["result"]["text"] == "海报标题"
    assert payload["started_at"] == started_at.isoformat()

    stage_result_cache_service.delete_stage_result_cache(cache_path)

    assert not cache_path.exists()


@pytest.mark.asyncio
async def test_pipeline_stage_cache_survives_main_commit_failure(tmp_path, monkeypatch):
    db = _PipelineHandlerDb(fail_commit=True)
    deleted_paths: list[Path] = []

    async def fake_raise_if_source_unavailable(*_args, **_kwargs):
        return None

    async def fake_run_stage(*_args, **_kwargs):
        return {"status": "done", "text": "LLM result that must not be lost"}

    async def fake_record_stage_artifact(*_args, **_kwargs):
        return "artifact-hash"

    async def fake_record_stage_run(*_args, **_kwargs):
        return None

    async def fake_enqueue_successors(*_args, **_kwargs):
        return []

    def fake_write_stage_result_cache(**kwargs):
        kwargs["cache_dir"] = tmp_path
        return stage_result_cache_service.write_stage_result_cache(**kwargs)

    def fake_delete_stage_result_cache(path):
        deleted_paths.append(path)
        stage_result_cache_service.delete_stage_result_cache(path)

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", lambda: _PipelineHandlerSession(db))
    monkeypatch.setattr(pipeline_service, "raise_if_source_unavailable", fake_raise_if_source_unavailable)
    monkeypatch.setattr(pipeline_service, "_run_stage", fake_run_stage)
    monkeypatch.setattr(pipeline_service, "_record_stage_artifact", fake_record_stage_artifact)
    monkeypatch.setattr(pipeline_service, "_record_stage_run", fake_record_stage_run)
    monkeypatch.setattr(pipeline_service, "settle_pipeline_stage_successors", fake_enqueue_successors)
    monkeypatch.setattr(pipeline_service, "document_deep_pipeline_complete", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(pipeline_service, "write_stage_result_cache", fake_write_stage_result_cache)
    monkeypatch.setattr(pipeline_service, "delete_stage_result_cache", fake_delete_stage_result_cache)

    with pytest.raises(RuntimeError, match="commit failed"):
        await pipeline_service._pipeline_stage_handler({
            "document_id": db.doc.id,
            "user_id": 1,
            "stage": "graph",
            "task_id": 777,
            "pipeline_run_id": db.run.id,
        })

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    assert deleted_paths == []
    payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert payload["result"]["text"] == "LLM result that must not be lost"
    assert payload["pipeline_run_id"] == db.run.id
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_pipeline_stage_rolls_back_before_source_check_after_stage_error(monkeypatch):
    db = _PipelineHandlerDb()
    observed = {}

    class SourceState:
        available = True
        reason = ""

    async def fake_raise_if_source_unavailable(*_args, **_kwargs):
        return None

    async def fake_run_stage(*_args, **_kwargs):
        raise RuntimeError("stage exploded")

    async def fake_get_source_state(_db, file_id):
        observed["rollbacks_before_source_check"] = db.rollbacks
        observed["file_id"] = file_id
        return SourceState()

    async def fake_record_stage_artifact(*_args, **_kwargs):
        return "artifact-hash"

    async def fake_record_stage_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", lambda: _PipelineHandlerSession(db))
    monkeypatch.setattr(pipeline_service, "raise_if_source_unavailable", fake_raise_if_source_unavailable)
    monkeypatch.setattr(pipeline_service, "_run_stage", fake_run_stage)
    monkeypatch.setattr(pipeline_service, "get_source_file_availability", fake_get_source_state)
    monkeypatch.setattr(pipeline_service, "_record_stage_artifact", fake_record_stage_artifact)
    monkeypatch.setattr(pipeline_service, "_record_stage_run", fake_record_stage_run)

    result = await pipeline_service._pipeline_stage_handler({
        "document_id": db.doc.id,
        "user_id": 1,
        "stage": "page_render",
        "task_id": 777,
        "pipeline_run_id": db.run.id,
    })

    assert observed["rollbacks_before_source_check"] == 1
    assert observed["file_id"] == db.doc.file_id
    assert result["task_status"] == "failed"
    assert result["reason"] == "stage exploded"


@pytest.mark.asyncio
async def test_pipeline_stage_returned_failure_persists_page_diagnostics(monkeypatch):
    db = _PipelineHandlerDb()

    async def fake_raise_if_source_unavailable(*_args, **_kwargs):
        return None

    async def fake_run_stage(*_args, **_kwargs):
        return {
            "status": "failed",
            "failed_pages": [{"page": 1, "error": "cannot identify image"}],
            "pages": [{"page": 1, "status": "failed"}],
        }

    async def fake_record_stage_artifact(*_args, **_kwargs):
        return "artifact-hash"

    async def fake_record_stage_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(pipeline_service, "AsyncSessionLocal", lambda: _PipelineHandlerSession(db))
    monkeypatch.setattr(pipeline_service, "raise_if_source_unavailable", fake_raise_if_source_unavailable)
    monkeypatch.setattr(pipeline_service, "_run_stage", fake_run_stage)
    monkeypatch.setattr(pipeline_service, "_record_stage_artifact", fake_record_stage_artifact)
    monkeypatch.setattr(pipeline_service, "_record_stage_run", fake_record_stage_run)

    response = await pipeline_service._pipeline_stage_handler({
        "document_id": db.doc.id,
        "user_id": 1,
        "stage": "page_render",
        "task_id": 777,
        "pipeline_run_id": db.run.id,
    })

    diagnostics = response["result"]["failure_diagnostics"]
    assert response["task_status"] == "failed"
    assert diagnostics["exception_chain"][0]["message"] == "failed"
    assert diagnostics["stage_result"]["failed_pages"] == [{"page": 1, "error": "cannot identify image"}]


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
async def test_pipeline_stage_artifact_records_exact_dag_stage(monkeypatch):
    captured: dict = {}

    async def fake_record_analysis_artifact(**kwargs):
        captured.update(kwargs)
        return 88

    async def fake_prompt_hash(_db, stage):
        return f"prompt:{stage}"

    monkeypatch.setattr(pipeline_service, "record_analysis_artifact", fake_record_analysis_artifact)
    monkeypatch.setattr(pipeline_service, "resolve_stage_prompt_hash", fake_prompt_hash)
    doc = _FakeDocument()

    output_hash = await pipeline_service._record_stage_artifact(
        object(),
        doc=doc,
        pipeline_run_id=1000,
        task_id=777,
        stage="raw_vision",
        status="degraded",
        started_at=datetime.now(timezone.utc),
        result={
            "status": "degraded",
            "model_diagnostics": [
                {
                    "requested_profile": "gpt-5.5-knowledge",
                    "selected_profile": "deepseek-v4-flash",
                }
            ],
        },
        reason="model_fallback",
        duration_ms=123,
    )

    assert output_hash
    assert captured["stage"] == "raw_vision"
    assert captured["schema_version"] == "raw_vision_v1"
    assert captured["task_id"] == 777
    assert captured["pipeline_run_id"] == 1000
    assert captured["prompt_hash_value"] == "prompt:raw_vision"
    assert captured["model_profile"] == "gpt-5.5-knowledge"
    assert captured["model_used"] == "deepseek-v4-flash"
    assert captured["diagnostics"]["model_diagnostics"][0]["selected_profile"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_pipeline_stage_artifact_input_hash_ignores_queue_attempt_identity(monkeypatch):
    input_hashes: list[str] = []

    async def fake_record_analysis_artifact(**kwargs):
        input_hashes.append(kwargs["input_hash"])
        return 88

    async def fake_prompt_hash(_db, _stage):
        return "prompt:graph"

    monkeypatch.setattr(pipeline_service, "record_analysis_artifact", fake_record_analysis_artifact)
    monkeypatch.setattr(pipeline_service, "resolve_stage_prompt_hash", fake_prompt_hash)
    doc = _FakeDocument()
    result = {"status": "done", "nodes": 3}

    for task_id, pipeline_run_id in ((777, 1000), (778, 1001)):
        await pipeline_service._record_stage_artifact(
            object(),
            doc=doc,
            task_id=task_id,
            pipeline_run_id=pipeline_run_id,
            stage="graph",
            status="done",
            started_at=datetime.now(timezone.utc),
            result=result,
            duration_ms=123,
        )

    assert len(input_hashes) == 2
    assert input_hashes[0] == input_hashes[1]


@pytest.mark.asyncio
async def test_source_validate_skips_office_lock_files(monkeypatch):
    async def fake_source_available(*_args, **_kwargs):
        return SimpleNamespace(available=True, physical_path=None)

    monkeypatch.setattr(source_validate_stage, "get_source_file_availability", fake_source_available)
    monkeypatch.setattr(source_validate_stage, "check_file_access", fake_source_available)

    db = _EmptyParseDb()
    db.doc.filename = "~$亚捷招商话术"
    db.doc.extension = "docx"

    result = await pipeline_service._run_stage(
        db,
        doc=db.doc,
        user_id=db.doc.owner_id,
        stage=pipeline_service.ROOT_STAGE,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "non_content_office_lock_file"
    assert db.doc.parse_status == "skipped"
    assert db.doc.vector_status == "skipped"
    assert db.doc.raw_status == "skipped"
    assert document_service.document_deep_pipeline_complete(db.doc) is True
    assert document_service.document_parse_allows_search(db.doc) is False


@pytest.mark.asyncio
async def test_source_validate_skips_windows_recycle_metadata_files(monkeypatch):
    async def fake_source_available(*_args, **_kwargs):
        return SimpleNamespace(available=True, physical_path=None)

    monkeypatch.setattr(source_validate_stage, "get_source_file_availability", fake_source_available)
    monkeypatch.setattr(source_validate_stage, "check_file_access", fake_source_available)

    db = _EmptyParseDb()
    db.doc.filename = "$IAH7BC8"
    db.doc.extension = "docx"

    result = await pipeline_service._run_stage(
        db,
        doc=db.doc,
        user_id=db.doc.owner_id,
        stage=pipeline_service.ROOT_STAGE,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "non_content_windows_recycle_metadata_file"
    assert db.doc.parse_status == "skipped"
    assert document_service.document_deep_pipeline_complete(db.doc) is True
    assert document_service.document_parse_allows_search(db.doc) is False


def test_appledouble_files_are_classified_from_header(tmp_path):
    appledouble = tmp_path / "metadata.docx"
    appledouble.write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X" + b"\x00" * 32)
    file_row = SimpleNamespace(name="metadata.docx", storage_path="aa/bb/metadata.docx")

    assert (
        source_file_state.classify_non_content_file(file_row, str(appledouble))
        == "non_content_appledouble_sidecar"
    )


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
async def test_parse_releases_stale_lock_owned_by_current_task(monkeypatch):
    async def empty_parse_document(*_args, **_kwargs):
        return _ParsedIr()

    monkeypatch.setattr(document_service, "parse_document", empty_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {"blocks": []})

    db = _StaleParseDbWithCurrentTask(task_id=777)
    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
        current_task_id=777,
    )

    assert result["status"] == "degraded"
    assert db.doc.parse_status == "degraded"
    assert db.doc.vector_status == "pending"
    assert db.doc.parse_worker_id == "user:1"


@pytest.mark.asyncio
async def test_parse_queue_task_releases_recent_lock_when_no_other_parse_task(monkeypatch):
    async def empty_parse_document(*_args, **_kwargs):
        return _ParsedIr()

    monkeypatch.setattr(document_service, "parse_document", empty_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {"blocks": []})

    db = _RecentParseDbWithCurrentTask(task_id=888)
    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
        current_task_id=888,
    )

    assert result["status"] == "degraded"
    assert db.doc.parse_status == "degraded"
    assert db.doc.vector_status == "pending"


@pytest.mark.asyncio
async def test_image_parse_index_skips_base_vectorization(monkeypatch):
    async def image_parse_document(*_args, **_kwargs):
        return _ParsedIr()

    async def fake_create_page_fusions(*_args, **_kwargs):
        return 1

    async def fail_chunk_and_embed(*_args, **_kwargs):
        raise AssertionError("image base blocks should not be embedded")

    monkeypatch.setattr(document_service, "parse_document", image_parse_document)
    monkeypatch.setattr(document_service, "to_legacy_dict", lambda _ir: {
        "blocks": [{"type": "图片", "text": "本地图片分析：海报轻摘要", "page": 1}]
    })
    monkeypatch.setattr(document_service, "create_page_fusions", fake_create_page_fusions)
    monkeypatch.setattr(document_service, "chunk_and_embed", fail_chunk_and_embed)

    db = _EmptyParseDb()
    db.doc.filename = "poster.jpg"
    db.doc.extension = "jpg"
    db.doc.mime_type = "image/jpeg"

    result = await document_service.parse_and_index_document(
        db,
        document_id=db.doc.id,
        owner_id=db.doc.owner_id,
        caller="user:1",
    )

    assert result["status"] == "degraded"
    assert result["stored_chunks"] == 0
    assert db.doc.parse_status == "degraded"
    assert db.doc.vector_status == "skipped"
    assert document_service.IMAGE_VECTOR_SKIPPED_MARKER in db.doc.parse_error
    assert document_service.document_parse_allows_search(db.doc) is True
    assert document_service.document_vector_stage_terminal(db.doc) is True


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
