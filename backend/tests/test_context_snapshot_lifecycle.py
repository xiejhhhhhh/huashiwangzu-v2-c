"""Test context snapshot lifecycle: list, restore, retention, admin fields.

Verifies snapshot management operations and the admin display fields
without a live database — uses source-level checks and data-structure
tests.
"""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
AGENT_ENGINE = BACKEND_ROOT.parent / "modules" / "agent" / "backend" / "engine"
AGENT_HANDLERS = BACKEND_ROOT.parent / "modules" / "agent" / "backend" / "handlers"
SNAPSHOT_SRC = (AGENT_ENGINE / "context_snapshot.py").read_text("utf-8")
ADMIN_SRC = (AGENT_HANDLERS / "admin.py").read_text("utf-8")


class TestSnapshotAdminFields:
    """Verify admin display fields for snapshot list/restore."""

    def test_snapshot_type_field(self):
        """Snapshot list must include snapshot_type."""
        assert "snapshot_type" in SNAPSHOT_SRC

    def test_event_boundaries_field(self):
        """Snapshot must have event_id_before and event_id_after."""
        assert "event_id_before" in SNAPSHOT_SRC
        assert "event_id_after" in SNAPSHOT_SRC

    def test_compression_ratio_field(self):
        """Snapshot must have compression_ratio."""
        assert "compression_ratio" in SNAPSHOT_SRC

    def test_restored_from_field(self):
        """Snapshot must have restored_from field."""
        assert "restored_from" in SNAPSHOT_SRC

    def test_message_counts_field(self):
        """Snapshot must have message count fields."""
        assert "message_count_before" in SNAPSHOT_SRC
        assert "message_count_after" in SNAPSHOT_SRC

    def test_token_estimates_field(self):
        """Snapshot must have token estimate fields."""
        assert "token_estimate_before" in SNAPSHOT_SRC
        assert "token_estimate_after" in SNAPSHOT_SRC


class TestSnapshotList:
    """Verify list_snapshots returns correct data."""

    def test_list_snapshots_exists(self):
        """list_snapshots must be defined."""
        assert "async def list_snapshots" in SNAPSHOT_SRC

    def test_list_snapshots_returns_list(self):
        """list_snapshots must return a list."""
        assert "return list(r.scalars().all())" in SNAPSHOT_SRC

    def test_list_snapshots_ordered(self):
        """list_snapshots must order by newest first."""
        assert "order_by(desc(ContextSnapshot.id))" in SNAPSHOT_SRC

    def test_list_snapshots_has_limit(self):
        """list_snapshots must accept a limit parameter."""
        assert "limit(limit)" in SNAPSHOT_SRC or ".limit(limit)" in SNAPSHOT_SRC


class TestSnapshotRestore:
    """Verify restore_snapshot produces audit trail."""

    def test_restore_snapshot_exists(self):
        """restore_snapshot must be defined."""
        assert "async def restore_snapshot" in SNAPSHOT_SRC

    def test_restore_records_provenance(self):
        """restore_snapshot must call record_restore_provenance."""
        assert "record_restore_provenance" in SNAPSHOT_SRC

    def test_restore_provenance_exists(self):
        """record_restore_provenance must be defined."""
        assert "async def record_restore_provenance" in SNAPSHOT_SRC

    def test_restore_provenance_writes_event(self):
        """record_restore_provenance must call record_event with snapshot_restore type."""
        assert "snapshot_restore" in SNAPSHOT_SRC

    def test_restore_provenance_includes_snapshot_id(self):
        """Restore provenance event must include snapshot_id."""
        assert "snapshot_id" in SNAPSHOT_SRC

    def test_restore_returns_messages(self):
        """restore_snapshot must return a list of messages."""
        assert "return data" in SNAPSHOT_SRC or "return []" in SNAPSHOT_SRC

    def test_restore_handles_missing_snapshot(self):
        """restore_snapshot must return empty list for missing snapshot."""
        assert "return []" in SNAPSHOT_SRC


