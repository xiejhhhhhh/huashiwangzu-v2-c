from pathlib import Path

from app.config import PROJECT_ROOT, Settings


def test_relative_storage_paths_resolve_from_project_root() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET="test-secret",
        UPLOAD_DIR="data/uploads",
        STORAGE_ROOT="data/uploads",
    )

    assert settings.UPLOAD_DIR == str((PROJECT_ROOT / "data/uploads").resolve())
    assert settings.STORAGE_ROOT == str((PROJECT_ROOT / "data/uploads").resolve())


def test_absolute_storage_paths_are_preserved(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    storage_root = tmp_path / "storage"
    settings = Settings(
        _env_file=None,
        JWT_SECRET="test-secret",
        UPLOAD_DIR=str(upload_dir),
        STORAGE_ROOT=str(storage_root),
    )

    assert settings.UPLOAD_DIR == str(upload_dir.resolve())
    assert settings.STORAGE_ROOT == str(storage_root.resolve())
