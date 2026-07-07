#!/usr/bin/env python3
"""Bulk-upload enterprise files into the knowledge module through public HTTP APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib import error, request
from urllib.parse import unquote, urlparse

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm"}
DEFAULT_EXCLUDED_DIR_NAMES = {
    "$RECYCLE.BIN",
    ".DocumentRevisions-V100",
    ".Spotlight-V100",
    ".TemporaryItems",
    ".Trashes",
    ".fseventsd",
    "__MACOSX",
}
DEFAULT_EXCLUDED_FILE_PREFIXES = ("._", "~$")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_ENV_FILE = PROJECT_ROOT / "backend" / ".env"
EXPECTED_DB_NAME = "华世王镞_v2"

# The live backend is started with cwd=backend, so relative storage settings such
# as "data/uploads" resolve under backend/. Keep this script aligned when it is
# executed from the project root.
os.environ.setdefault("UPLOAD_DIR", str(BACKEND_DIR / "data" / "uploads"))
os.environ.setdefault("STORAGE_ROOT", str(BACKEND_DIR / "data" / "uploads"))

for import_root in (PROJECT_ROOT, BACKEND_DIR):
    import_path = str(import_root)
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _json_request(base_url: str, path: str, payload: dict, token: str | None = None, timeout: int = 120) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(f"{base_url}{path}", data=body, headers=headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(base_url: str, path: str, token: str | None = None, timeout: int = 60) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(f"{base_url}{path}", headers=headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_extensions(value: str | None) -> set[str]:
    if not value:
        return set(SUPPORTED_EXTENSIONS)
    items: set[str] = set()
    for raw in value.split(","):
        ext = raw.strip().lower()
        if not ext:
            continue
        items.add(ext if ext.startswith(".") else f".{ext}")
    return items


def _parse_excluded_dir_names(values: list[str]) -> set[str]:
    names = set(DEFAULT_EXCLUDED_DIR_NAMES)
    for value in values:
        for raw in value.split(","):
            name = raw.strip()
            if name:
                names.add(name)
    return names


def _contains_excluded_dir(path: Path, root: Path, excluded_dir_names: set[str]) -> bool:
    try:
        relative_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        relative_parts = path.parts[:-1]
    return any(part in excluded_dir_names for part in relative_parts)


def _is_excluded_file_name(path: Path) -> bool:
    return path.name == ".DS_Store" or path.name.startswith(DEFAULT_EXCLUDED_FILE_PREFIXES)


def _relative_folder(root_name: str, path: Path, root: Path) -> str:
    rel_parent = path.parent.relative_to(root).as_posix()
    return root_name if rel_parent == "." else f"{root_name}/{rel_parent}"


def _multipart_upload(
    base_url: str,
    path: Path,
    root: Path,
    token: str,
    target_root_name: str,
    timeout: int = 300,
) -> dict:
    boundary = f"----kb-bulk-{time.time_ns()}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="relative_path"\r\n\r\n'
        f"{_relative_folder(target_root_name, path, root)}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + path.read_bytes() + tail
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = request.Request(f"{base_url}/api/files/upload", data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _queue_depth(base_url: str) -> tuple[int, int]:
    try:
        health = _get_json(base_url, "/api/health")
    except Exception:
        return 0, 0
    queue = (((health.get("data") or {}).get("task_queue")) or {})
    return int(queue.get("pending") or 0), int(queue.get("running") or 0)


def _file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def _database_name_from_url(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    return unquote(parsed.path.lstrip("/"))


def _assert_expected_db_name(db_name: str, source: str) -> None:
    if db_name != EXPECTED_DB_NAME:
        raise SystemExit(
            f"Refusing to use database {db_name!r} from {source}; expected {EXPECTED_DB_NAME!r}"
        )


def _project_db_config() -> dict:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        normalized = database_url.replace("postgresql+asyncpg://", "postgresql://")
        _assert_expected_db_name(_database_name_from_url(normalized), "DATABASE_URL")
        return {"url": normalized}

    from app.config import get_settings

    settings = get_settings()
    _assert_expected_db_name(settings.DB_NAME, "app.config.Settings")
    kwargs = {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "user": settings.DB_USER,
        "dbname": settings.DB_NAME,
    }
    if settings.DB_PASSWORD:
        kwargs["password"] = settings.DB_PASSWORD
    return {"kwargs": kwargs}


def _connect_project_db(psycopg_module):
    config = _project_db_config()
    if "url" in config:
        return psycopg_module.connect(config["url"])
    return psycopg_module.connect(**config["kwargs"])


def _normalize_logical_path(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _existing_md5s() -> set[str]:
    driver = "psycopg"
    try:
        import psycopg
    except Exception:
        try:
            import psycopg2 as psycopg  # type: ignore[no-redef]
            driver = "psycopg2"
        except Exception as exc:
            print(json.dumps({
                "event": "md5_prefilter_unavailable",
                "error": str(exc),
            }, ensure_ascii=False), flush=True)
            return set()
    with _connect_project_db(psycopg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select md5_hash
                from framework_file_items
                where coalesce(deleted,false)=false and md5_hash is not null
                union
                select md5_hash
                from kb_documents
                where coalesce(deleted,false)=false and md5_hash is not null
                """
            )
            values = {str(row[0]) for row in cur.fetchall() if row and row[0]}
            print(json.dumps({
                "event": "md5_prefilter_loaded",
                "driver": driver,
                "count": len(values),
            }, ensure_ascii=False), flush=True)
            return values


