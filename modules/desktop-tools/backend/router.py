"""FastAPI router for desktop-tools module.

Provides complete CRUD + artifact bridge capabilities for Agent file operations.
All queries are owner-isolated. No Agent should handle base64 or physical paths.
"""
import io
import json
import os

from app.core.exceptions import AppException, NotFound, ValidationError
from app.database import AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.artifact_service import (
    get_artifact,
    list_artifact_versions,
    publish_artifact,
    restore_artifact_version,
)
from app.services.artifact_service import (
    replace_file_from_artifact as svc_replace_from_artifact,
)
from app.services.file_ops_service import copy_item
from app.services.file_reader import get_file_content_bytes, resolve_caller_user_id
from app.services.file_service import check_file_access, delete_to_trash, rename_item
from app.services.file_upload_service import replace_file_content, upload_file
from app.services.module_registry import call_capability, register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

try:
    from .services import file_contract
except ImportError:
    from services import file_contract

_EXT_PARSER_MAP = file_contract.EXT_PARSER_MAP
_TEXT_EXTS = file_contract.TEXT_EXTS
MAX_PAGE_SIZE = file_contract.MAX_PAGE_SIZE
MAX_READ_BLOCKS = file_contract.MAX_READ_BLOCKS
MAX_READ_CHARS = file_contract.MAX_READ_CHARS
_coerce_non_negative_int = file_contract.coerce_non_negative_int
_coerce_page = file_contract.coerce_page
_coerce_page_size = file_contract.coerce_page_size
_coerce_positive_int = file_contract.coerce_positive_int
_file_to_item = file_contract.file_to_item
_folder_to_item = file_contract.folder_to_item
_limit_blocks = file_contract.limit_blocks
_normalize_extension = file_contract.normalize_extension
_normalize_file_name = file_contract.normalize_file_name
_truncate_text = file_contract.truncate_text

router = APIRouter(prefix="/api/desktop-tools", tags=["desktop-tools"])


# ── Framework model imports (used inside handler functions) ──────────
# These are imported lazily inside handlers to avoid circular imports
# at module load time.


# =====================================================================
# Capability: desktop:list_files
# =====================================================================
async def _list_files(params: dict, caller: str) -> dict:
    """List files in a folder (or root). Owner-isolated."""
    from app.models.file import File, Folder

    owner_id = resolve_caller_user_id(caller)
    folder_id = _coerce_non_negative_int(params.get("folder_id", 0), "folder_id")
    page = _coerce_page(params.get("page", 1))
    page_size = _coerce_page_size(params.get("page_size", 50))
    offset = (page - 1) * page_size

    async with AsyncSessionLocal() as db:
        if folder_id:
            folder = await db.get(Folder, folder_id)
            if not folder or folder.deleted or folder.owner_id != owner_id:
                raise NotFound("Folder not found")

        folder_cond = Folder.parent_id.is_(None) if folder_id == 0 else Folder.parent_id == folder_id
        file_cond = File.folder_id.is_(None) if folder_id == 0 else File.folder_id == folder_id

        folder_total = await db.scalar(
            select(func.count(Folder.id)).where(
                folder_cond,
                Folder.owner_id == owner_id,
                Folder.deleted.is_(False),
            )
        ) or 0
        file_total = await db.scalar(
            select(func.count(File.id)).where(
                file_cond,
                File.owner_id == owner_id,
                File.deleted.is_(False),
            )
        ) or 0

        folder_limit = max(0, min(page_size, folder_total - offset))
        folders = []
        if folder_limit:
            folders_result = await db.execute(
                select(Folder).where(
                    folder_cond,
                    Folder.owner_id == owner_id,
                    Folder.deleted.is_(False),
                ).order_by(Folder.name)
                .offset(offset)
                .limit(folder_limit)
            )
            folders = folders_result.scalars().all()

        file_offset = max(0, offset - folder_total)
        file_limit = page_size - len(folders)
        files = []
        if file_limit:
            files_result = await db.execute(
                select(File).where(
                    file_cond,
                    File.owner_id == owner_id,
                    File.deleted.is_(False),
                ).order_by(File.created_at.desc())
                .offset(file_offset)
                .limit(file_limit)
            )
            files = files_result.scalars().all()

        items = [_folder_to_item(f) for f in folders] + [_file_to_item(f) for f in files]

    return {
        "items": items,
        "total": folder_total + file_total,
        "page": page,
        "page_size": page_size,
        "folder_id": folder_id,
    }


