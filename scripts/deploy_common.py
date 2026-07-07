#!/usr/bin/env python3
"""Shared deployment initializer for Huashi Wangzu V2.

This script is called by the macOS and Windows deployment wrappers after Python
packages are installed. It prepares backend/.env, creates the PostgreSQL
database/extensions, initializes framework tables, seeds default data, and runs
module-owned idempotent database initializers when present.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
MODULES_DIR = PROJECT_ROOT / "modules"
ENV_PATH = BACKEND_DIR / ".env"


@dataclass(frozen=True)
class DeployConfig:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    seed_password: str
    skip_seed: bool
    skip_modules: bool


def log(message: str) -> None:
    print(f"[deploy] {message}", flush=True)


def parse_args() -> DeployConfig:
    parser = argparse.ArgumentParser(description="Initialize Huashi Wangzu V2 deployment")
    parser.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "5432")))
    parser.add_argument("--db-user", default=os.getenv("DB_USER", "postgres"))
    parser.add_argument("--db-password", default=os.getenv("DB_PASSWORD", ""))
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "华世王镞_v2"))
    parser.add_argument("--seed-password", default=os.getenv("V2_SEED_DEFAULT_PASSWORD", ""))
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--skip-modules", action="store_true")
    args = parser.parse_args()

    if not args.skip_seed and not args.seed_password:
        raise SystemExit("--seed-password or V2_SEED_DEFAULT_PASSWORD is required unless --skip-seed is used")

    return DeployConfig(
        db_host=args.db_host,
        db_port=args.db_port,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        seed_password=args.seed_password,
        skip_seed=args.skip_seed,
        skip_modules=args.skip_modules,
    )


def parse_env_file(path: Path) -> dict[str, str]:
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


def format_env_value(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or "#" in value or '"' in value or "'" in value:
        return json.dumps(value, ensure_ascii=False)
    return value


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={format_env_value(remaining.pop(key))}")
                continue
        output.append(raw_line)

    if remaining and output and output[-1].strip():
        output.append("")
    for key, value in remaining.items():
        output.append(f"{key}={format_env_value(value)}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def write_backend_env(config: DeployConfig) -> None:
    existing = parse_env_file(ENV_PATH)
    updates = {
        "DB_HOST": config.db_host,
        "DB_PORT": str(config.db_port),
        "DB_USER": config.db_user,
        "DB_PASSWORD": config.db_password,
        "DB_NAME": config.db_name,
        "APP_HOST": existing.get("APP_HOST") or "127.0.0.1",
        "APP_PORT": existing.get("APP_PORT") or "33000",
        "JWT_SECRET": existing.get("JWT_SECRET") or secrets.token_urlsafe(48),
    }
    upsert_env(ENV_PATH, updates)
    log(f"backend env ready: {ENV_PATH}")


async def connect_database(config: DeployConfig, database: str) -> Any:
    import asyncpg

    return await asyncpg.connect(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password or None,
        database=database,
    )


async def ensure_database(config: DeployConfig) -> None:
    maintenance_db = os.getenv("PGDATABASE") or "postgres"
    conn = await connect_database(config, maintenance_db)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", config.db_name)
        if not exists:
            db_name = quote_ident(config.db_name)
            await conn.execute(f"CREATE DATABASE {db_name}")
            log(f"created database: {config.db_name}")
        else:
            log(f"database exists: {config.db_name}")
    finally:
        await conn.close()

    target = await connect_database(config, config.db_name)
    try:
        await target.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await target.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        log("database extensions ready: vector, pg_trgm")
    finally:
        await target.close()


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def prepare_backend_imports(config: DeployConfig) -> None:
    os.environ["DB_HOST"] = config.db_host
    os.environ["DB_PORT"] = str(config.db_port)
    os.environ["DB_USER"] = config.db_user
    os.environ["DB_PASSWORD"] = config.db_password
    os.environ["DB_NAME"] = config.db_name
    os.environ.setdefault("APP_HOST", "127.0.0.1")
    os.environ.setdefault("APP_PORT", "33000")
    if not os.getenv("JWT_SECRET"):
        existing = parse_env_file(ENV_PATH)
        os.environ["JWT_SECRET"] = existing.get("JWT_SECRET") or secrets.token_urlsafe(48)
    if config.seed_password:
        os.environ["V2_SEED_DEFAULT_PASSWORD"] = config.seed_password

    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


async def initialize_framework(config: DeployConfig) -> None:
    prepare_backend_imports(config)

    from app.database import AsyncSessionLocal, dispose_db, init_db
    from app.models.system import ensure_framework_scheduling_columns
    from app.services.app_service import sync_apps_from_manifest
    from app.services.event_bus import _ensure_event_log_table

    await init_db()
    await ensure_framework_scheduling_columns()
    await _ensure_event_log_table()
    log("framework tables ready")

    if not config.skip_seed:
        from app import seed as seed_module

        seed_module.DEFAULT_PASSWORD = config.seed_password
        await seed_module.seed()
        log("framework seed data ready")

    async with AsyncSessionLocal() as db:
        result = await sync_apps_from_manifest(db)
        log(f"app manifests synced: {result}")

    if not config.skip_modules:
        await initialize_modules(AsyncSessionLocal)

    await dispose_db()


async def initialize_modules(async_session_factory) -> None:
    module_specs = list(iter_module_init_specs())
    if not module_specs:
        log("no module init hooks found")
        return

    for module_key, init_file in module_specs:
        try:
            await run_module_init(module_key, init_file, async_session_factory)
        except Exception as exc:  # noqa: BLE001 - deployment should report every module failure clearly.
            raise RuntimeError(f"module init failed: {module_key} ({init_file}): {exc}") from exc


def iter_module_init_specs() -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    if not MODULES_DIR.exists():
        return specs

    for manifest_path in sorted(MODULES_DIR.glob("*/manifest.json")):
        module_dir = manifest_path.parent
        if module_dir.name.startswith(("_", ".")):
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log(f"skip bad module manifest {manifest_path}: {exc}")
            continue
        if manifest.get("enabled") is False:
            continue
        backend_config = manifest.get("backend")
        if isinstance(backend_config, dict) and backend_config.get("enabled") is False:
            continue
        init_file = module_dir / "backend" / "init_db.py"
        if init_file.exists():
            specs.append((str(manifest.get("key") or module_dir.name), init_file))
    return specs


async def run_module_init(module_key: str, init_file: Path, async_session_factory) -> None:
    safe_key = module_key.replace("-", "_")
    backend_dir = init_file.parent
    package_name = f"deploy_modules.{safe_key}"
    module_name = f"{package_name}.init_db"

    ensure_namespace_package(package_name, backend_dir)
    spec = importlib.util.spec_from_file_location(module_name, init_file)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load module init spec: {init_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    init_func = getattr(module, "run_init", None)
    if not callable(init_func):
        init_func = getattr(module, "_run_startup_init", None)
    if not callable(init_func):
        init_func = find_ensure_tables_func(module)
    if not callable(init_func):
        log(f"module {module_key}: no init callable, skipped")
        return

    signature = inspect.signature(init_func)
    required_params = [
        param
        for param in signature.parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]

    if required_params:
        async with async_session_factory() as db:
            result = init_func(db)
            if inspect.isawaitable(result):
                await result
    elif inspect.iscoroutinefunction(init_func):
        await init_func()
    else:
        await asyncio.to_thread(init_func)
    log(f"module {module_key}: init ready")


def find_ensure_tables_func(module):
    for name in sorted(dir(module)):
        if name.startswith("ensure_") and name.endswith("tables"):
            candidate = getattr(module, name)
            if callable(candidate):
                return candidate
    return None


def ensure_namespace_package(package_name: str, backend_dir: Path) -> None:
    if "deploy_modules" not in sys.modules:
        import types

        top_pkg = types.ModuleType("deploy_modules")
        top_pkg.__path__ = []
        sys.modules["deploy_modules"] = top_pkg

    if package_name not in sys.modules:
        import types

        pkg = types.ModuleType(package_name)
        pkg.__path__ = [str(backend_dir)]
        sys.modules[package_name] = pkg


def main() -> None:
    config = parse_args()
    write_backend_env(config)
    asyncio.run(ensure_database(config))
    asyncio.run(initialize_framework(config))
    log("deployment initialization completed")


if __name__ == "__main__":
    main()
