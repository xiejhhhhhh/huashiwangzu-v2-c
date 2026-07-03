from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from scripts.maintenance import reset_runtime_data as reset_script


class FakeConnection:
    def __init__(
        self,
        tables: list[str],
        fk_edges: list[tuple[str, str]] | None = None,
    ) -> None:
        self.tables = tables
        self.fk_edges = fk_edges or []
        self.executed: list[str] = []
        self.closed = False

    async def fetch(self, query: str) -> list[dict[str, str]]:
        if "pg_constraint" in query:
            return [
                {"referenced_table": referenced_table, "dependent_table": dependent_table}
                for referenced_table, dependent_table in self.fk_edges
            ]
        return [{"table_name": table} for table in self.tables]

    async def execute(self, query: str) -> None:
        self.executed.append(query)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    conn = FakeConnection(
        [
            "framework_system_tasks",
            "framework_system_settings",
            "kb_documents",
            "agent_conversations",
            "framework_file_items",
            "unrelated_table",
        ]
    )

    async def fake_connect(**_kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(reset_script.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(
        reset_script,
        "_db_config",
        lambda: reset_script.DbConfig(
            host="127.0.0.1",
            port=5432,
            user="postgres",
            password="",
            name="huashiwangzu_v2",
        ),
    )
    return conn


def make_db_backup(tmp_path: Path) -> Path:
    backup = tmp_path / "db-backup"
    backup.mkdir()
    (backup / "database.sql").write_text("-- backup", encoding="utf-8")
    (backup / "manifest.json").write_text(
        '{"database_name": "huashiwangzu_v2"}',
        encoding="utf-8",
    )
    return backup


def patch_backend_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    backend_root = tmp_path / "backend"
    data_dir = backend_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(reset_script, "BACKEND_ROOT", backend_root)
    monkeypatch.setattr(reset_script, "BACKEND_DATA_DIR", data_dir)
    return data_dir


def run_reset(**kwargs: object) -> dict[str, object]:
    return asyncio.run(reset_script.reset_runtime_data(**kwargs))


def test_confirm_missing_or_wrong_rejects(fake_db: FakeConnection, tmp_path: Path) -> None:
    backup = make_db_backup(tmp_path)
    with pytest.raises(SystemExit, match="Apply requires"):
        run_reset(
            apply=True,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=backup,
            confirm="",
        )
    with pytest.raises(SystemExit, match="Apply requires"):
        run_reset(
            apply=True,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=backup,
            confirm="RESET wrong_db",
        )
    assert fake_db.executed == []


def test_production_database_name_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        reset_script,
        "_db_config",
        lambda: reset_script.DbConfig("127.0.0.1", 5432, "postgres", "", "customer_prod"),
    )
    with pytest.raises(SystemExit, match="production-like"):
        run_reset(
            apply=False,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=make_db_backup(tmp_path),
        )


def test_non_local_host_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        reset_script,
        "_db_config",
        lambda: reset_script.DbConfig("10.0.0.8", 5432, "postgres", "", "huashiwangzu_v2"),
    )
    with pytest.raises(SystemExit, match="non-local"):
        run_reset(
            apply=False,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=make_db_backup(tmp_path),
        )