async def _search_files(params: dict, caller: str) -> dict:
    """Search files by keyword / extension. Owner-isolated."""
    from app.models.file import File

    owner_id = resolve_caller_user_id(caller)
    keyword = str(params.get("keyword", "")).strip()
    extension = _normalize_extension(params.get("extension"))
    page = _coerce_page(params.get("page", 1))
    page_size = _coerce_page_size(params.get("page_size", 50))

    async with AsyncSessionLocal() as db:
        conds = [File.owner_id == owner_id, File.deleted.is_(False)]
        if keyword:
            conds.append(File.name.ilike(f"%{keyword}%"))
        if extension:
            conds.append(File.extension == extension)

        total = await db.scalar(select(func.count(File.id)).where(*conds)) or 0
        query = (
            select(File)
            .where(*conds)
            .order_by(File.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        files = result.scalars().all()

        items = [_file_to_item(f) for f in files]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "keyword": keyword,
        "extension": extension,
    }

# =====================================================================
# Capability: desktop:read_file
# =====================================================================
async def _read_file(params: dict, caller: str) -> dict:
    """Read file content, routing to the appropriate parser module by extension.

    If a format parser module is registered, delegates via call_capability.
    Pure text formats fall back to direct disk read when no parser is registered.
    Access-controlled: owner or shared users can read it.
    """
    from app.services.file_service import check_file_access

    owner_id = resolve_caller_user_id(caller)
    file_id = _coerce_positive_int(params.get("file_id", 0), "file_id")

    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, owner_id)

        ext = (file.extension or "").lower()
        file_info = {
            "file_id": file_id,
            "name": file.name,
            "extension": ext,
            "size": file.size,
            "mime_type": file.mime_type,
        }

        parser_module = _EXT_PARSER_MAP.get(ext)

        if parser_module:
            # Try to delegate to the format parser module
            try:
                parse_result = await call_capability(
                    parser_module,
                    "parse",
                    {"file_id": file_id},
                    caller=caller,
                    caller_role="viewer",
                )
                # Convert unified content blocks to plain text for Agent consumption
                if isinstance(parse_result, dict) and parse_result.get("success") is False:
                    raise ValidationError(str(parse_result.get("error") or f"{parser_module}:parse failed"))
                blocks = parse_result.get("blocks", [])
                if not isinstance(blocks, list):
                    raise ValidationError(f"Parser module '{parser_module}' returned invalid blocks")
                limited_blocks, limit_info = _limit_blocks(blocks)
                plain_text, content_limit_info = _truncate_text(
                    "\n\n".join(
                        b.get("text", "") for b in limited_blocks if b.get("text")
                    )
                )
                limit_info["returned_chars"] = content_limit_info["returned_chars"]
                return {
                    "success": True,
                    "file": file_info,
                    "content": plain_text,
                    "blocks": limited_blocks,
                    "parser": parser_module,
                    "truncated": limit_info["truncated"] or content_limit_info["truncated"],
                    "limits": limit_info,
                }
            except Exception as exc:
                # Parser module not available or error – fallback for text formats
                if ext not in _TEXT_EXTS:
                    raise ValidationError(
                        f"Parser module '{parser_module}' unavailable or failed: {exc}"
                    )
                # Fall through to direct text read
        elif ext not in _TEXT_EXTS:
            raise ValidationError(f"Unsupported file extension for reading: .{ext or 'unknown'}")

        # Direct read for pure-text formats
        from pathlib import Path

        from app.config import get_settings

        if not file.storage_path:
            raise NotFound("File storage path is empty")

        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise AppException("Invalid file path", status_code=400)
        if not full_path.exists() or not full_path.is_file():
            raise NotFound("File on disk not found")

        ALLOWED_ENCS = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
        raw = full_path.read_bytes()
        content = None
        for enc in ALLOWED_ENCS:
            try:
                content = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if content is None:
            content = raw.decode("utf-8", errors="replace")

        content, limit_info = _truncate_text(content)
        return {
            "success": True,
            "file": file_info,
            "content": content,
            "blocks": [{"type": "paragraph", "text": content}],
            "parser": "direct",
            "truncated": limit_info["truncated"],
            "limits": limit_info,
        }


