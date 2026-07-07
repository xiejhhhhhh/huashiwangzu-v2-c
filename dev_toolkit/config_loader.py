"""Configuration loading for local dev toolkit commands.

The checked-in example is intentionally non-secret. Local credentials and DSNs
belong in dev_toolkit/config.local.json or environment variables.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

EXPECTED_DB_NAME = "华世王镞_v2"

DEFAULT_CONFIG: dict[str, Any] = {
    "backend_base_url": "http://127.0.0.1:33000",
    "frontend_base_url": "http://127.0.0.1:5173",
    "db_dsn": "",
    "bge_m3_url": "http://127.0.0.1:30000",
    "accounts": {
        "admin": {"username": "", "password": "", "role": "admin"},
        "editor": {"username": "", "password": "", "role": "editor"},
        "viewer": {"username": "", "password": "", "role": "viewer"},
    },
    "memory_dir": "backend/logs/project_memory",
    "user_profile_path": "backend/logs/user_profile/profile.json",
    "embedding_cache": "dev_toolkit/memory_embeddings.json",
    "log_dir": "backend/logs",
    "release_gate": {
        "sandbox_jobs": 1,
        "sandbox_frontend_jobs": 1,
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else None


def _apply_env_overrides(config: dict[str, Any]) -> None:
    direct = {
        "DEV_TOOLKIT_BACKEND_BASE_URL": "backend_base_url",
        "DEV_TOOLKIT_FRONTEND_BASE_URL": "frontend_base_url",
        "DEV_TOOLKIT_DB_DSN": "db_dsn",
        "DEV_TOOLKIT_BGE_M3_URL": "bge_m3_url",
        "DEV_TOOLKIT_MEMORY_DIR": "memory_dir",
        "DEV_TOOLKIT_USER_PROFILE_PATH": "user_profile_path",
        "DEV_TOOLKIT_EMBEDDING_CACHE": "embedding_cache",
        "DEV_TOOLKIT_LOG_DIR": "log_dir",
    }
    for env_name, key in direct.items():
        value = _env(env_name)
        if value is not None:
            config[key] = value

    accounts = config.setdefault("accounts", {})
    for role in ("admin", "editor", "viewer"):
        account = accounts.setdefault(role, {"role": role})
        prefix = f"DEV_TOOLKIT_{role.upper()}"
        username = _env(f"{prefix}_USERNAME")
        password = _env(f"{prefix}_PASSWORD")
        user_id = _env(f"{prefix}_USER_ID")
        if username is not None:
            account["username"] = username
        if password is not None:
            account["password"] = password
        if user_id is not None:
            try:
                account["user_id"] = int(user_id)
            except ValueError:
                account["user_id"] = user_id

    release_gate = config.setdefault("release_gate", {})
    for env_name, key in (
        ("DEV_TOOLKIT_SANDBOX_JOBS", "sandbox_jobs"),
        ("DEV_TOOLKIT_SANDBOX_FRONTEND_JOBS", "sandbox_frontend_jobs"),
    ):
        value = _env(env_name)
        if value is not None:
            release_gate[key] = int(value)


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _db_name_from_dsn(dsn: str) -> str:
    return unquote(urlparse(dsn).path.lstrip("/"))


def _build_db_dsn_from_backend_env(repo_root: Path) -> str:
    env = _read_env_file(repo_root / "backend" / ".env")
    db_name = env.get("DB_NAME", EXPECTED_DB_NAME)
    user = env.get("DB_USER", "postgres")
    password = env.get("DB_PASSWORD", "")
    host = env.get("DB_HOST", "127.0.0.1")
    port = env.get("DB_PORT", "5432")
    auth = quote(user, safe="")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"
    return f"postgresql://{auth}@{host}:{port}/{quote(db_name, safe='')}"


def _validate_db_dsn(dsn: str) -> None:
    db_name = _db_name_from_dsn(dsn)
    if db_name != EXPECTED_DB_NAME:
        raise RuntimeError(
            f"dev_toolkit db_dsn points to {db_name!r}; expected {EXPECTED_DB_NAME!r}"
        )


def load_config(repo_root: Path) -> dict[str, Any]:
    toolkit_dir = repo_root / "dev_toolkit"
    config = _merge(DEFAULT_CONFIG, _read_json(toolkit_dir / "config.example.json"))
    config = _merge(config, _read_json(toolkit_dir / "config.local.json"))
    _apply_env_overrides(config)
    if not config.get("db_dsn"):
        config["db_dsn"] = _build_db_dsn_from_backend_env(repo_root)
    _validate_db_dsn(str(config["db_dsn"]))
    return config
