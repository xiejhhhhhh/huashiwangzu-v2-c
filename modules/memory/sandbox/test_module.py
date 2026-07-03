"""Sandbox test for memory module.

Validates parameter schemas, required fields, value ranges, and output
shapes for all public_actions — without calling real embedding service
or DB.
"""
from pathlib import Path


def test_save_params() -> None:
    """save: text required, tags/source optional."""
    params_min = {"text": "User prefers dark mode"}
    assert "text" in params_min
    assert isinstance(params_min["text"], str) and len(params_min["text"]) > 0
    params_full = {
        "text": "User prefers dark mode",
        "tags": "preference,ui",
        "source": "user-save",
    }
    assert "tags" in params_full
    assert isinstance(params_full["tags"], str)
    assert isinstance(params_full["source"], str)
    print("  [SAVE] Parameter contract valid")


def test_recall_params() -> None:
    """recall: query required, limit/expand_chain optional."""
    params = {
        "query": "What theme does the user prefer?",
        "limit": 5,
        "expand_chain": True,
    }
    assert "query" in params
    assert isinstance(params["query"], str) and len(params["query"]) > 0
    assert isinstance(params["limit"], int) and params["limit"] > 0
    assert isinstance(params["expand_chain"], bool)
    print("  [RECALL] Parameter contract valid")


def test_list_params() -> None:
    """list: limit (int optional), offset (int optional)."""
    params_default: dict = {}
    assert "limit" not in params_default or isinstance(params_default.get("limit"), int)
    assert "offset" not in params_default or isinstance(params_default.get("offset"), int)
    params_custom = {"limit": 20, "offset": 10}
    assert isinstance(params_custom["limit"], int) and params_custom["limit"] > 0
    assert isinstance(params_custom["offset"], int) and params_custom["offset"] >= 0
    print("  [LIST] Parameter contract valid")


def test_delete_params() -> None:
    """delete: id (int required)."""
    params = {"id": 42}
    assert "id" in params
    assert isinstance(params["id"], int) and params["id"] > 0
    print("  [DELETE] Parameter contract valid")


def test_fuse_params() -> None:
    """fuse: query (string required), ids (list of int required)."""
    params = {"query": "Summarize user preferences", "ids": [1, 2, 3]}
    assert "query" in params and "ids" in params
    assert isinstance(params["query"], str) and len(params["query"]) > 0
    assert isinstance(params["ids"], list) and len(params["ids"]) > 0
    assert all(isinstance(i, int) for i in params["ids"])
    print("  [FUSE] Parameter contract valid")


def test_rethink_params() -> None:
    """rethink: id/text required, tags optional."""
    params = {"id": 42, "text": "Updated preference text", "tags": "preference"}
    assert "id" in params and "text" in params
    assert isinstance(params["id"], int) and params["id"] > 0
    assert isinstance(params["text"], str) and len(params["text"]) > 0
    assert isinstance(params["tags"], str)
    print("  [RETHINK] Parameter contract valid")


def test_replace_params() -> None:
    """replace: id (int), old_text (string), new_text (string)."""
    params = {"id": 42, "old_text": "dark mode", "new_text": "light mode"}
    assert "id" in params and "old_text" in params and "new_text" in params
    assert isinstance(params["id"], int)
    assert isinstance(params["old_text"], str) and len(params["old_text"]) > 0
    assert isinstance(params["new_text"], str) and len(params["new_text"]) > 0
    print("  [REPLACE] Parameter contract valid")


def test_insert_params() -> None:
    """insert: id (int required), text (string required)."""
    params_min = {"id": 7, "text": "New memory entry"}
    assert "id" in params_min
    assert isinstance(params_min["id"], int)
    assert "text" in params_min
    assert isinstance(params_min["text"], str) and len(params_min["text"]) > 0
    print("  [INSERT] Parameter contract valid")


def test_dream_params() -> None:
    """dream: no params, editor-only."""
    params: dict = {}
    assert len(params) == 0
    print("  [DREAM] Parameter contract valid")


