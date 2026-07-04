from pathlib import Path

from dev_toolkit import asset_lifecycle_tools as tools


def test_marker_predicate_includes_required_test_marker() -> None:
    predicate = tools._marker_predicate("f.name")

    assert "smoke-" in predicate
    assert "like '%test-%'" not in predicate
    assert "test-upload-" in predicate
    assert "test-file-" in predicate
    assert "test-pollution-" in predicate
    assert "lifecycle-source-" in predicate


def test_cleanup_sql_protects_shared_physical_storage() -> None:
    sql = tools._cleanup_sql(10)

    assert "candidate_docs" in sql
    assert "archived_docs" in sql
    assert "archived_packages" in sql
    assert "deleted_recycle" in sql
    assert "deleted_files" in sql
    assert "d.filename" in sql
    assert "archived_by_test_data_cleanup" in sql
    assert "source_permanently_deleted" in sql
    assert "framework_file_recycle_items" in sql
    assert "framework_file_items" in sql
    assert "framework_content_packages" in sql
    assert "kb_documents" in sql
    assert "source_file_id in (select id from candidate_files)" in sql
    assert "origin_id in (select id from candidate_files)" in sql
    assert "candidate_storage_paths" in sql
    assert "f.id not in (select id from candidate_files)" in sql
    assert "f.storage_path = cf.storage_path" in sql
    assert "f.md5_hash = cf.md5_hash" in sql


def test_audit_sql_reports_all_pollution_domains() -> None:
    sql = tools._audit_sql(10)

    assert "active_test_files" in sql
    assert "recycled_test_files" in sql
    assert "knowledge_documents_from_test_files" in sql
    assert "content_packages_from_test_files" in sql
    assert "uploads_test_artifacts" in sql
    assert "candidate_file_count" in sql
    assert "like '%test-%'" not in tools._marker_predicate("f.name")


def test_cleanup_requires_confirm(monkeypatch, tmp_path: Path) -> None:
    def fake_run_json_sql(repo_root: Path, sql: str, *, readonly: bool) -> dict:
        return {
            "active_test_files": 1,
            "recycled_test_files": 2,
            "knowledge_documents_from_test_files": 3,
            "content_packages_from_test_files": 4,
            "uploads_test_artifacts": 5,
            "candidate_file_count": 6,
            "candidate_file_ids": [1, 2],
            "sample_files": [],
        }

    monkeypatch.setattr(tools, "_run_json_sql", fake_run_json_sql)

    dry_run = tools.cleanup_test_data_pollution(tmp_path, dry_run=True, limit=2)
    assert dry_run["changed"] == 0
    assert dry_run["confirm_token"] == "CLEAN_TEST_DATA"

    rejected = tools.cleanup_test_data_pollution(
        tmp_path,
        dry_run=False,
        limit=2,
        confirm="WRONG",
    )
    assert rejected["success"] is False
    assert rejected["confirm_token"] == "CLEAN_TEST_DATA"


def test_delete_upload_paths_stays_inside_upload_root(tmp_path: Path) -> None:
    upload_root = tmp_path / "data" / "uploads"
    upload_root.mkdir(parents=True)
    candidate = upload_root / "candidate.txt"
    candidate.write_text("x")

    result = tools._delete_upload_paths(
        tmp_path,
        ["candidate.txt", "../outside.txt", "missing.txt"],
    )

    assert result["physical_deleted_files"] == 1
    assert result["physical_skipped_files"] == 2
    assert not candidate.exists()
    assert result["physical_delete_errors"][0]["error"] == "outside_upload_root"


def test_upload_root_resolves_relative_backend_upload_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_DIR", "data/uploads")

    assert tools._upload_root(tmp_path) == (tmp_path / "backend" / "data" / "uploads").resolve()