def _existing_logical_paths(owner_id: int, prefix: str = "企业微盘导入") -> set[str]:
    driver = "psycopg"
    try:
        import psycopg
    except Exception:
        try:
            import psycopg2 as psycopg  # type: ignore[no-redef]
            driver = "psycopg2"
        except Exception as exc:
            print(json.dumps({
                "event": "path_prefilter_unavailable",
                "error": str(exc),
            }, ensure_ascii=False), flush=True)
            return set()
    with _connect_project_db(psycopg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                with recursive folder_paths as (
                    select id,parent_id,name,name::text as path,owner_id
                    from framework_file_folders
                    where parent_id is null and coalesce(deleted,false)=false and owner_id=%s
                    union all
                    select f.id,f.parent_id,f.name,(fp.path || '/' || f.name)::text,f.owner_id
                    from framework_file_folders f
                    join folder_paths fp on fp.id=f.parent_id
                    where coalesce(f.deleted,false)=false and f.owner_id=%s
                )
                select coalesce(fp.path,'') || case when fp.path is null then '' else '/' end
                    || fi.name || case when fi.extension <> '' then '.' || fi.extension else '' end as logical_path
                from framework_file_items fi
                left join folder_paths fp on fp.id=fi.folder_id
                where coalesce(fi.deleted,false)=false
                    and fi.owner_id=%s
                    and coalesce(fp.path,'') like %s
                """,
                (owner_id, owner_id, owner_id, f"{prefix}%"),
            )
            values = {_normalize_logical_path(str(row[0])) for row in cur.fetchall() if row and row[0]}
            print(json.dumps({
                "event": "path_prefilter_loaded",
                "driver": driver,
                "count": len(values),
            }, ensure_ascii=False), flush=True)
            return values


def _logical_path(path: Path, root: Path, target_root_name: str) -> str:
    prefix = _relative_folder(target_root_name, path, root)
    # The framework stores file extensions normalized to lowercase while
    # preserving the stem. Mirror that path shape so existing-path prefiltering
    # does not retry files such as ``3.JPG`` after they were stored as ``3.jpg``.
    filename = f"{path.stem}{path.suffix.lower()}" if path.suffix else path.name
    return _normalize_logical_path(f"{prefix}/{filename}")


def _current_db_identity() -> dict[str, str]:
    config = _project_db_config()
    if "url" in config:
        parsed = urlparse(config["url"])
        return {
            "host": parsed.hostname or "",
            "port": str(parsed.port or ""),
            "user": parsed.username or "",
            "name": _database_name_from_url(config["url"]),
            "source": "DATABASE_URL",
        }
    kwargs = config["kwargs"]
    return {
        "host": str(kwargs.get("host") or ""),
        "port": str(kwargs.get("port") or ""),
        "user": str(kwargs.get("user") or ""),
        "name": str(kwargs.get("dbname") or ""),
        "source": "app.config.Settings",
    }


def _iter_files(
    root: Path,
    max_size: int,
    extensions: set[str],
    excluded_dir_names: set[str],
) -> list[Path]:
    items: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _contains_excluded_dir(path, root, excluded_dir_names):
            continue
        if _is_excluded_file_name(path):
            continue
        ext = path.suffix.lower()
        if ext in VIDEO_EXTENSIONS or ext not in extensions:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size <= 0 or size > max_size:
            continue
        items.append(path)
    return sorted(items, key=lambda p: (p.suffix.lower() not in {".pdf", ".docx", ".xlsx", ".pptx"}, p.stat().st_size))


async def _direct_upload_and_register(path: Path, root: Path, owner_id: int, target_root_name: str) -> dict:
    from app.database import AsyncSessionLocal
    from app.services.file_upload_service import _detect_mime_by_header, upload_file_from_path

    from modules.knowledge.backend.services.document_service import register_document

    tmp_path = Path(tempfile.mkstemp(prefix="kb-bulk-", suffix=path.suffix)[1])
    try:
        shutil.copyfile(path, tmp_path)
        relative_path = _relative_folder(target_root_name, path, root)
        async with AsyncSessionLocal() as db:
            file_info = await upload_file_from_path(
                db,
                tmp_path,
                path.name,
                owner_id,
                relative_path=relative_path,
                md5_hex=_file_md5(path),
                mime_type=_detect_mime_by_header(path, path.name),
            )
            doc_info = await register_document(db, int(file_info["id"]), owner_id, catalog_id=None)
            return {"file": file_info, "document": doc_info}
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:33000")
    parser.add_argument("--username", default=os.getenv("KB_BULK_USERNAME", "何焜华"))
    parser.add_argument("--password", default=os.getenv("KB_BULK_PASSWORD", ""))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--max-size-mb", type=int, default=120)
    parser.add_argument("--queue-high-water", type=int, default=12)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    parser.add_argument("--skip-existing-md5", action="store_true")
    parser.add_argument("--skip-existing-path", action="store_true")
    parser.add_argument("--direct-owner-id", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--target-root-name", default="企业微盘导入")
    parser.add_argument("--extensions", default=None, help="Comma-separated extension allowlist, e.g. .pdf,.docx")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name to skip while scanning. Can be repeated or comma-separated.",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser().resolve()
    loaded_env = _load_env_file(env_file)
    db_identity = _current_db_identity()

    if not args.password and not args.dry_run and args.direct_owner_id <= 0:
        raise SystemExit("KB_BULK_PASSWORD is required")

    root = Path(args.root).expanduser().resolve()
    token = ""
    if not args.dry_run and args.direct_owner_id <= 0:
        login = _json_request(args.base_url, "/api/login", {"username": args.username, "password": args.password})
        token = login["data"]["access_token"]
    max_size = args.max_size_mb * 1024 * 1024
    extensions = _parse_extensions(args.extensions)
    excluded_dir_names = _parse_excluded_dir_names(args.exclude_dir)
    existing_md5s = _existing_md5s() if args.skip_existing_md5 else set()
    existing_paths = (
        _existing_logical_paths(args.direct_owner_id, args.target_root_name)
        if args.skip_existing_path and args.direct_owner_id > 0
        else set()
    )
    candidates = _iter_files(root, max_size, extensions, excluded_dir_names)
    files: list[Path] = []
    skipped_existing = 0
    skipped_existing_path = 0
    for path in candidates:
        if args.skip_existing_md5 and _file_md5(path) in existing_md5s:
            skipped_existing += 1
            continue
        if args.skip_existing_path and _logical_path(path, root, args.target_root_name) in existing_paths:
            skipped_existing_path += 1
            continue
        files.append(path)
        if len(files) >= args.limit:
            break

    print(json.dumps({
        "event": "start",
        "root": str(root),
        "selected": len(files),
        "limit": args.limit,
        "max_size_mb": args.max_size_mb,
        "candidates": len(candidates),
        "target_root_name": args.target_root_name,
        "extensions": sorted(extensions),
        "excluded_dir_names": sorted(excluded_dir_names),
        "skipped_existing_md5": skipped_existing,
        "skipped_existing_path": skipped_existing_path,
        "dry_run": args.dry_run,
        "direct_owner_id": args.direct_owner_id,
        "env_file": str(env_file),
        "loaded_env_keys": sorted(k for k in loaded_env if k != "DB_PASSWORD"),
        "db": db_identity,
    }, ensure_ascii=False), flush=True)
    if args.dry_run:
        for idx, path in enumerate(files[:50], start=1):
            print(json.dumps({
                "event": "would_upload",
                "index": idx,
                "size": path.stat().st_size,
                "path": str(path),
            }, ensure_ascii=False), flush=True)
        return 0

    uploaded = 0
    skipped = 0
    failed = 0
    for idx, path in enumerate(files, start=1):
        while True:
            pending, running = _queue_depth(args.base_url)
            if pending + running < args.queue_high_water:
                break
            print(json.dumps({
                "event": "throttle",
                "pending": pending,
                "running": running,
                "queue_high_water": args.queue_high_water,
            }, ensure_ascii=False), flush=True)
            time.sleep(args.sleep_seconds)

        try:
            if args.direct_owner_id > 0:
                import asyncio
                result = {
                    "success": True,
                    "data": asyncio.run(
                        _direct_upload_and_register(path, root, args.direct_owner_id, args.target_root_name)
                    ),
                }
            else:
                result = _multipart_upload(args.base_url, path, root, token, args.target_root_name)
            if result.get("success"):
                uploaded += 1
                data = result.get("data") or {}
                file_data = data.get("file") if isinstance(data.get("file"), dict) else data
                document_data = data.get("document") if isinstance(data.get("document"), dict) else {}
                print(json.dumps({
                    "event": "uploaded",
                    "index": idx,
                    "file_id": file_data.get("id"),
                    "document_id": document_data.get("document_id"),
                    "size": path.stat().st_size,
                    "path": str(path),
                }, ensure_ascii=False), flush=True)
            else:
                failed += 1
                print(json.dumps({"event": "failed", "index": idx, "path": str(path), "error": result.get("error")}, ensure_ascii=False), flush=True)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code == 409:
                skipped += 1
                print(json.dumps({"event": "skipped_conflict", "index": idx, "path": str(path)}, ensure_ascii=False), flush=True)
            else:
                failed += 1
                print(json.dumps({"event": "http_error", "index": idx, "code": exc.code, "path": str(path), "body": body[:500]}, ensure_ascii=False), flush=True)
        except Exception as exc:
            message = str(exc)
            if "A file with the same name already exists in this directory" in message:
                skipped += 1
                print(json.dumps({
                    "event": "skipped_conflict",
                    "index": idx,
                    "path": str(path),
                    "error": message,
                }, ensure_ascii=False), flush=True)
                continue
            failed += 1
            print(json.dumps({"event": "error", "index": idx, "path": str(path), "error": message}, ensure_ascii=False), flush=True)

    pending, running = _queue_depth(args.base_url)
    print(json.dumps({
        "event": "done",
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "pending": pending,
        "running": running,
    }, ensure_ascii=False), flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