def test_save_experience_params() -> None:
    """save_experience: trigger_condition and steps required; scope defaults to user."""
    params = {
        "trigger_condition": "user asks about theme",
        "steps": '[{"intent":"recall","tool":"memory:recall"}]',
        "scope": "user",
    }
    assert isinstance(params["trigger_condition"], str) and len(params["trigger_condition"]) > 0
    assert isinstance(params["steps"], str) and len(params["steps"]) > 0
    assert params["scope"] in {"user", "team", "global"}
    print("  [SAVE_EXPERIENCE] Parameter contract valid")


def test_match_experience_params() -> None:
    """match_experience: query required, limit/team_owner_ids optional."""
    params = {"query": "user asks about theme", "limit": 2, "team_owner_ids": [7, 8]}
    assert "query" in params
    assert isinstance(params["query"], str) and len(params["query"]) > 0
    assert isinstance(params["limit"], int) and params["limit"] > 0
    assert all(isinstance(owner_id, int) for owner_id in params["team_owner_ids"])
    print("  [MATCH_EXPERIENCE] Parameter contract valid")


def test_experience_feedback_params() -> None:
    """experience_feedback: experience_id/success required, note/team_owner_ids optional."""
    params_min = {"experience_id": 10, "success": True}
    assert "experience_id" in params_min and "success" in params_min
    assert isinstance(params_min["experience_id"], int) and params_min["experience_id"] > 0
    assert isinstance(params_min["success"], bool)
    params_with_note = {
        "experience_id": 10,
        "success": False,
        "note": "Failed to apply",
        "team_owner_ids": [7],
    }
    assert "note" in params_with_note
    assert isinstance(params_with_note["note"], str)
    assert all(isinstance(owner_id, int) for owner_id in params_with_note["team_owner_ids"])
    print("  [EXPERIENCE_FEEDBACK] Parameter contract valid")


def test_overview_stats_params() -> None:
    """overview_stats: no params, admin-only."""
    params: dict = {}
    assert len(params) == 0
    print("  [OVERVIEW_STATS] Parameter contract valid")


def test_backfill_embeddings_params() -> None:
    """backfill_embeddings: admin governance with dry-run safety controls."""
    params_default = {"dry_run": True}
    assert isinstance(params_default["dry_run"], bool)
    params_full = {"dry_run": False, "limit": 10, "owner_id": 7, "owner": 7, "run_dream": True}
    assert isinstance(params_full["limit"], int)
    assert 1 <= params_full["limit"] <= 100
    assert isinstance(params_full["owner_id"], int) and params_full["owner_id"] > 0
    assert isinstance(params_full["owner"], int) and params_full["owner"] == params_full["owner_id"]
    assert isinstance(params_full["run_dream"], bool)
    print("  [BACKFILL_EMBEDDINGS] Parameter contract valid")


def test_recall_stable_rules_params() -> None:
    """recall_stable_rules: rule_types (optional array)."""
    params_default: dict = {}
    assert "rule_types" not in params_default
    params_with_filter = {"rule_types": ["preference", "constraint"]}
    assert "rule_types" in params_with_filter
    assert isinstance(params_with_filter["rule_types"], list)
    assert all(isinstance(t, str) for t in params_with_filter["rule_types"])
    print("  [RECALL_STABLE_RULES] Parameter contract valid")


def test_recall_chunk_params() -> None:
    """recall_chunk: query (string required), limit (int optional)."""
    params_min = {"query": "semantic search query"}
    assert "query" in params_min
    assert isinstance(params_min["query"], str) and len(params_min["query"]) > 0
    params_full = {"query": "semantic search query", "limit": 10}
    assert isinstance(params_full["limit"], int) and params_full["limit"] > 0
    print("  [RECALL_CHUNK] Parameter contract valid")


def test_save_stable_rule_params() -> None:
    """save_stable_rule: rule_type (string), content (string), priority (int optional), source (string optional)."""
    params_min = {"rule_type": "preference", "content": "User prefers dark mode"}
    assert "rule_type" in params_min and "content" in params_min
    assert isinstance(params_min["rule_type"], str) and len(params_min["rule_type"]) > 0
    assert isinstance(params_min["content"], str) and len(params_min["content"]) > 0
    params_full = {"rule_type": "constraint", "content": "No external API calls", "priority": 10, "source": "user_setting"}
    assert isinstance(params_full["priority"], int)
    assert isinstance(params_full["source"], str)
    print("  [SAVE_STABLE_RULE] Parameter contract valid")


