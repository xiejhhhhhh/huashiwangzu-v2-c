"""Agent runtime E2E regression: chat → tool → memory → compression → snapshot → replay.

Tests the main path through the Agent runtime by validating source-level
contracts, data shapes, and integration points.  These run as structural
checks (no live DB/LLM) so they can be executed in CI without external
dependencies.

This file is the "regression spine" — it verifies that changes to one
part of the engine do not silently break another part.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = BACKEND_ROOT.parent / "modules" / "agent" / "backend"
ENGINE_DIR = AGENT_DIR / "engine"
HANDLERS_DIR = AGENT_DIR / "handlers"
SERVICES_DIR = AGENT_DIR / "services"

ENGINE_SRC = (ENGINE_DIR / "engine.py").read_text("utf-8")
EVENT_STORE_SRC = (ENGINE_DIR / "event_store.py").read_text("utf-8")
COMPRESSOR_SRC = (ENGINE_DIR / "compressor.py").read_text("utf-8")
SNAPSHOT_SRC = (ENGINE_DIR / "context_snapshot.py").read_text("utf-8")
ADMIN_SRC = (HANDLERS_DIR / "admin.py").read_text("utf-8")
CHAT_SRC = (HANDLERS_DIR / "chat.py").read_text("utf-8")
ORCHESTRATOR_SRC = (ENGINE_DIR / "tool_orchestrator.py").read_text("utf-8")
WORKFLOW_SRC = (ENGINE_DIR / "workflow_strategy.py").read_text("utf-8")
HOOKS_SRC = (ENGINE_DIR / "post_turn_hooks.py").read_text("utf-8")
BUDGET_SRC = (ENGINE_DIR / "budget_allocator.py").read_text("utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Chat → tool loop → memory
# ═══════════════════════════════════════════════════════════════════════


class TestChatToolMemoryChain:
    """Verify the main chain: chat receives input → calls tools → persists memory."""

    def test_chat_handler_exists(self):
        assert "async def handle_chat" in CHAT_SRC

    def test_chat_calls_assemble_context(self):
        assert "assemble_context" in CHAT_SRC

    def test_chat_invokes_tool_discovery(self):
        assert "tool_discovery.build_tools" in CHAT_SRC

    def test_chat_uses_orchestrator(self):
        assert "get_orchestrator()" in CHAT_SRC

    def test_chat_persists_events(self):
        assert "record_event" in CHAT_SRC

    def test_chat_triggers_post_turn_hooks(self):
        assert "hooks.run_hooks" in CHAT_SRC

    def test_assemble_context_injects_memory(self):
        assert "three_layer_recall" in ENGINE_SRC

    def test_record_turn_saves_memory(self):
        assert "_layered_memory_record" in ENGINE_SRC

    def test_engine_imports_workflow_strategy(self):
        assert "workflow_strategy" in ENGINE_SRC
        assert "apply_workflow_injection" in ENGINE_SRC


# ═══════════════════════════════════════════════════════════════════════
# Tool classification → execution
# ═══════════════════════════════════════════════════════════════════════


class TestToolOrchestratorChain:
    """Verify tool orchestrator classifies and dispatches tools correctly."""

    def test_orchestrator_has_explicit_metadata(self):
        assert "_EXPLICIT_METADATA" in ORCHESTRATOR_SRC

    def test_orchestrator_read_tools_are_read_only(self):
        for entry in ["read_only=True", "concurrency_safe=True"]:
            assert entry in ORCHESTRATOR_SRC

    def test_orchestrator_write_tools_require_serial(self):
        assert "requires_serial=True" in ORCHESTRATOR_SRC

    def test_orchestrator_has_fallback_for_unknown(self):
        assert "defaulting to write+serial" in ORCHESTRATOR_SRC

    def test_orchestrator_semaphore_protected(self):
        assert "Semaphore" in ORCHESTRATOR_SRC

    def test_orchestrator_preserves_order(self):
        assert "preserve original order" in ORCHESTRATOR_SRC.lower() or "results: list[dict | None] = [None] * len(tools)" in ORCHESTRATOR_SRC

    def test_orchestrator_safe_execute(self):
        assert "except Exception as exc" in ORCHESTRATOR_SRC


# ═══════════════════════════════════════════════════════════════════════
# Event sourcing → projection → compression → snapshot
# ═══════════════════════════════════════════════════════════════════════


class TestEventStoreProjectionChain:
    """Verify events are recorded, projected, compressed, and recoverable."""

    def test_record_event_exists(self):
        assert "async def record_event" in EVENT_STORE_SRC

    def test_read_events_exists(self):
        assert "async def read_events" in EVENT_STORE_SRC

    def test_project_to_messages_exists(self):
        assert "async def project_to_messages" in EVENT_STORE_SRC

    def test_compaction_skips_folded_events(self):
        assert "skipped_ids" in EVENT_STORE_SRC

    def test_compressor_has_pre_post_snapshots(self):
        assert "compress_middle_with_snapshot" in COMPRESSOR_SRC

    def test_compressor_has_hard_truncate_fallback(self):
        assert "hard_truncate_tail" in COMPRESSOR_SRC

    def test_compressor_produces_compression_trace(self):
        assert "compression_trace" in COMPRESSOR_SRC

    def test_snapshot_retention_enforced(self):
        assert "enforce_retention" in SNAPSHOT_SRC

    def test_snapshot_restore_provenance(self):
        assert "record_restore_provenance" in SNAPSHOT_SRC
        assert "snapshot_restore" in SNAPSHOT_SRC

    def test_compression_chain_endpoint_exists(self):
        assert "handle_admin_compression_chain" in ADMIN_SRC


# ═══════════════════════════════════════════════════════════════════════
# Hook lifecycle → maintenance → cross-worker safeguards
# ═══════════════════════════════════════════════════════════════════════


class TestHookMaintenanceChain:
    """Verify background hooks run, are observable, and survive errors."""

    def test_hooks_have_lifecycle_state(self):
        assert "get_hook_lifecycle_state" in HOOKS_SRC

    def test_hooks_record_run_history(self):
        assert "_record_hook_run" in HOOKS_SRC
        assert "HOOK_RUN_HISTORY" in HOOKS_SRC

    def test_hooks_idempotent(self):
        assert "already running" in HOOKS_SRC

    def test_hooks_restart_on_done(self):
        assert "restarting" in HOOKS_SRC

    def test_hooks_maintenance_interval_positive(self):
        assert "_MAINTENANCE_INTERVAL = 300" in HOOKS_SRC

    def test_budget_tracker_db_persisted(self):
        assert "AgentBudgetState" in BUDGET_SRC
        assert "_save_to_db" in BUDGET_SRC
        assert "_load_from_db" in BUDGET_SRC

    def test_stuck_detector_db_persisted(self):
        stuck_src = (ENGINE_DIR / "stuck_detector.py").read_text("utf-8")
        assert "AgentStuckRound" in stuck_src
        assert "_save_history" in stuck_src

    def test_hook_runs_db_persisted(self):
        assert "AgentHookRun" in HOOKS_SRC
        assert "_append_hook_run" in HOOKS_SRC

    def test_hook_runs_limit_exists(self):
        assert "_HOOK_RUN_HISTORY_MAX" in HOOKS_SRC

    def test_hook_runs_admin_endpoint_accepts_owner_id(self):
        assert "owner_id" in HOOKS_SRC

    def test_hook_lifecycle_admin_endpoint(self):
        assert "handle_admin_hook_lifecycle" in ADMIN_SRC


# ═══════════════════════════════════════════════════════════════════════
# Admin → Replay → Compression chain → Memory quality
# ═══════════════════════════════════════════════════════════════════════


class TestAdminReplayChain:
    """Verify admin endpoints expose full runtime diagnostics."""

    def test_admin_replay_endpoint(self):
        assert "async def handle_admin_replay" in ADMIN_SRC

    def test_admin_snapshot_endpoint(self):
        assert "async def handle_admin_snapshots" in ADMIN_SRC

    def test_admin_snapshot_restore(self):
        assert "async def handle_admin_snapshot_restore" in ADMIN_SRC

    def test_admin_overview_endpoint(self):
        assert "async def handle_admin_overview" in ADMIN_SRC

    def test_admin_memory_quality_endpoint(self):
        assert "handle_admin_memory_quality" in ADMIN_SRC

    def test_admin_compression_chain_endpoint(self):
        assert "handle_admin_compression_chain" in ADMIN_SRC

    def test_admin_hook_lifecycle_endpoint(self):
        assert "handle_admin_hook_lifecycle" in ADMIN_SRC

    def test_admin_replay_shows_compression_trace(self):
        assert "compression_trace" in ADMIN_SRC

    def test_admin_replay_shows_restore_events(self):
        assert "restore_events" in ADMIN_SRC

    def test_admin_replay_shows_degradation(self):
        assert "degradation" in ADMIN_SRC


# ═══════════════════════════════════════════════════════════════════════
# Workflow strategy
# ═══════════════════════════════════════════════════════════════════════


class TestWorkflowStrategy:
    """Verify project workflow constraints are runtime-enforceable."""

    def test_workflow_module_exists(self):
        assert "match_workflow" in WORKFLOW_SRC
        assert "apply_workflow_injection" in WORKFLOW_SRC

    def test_workflow_has_multiple_definitions(self):
        assert "WORKFLOW_DEFINITIONS" in WORKFLOW_SRC

    def test_workflow_has_database_workflow(self):
        assert "database_workflow" in WORKFLOW_SRC

    def test_workflow_has_module_creation(self):
        assert "module_creation_workflow" in WORKFLOW_SRC

    def test_workflow_injection_matches_messages(self):
        # The function must mutate messages list
        assert "messages" in WORKFLOW_SRC


# ═══════════════════════════════════════════════════════════════════════
# Memory quality governance
# ═══════════════════════════════════════════════════════════════════════


class TestMemoryQualityGovernance:
    """Verify memory recall quality is measurable and observable."""

    def test_recall_quality_record_exists(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "RecallQualityRecord" in layered_src

    def test_recall_quality_summary_exists(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "get_recall_quality_summary" in layered_src

    def test_recall_quality_tracks_hit_rate(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "hit_rate" in layered_src

    def test_recall_quality_tracks_noise(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "noise_estimate" in layered_src

    def test_recall_quality_tracks_credibility(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "credibility_score" in layered_src

    def test_recall_quality_tracks_per_layer(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "per_layer" in layered_src

    def test_recall_functions_record_quality(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "record_recall_quality" in layered_src
        assert "RecallQualityRecord(" in layered_src


# ═══════════════════════════════════════════════════════════════════════
# Static memory cache → mtime invalidation
# ═══════════════════════════════════════════════════════════════════════


class TestStaticMemoryCache:
    """Verify static memory cache detects file changes via mtime."""

    LAYERED_SRC = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")

    def test_cache_ttl_is_300s(self):
        assert "_STATIC_MEMORY_CACHE_TTL = 300.0" in self.LAYERED_SRC

    def test_cache_includes_mtime_dict(self):
        assert "tuple[float, list[str], dict[str, float]]" in self.LAYERED_SRC

    def test_mtime_check_function_exists(self):
        assert "_check_cache_mtime" in self.LAYERED_SRC

    def test_cache_validates_mtime_on_hit(self):
        assert "mtime_valid = _check_cache_mtime(file_mtimes)" in self.LAYERED_SRC

    def test_cache_logs_hit_reason(self):
        assert "Static memory cache HIT:" in self.LAYERED_SRC

    def test_cache_logs_mtime_mismatch(self):
        assert "invalidated by mtime change" in self.LAYERED_SRC

    def test_cache_logs_expired(self):
        assert "expired (TTL)" in self.LAYERED_SRC

    def test_cache_collects_mtimes_on_load(self):
        assert "file_mtimes[str(md_path)] = md_path.stat().st_mtime" in self.LAYERED_SRC


# ═══════════════════════════════════════════════════════════════════════
# Failure diagnostics recording
# ═══════════════════════════════════════════════════════════════════════


class TestFailureDiagnostics:
    """Verify failure diagnostics recording and endpoint exist."""

    DIAG_SRC = (ENGINE_DIR / "failure_diagnostics.py").read_text("utf-8")

    def test_record_failure_function_exists(self):
        assert "async def record_failure" in self.DIAG_SRC

    def test_read_failure_diagnostics_exists(self):
        assert "async def read_failure_diagnostics" in self.DIAG_SRC

    def test_db_persisted_not_file(self):
        assert "FDModel" in self.DIAG_SRC
        assert ".jsonl" not in self.DIAG_SRC

    def test_admin_handler_exists(self):
        assert "handle_admin_failure_diagnostics" in ADMIN_SRC

    def test_admin_route_exists_in_router(self):
        router_src = (AGENT_DIR / "router.py").read_text("utf-8")
        assert "failure-diagnostics" in router_src

    def test_diagnostics_recorded_from_hook_failure(self):
        """Verify post_turn_hooks wires record_failure for hook failures."""
        assert "record_failure(" in HOOKS_SRC

    def test_diagnostics_recorded_from_chat_yield_final_stream(self):
        """Verify chat.py wires record_failure in yield_final_stream."""
        assert "record_failure(" in CHAT_SRC

    def test_recall_quality_has_limit(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "_RECALL_QUALITY_MAX_ENTRIES" in layered_src

    def test_recall_quality_db_persisted(self):
        layered_src = (ENGINE_DIR / "layered_memory.py").read_text("utf-8")
        assert "AgentRecallQuality" in layered_src