# =====================================================================
# Capability: desktop:list_apps
# =====================================================================
async def _list_apps(params: dict, caller: str) -> dict:
    """List desktop applications accessible to the current user."""
    from app.models.app import App
    from app.services.app_service import can_user_access_app

    owner_id = resolve_caller_user_id(caller)

    async with AsyncSessionLocal() as db:
        # We need the User model to check role-based access
        from app.models.user import User as UserModel

        user = await db.get(UserModel, owner_id)
        if not user:
            return {"apps": []}

        result = await db.execute(
            select(App).where(App.enabled.is_(True)).order_by(App.sort_order, App.name)
        )
        apps = result.scalars().all()

        accessible = []
        for app in apps:
            if can_user_access_app(app, user):
                public_actions = app.public_actions or []
                manifest_actions = public_actions if isinstance(public_actions, list) else []

                accessible.append({
                    "id": app.id,
                    "key": app.key,
                    "name": app.name,
                    "icon": app.icon,
                    "category": app.category,
                    "description": app.description or "",
                    "sort_order": app.sort_order,
                    "singleton": app.singleton,
                    "show_in_launcher": app.show_in_launcher,
                    "show_on_desktop": app.show_on_desktop,
                    "window_type": app.window_type,
                    "default_width": app.default_width,
                    "default_height": app.default_height,
                    "public_actions": manifest_actions,
                })

    return {"apps": accessible}


# =====================================================================
# Capability: desktop:get_file
# =====================================================================
async def _get_file(params: dict, caller: str) -> dict:
    """Get a single file's metadata by file_id."""

    owner_id = resolve_caller_user_id(caller)
    file_id = _coerce_positive_int(params.get("file_id", 0), "file_id")

    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, owner_id)

    return {
        "file_id": file.id,
        "name": file.name,
        "extension": file.extension,
        "size": file.size,
        "mime_type": file.mime_type,
        "folder_id": file.folder_id,
        "created_at": str(file.created_at) if file.created_at else None,
        "updated_at": str(file.updated_at) if file.updated_at else None,
        "md5_hash": file.md5_hash,
    }


# =====================================================================
# Capability: desktop:create_file
# =====================================================================
async def _create_file(params: dict, caller: str) -> dict:
    """Create a new file. Accepts text content or generates from template.
    For binary content, use create_file then replace_file_from_artifact.
    """
    owner_id = resolve_caller_user_id(caller)
    name = _normalize_file_name(params.get("name", "Untitled"))
    extension = _normalize_extension(params.get("extension", "txt")) or "txt"
    content = params.get("content", "")
    folder_id = (
        _coerce_positive_int(params.get("folder_id"), "folder_id")
        if params.get("folder_id") is not None
        else None
    )
    if not isinstance(content, (str, bytes, bytearray)):
        raise ValidationError("content must be text or bytes")

    async with AsyncSessionLocal() as db:
        result = await upload_file(
            db, io.BytesIO(content.encode("utf-8") if isinstance(content, str) else bytes(content)),
            f"{name}.{extension}", owner_id, folder_id,
        )

    return {
        "file_id": result["id"],
        "name": result["name"],
        "extension": result["extension"],
        "size": result["size"],
        "mime_type": result["mime_type"],
    }


