import os
import json
import shutil
from datetime import datetime

BACKUP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "backups")


def _ensure_backup_dir() -> str:
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    return BACKUP_ROOT


def _format_size(bytes_val: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    i = 0
    size = float(bytes_val)
    while size >= 1024 and i < 3:
        size /= 1024
        i += 1
    return f"{round(size, 2)} {units[i]}"


def _dir_size(dir_path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(dir_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def _read_manifest(manifest_path: str) -> dict | None:
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _is_complete(backup_dir: str, manifest: dict) -> bool:
    file_list = manifest.get("file_list", [])
    if not file_list:
        return False
    for entry in file_list:
        rel_path = entry.get("path", "")
        if not rel_path or not os.path.isfile(os.path.join(backup_dir, rel_path)):
            return False
    return True


def get_backup_list() -> list[dict]:
    root = _ensure_backup_dir()
    try:
        entries = sorted(os.listdir(root), reverse=True)
    except OSError:
        return []
    results = []
    for name in entries:
        dir_path = os.path.join(root, name)
        manifest_path = os.path.join(dir_path, "manifest.json")
        if not os.path.isdir(dir_path) or not os.path.isfile(manifest_path):
            continue
        manifest = _read_manifest(manifest_path)
        if manifest is None:
            continue
        results.append({
            "backup_name": name,
            "backup_time": manifest.get("backup_time", name),
            "database_name": manifest.get("database_name", "unknown"),
            "backup_size": _format_size(_dir_size(dir_path)),
            "backup_status": "complete" if _is_complete(dir_path, manifest) else "incomplete",
        })
    return results


def get_backup_detail(name: str) -> dict | None:
    root = _ensure_backup_dir()
    dir_path = os.path.join(root, name)
    manifest_path = os.path.join(dir_path, "manifest.json")
    if not os.path.isdir(dir_path) or not os.path.isfile(manifest_path):
        return None
    manifest = _read_manifest(manifest_path)
    if manifest is None:
        return None
    file_list = manifest.get("file_list", [])
    return {
        "backup_name": name,
        "backup_time": manifest.get("backup_time", name),
        "database_name": manifest.get("database_name", "unknown"),
        "upload_source": manifest.get("upload_source", ""),
        "upload_source_note": manifest.get("upload_source_note", ""),
        "backup_size": _format_size(_dir_size(dir_path)),
        "backup_status": "complete" if _is_complete(dir_path, manifest) else "incomplete",
        "file_count": len(file_list) if isinstance(file_list, list) else 0,
        "file_list": file_list if isinstance(file_list, list) else [],
    }
