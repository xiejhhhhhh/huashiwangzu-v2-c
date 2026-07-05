import json
from pathlib import Path

from dev_toolkit.config_loader import load_config


def test_load_config_merges_example_local_and_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    toolkit_dir = tmp_path / "dev_toolkit"
    toolkit_dir.mkdir()
    (toolkit_dir / "config.example.json").write_text(
        json.dumps({
            "backend_base_url": "http://example",
            "db_dsn": "",
            "accounts": {
                "admin": {"username": "example-admin", "password": "", "role": "admin"},
            },
            "release_gate": {"sandbox_jobs": 1, "sandbox_frontend_jobs": 1},
        }),
        encoding="utf-8",
    )
    (toolkit_dir / "config.local.json").write_text(
        json.dumps({
            "db_dsn": "postgresql://local/test",
            "accounts": {
                "admin": {"password": "local-secret"},
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEV_TOOLKIT_BACKEND_BASE_URL", "http://env")
    monkeypatch.setenv("DEV_TOOLKIT_USER_PROFILE_PATH", "backend/logs/custom_profile.json")
    monkeypatch.setenv("DEV_TOOLKIT_ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("DEV_TOOLKIT_SANDBOX_JOBS", "3")

    config = load_config(tmp_path)

    assert config["backend_base_url"] == "http://env"
    assert config["db_dsn"] == "postgresql://local/test"
    assert config["user_profile_path"] == "backend/logs/custom_profile.json"
    assert config["accounts"]["admin"]["username"] == "env-admin"
    assert config["accounts"]["admin"]["password"] == "local-secret"
    assert config["release_gate"]["sandbox_jobs"] == 3