# =====================================================================
# Capability: desktop:replace_file
# Now supports three input modes:
#   1. new_content (string text) — for text files
#   2. source_artifact_id (int) — replace from an artifact (no base64 needed)
#   3. source_file_id (int) — replace from another file
# =====================================================================
async def _replace_file(params: dict, caller: str) -> dict:
    """Replace an existing file's content. No base64 needed for binary files
    — use source_artifact_id or source_file_id instead.
    """
    owner_id = resolve_caller_user_id(caller)
    old_file_id = _coerce_positive_int(params.get("old_file_id", 0), "old_file_id")
    new_content = params.get("new_content", "")
    source_artifact_id = params.get("source_artifact_id")
    source_file_id = params.get("source_file_id")

    async with AsyncSessionLocal() as db:
        await check_file_access(db, old_file_id, owner_id)

        if source_artifact_id is not None:
            artifact_id = _coerce_positive_int(source_artifact_id, "source_artifact_id")
            artifact = await get_artifact(db, artifact_id, owner_id)
            if artifact.get("file_id"):
                content_bytes = await get_file_content_bytes(artifact["file_id"], owner_id)
            elif artifact.get("content_text"):
                content_bytes = artifact["content_text"].encode("utf-8")
            elif artifact.get("content_json"):
                content_bytes = json.dumps(artifact["content_json"], ensure_ascii=False).encode("utf-8")
            else:
                raise ValidationError("Artifact has no content")
            result = await replace_file_content(db, old_file_id, owner_id, content_bytes)
        elif source_file_id is not None:
            source_id = _coerce_positive_int(source_file_id, "source_file_id")
            content_bytes = await get_file_content_bytes(source_id, owner_id)
            result = await replace_file_content(db, old_file_id, owner_id, content_bytes)
        elif new_content != "":
            if not isinstance(new_content, str):
                raise ValidationError("new_content must be a string")
            result = await replace_file_content(db, old_file_id, owner_id, new_content.encode("utf-8"))
        else:
            raise ValidationError("Provide new_content, source_artifact_id, or source_file_id")

    return {
        "old_file_id": old_file_id,
        "new_file_id": result["id"],
        "name": result["name"],
        "size": result["size"],
        "md5_hash": result.get("md5_hash"),
    }


# =====================================================================
# Capability: desktop:delete_file
# =====================================================================
async def _delete_file(params: dict, caller: str) -> dict:
    """Soft-delete a file. Supports restore."""
    owner_id = resolve_caller_user_id(caller)
    file_id = _coerce_positive_int(params.get("file_id", 0), "file_id")

    async with AsyncSessionLocal() as db:
        await delete_to_trash(db, "file", file_id, owner_id)

    return {"file_id": file_id, "deleted": True}


# =====================================================================
# Capability: desktop:rename_file
# =====================================================================
async def _rename_file(params: dict, caller: str) -> dict:
    """Rename a file."""
    owner_id = resolve_caller_user_id(caller)
    file_id = _coerce_positive_int(params.get("file_id", 0), "file_id")
    new_name = _normalize_file_name(params.get("new_name", ""))

    async with AsyncSessionLocal() as db:
        await rename_item(db, "file", file_id, new_name, owner_id)

    return {"file_id": file_id, "new_name": new_name}


# =====================================================================
# Capability: desktop:copy_file
# =====================================================================
async def _copy_file(params: dict, caller: str) -> dict:
    """Copy a file to a target folder."""
    owner_id = resolve_caller_user_id(caller)
    file_id = _coerce_positive_int(params.get("file_id", 0), "file_id")
    target_folder_id = (
        _coerce_positive_int(params.get("target_folder_id"), "target_folder_id")
        if params.get("target_folder_id") is not None
        else None
    )

    async with AsyncSessionLocal() as db:
        result = await copy_item(db, "file", file_id, target_folder_id, owner_id)

    return {"file_id": file_id, "new_file_id": result.id}


# =====================================================================
# Capability: desktop:list_versions
# =====================================================================
async def _list_versions(params: dict, caller: str) -> dict:
    """List all available versions of a file (via linked artifact)."""
    owner_id = resolve_caller_user_id(caller)
    artifact_id = _coerce_positive_int(params.get("artifact_id", 0), "artifact_id")

    async with AsyncSessionLocal() as db:
        versions = await list_artifact_versions(db, artifact_id, owner_id)

    return {"artifact_id": artifact_id, "versions": versions}


