"""Boundary regression tests for cross-module decoupling contracts.

Each test asserts a specific boundary rule that must not be violated.
These are read-only static analyses (no DB, no server).
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_file_transfer_no_knowledge_ingest_hardcode() -> None:
    """file_transfer.py must not hardcode 'knowledge' + 'ingest'."""
    source = _read("backend/app/routers/file_transfer.py")
    # The old hardcoded pattern was: call_capability("knowledge", "ingest", ...)
    # Now it should only emit_module_event, never reference 'knowledge'+'ingest'
    assert '"knowledge"' not in source or '"ingest"' not in source, (
        "file_transfer.py must not hardcode knowledge:ingest"
    )


def test_agent_admin_no_direct_memory_table_read() -> None:
    """agent admin.py must not reference memory module tables directly."""
    source = _read("modules/agent/backend/handlers/admin.py")
    forbidden = ["agent_memory", "memory_links", "agent_experiences"]
    for table in forbidden:
        assert table not in source, (
            f"admin.py must not directly reference '{table}' table"
        )


def test_memory_manifest_has_overview_stats() -> None:
    """memory manifest.json must declare overview_stats public action."""
    manifest = _read("modules/memory/manifest.json")
    assert "overview_stats" in manifest, (
        "memory manifest.json must declare 'overview_stats' public action"
    )


def test_memory_router_registers_overview_stats() -> None:
    """memory router.py must register overview_stats capability."""
    source = _read("modules/memory/backend/router.py")
    assert '"memory", "overview_stats"' in source or "'memory', 'overview_stats'" in source, (
        "memory router.py must register 'overview_stats' capability"
    )


def test_memory_router_overview_stats_min_role_admin() -> None:
    """memory overview_stats must have min_role='admin'."""
    source = _read("modules/memory/backend/router.py")
    assert "min_role=\"admin\"" in source or "min_role='admin'", (
        "memory overview_stats registration must require admin role"
    )


def test_knowledge_manifest_has_file_uploaded_event_handler() -> None:
    """knowledge manifest.json must declare file.uploaded event handler."""
    manifest = _read("modules/knowledge/manifest.json")
    assert "file.uploaded" in manifest, (
        "knowledge manifest.json must declare 'file.uploaded' event handler"
    )


def test_no_cross_module_import_in_non_sandbox_code() -> None:
    """Non-sandbox code must not import from other modules."""
    checks = [
        ("backend/app/routers/file_transfer.py", "from modules."),
        ("backend/app/services/app_service.py", "from modules."),
        ("modules/agent/backend/handlers/admin.py", "from modules."),
    ]
    for filepath, pattern in checks:
        source = _read(filepath)
        assert pattern not in source, (
            f"{filepath} must not use cross-module import pattern '{pattern}'"
        )