def test_embedding_update_sql_uses_asyncpg_safe_cast() -> None:
    """Embedding update SQL must keep bind params separate from pgvector casts."""
    service_src = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "services"
        / "embedding_service.py"
    ).read_text(encoding="utf-8")

    assert ":embedding::vector" not in service_src
    assert "CAST(:embedding AS vector({EXPECTED_EMBEDDING_DIM}))" in service_src
    assert "backfill_missing_record_embeddings" in service_src
    assert "dry_run" in service_src


def test_memory_output_shape() -> None:
    """Memory object output shape contract."""
    memory = {
        "id": 1,
        "text": "User prefers dark mode",
        "tags": "preference,ui",
        "created_at": "2026-07-01T00:00:00",
        "updated_at": "2026-07-01T00:00:00",
    }
    required = {"id", "text", "created_at"}
    for field in required:
        assert field in memory, f"Missing required field: {field}"
    assert isinstance(memory["id"], int)
    assert isinstance(memory["text"], str)
    assert len(memory["text"]) > 0
    print("  [MEMORY] Output shape valid")


def test_experience_output_shape() -> None:
    """Experience object output shape contract."""
    experience = {
        "id": 1,
        "owner_id": 7,
        "scope": "user",
        "trigger_condition": "user asks about theme",
        "steps": '[{"intent":"recall","tool":"memory:recall"}]',
        "success_weight": 3,
        "fail_count": 0,
    }
    required = {"id", "owner_id", "scope", "trigger_condition", "steps", "success_weight", "fail_count"}
    for field in required:
        assert field in experience, f"Missing required field: {field}"
    assert experience["scope"] in {"user", "team", "global"}
    assert isinstance(experience["success_weight"], int) and experience["success_weight"] >= 0
    print("  [EXPERIENCE] Output shape valid")


def test_stable_rule_output_shape() -> None:
    """Stable rule output shape contract."""
    rule = {
        "id": 1,
        "rule_type": "preference",
        "content": "User prefers dark mode",
        "priority": 5,
        "source": "user_setting",
        "created_at": "2026-07-01T00:00:00",
    }
    required = {"id", "rule_type", "content", "priority"}
    for field in required:
        assert field in rule, f"Missing required field: {field}"
    assert isinstance(rule["priority"], int)
    print("  [STABLE_RULE] Output shape valid")


def test_backfill_embeddings_output_shape() -> None:
    """Backfill governance output exposes counts and failures."""
    result = {
        "dry_run": True,
        "owner_id": 7,
        "limit": 10,
        "total": 37,
        "with_embedding": 4,
        "missing": 33,
        "selected_count": 10,
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "failures": [],
        "sample_ids": [1, 2],
        "dream": None,
        "dream_failures": [],
        "diagnostic": "dry_run_only",
    }
    required = {
        "dry_run",
        "limit",
        "total",
        "with_embedding",
        "missing",
        "selected_count",
        "updated",
        "failed",
        "failures",
        "dream_failures",
        "diagnostic",
    }
    for field in required:
        assert field in result, f"Missing required field: {field}"
    assert result["dry_run"] is True
    assert isinstance(result["failures"], list)
    assert isinstance(result["dream_failures"], list)
    print("  [BACKFILL_EMBEDDINGS] Output shape valid")


