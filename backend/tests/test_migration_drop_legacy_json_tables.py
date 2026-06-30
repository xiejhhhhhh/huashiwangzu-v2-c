"""Verify legacy framework_file_json_* tables are retired from ORM, migration,
and full-lifecycle fresh install."""

import os
import subprocess
import sys

import pytest

from app.models.base import Base

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── ORM layer ─────────────────────────────────────────────────────────


class TestMetadataClean:
    """Base.metadata must NOT contain legacy file_json tables."""

    def test_no_legacy_tables_in_metadata(self) -> None:
        json_tables = [t for t in Base.metadata.tables
                       if "file_json" in t]
        assert json_tables == [], (
            f"Legacy tables still registered in metadata: {json_tables}"
        )


# ── Migration head ────────────────────────────────────────────────────


class TestMigrationHead:
    """Current Alembic head must include the drop-legacy revision."""

    def test_head_includes_drop_revision(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            capture_output=True, text=True, cwd=BACKEND_DIR,
        )
        assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
        assert "132d955fc2d4" in result.stdout, (
            f"Drop-legacy revision 132d955fc2d4 not in heads.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ── Fresh install lifecycle (isolated temp DB) ────────────────────────


class TestFreshInstallLifecycle:
    """A brand-new database (full migration chain) must also have no legacy tables."""

    TEMP_DB = "test_temp_drop_legacy_json"

    @classmethod
    def setup_class(cls) -> None:
        _psql(f"DROP DATABASE IF EXISTS {cls.TEMP_DB}")
        _psql(f"CREATE DATABASE {cls.TEMP_DB}")

    @classmethod
    def teardown_class(cls) -> None:
        _psql(f"DROP DATABASE IF EXISTS {cls.TEMP_DB}")

    def test_fresh_install_has_no_legacy_tables(self) -> None:
        _alembic_upgrade(self.TEMP_DB)

        rows = _psql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name LIKE 'framework_file_json_%'",
            db=self.TEMP_DB,
        )
        legacy = [r for r in rows if r.strip()]
        assert legacy == [], (
            f"Fresh install still has legacy tables: {legacy}"
        )

    def test_fresh_install_upgrade_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True, text=True, cwd=BACKEND_DIR,
            env={**os.environ, "PGDATABASE": self.TEMP_DB},
        )
        assert result.returncode == 0, (
            f"alembic current failed: {result.stderr}"
        )
        assert "132d955fc2d4" in result.stdout, (
            f"Alembic current should be 132d955fc2d4, got: {result.stdout}"
        )


# ── helpers ────────────────────────────────────────────────────────────


def _psql(sql: str, db: str | None = None) -> list[str]:
    """Run a SQL command via psql and return non-empty output lines."""
    cmd = [
        "/Library/PostgreSQL/17/bin/psql",
        "-d", db or "华世王镞_v2",
        "-t", "-A",
        "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (
        f"psql failed:\n  cmd: {' '.join(cmd)}\n"
        f"  stderr: {result.stderr}"
    )
    return [l for l in result.stdout.split("\n") if l.strip()]


def _alembic_upgrade(db: str) -> None:
    """Run alembic upgrade head against the given database."""
    env = {**os.environ, "PGDATABASE": db}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, cwd=BACKEND_DIR,
        env=env, timeout=60,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head on {db} failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