def test_non_local_host_override_requires_dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = reset_script.DbConfig("10.0.0.8", 5432, "postgres", "", "huashiwangzu_v2")
    monkeypatch.delenv("RESET_RUNTIME_ALLOW_REMOTE_DEV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(SystemExit, match="RESET_RUNTIME_ALLOW_REMOTE_DEV"):
        reset_script._validate_db_safety(cfg, allow_non_local_db=True)

    monkeypatch.setenv("RESET_RUNTIME_ALLOW_REMOTE_DEV", "1")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(SystemExit, match="APP_ENV"):
        reset_script._validate_db_safety(cfg, allow_non_local_db=True)

    monkeypatch.setenv("APP_ENV", "test")
    reset_script._validate_db_safety(cfg, allow_non_local_db=True)


def test_scope_uses_explicit_allowlist(fake_db: FakeConnection, tmp_path: Path) -> None:
    result = run_reset(
        apply=True,
        scope="knowledge",
        clean_files=False,
        backup_dir=None,
        db_backup=make_db_backup(tmp_path),
        confirm="RESET huashiwangzu_v2",
    )

    assert result["truncate_tables"] == ["kb_documents"]
    assert result["affected_tables"] == ["kb_documents"]
    assert result["offending_tables"] == []
    assert "framework_system_settings" in result["available_tables"]
    assert "kb_chunks" in result["skipped_tables"]
    assert "unrelated_table" not in result["truncate_tables"]
    assert fake_db.executed == ['TRUNCATE TABLE "kb_documents" RESTART IDENTITY RESTRICT']
    assert "CASCADE" not in fake_db.executed[0]


def test_knowledge_scope_rejects_fk_closure_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    conn = FakeConnection(
        ["kb_documents", "framework_file_items"],
        fk_edges=[("kb_documents", "framework_file_items")],
    )

    async def fake_connect(**_kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(reset_script.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(
        reset_script,
        "_db_config",
        lambda: reset_script.DbConfig("127.0.0.1", 5432, "postgres", "", "huashiwangzu_v2"),
    )

    with pytest.raises(SystemExit, match="framework_file_items"):
        run_reset(
            apply=True,
            scope="knowledge",
            clean_files=False,
            backup_dir=None,
            db_backup=make_db_backup(tmp_path),
            confirm="RESET huashiwangzu_v2",
        )

    assert conn.executed == []


def test_fk_closure_inside_scope_executes_with_restrict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    conn = FakeConnection(
        ["kb_documents", "kb_chunks"],
        fk_edges=[("kb_documents", "kb_chunks")],
    )

    async def fake_connect(**_kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(reset_script.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(
        reset_script,
        "_db_config",
        lambda: reset_script.DbConfig("127.0.0.1", 5432, "postgres", "", "huashiwangzu_v2"),
    )

    result = run_reset(
        apply=True,
        scope="knowledge",
        clean_files=False,
        backup_dir=None,
        db_backup=make_db_backup(tmp_path),
        confirm="RESET huashiwangzu_v2",
    )

    assert result["offending_tables"] == []
    assert result["affected_tables"] == ["kb_documents", "kb_chunks"]
    assert conn.executed == [
        'TRUNCATE TABLE "kb_documents", "kb_chunks" RESTART IDENTITY RESTRICT'
    ]


def test_dry_run_does_not_truncate_or_clear_files(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = patch_backend_data_dir(monkeypatch, tmp_path)
    runtime_dir = data_dir / "uploads"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "file.txt").write_text("keep", encoding="utf-8")

    result = run_reset(
        apply=False,
        scope="files",
        clean_files=True,
        backup_dir=None,
        db_backup=None,
    )

    assert result["applied"] is False
    assert result["truncate_tables"] == ["framework_file_items"]
    assert fake_db.executed == []
    assert (runtime_dir / "file.txt").read_text(encoding="utf-8") == "keep"
    assert result["archived_dirs"] == []
    assert result["cleared_dirs"] == []


def test_clean_files_apply_requires_backup_dir(fake_db: FakeConnection, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--backup-dir is required"):
        run_reset(
            apply=True,
            scope="files",
            clean_files=True,
            backup_dir=None,
            db_backup=make_db_backup(tmp_path),
            confirm="RESET huashiwangzu_v2",
        )
    assert fake_db.executed == []


def test_backup_dir_inside_runtime_dir_rejected(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = patch_backend_data_dir(monkeypatch, tmp_path)
    runtime_dir = data_dir / "uploads"
    backup_dir = runtime_dir / "backup"
    backup_dir.mkdir(parents=True)

    with pytest.raises(SystemExit, match="must not be inside"):
        run_reset(
            apply=True,
            scope="files",
            clean_files=True,
            backup_dir=backup_dir,
            db_backup=make_db_backup(tmp_path),
            confirm="RESET huashiwangzu_v2",
        )
    assert fake_db.executed == []


def test_runtime_symlink_rejected(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = patch_backend_data_dir(monkeypatch, tmp_path)
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    symlink_dir = data_dir / "uploads"
    symlink_dir.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(SystemExit, match="symlink"):
        run_reset(
            apply=True,
            scope="files",
            clean_files=True,
            backup_dir=tmp_path / "archive",
            db_backup=make_db_backup(tmp_path),
            confirm="RESET huashiwangzu_v2",
        )
    assert fake_db.executed == []


def test_backend_data_dir_symlink_rejected(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "backend"
    real_data = tmp_path / "real-data"
    backend_root.mkdir()
    real_data.mkdir()
    data_link = backend_root / "data"
    data_link.symlink_to(real_data, target_is_directory=True)
    monkeypatch.setattr(reset_script, "BACKEND_ROOT", backend_root)
    monkeypatch.setattr(reset_script, "BACKEND_DATA_DIR", data_link)

    with pytest.raises(SystemExit, match="BACKEND_DATA_DIR"):
        run_reset(
            apply=False,
            scope="files",
            clean_files=True,
            backup_dir=None,
            db_backup=None,
        )

    assert fake_db.executed == []


def test_backend_data_dir_must_resolve_under_backend_root(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    outside_data = tmp_path / "outside-data"
    outside_data.mkdir()
    monkeypatch.setattr(reset_script, "BACKEND_ROOT", backend_root)
    monkeypatch.setattr(reset_script, "BACKEND_DATA_DIR", outside_data)

    with pytest.raises(SystemExit, match="outside backend root"):
        run_reset(
            apply=False,
            scope="files",
            clean_files=True,
            backup_dir=None,
            db_backup=None,
        )

    assert fake_db.executed == []


def test_files_scope_clean_files_does_not_clear_agent_runtime(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = patch_backend_data_dir(monkeypatch, tmp_path)
    uploads_dir = data_dir / "uploads"
    agent_dir = data_dir / "agent"
    uploads_dir.mkdir()
    agent_dir.mkdir()
    (uploads_dir / "file.txt").write_text("delete", encoding="utf-8")
    (agent_dir / "state.json").write_text("keep", encoding="utf-8")

    result = run_reset(
        apply=True,
        scope="files",
        clean_files=True,
        backup_dir=tmp_path / "archive",
        db_backup=make_db_backup(tmp_path),
        confirm="RESET huashiwangzu_v2",
    )

    assert result["cleared_dirs"] == [str(uploads_dir)]
    assert not (uploads_dir / "file.txt").exists()
    assert (agent_dir / "state.json").read_text(encoding="utf-8") == "keep"


def test_agent_scope_clean_files_clears_agent_runtime_only(
    fake_db: FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = patch_backend_data_dir(monkeypatch, tmp_path)
    uploads_dir = data_dir / "uploads"
    agent_dir = data_dir / "agent"
    uploads_dir.mkdir()
    agent_dir.mkdir()
    (uploads_dir / "file.txt").write_text("keep", encoding="utf-8")
    (agent_dir / "state.json").write_text("delete", encoding="utf-8")

    run_reset(
        apply=True,
        scope="agent",
        clean_files=True,
        backup_dir=tmp_path / "archive",
        db_backup=make_db_backup(tmp_path),
        confirm="RESET huashiwangzu_v2",
    )

    assert (uploads_dir / "file.txt").read_text(encoding="utf-8") == "keep"
    assert not (agent_dir / "state.json").exists()


def test_db_backup_missing_rejected(fake_db: FakeConnection, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--db-backup"):
        run_reset(
            apply=True,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=tmp_path / "missing.sql",
            confirm="RESET huashiwangzu_v2",
        )
    assert fake_db.executed == []


def test_db_backup_manifest_database_mismatch_rejected(
    fake_db: FakeConnection,
    tmp_path: Path,
) -> None:
    backup = tmp_path / "db-backup"
    backup.mkdir()
    (backup / "database.sql").write_text("-- backup", encoding="utf-8")
    (backup / "manifest.json").write_text('{"database_name": "other_db"}', encoding="utf-8")

    with pytest.raises(SystemExit, match="database mismatch"):
        run_reset(
            apply=True,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=backup,
            confirm="RESET huashiwangzu_v2",
        )

    assert fake_db.executed == []


def test_plain_db_backup_file_must_be_non_empty_and_is_reported(
    fake_db: FakeConnection,
    tmp_path: Path,
) -> None:
    empty_backup = tmp_path / "empty.dump"
    empty_backup.write_bytes(b"")
    with pytest.raises(SystemExit, match="non-empty"):
        run_reset(
            apply=True,
            scope="tasks",
            clean_files=False,
            backup_dir=None,
            db_backup=empty_backup,
            confirm="RESET huashiwangzu_v2",
        )

    backup_file = tmp_path / "backup.dump"
    backup_file.write_bytes(b"backup")
    result = run_reset(
        apply=True,
        scope="tasks",
        clean_files=False,
        backup_dir=None,
        db_backup=backup_file,
        confirm="RESET huashiwangzu_v2",
    )

    assert result["db_backup"] == str(backup_file)


def test_apply_cli_requires_explicit_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["reset_runtime_data.py", "--yes"])
    with pytest.raises(SystemExit):
        reset_script.parse_args()

    monkeypatch.setattr(sys, "argv", ["reset_runtime_data.py"])
    args = reset_script.parse_args()
    assert args.scope == "all-runtime"
