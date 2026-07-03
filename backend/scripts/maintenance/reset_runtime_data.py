#!/usr/bin/env python3
"""Safely reset selected runtime data for a local development database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
BACKEND_DATA_DIR = BACKEND_ROOT / "data"
ENV_PATH = BACKEND_ROOT / ".env"

Scope = Literal["tasks", "knowledge", "agent", "files", "all-runtime"]

LOCAL_DB_HOSTS = {"127.0.0.1", "localhost", "::1"}
PRODUCTION_DB_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (r"prod", r"production", r"prd", r"生产")
)

TASK_TABLES = (
    "framework_system_tasks",
    "framework_system_task_queues",
    "framework_workflow_runs",
    "framework_workflow_step_records",
    "framework_event_log",
)

KNOWLEDGE_TABLES = (
    "kb_documents",
    "kb_chunks",
    "kb_page_fusions",
    "kb_raw_data",
    "kb_entity_dictionary",
    "kb_entity_aliases",
    "kb_disambiguation",
    "kb_graph_nodes",
    "kb_graph_edges",
    "kb_chunk_entities",
    "kb_evidence",
    "kb_conclusion_evidence",
    "kb_entity_merge_log",
    "kb_governance_candidates",
    "kb_document_profiles",
    "kb_file_relations",
    "kb_pipeline_runs",
    "kb_pipeline_stage_runs",
    "kb_pipeline_stale",
)

AGENT_TABLES = (
    "agent_conversations",
    "agent_messages",
    "agent_message_meta",
    "agent_events",
    "agent_failure_diagnostics",
    "agent_context_snapshots",
    "agent_trajectory_records",
    "agent_checkpoints",
    "agent_approval_queue",
    "agent_usage_daily",
    "agent_context_compactions",
    "agent_review_tasks",
    "agent_review_results",
    "agent_skill_usage",
    "agent_tool_guide_candidates",
)

FILE_TABLES = (
    "framework_file_items",
    "framework_file_folders",
    "framework_file_shares",
    "framework_file_recycle_items",
    "framework_file_upload_sessions",
    "framework_file_assets",
    "framework_content_packages",
    "framework_content_package_versions",
    "framework_resources",
    "framework_resource_refs",
    "framework_artifacts",
    "framework_artifact_versions",
    "framework_artifact_operations",
)

SCOPE_TABLES: dict[Scope, tuple[str, ...]] = {
    "tasks": TASK_TABLES,
    "knowledge": KNOWLEDGE_TABLES,
    "agent": AGENT_TABLES,
    "files": FILE_TABLES,
    "all-runtime": TASK_TABLES + KNOWLEDGE_TABLES + AGENT_TABLES + FILE_TABLES,
}

@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    name: str


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _db_config() -> DbConfig:
    env = {**_read_env(ENV_PATH), **os.environ}
    return DbConfig(
        host=env.get("DB_HOST", "127.0.0.1"),
        port=int(env.get("DB_PORT", "5432")),
        user=env.get("DB_USER", "postgres"),
        password=env.get("DB_PASSWORD", ""),
        name=env.get("DB_NAME", "huashiwangzu_v2"),
    )


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _validate_db_safety(cfg: DbConfig, *, allow_non_local_db: bool) -> None:
    if any(pattern.search(cfg.name) for pattern in PRODUCTION_DB_PATTERNS):
        raise SystemExit(f"Refusing to reset production-like database name: {cfg.name}")
    if cfg.host.lower() in LOCAL_DB_HOSTS:
        return
    if not allow_non_local_db:
        raise SystemExit(f"Refusing non-local database host {cfg.host!r}")
    env = {**_read_env(ENV_PATH), **os.environ}
    app_env = env.get("APP_ENV", "").lower()
    if env.get("RESET_RUNTIME_ALLOW_REMOTE_DEV") != "1":
        raise SystemExit("RESET_RUNTIME_ALLOW_REMOTE_DEV=1 is required for non-local database resets")
    if app_env not in {"development", "test"}:
        raise SystemExit("APP_ENV must be development or test for non-local database resets")


def _validate_confirm(cfg: DbConfig, *, apply: bool, confirm: str) -> None:
    expected = f"RESET {cfg.name}"
    if apply and confirm != expected:
        raise SystemExit(f'Apply requires --confirm "{expected}"')


def _manifest_database_name(manifest: dict[str, object]) -> str:
    for key in ("database_name", "db_name"):
        value = manifest.get(key)
        if isinstance(value, str):
            return value
    database = manifest.get("database")
    if isinstance(database, str):
        return database
    if isinstance(database, dict):
        for key in ("name", "database_name", "db_name"):
            value = database.get(key)
            if isinstance(value, str):
                return value
    return ""


def _validate_db_backup(path: Path | None, *, apply: bool, database_name: str) -> None:
    if not apply:
        return
    if path is None:
        raise SystemExit("--db-backup is required when applying a reset")
    if path.is_file():
        if path.stat().st_size <= 0:
            raise SystemExit("--db-backup file must be non-empty")
        return
    if path.is_dir() and (path / "database.sql").is_file() and (path / "manifest.json").is_file():
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SystemExit("--db-backup manifest.json must be valid JSON") from exc
        if not isinstance(manifest, dict):
            raise SystemExit("--db-backup manifest.json must be a JSON object")
        backup_database_name = _manifest_database_name(manifest)
        if not backup_database_name:
            raise SystemExit("--db-backup manifest.json must include database_name")
        if backup_database_name != database_name:
            raise SystemExit(
                f"--db-backup database mismatch: backup={backup_database_name!r}, current={database_name!r}"
            )
        return
    raise SystemExit("--db-backup must be an existing file or a directory containing database.sql and manifest.json")


def _validate_backend_data_dir() -> Path:
    raw_backend_data = BACKEND_DATA_DIR.expanduser()
    if raw_backend_data.is_symlink():
        raise SystemExit(f"Refusing symlink BACKEND_DATA_DIR: {_relative(raw_backend_data)}")
    backend_data = raw_backend_data.resolve()
    backend_root = BACKEND_ROOT.expanduser().resolve()
    protected = {
        Path("/").resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.expanduser().resolve(),
        backend_root,
    }
    if backend_data in protected:
        raise SystemExit(f"Refusing protected BACKEND_DATA_DIR: {_relative(backend_data)}")
    try:
        backend_data.relative_to(backend_root)
    except ValueError as exc:
        raise SystemExit(f"BACKEND_DATA_DIR is outside backend root: {_relative(backend_data)}") from exc
    return backend_data


def _validate_runtime_dirs(paths: list[Path]) -> list[Path]:
    backend_data = _validate_backend_data_dir()
    forbidden = {PROJECT_ROOT.resolve(), BACKEND_ROOT.resolve(), backend_data}
    safe_paths: list[Path] = []
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_symlink():
            raise SystemExit(f"Refusing to clean symlink runtime directory: {_relative(path)}")
        resolved = path.resolve()
        if resolved in forbidden:
            raise SystemExit(f"Refusing to clean protected directory: {_relative(resolved)}")
        try:
            resolved.relative_to(backend_data)
        except ValueError as exc:
            raise SystemExit(f"Runtime directory is outside backend/data: {_relative(resolved)}") from exc
        safe_paths.append(resolved)
    return safe_paths


def _validate_backup_dir(backup_dir: Path | None, runtime_dirs: list[Path], *, apply: bool, clean_files: bool) -> None:
    if not apply or not clean_files:
        return
    if backup_dir is None:
        raise SystemExit("--backup-dir is required with --yes --clean-files")
    backup_resolved = backup_dir.expanduser().resolve()
    for runtime_dir in runtime_dirs:
        try:
            backup_resolved.relative_to(runtime_dir)
        except ValueError:
            continue
        raise SystemExit("--backup-dir must not be inside a runtime directory that will be cleaned")


def _runtime_dirs_for_scope(scope: Scope, *, clean_files: bool) -> list[Path]:
    if not clean_files:
        return []
    if scope not in {"files", "agent", "all-runtime"}:
        raise SystemExit("--clean-files requires --scope files, agent, or all-runtime")
    files_dirs = [
        BACKEND_DATA_DIR / "uploads",
        BACKEND_DATA_DIR / "workspaces",
        BACKEND_DATA_DIR / ".tmp_downloads",
        BACKEND_DATA_DIR / ".tmp_exports",
    ]
    agent_dirs = [BACKEND_DATA_DIR / "agent"]
    if scope == "files":
        return _validate_runtime_dirs(files_dirs)
    if scope == "agent":
        return _validate_runtime_dirs(agent_dirs)
    return _validate_runtime_dirs(files_dirs + agent_dirs)


async def _table_names(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    return [str(row["table_name"]) for row in rows]


async def _foreign_key_edges(conn: asyncpg.Connection) -> list[tuple[str, str]]:
    rows = await conn.fetch(
        """
        SELECT referenced_table.relname AS referenced_table,
               dependent_table.relname AS dependent_table
        FROM pg_constraint constraint_info
        JOIN pg_class dependent_table ON dependent_table.oid = constraint_info.conrelid
        JOIN pg_namespace dependent_schema ON dependent_schema.oid = dependent_table.relnamespace
        JOIN pg_class referenced_table ON referenced_table.oid = constraint_info.confrelid
        JOIN pg_namespace referenced_schema ON referenced_schema.oid = referenced_table.relnamespace
        WHERE constraint_info.contype = 'f'
          AND dependent_schema.nspname = 'public'
          AND referenced_schema.nspname = 'public'
        ORDER BY referenced_table.relname, dependent_table.relname
        """
    )
    return [
        (str(row["referenced_table"]), str(row["dependent_table"]))
        for row in rows
    ]


def _fk_dependency_closure(
    seed_tables: list[str],
    edges: list[tuple[str, str]],
    available_tables: list[str],
) -> list[str]:
    dependents_by_referenced: dict[str, list[str]] = {}
    available_set = set(available_tables)
    for referenced_table, dependent_table in edges:
        if referenced_table in available_set and dependent_table in available_set:
            dependents_by_referenced.setdefault(referenced_table, []).append(dependent_table)

    affected = set(seed_tables)
    pending = list(seed_tables)
    while pending:
        current = pending.pop(0)
        for dependent_table in dependents_by_referenced.get(current, []):
            if dependent_table not in affected:
                affected.add(dependent_table)
                pending.append(dependent_table)
    return [table for table in available_tables if table in affected]


def _archive_runtime_dirs(paths: list[Path], backup_dir: Path) -> list[str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = backup_dir / f"runtime_files_{stamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in paths:
            if not path.exists():
                continue
            tar.add(path, arcname=_relative(path))
            archived.append(_relative(path))
    if not archived:
        archive_path.unlink(missing_ok=True)
    return archived


def _clear_runtime_dirs(paths: list[Path]) -> list[str]:
    cleared: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.unlink()
        cleared.append(_relative(path))
    return cleared


async def reset_runtime_data(
    *,
    apply: bool,
    scope: Scope,
    clean_files: bool,
    backup_dir: Path | None,
    db_backup: Path | None,
    confirm: str = "",
    allow_non_local_db: bool = False,
) -> dict[str, object]:
    cfg = _db_config()
    _validate_db_safety(cfg, allow_non_local_db=allow_non_local_db)
    _validate_confirm(cfg, apply=apply, confirm=confirm)
    _validate_db_backup(db_backup, apply=apply, database_name=cfg.name)
    runtime_dirs = _runtime_dirs_for_scope(scope, clean_files=clean_files)
    _validate_backup_dir(backup_dir, runtime_dirs, apply=apply, clean_files=clean_files)

    conn = await asyncpg.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password or None,
        database=cfg.name,
    )
    try:
        available_tables = await _table_names(conn)
        available_set = set(available_tables)
        allowed_tables = SCOPE_TABLES[scope]
        truncate_tables = [table for table in allowed_tables if table in available_set]
        skipped_tables = [table for table in allowed_tables if table not in available_set]
        fk_edges = await _foreign_key_edges(conn)
        affected_tables = _fk_dependency_closure(truncate_tables, fk_edges, available_tables)
        offending_tables = sorted(set(affected_tables) - set(allowed_tables))
        archived_dirs: list[str] = []
        cleared_dirs: list[str] = []

        if apply and offending_tables:
            raise SystemExit(
                "Refusing reset because FK dependency closure reaches tables outside "
                f"scope {scope!r}: {', '.join(offending_tables)}"
            )

        if apply:
            if clean_files and backup_dir is not None:
                archived_dirs = _archive_runtime_dirs(runtime_dirs, backup_dir.expanduser().resolve())
            if affected_tables:
                quoted = ", ".join(_quote_ident(table) for table in affected_tables)
                await conn.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY RESTRICT")
            if clean_files:
                cleared_dirs = _clear_runtime_dirs(runtime_dirs)

        return {
            "applied": apply,
            "scope": scope,
            "database": cfg.name,
            "truncate_tables": truncate_tables,
            "affected_tables": affected_tables,
            "offending_tables": offending_tables,
            "available_tables": available_tables,
            "skipped_tables": skipped_tables,
            "clean_files": clean_files,
            "archived_dirs": archived_dirs,
            "cleared_dirs": cleared_dirs,
            "db_backup": str(db_backup) if db_backup else "",
            "backup_dir": str(backup_dir) if backup_dir else "",
        }
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely reset selected development runtime data")
    parser.add_argument("--yes", action="store_true", help="Apply the reset; without this flag the script is dry-run")
    parser.add_argument("--confirm", default="", help='Required with --yes: "RESET <db_name>"')
    parser.add_argument("--scope", choices=tuple(SCOPE_TABLES), default=None, help="Runtime data scope")
    parser.add_argument(
        "--clean-files",
        action="store_true",
        help="Archive and clear runtime files for files/agent/all-runtime",
    )
    parser.add_argument("--backup-dir", default="", help="Directory to store runtime file archive before cleaning files")
    parser.add_argument("--db-backup", default="", help="Existing DB backup file or backup directory")
    parser.add_argument("--allow-non-local-db", action="store_true", help="Allow DB hosts outside localhost/127.0.0.1/::1")
    args = parser.parse_args()
    if args.yes and args.scope is None:
        parser.error("--scope is required with --yes")
    if args.scope is None:
        args.scope = "all-runtime"
    return args


def main() -> None:
    args = parse_args()
    backup_dir = Path(args.backup_dir).expanduser().resolve() if args.backup_dir else None
    db_backup = Path(args.db_backup).expanduser().resolve() if args.db_backup else None
    result = asyncio.run(
        reset_runtime_data(
            apply=bool(args.yes),
            scope=args.scope,
            clean_files=bool(args.clean_files),
            backup_dir=backup_dir,
            db_backup=db_backup,
            confirm=str(args.confirm),
            allow_non_local_db=bool(args.allow_non_local_db),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