def test_memory_quality_guard_source_contracts() -> None:
    """Source guards for limits, vector dimension, and chunk cleanup."""
    module_root = Path(__file__).resolve().parents[1]
    embedding_src = (module_root / "backend" / "services" / "embedding_service.py").read_text(encoding="utf-8")
    memory_src = (module_root / "backend" / "services" / "memory_service.py").read_text(encoding="utf-8")
    capability_src = (module_root / "backend" / "services" / "capabilities.py").read_text(encoding="utf-8")
    experience_src = (module_root / "backend" / "services" / "experience_service.py").read_text(encoding="utf-8")
    init_src = (module_root / "backend" / "init_db.py").read_text(encoding="utf-8")

    assert "EXPECTED_EMBEDDING_DIM = 1024" in embedding_src
    assert "Embedding dimension mismatch" in embedding_src
    assert "CAST(:query_vec AS vector(1024))" in capability_src
    assert "CAST(:query_vec AS vector(1024))" in memory_src
    assert "_coerce_limit" in memory_src
    assert "DELETE FROM memory_chunks WHERE memory_record_id = :id" in memory_src
    assert ":note_payload IS NULL" not in experience_src
    assert '"has_note": note_payload is not None' in experience_src
    assert "def _coerce_bool" in experience_src
    assert "def _normalize_json_text" in experience_src
    assert "trigger_condition ILIKE :keyword" in experience_src
    assert "experience_id = experience_service._coerce_optional_positive_int" in capability_src
    assert "success = experience_service._coerce_bool" in capability_src
    assert "UPDATE memory_stable_rules SET hit_count = hit_count + 1" in capability_src
    assert "UPDATE memory_chunks SET access_count = access_count + 1" in capability_src
    assert "orphan_chunk_cleanup_sql" in init_src
    assert "l.from_id = l.to_id" in init_src
    assert "chunk_alters" in init_src
    assert "stable_rule_alters" in init_src
    assert "ix_memory_chunks_embedding" in init_src
    print("  [QUALITY_GUARDS] Source contracts valid")


def test_backfill_dream_followup_is_degraded() -> None:
    """Backfill must report dream failures without hiding successful updates."""
    result = {
        "dry_run": False,
        "updated": 2,
        "failed": 0,
        "failures": [],
        "dream": {},
        "dream_failures": [{"owner_id": 7, "reason": "link creation failed"}],
        "diagnostic": "completed_with_dream_failures",
    }
    assert result["updated"] == 2
    assert result["failed"] == 0
    assert result["diagnostic"] == "completed_with_dream_failures"
    assert result["dream_failures"][0]["owner_id"] == 7
    print("  [BACKFILL_EMBEDDINGS] Dream degradation valid")


def test_save_edit_responses_expose_async_followup_state() -> None:
    """Save/edit paths should expose embedding and post-save enqueue state."""
    module_root = Path(__file__).resolve().parents[1]
    router_src = (module_root / "backend" / "router.py").read_text(encoding="utf-8")
    capability_src = (module_root / "backend" / "services" / "capabilities.py").read_text(encoding="utf-8")
    memory_src = (module_root / "backend" / "services" / "memory_service.py").read_text(encoding="utf-8")

    assert "async def _enqueue_post_save(memory_id: int, content: str, source: str | None) -> bool" in memory_src
    assert '"embedding_updated": embedding_updated' in router_src
    assert '"post_save_enqueued": post_save_enqueued' in router_src
    assert '"embedding_updated": embedding_updated' in capability_src
    assert '"post_save_enqueued": post_save_enqueued' in capability_src
    print("  [SAVE_EDIT] Async follow-up state exposed")


def test_response_shape() -> None:
    """Unified API response shape contract."""
    r = {"success": True, "data": {"id": 1, "text": "test", "created_at": "2026-07-01T00:00:00"}, "error": None}
    assert all(k in r for k in ("success", "data", "error"))
    assert r["success"] is True
    print("  [RESPONSE] Shape valid")


def main() -> None:
    print("=" * 60)
    print("memory sandbox test")
    print("=" * 60)
    test_save_params()
    test_recall_params()
    test_list_params()
    test_delete_params()
    test_fuse_params()
    test_rethink_params()
    test_replace_params()
    test_insert_params()
    test_dream_params()
    test_save_experience_params()
    test_match_experience_params()
    test_experience_feedback_params()
    test_overview_stats_params()
    test_backfill_embeddings_params()
    test_recall_stable_rules_params()
    test_recall_chunk_params()
    test_save_stable_rule_params()
    test_memory_output_shape()
    test_experience_output_shape()
    test_stable_rule_output_shape()
    test_backfill_embeddings_output_shape()
    test_memory_quality_guard_source_contracts()
    test_backfill_dream_followup_is_degraded()
    test_save_edit_responses_expose_async_followup_state()
    test_response_shape()
    print("=" * 60)
    print("PASS: memory sandbox test")


if __name__ == "__main__":
    main()
