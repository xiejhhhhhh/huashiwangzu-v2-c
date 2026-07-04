from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest

from dev_toolkit import db_reverse_tools

pytest.importorskip("mcp")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path
    toolkit_dir = repo / "dev_toolkit"
    toolkit_dir.mkdir()
    (toolkit_dir / "config.local.json").write_text(
        json.dumps({"db_dsn": "postgresql://readonly/test"}),
        encoding="utf-8",
    )

    knowledge_backend = repo / "modules" / "knowledge" / "backend"
    knowledge_backend.mkdir(parents=True)
    (knowledge_backend.parent / "manifest.json").write_text(
        json.dumps({"public_actions": [{"action": "search"}]}),
        encoding="utf-8",
    )
    (knowledge_backend / "router.py").write_text(
        "from app.services.module_registry import register_capability\n"
        "TABLE = 'kb_documents'\n"
        "register_capability('knowledge', 'search', object())\n",
        encoding="utf-8",
    )

    image_backend = repo / "modules" / "image-gen" / "backend"
    image_backend.mkdir(parents=True)
    (image_backend.parent / "manifest.json").write_text(
        json.dumps({"public_actions": [{"action": "generate"}]}),
        encoding="utf-8",
    )
    (image_backend / "router.py").write_text(
        "from app.services.module_registry import register_capability\n"
        "TABLE = 'imagegen_records'\n"
        "register_capability('image-gen', 'generate', object())\n",
        encoding="utf-8",
    )

    backend_app = repo / "backend" / "app"
    backend_app.mkdir(parents=True)
    (backend_app / "files.py").write_text("TABLE = 'framework_file_shares'\n", encoding="utf-8")
    return repo


def test_db_reverse_audit_classifies_empty_tables_without_real_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _make_repo(tmp_path)
    counts = {
        "framework_file_shares": 0,
        "kb_documents": 0,
        "legacy_unused": 0,
        "imagegen_records": 12,
    }

    async def fake_execute_sql(
        query: str,
        *,
        dsn: str | None = None,
        columns: Any = None,
        timeout: int = 60,
    ) -> list[dict[str, Any]]:
        assert dsn == "postgresql://readonly/test"
        if "information_schema.tables" in query:
            return [{"table_name": table} for table in counts]
        for table, count in counts.items():
            if f'"{table}"' in query:
                return [{"count": str(count)}]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(db_reverse_tools, "_execute_sql", fake_execute_sql)

    result = anyio.run(db_reverse_tools.db_reverse_audit, repo)

    assert result["success"] is True
    assert result["read_only"] is True
    assert result["table_count"] == 4
    assert [row["table"] for row in result["non_empty_tables"]] == ["imagegen_records"]

    expected_empty = {row["table"] for row in result["expected_empty"]}
    requires_probe = {row["table"] for row in result["requires_flow_probe"]}
    suspicious = {row["table"] for row in result["suspicious_empty"]}

    assert "framework_file_shares" in expected_empty
    assert "kb_documents" in requires_probe
    assert "legacy_unused" in suspicious

    shares = next(row for row in result["tables"] if row["table"] == "framework_file_shares")
    assert shares["issues"] == []

    kb = next(row for row in result["tables"] if row["table"] == "kb_documents")
    assert kb["likely_owner"]["module"] == "knowledge"
    assert kb["module_hint"]["has_router"] is True
    assert kb["module_hint"]["has_capability_registration"] is True
    assert kb["code_reference_count"] >= 1
    assert "call_capability" in kb["next_probe"]

    legacy = next(row for row in result["tables"] if row["table"] == "legacy_unused")
    assert "orphan_table" in legacy["issues"]


def test_db_reverse_audit_supports_filter_and_countless_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _make_repo(tmp_path)
    calls: list[str] = []

    async def fake_execute_sql(
        query: str,
        *,
        dsn: str | None = None,
        columns: Any = None,
        timeout: int = 60,
    ) -> list[dict[str, Any]]:
        calls.append(query)
        return [{"table_name": "kb_documents"}, {"table_name": "framework_file_shares"}]

    monkeypatch.setattr(db_reverse_tools, "_execute_sql", fake_execute_sql)

    async def run_audit() -> dict[str, Any]:
        return await db_reverse_tools.db_reverse_audit(repo, table_filter="kb_", count_rows=False)

    result = anyio.run(run_audit)

    assert [row["table"] for row in result["tables"]] == ["kb_documents"]
    assert result["tables"][0]["row_count"] is None
    assert result["tables"][0]["empty_classification"]["level"] == "unknown"
    assert len(calls) == 1


def test_execute_sql_rejects_write_before_psql(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("psql should not be started for mutating SQL")

    monkeypatch.setattr(db_reverse_tools.asyncio, "create_subprocess_exec", fail_if_called)

    async def run_rejected_sql() -> list[dict[str, Any]]:
        return await db_reverse_tools._execute_sql(
            "DELETE FROM framework_file_items",
            dsn="postgresql://readonly/test",
        )

    with pytest.raises(ValueError):
        anyio.run(run_rejected_sql)