# =====================================================================
# Capability: desktop:restore_version
# =====================================================================
async def _restore_version(params: dict, caller: str) -> dict:
    """Restore a file to a previous version."""
    owner_id = resolve_caller_user_id(caller)
    artifact_id = _coerce_positive_int(params.get("artifact_id", 0), "artifact_id")
    version_id = _coerce_positive_int(params.get("version_id", 0), "version_id")

    async with AsyncSessionLocal() as db:
        result = await restore_artifact_version(db, artifact_id, version_id, owner_id)

    return {"artifact_id": artifact_id, "version_id": version_id, "artifact": result}


# =====================================================================
# Capability: desktop:replace_file_from_artifact
# =====================================================================
async def _replace_file_from_artifact(params: dict, caller: str) -> dict:
    """Replace a desktop file using content from an artifact.
    No base64 needed — system handles binary internally.
    """
    owner_id = resolve_caller_user_id(caller)
    target_file_id = _coerce_positive_int(params.get("target_file_id", 0), "target_file_id")
    source_artifact_id = _coerce_positive_int(params.get("source_artifact_id", 0), "source_artifact_id")

    async with AsyncSessionLocal() as db:
        result = await svc_replace_from_artifact(
            db, owner_id, target_file_id, source_artifact_id,
        )

    return result


# =====================================================================
# Capability: desktop:publish_artifact
# =====================================================================
async def _publish_artifact(params: dict, caller: str) -> dict:
    """Publish an artifact to the desktop as a file.
    Creates or replaces a desktop file entry from artifact content.
    """
    owner_id = resolve_caller_user_id(caller)
    artifact_id = _coerce_positive_int(params.get("artifact_id", 0), "artifact_id")
    target_file_id = (
        _coerce_positive_int(params.get("target_file_id"), "target_file_id")
        if params.get("target_file_id") is not None
        else None
    )

    async with AsyncSessionLocal() as db:
        result = await publish_artifact(
            db, artifact_id, owner_id,
            target_file_id=target_file_id,
        )

    return result


# =====================================================================
# Capability: desktop:refresh
# =====================================================================
async def _refresh_desktop(params: dict, caller: str) -> dict:
    """Trigger desktop file list refresh."""
    return {"refreshed": True}


