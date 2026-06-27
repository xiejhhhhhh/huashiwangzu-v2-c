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
RUNTIME_DIR = AGENT_DIR / "runtime"
SERVICES_DIR = AGENT_DIR / "services"

ENGINE_SRC = (ENGINE_DIR / "engine.py").read_text("utf-8")
EVENT_STORE_SRC = (ENGINE_DIR / "event_store.py").read_text("utf-8")
COMPRESSOR_SRC = (ENGINE_DIR / "compressor.py").read_text("utf-8")
SNAPSHOT_SRC = (ENGINE_DIR / "context_snapshot.py").read_text("utf-8")
ADMIN_SRC = (HANDLERS_DIR / "admin.py").read_text("utf-8")
ROUTER_SRC = (AGENT_DIR / "router.py").read_text("utf-8")
CONVERSATION_RUNTIME_SRC = (RUNTIME_DIR / "conversation_runtime.py").read_text("utf-8")
TOOL_LOOP_RUNTIME_SRC = (RUNTIME_DIR / "tool_loop_runtime.py").read_text("utf-8")
ORCHESTRATOR_SRC = (ENGINE_DIR / "tool_orchestrator.py").read_text("utf-8")
WORKFLOW_SRC = (ENGINE_DIR / "workflow_strategy.py").read_text("utf-8")
HOOKS_SRC = (ENGINE_DIR / "post_turn_hooks.py").read_text("utf-8")
BUDGET_SRC = (ENGINE_DIR / "budget_allocator.py").read_text("utf-8")
MODELS_SRC = (AGENT_DIR / "models.py").read_text("utf-8")
INIT_SRC = (AGENT_DIR / "init_db.py").read_text("utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Chat → tool loop → memory
# ═══════════════════════════════════════════════════════════════════════


class TestChatToolMemoryChain:
    """Verify the main chain: chat receives input → calls tools → persists memory."""

    def test_chat_router_uses_conversation_runtime(self):
        assert "ConversationRuntime" in ROUTER_SRC
        assert "runtime.execute(payload, db, user)" in ROUTER_SRC

    def test_conversation_runtime_calls_assemble_context(self):
        assert "assemble_context" in CONVERSATION_RUNTIME_SRC

    def test_conversation_runtime_invokes_tool_discovery(self):
        assert "tool_discovery.build_tools" in CONVERSATION_RUNTIME_SRC

    def test_tool_loop_uses_orchestrator(self):
        assert "get_orchestrator()" in TOOL_LOOP_RUNTIME_SRC

    def test_conversation_runtime_persists_events(self):
        assert "record_event" in CONVERSATION_RUNTIME_SRC

    def test_tool_loop_triggers_post_turn_hooks(self):
        assert "run_post_turn_hooks" in TOOL_LOOP_RUNTIME_SRC

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

    def test_budget_tracker_file_persisted(self):
        assert "_BUDGET_DATA_FILE" in BUDGET_SRC
        assert "_save_budget_state" in BUDGET_SRC
        assert "_load_budget_state" in BUDGET_SRC

    def test_stuck_detector_file_persisted(self):
        stuck_src = (ENGINE_DIR / "stuck_detector.py").read_text("utf-8")
        assert "_SAVE_PATH" in stuck_src or "_STUCK_DATA_FILE" in stuck_src
        assert "tempfile.mkstemp" in stuck_src

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
# Edit-resubmit (soft-branch) — message inline edit
# ═══════════════════════════════════════════════════════════════════════


class TestEditResubmitChain:
    """Verify the edit-resubmit (soft branch) feature is wired correctly."""

    CONV_SVC_SRC = (SERVICES_DIR / "conversation_service.py").read_text("utf-8")

    def test_edit_and_resubmit_function_exists(self):
        assert "async def edit_and_resubmit" in self.CONV_SVC_SRC

    def test_archive_messages_after_exists(self):
        assert "async def archive_messages_after" in self.CONV_SVC_SRC

    def test_invalidate_checkpoints_after_exists(self):
        assert "async def invalidate_checkpoints_after" in self.CONV_SVC_SRC

    def test_get_messages_filters_by_status(self):
        assert "AgentMessage.status == status" in self.CONV_SVC_SRC or 'status="active"' in self.CONV_SVC_SRC

    def test_count_conversation_messages_filters_active(self):
        assert 'AgentMessage.status == "active"' in self.CONV_SVC_SRC

    def test_agent_message_has_status_field(self):
        assert 'status: Mapped[str] = mapped_column(String(16), default="active"' in MODELS_SRC

    def test_agent_message_has_edited_from_field(self):
        assert "edited_from_message_id" in MODELS_SRC

    def test_agent_message_has_branch_root_field(self):
        assert "branch_root_message_id" in MODELS_SRC

    def test_router_has_edit_resubmit_endpoint(self):
        assert "edit-resubmit" in ROUTER_SRC
        assert "edit_resubmit" in ROUTER_SRC

    def test_router_uses_edit_resubmit_request(self):
        assert "EditResubmitRequest" in ROUTER_SRC

    def test_conversation_runtime_has_execute_edit_resubmit(self):
        assert "async def execute_edit_resubmit" in CONVERSATION_RUNTIME_SRC

    def test_conversation_runtime_calls_edit_and_resubmit(self):
        assert "edit_and_resubmit" in CONVERSATION_RUNTIME_SRC

    def test_conversation_runtime_rerecords_edited_user_event(self):
        assert '"user_msg"' in CONVERSATION_RUNTIME_SRC
        assert "edited_message_id" in CONVERSATION_RUNTIME_SRC

    def test_event_store_delete_events_after_supports_inclusive(self):
        assert "inclusive" in EVENT_STORE_SRC

    def test_schemas_has_edit_resubmit_request(self):
        schemas_src = (AGENT_DIR / "schemas.py").read_text("utf-8")
        assert "class EditResubmitRequest" in schemas_src

    def test_message_meta_accepts_usage(self):
        assert "usage:" in MODELS_SRC
        assert "usage: dict | None = None" in self.CONV_SVC_SRC
        assert "ensure_message_meta_usage_column" in INIT_SRC

    def test_frontend_index_uses_new_endpoint(self):
        frontend_src = (AGENT_DIR.parent / "frontend" / "index.vue").read_text("utf-8")
        assert "edit-resubmit" in frontend_src

    def test_frontend_has_shared_stream_processor(self):
        frontend_src = (AGENT_DIR.parent / "frontend" / "index.vue").read_text("utf-8")
        assert "processStreamResponse" in frontend_src

    def test_init_db_has_message_status_migration(self):
        assert "ensure_message_status_column" in INIT_SRC
        assert "edited_from_message_id" in INIT_SRC or "ADD COLUMN IF NOT EXISTS status" in INIT_SRC