class TestSnapshotRetention:
    """Verify retention policy enforcement."""

    def test_enforce_retention_exists(self):
        """enforce_retention must be defined."""
        assert "async def enforce_retention" in SNAPSHOT_SRC

    def test_enforce_retention_returns_pruned_count(self):
        """enforce_retention must return dict with pruned count."""
        assert "pruned" in SNAPSHOT_SRC

    def test_periodic_retention_limit(self):
        """Periodic retention must cap at MAX_PERIODIC_PER_CONVERSATION."""
        assert "MAX_PERIODIC_PER_CONVERSATION" in SNAPSHOT_SRC
        assert "periodic" in SNAPSHOT_SRC
        assert ".offset(max_keep)" in SNAPSHOT_SRC

    def test_compress_retention_limit(self):
        """Compress retention must cap at MAX_COMPRESS_PAIRS."""
        assert "MAX_COMPRESS_PAIRS" in SNAPSHOT_SRC
        assert "pre_compress" in SNAPSHOT_SRC
        assert "post_compress" in SNAPSHOT_SRC

    def test_get_latest_snapshot_exists(self):
        """get_latest_snapshot must be defined."""
        assert "async def get_latest_snapshot" in SNAPSHOT_SRC

    def test_count_snapshots_exists(self):
        """count_snapshots must be defined."""
        assert "async def count_snapshots" in SNAPSHOT_SRC


class TestAdminEndpoints:
    """Verify admin snapshot endpoints exist in the admin handler."""

    def test_admin_snapshots_handler_exists(self):
        """Admin handler must define handle_admin_snapshots."""
        assert "async def handle_admin_snapshots" in ADMIN_SRC

    def test_admin_snapshot_restore_handler_exists(self):
        """Admin handler must define handle_admin_snapshot_restore."""
        assert "async def handle_admin_snapshot_restore" in ADMIN_SRC

    def test_admin_snapshot_fields_complete(self):
        """Admin snapshot response must include all display fields."""
        display_fields = [
            '"snapshot_type"',
            '"event_id_before"',
            '"event_id_after"',
            '"message_count_before"',
            '"message_count_after"',
            '"token_estimate_before"',
            '"token_estimate_after"',
            '"compression_ratio"',
            '"restored_from"',
            '"summary"',
            '"created_at"',
        ]
        for field in display_fields:
            assert field in ADMIN_SRC, f"Admin snapshot response missing field: {field}"

    def test_admin_snapshot_restore_fields(self):
        """Admin snapshot restore response must include key metadata."""
        restore_fields = [
            '"snapshot_id"',
            '"restored_messages"',
            '"snapshot_type"',
            '"compression_ratio"',
            '"event_id_before"',
            '"event_id_after"',
        ]
        for field in restore_fields:
            assert field in ADMIN_SRC, f"Admin snapshot restore response missing field: {field}"


class TestPostTurnHooksLifecycle:
    """Verify post-turn hooks lifecycle is well-defined."""

    SRC = (AGENT_ENGINE / "post_turn_hooks.py").read_text("utf-8")

    def test_setup_global_hooks_starts_background_task(self):
        """setup_global_hooks must create a background asyncio task."""
        assert "asyncio.create_task" in self.SRC

    def test_setup_global_hooks_has_maintenance_loop(self):
        """setup_global_hooks must have a maintenance loop."""
        assert "_maintenance_loop" in self.SRC
        assert "_run_global_retention" in self.SRC

    def test_background_retention_calls_enforce_retention(self):
        """_run_global_retention must call context_snapshot.enforce_retention."""
        assert "enforce_retention" in self.SRC

    def test_background_retention_queries_all_conversations(self):
        """_run_global_retention must query all distinct conversation_ids."""
        assert "SELECT DISTINCT conversation_id" in self.SRC

    def test_background_retention_error_handling(self):
        """_run_global_retention must handle per-conversation errors non-fatally."""
        assert "logger.warning(\"Global retention: conv=%s failed" in self.SRC

    def test_maintenance_loop_restarts_after_exception(self):
        """Maintenance loop must catch exceptions and continue."""
        assert "logger.exception(\"Maintenance loop iteration failed" in self.SRC

    def test_setup_global_hooks_is_idempotent(self):
        """setup_global_hooks must skip re-creation if task already running."""
        assert "already running" in self.SRC

    def test_get_hooks_triggers_setup_global_hooks(self):
        """engine.get_hooks() must call setup_global_hooks on first access."""
        engine_src = (AGENT_ENGINE / "engine.py").read_text("utf-8")
        assert "setup_global_hooks()" in engine_src