register_capability(
    "desktop-tools", "list_files", _list_files,
    description="List files in a folder (or root). Returns file name, type, size, and id.",
    brief="列出桌面文件",
    parameters={
        "type": "object",
        "properties": {
            "folder_id": {"type": "integer", "description": "Folder ID (0 or omit for root)", "default": 0},
            "page": {"type": "integer", "description": "Page number", "default": 1},
            "page_size": {
                "type": "integer",
                "description": "Items per page (max 100)",
                "default": 50,
            },
        },
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "search_files", _search_files,
    description="Search files by keyword and/or extension. Returns matching file metadata.",
    brief="搜索桌面文件",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search keyword (file name contains)", "default": ""},
            "extension": {"type": "string", "description": "Filter by extension (e.g. pdf, txt)", "default": None},
            "page": {"type": "integer", "description": "Page number", "default": 1},
            "page_size": {
                "type": "integer",
                "description": "Items per page (max 100)",
                "default": 50,
            },
        },
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "read_file", _read_file,
    description=(
        "Read file content by file_id. Routes to correct parser and returns "
        f"text content capped at {MAX_READ_CHARS} chars with truncation metadata."
    ),
    brief="读取文件内容",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID in the file storage system"},
        },
        "required": ["file_id"],
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "list_apps", _list_apps,
    description="List desktop applications available to the current user.",
    brief="列出可用桌面应用",
    parameters={
        "type": "object",
        "properties": {},
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "get_file", _get_file,
    description="Get a single file's metadata by file_id.",
    brief="获取文件详情",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID"},
        },
        "required": ["file_id"],
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "create_file", _create_file,
    description="Create a new file with text content. For binary content, use artifact-based replace.",
    brief="创建文件",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "File name (without extension)", "default": "Untitled"},
            "extension": {"type": "string", "description": "File extension", "default": "txt"},
            "content": {"type": "string", "description": "File content as text", "default": ""},
            "folder_id": {"type": "integer", "description": "Target folder ID (optional)"},
        },
        "required": ["name", "extension"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "replace_file", _replace_file,
    brief="替换桌面文件内容",
    description="Replace an existing file's content. Supports text (new_content), "
                "artifact source (source_artifact_id), or file source (source_file_id). No base64 needed.",
    parameters={
        "type": "object",
        "properties": {
            "old_file_id": {"type": "integer", "description": "Existing file ID to replace"},
            "new_content": {"type": "string", "description": "New file content as plain text", "default": ""},
            "source_artifact_id": {"type": "integer", "description": "Source artifact ID", "default": None},
            "source_file_id": {"type": "integer", "description": "Source file ID to copy content from", "default": None},
        },
        "required": ["old_file_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "delete_file", _delete_file,
    brief="删除文件",
    description="Soft-delete a file. Can be restored later.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID to delete"},
        },
        "required": ["file_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "rename_file", _rename_file,
    brief="重命名文件",
    description="Rename a file.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID"},
            "new_name": {"type": "string", "description": "New file name (without extension)"},
        },
        "required": ["file_id", "new_name"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "copy_file", _copy_file,
    brief="复制文件",
    description="Copy a file to a target folder.",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID to copy"},
            "target_folder_id": {"type": "integer", "description": "Target folder ID (optional)"},
        },
        "required": ["file_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "list_versions", _list_versions,
    brief="列出文件版本",
    description="List all available versions of a file (via linked artifact).",
    parameters={
        "type": "object",
        "properties": {
            "artifact_id": {"type": "integer", "description": "Artifact ID to list versions for"},
        },
        "required": ["artifact_id"],
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "restore_version", _restore_version,
    brief="恢复文件版本",
    description="Restore a file to a previous version.",
    parameters={
        "type": "object",
        "properties": {
            "artifact_id": {"type": "integer", "description": "Artifact ID"},
            "version_id": {"type": "integer", "description": "Version ID to restore"},
        },
        "required": ["artifact_id", "version_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "replace_file_from_artifact", _replace_file_from_artifact,
    brief="从制品替换桌面文件",
    description="Replace a desktop file using content from an artifact. No base64 needed.",
    parameters={
        "type": "object",
        "properties": {
            "target_file_id": {"type": "integer", "description": "Desktop file ID to replace"},
            "source_artifact_id": {"type": "integer", "description": "Artifact ID with the new content"},
        },
        "required": ["target_file_id", "source_artifact_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "publish_artifact", _publish_artifact,
    brief="发布制品到桌面",
    description="Publish an artifact to the desktop as a file. Creates or replaces a desktop file entry.",
    parameters={
        "type": "object",
        "properties": {
            "artifact_id": {"type": "integer", "description": "Artifact ID to publish"},
            "target_file_id": {"type": "integer", "description": "Target desktop file ID (optional, creates new if omitted)"},
        },
        "required": ["artifact_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "refresh", _refresh_desktop,
    brief="刷新桌面",
    description="Trigger desktop file list reload.",
    parameters={
        "type": "object",
        "properties": {},
    },
    min_role="viewer",
)


# =====================================================================
# HTTP endpoints (for direct testing / sandbox)
# =====================================================================

class ListFilesRequest(BaseModel):
    folder_id: int = 0
    page: int = 1
    page_size: int = 50


class SearchFilesRequest(BaseModel):
    keyword: str = ""
    extension: str | None = None
    page: int = 1
    page_size: int = 50


class ReadFileRequest(BaseModel):
    file_id: int


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "desktop-tools", "status": "ok"})


@router.post("/list-files")
async def http_list_files(
    body: ListFilesRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _list_files(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/search-files")
async def http_search_files(
    body: SearchFilesRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _search_files(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/read-file")
async def http_read_file(
    body: ReadFileRequest,
    user: User = Depends(require_permission("viewer")),
):
    result = await _read_file(body.model_dump(), f"user:{user.id}")
    return ApiResponse(data=result)


@router.get("/list-apps")
async def http_list_apps(
    user: User = Depends(require_permission("viewer")),
):
    result = await _list_apps({}, f"user:{user.id}")
    return ApiResponse(data=result)
