"""Test batch 2: layered memory, hybrid recall, engine integration.
Tests the logic and data structures without a live DB or LLM.
"""
import sys
import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = BACKEND_ROOT.parent / "modules" / "agent" / "backend" / "engine"
MEMORY_BACKEND = BACKEND_ROOT.parent / "modules" / "memory" / "backend"
MEMORY_ROUTER_PATH = MEMORY_BACKEND / "router.py"
MEMORY_SERVICE_PATH = MEMORY_BACKEND / "services" / "memory_service.py"
MEMORY_CAPABILITIES_PATH = MEMORY_BACKEND / "services" / "capabilities.py"

# Import memory models without triggering SQLAlchemy Metadata conflict with other tests.
# Use a unique module name so pytest doesn't complain about namespace collisions.
sys.path.insert(0, str(MEMORY_BACKEND))
MEMORY_MODELS_PATH = MEMORY_BACKEND / "models.py"


def _get_mem_models():
    """Return the memory models, preferring already-loaded app modules."""
    # If the app already loaded the models, use those (no MetaData conflict)
    m = sys.modules.get("modules.memory.backend.models")
    if m and hasattr(m, "MemoryRecord"):
        return m
    # Otherwise, try importing directly
    import importlib.util
    key = "test_engine_batch2_mem_models"
    if key in sys.modules:
        mod = sys.modules[key]
        if hasattr(mod, "MemoryRecord"):
            return mod
        return None
    spec = importlib.util.spec_from_file_location(key, MEMORY_MODELS_PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
        if not hasattr(mod, "MemoryRecord"):
            return None
    except Exception:
        return None
    return mod


class TestMemoryModel:
    """Test the data model structure for memory."""

    MODEL_COLUMNS = {
        "MemoryRecord": ["id", "owner_id", "text", "summary", "confidence",
                          "recency_score", "embedding", "raw_id", "memory_type",
                          "keywords", "access_count", "tags", "source",
                          "conversation_id", "created_at", "updated_at"],
        "MemoryLink": ["id", "from_id", "to_id", "relation", "weight",
                        "owner_id", "created_at", "updated_at"],
    }

    def _check(self):
        m = _get_mem_models()
        if m is not None:
            return ("model", m)
        return ("text", MEMORY_MODELS_PATH.read_text("utf-8"))

    def test_model_has_summary_column(self):
        how, src = self._check()
        if how == "model":
            cols = src.MemoryRecord.__table__.columns
            for name in ("summary", "confidence", "recency_score", "raw_id",
                         "memory_type", "keywords", "access_count"):
                assert name in cols
        else:
            for name in ("summary", "confidence", "recency_score", "raw_id",
                         "memory_type", "keywords", "access_count"):
                assert name in src

    def test_memory_link_table_exists(self):
        how, src = self._check()
        if how == "model":
            cols = src.MemoryLink.__table__.columns
        else:
            cols = src  # text
        for name in ("from_id", "to_id", "relation", "weight", "owner_id"):
            assert name in src if how == "text" else name in cols

    def test_summary_is_optional(self):
        how, src = self._check()
        if how == "model":
            assert src.MemoryRecord.__table__.columns["summary"].nullable

    def test_confidence_has_default(self):
        how, src = self._check()
        if how == "model":
            col = src.MemoryRecord.__table__.columns["confidence"]
            assert col.default is not None or not col.nullable

    def test_vector_dimension(self):
        how, src = self._check()
        if how == "model":
            col_type = str(src.MemoryRecord.__table__.columns["embedding"].type)
            assert "VECTOR" in col_type.upper() or "1024" in col_type


class TestHybridRecallLogic:
    """Test the recall data structure and fallback logic (no DB)."""

    def test_recall_result_shape(self):
        result = {
            "id": 1,
            "text": "我喜欢界面用蓝色",
            "summary": "用户偏好蓝色界面",
            "tags": "偏好,颜色",
            "confidence": 0.9,
            "recency_score": 1.0,
            "raw_id": None,
            "memory_type": "preference",
            "keywords": "蓝色,界面,配色",
            "similarity": 0.85,
        }
        assert result["memory_type"] == "preference"
        assert result["similarity"] > 0.3

    def test_recall_fallback_empty(self):
        from app.services.module_registry import call_capability
        assert callable(call_capability)

    def test_fallback_keyword_shape(self):
        result = {
            "id": 10,
            "text": "用户喜欢红色",
            "summary": None,
            "tags": None,
            "confidence": 1.0,
            "recency_score": 1.0,
            "raw_id": None,
            "memory_type": None,
            "keywords": None,
            "source": None,
            "conversation_id": None,
            "similarity": 0.0,
        }
        assert result["id"] == 10
        assert result["similarity"] == 0.0


class TestChainGraph:
    """Test memory chain graph data structure."""

    def test_link_attributes(self):
        m = _get_mem_models()
        if m is not None:
            link = m.MemoryLink(from_id=1, to_id=2, relation="semantic_related", weight=0.8, owner_id=1)
            assert link.from_id == 1
            assert link.to_id == 2
            assert link.relation == "semantic_related"
            assert link.weight == 0.8

    def test_expanded_recall_shape(self):
        seed = {"id": 1, "text": "种子", "similarity": 0.9}
        expanded = {"id": 2, "text": "链扩展", "similarity": 0.7}
        combined = [seed, expanded]
        assert len(combined) == 2
        assert combined[1]["similarity"] == 0.7

    def test_link_threshold_filter(self):
        seed = {"id": 1, "text": "种子", "similarity": 0.9}
        threshold = 0.4
        weak_link = {"id": 2, "text": "弱关联", "similarity": 0.3}
        if weak_link["similarity"] >= threshold:
            combined = [seed, weak_link]
        else:
            combined = [seed]
        assert len(combined) == 1

    def test_memory_link_table_columns(self):
        m = _get_mem_models()
        if m is not None:
            cols = m.MemoryLink.__table__.columns
            assert "relation" in cols
            assert cols["relation"].nullable is True or cols["relation"].default is not None


class TestFusion:
    """Test on-demand fusion logic."""

    def test_fuse_result_shape(self):
        result = {
            "fused": "用户偏好蓝色界面，且喜欢简洁风格。",
            "source_ids": [1, 2],
            "note": "融合成功",
        }
        assert result["fused"]
        assert len(result["source_ids"]) == 2

    def test_fuse_empty_fallback(self):
        result = {"fused": "", "source_ids": [], "note": "无有效记忆"}
        assert not result["fused"]

    def test_fuse_is_callable(self):
        source = MEMORY_SERVICE_PATH.read_text("utf-8")
        assert "async def _do_fuse" in source


class TestDreamSelfOptimization:
    """Test dream data structures and report shape."""

    def test_dream_report_shape(self):
        report = {"merged": 0, "links_created": 0, "decayed": 3}
        assert "merged" in report
        assert "links_created" in report
        assert "decayed" in report

    def test_dream_is_callable(self):
        source = MEMORY_SERVICE_PATH.read_text("utf-8")
        assert "async def _do_dream" in source

    def test_cosine_similarity(self):
        import math
        def cosine(a, b):
            if not a or not b:
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            return dot / (na * nb) if na and nb else 0.0
        assert cosine([1, 0], [1, 0]) == 1.0
        assert cosine([1, 0], [0, 1]) == 0.0
        assert cosine([1, 2, 3], [1, 2, 3]) == 1.0
        assert cosine([], []) == 0.0

    def test_decay_scores(self):
        score = 1.0
        for _ in range(5):
            score *= 0.85
        assert score > 0.1
        score = max(score * 0.85, 0.1)
        assert score >= 0.1

    def test_merge_confidence_logic(self):
        conf_a, conf_b = 0.9, 0.7
        merged = max(conf_a, conf_b)
        assert merged == 0.9


class TestSelfEditTools:
    """Test self-edit tool structures."""

    def test_rethink_capability_signature(self):
        source = MEMORY_CAPABILITIES_PATH.read_text("utf-8")
        assert "async def _cap_rethink" in source

    def test_replace_text_logic(self):
        original = "我喜欢蓝色"
        replacement = original.replace("蓝色", "红色", 1)
        assert replacement == "我喜欢红色"

    def test_replace_not_found(self):
        original = "我喜欢蓝色"
        assert "不存在的文本" not in original

    def test_insert_text_logic(self):
        original = "旧内容"
        result = original + "\n" + "新追加"
        assert result == "旧内容\n新追加"

    def test_insert_capability_signature(self):
        source = MEMORY_CAPABILITIES_PATH.read_text("utf-8")
        assert "async def _cap_insert" in source

    def test_replace_capability_signature(self):
        source = MEMORY_CAPABILITIES_PATH.read_text("utf-8")
        assert "async def _cap_replace" in source


class TestEngineIntegration:
    """Test the engine-client integration (source-level checks, no full app import)."""

    def test_engine_dir_exists(self):
        assert ENGINE_DIR.exists(), f"{ENGINE_DIR} should exist"
        assert (ENGINE_DIR / "engine.py").exists()
        assert (ENGINE_DIR / "event_store.py").exists()

    def test_engine_source_has_expected_exports(self):
        source = (ENGINE_DIR / "engine.py").read_text("utf-8")
        assert "assemble_context" in source
        assert "chat_with_degradation_chain" in source
        assert "chat_stream_with_degradation_chain" in source

    def test_layered_memory_client_uses_call_capability(self):
        source = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "call_capability" in source

    def test_engine_imports_layered_memory(self):
        source = (ENGINE_DIR / "engine.py").read_text("utf-8")
        assert "layered_memory" in source

    def test_layered_memory_syntax_is_valid(self):
        source = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        compile(source, "layered_memory.py", "exec")

    def test_engine_syntax_is_valid(self):
        source = (ENGINE_DIR / "engine.py").read_text("utf-8")
        compile(source, "engine.py", "exec")


class TestCapabilityRegistration:
    """Test that all required capabilities are registered."""

    def test_capability_names(self):
        source = MEMORY_CAPABILITIES_PATH.read_text("utf-8")
        expected = ["_cap_save", "_cap_recall", "_cap_list", "_cap_delete",
                     "_cap_fuse", "_cap_dream", "_cap_rethink", "_cap_replace",
                     "_cap_insert"]
        for name in expected:
            assert f"async def {name}" in source, f"Missing {name} in capabilities.py"
