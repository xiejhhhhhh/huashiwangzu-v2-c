"""FastAPI router for desktop-tools module.

Exposes 4 cross-module capabilities (desktop:list_files, desktop:search_files,
desktop:read_file, desktop:list_apps) that bridge framework file/app capabilities
to the Agent's tool discovery system. All queries are owner-isolated.
"""
import os

from app.database import AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import call_capability, register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

router = APIRouter(prefix="/api/desktop-tools", tags=["desktop-tools"])


# ── Framework model imports (used inside handler functions) ──────────
# These are imported lazily inside handlers to avoid circular imports
# at module load time.


# ── Helper: build flat file list items ───────────────────────────────
_FILE_FIELDS = (
    "id",
    "name",
    "extension",
    "size",
    "mime_type",
    "folder_id",
    "created_at",
    "updated_at",
)


def _file_to_item(file) -> dict:
    return {k: getattr(file, k, None) for k in _FILE_FIELDS}


def _folder_to_item(folder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "extension": None,
        "size": 0,
        "mime_type": None,
        "folder_id": folder.parent_id,
        "created_at": str(folder.created_at) if folder.created_at else None,
        "updated_at": str(folder.created_at) if folder.created_at else None,
        "is_folder": True,
    }


# =====================================================================
# Capability: desktop:list_files
# =====================================================================
async def _list_files(params: dict, caller: str) -> dict:
    """List files in a folder (or root). Owner-isolated."""
    from app.models.file import File, Folder

    owner_id = resolve_caller_user_id(caller)
    folder_id = int(params.get("folder_id", 0))
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 50))

    async with AsyncSessionLocal() as db:
        folders_result = await db.execute(
            select(Folder).where(
                Folder.parent_id == (None if folder_id == 0 else folder_id),
                Folder.owner_id == owner_id,
                Folder.deleted == False,
            ).order_by(Folder.name)
        )
        folders = folders_result.scalars().all()

        file_query = (
            select(File).where(
                File.folder_id.is_(None) if folder_id == 0 else File.folder_id == folder_id,
                File.owner_id == owner_id,
                File.deleted == False,
            ).order_by(File.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        files_result = await db.execute(file_query)
        files = files_result.scalars().all()

        items = [_folder_to_item(f) for f in folders] + [_file_to_item(f) for f in files]

    return {
        "items": items,
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "folder_id": folder_id,
    }


# =====================================================================
# Capability: desktop:search_files
# =====================================================================
async def _search_files(params: dict, caller: str) -> dict:
    """Search files by keyword / extension. Owner-isolated."""
    from app.models.file import File

    owner_id = resolve_caller_user_id(caller)
    keyword = params.get("keyword", "")
    extension = params.get("extension")
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 50))

    async with AsyncSessionLocal() as db:
        conds = [File.owner_id == owner_id, File.deleted == False]
        if keyword:
            conds.append(File.name.ilike(f"%{keyword}%"))
        if extension:
            ext_clean = extension.strip().lstrip(".")
            conds.append(File.extension == ext_clean)

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
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "keyword": keyword,
        "extension": extension,
    }


# =====================================================================
# Capability: desktop:read_file
# =====================================================================
_EXT_PARSER_MAP = {
    "pdf": "pdf-parser",
    "docx": "docx-parser",
    "xlsx": "xlsx-parser",
    "xls": "xlsx-parser",
    "csv": "xlsx-parser",
    "pptx": "pptx-parser",
    "txt": "text-parser",
    "md": "text-parser",
    "markdown": "text-parser",
    "text": "text-parser",
    "log": "text-parser",
}

# Pure-text formats that can be read directly (fallback if parser module not available)
_TEXT_EXTS = {"txt", "md", "markdown", "text", "log", "csv"}


async def _read_file(params: dict, caller: str) -> dict:
    """Read file content, routing to the appropriate parser module by extension.

    If a format parser module is registered, delegates via call_capability.
    Pure text formats fall back to direct disk read when no parser is registered.
    Access-controlled: owner or shared users can read it.
    """
    from app.services.file_service import check_file_access

    owner_id = resolve_caller_user_id(caller)
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    async with AsyncSessionLocal() as db:
        try:
            file = await check_file_access(db, file_id, owner_id)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

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
                blocks = parse_result.get("blocks", [])
                plain_text = "\n\n".join(
                    b.get("text", "") for b in blocks if b.get("text")
                )
                return {
                    "success": True,
                    "file": file_info,
                    "content": plain_text,
                    "blocks": blocks,
                    "parser": parser_module,
                }
            except Exception as exc:
                # Parser module not available or error – fallback for text formats
                if ext not in _TEXT_EXTS:
                    return {
                        "success": False,
                        "error": f"Parser module '{parser_module}' unavailable or failed: {exc}",
                        "file": file_info,
                    }
                # Fall through to direct text read

        # Direct read for pure-text formats
        from pathlib import Path

        from app.config import get_settings

        if not file.storage_path:
            return {"success": False, "error": "File storage path is empty", "file": file_info}

        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            return {"success": False, "error": "Invalid file path", "file": file_info}
        if not full_path.exists() or not full_path.is_file():
            return {"success": False, "error": "File on disk not found", "file": file_info}

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

        return {
            "success": True,
            "file": file_info,
            "content": content,
            "blocks": [{"type": "paragraph", "text": content}],
            "parser": "direct",
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
            select(App).where(App.enabled == True).order_by(App.sort_order, App.name)
        )
        apps = result.scalars().all()

        accessible = []
        for app in apps:
            if can_user_access_app(app, user):
                manifest_actions = []
                if app.backend_config:
                    public_actions = app.backend_config.get("public_actions")
                    if public_actions:
                        manifest_actions = public_actions

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
# Register capabilities with framework
# =====================================================================

register_capability(
    "desktop-tools", "list_files", _list_files,
    description="List files in a folder (or root). Returns file name, type, size, and id.",
    brief="列出桌面文件",
    parameters={
        "type": "object",
        "properties": {
            "folder_id": {"type": "integer", "description": "Folder ID (0 or omit for root)", "default": 0},
            "page": {"type": "integer", "description": "Page number", "default": 1},
            "page_size": {"type": "integer", "description": "Items per page", "default": 50},
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
            "page_size": {"type": "integer", "description": "Items per page", "default": 50},
        },
    },
    min_role="viewer",
)

register_capability(
    "desktop-tools", "read_file", _read_file,
    description="Read file content by file_id. Automatically routes to the correct parser for PDF, DOCX, XLSX, PPTX, TXT, MD. Returns the file's text content.",
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


# =====================================================================
# Capability: desktop:replace_file
# =====================================================================
async def _replace_file(params: dict, caller: str) -> dict:
    """Replace an existing desktop file entry. Does NOT delete physical file.

    Soft-deletes the old file entry and creates a new one.
    Physical files stay on disk; old entry is marked deleted for later
    cleanup (3-month retention policy).
    """
    import io as _io
    from datetime import datetime, timezone

    from app.services.file_service import check_file_access
    from app.services.file_upload_service import upload_file

    owner_id = resolve_caller_user_id(caller)
    old_file_id = int(params.get("old_file_id", 0))
    new_filename = params.get("new_filename", "")
    new_content = params.get("new_content", "")  # text content
    new_bytes_b64 = params.get("new_bytes_base64", "")  # binary content base64

    if old_file_id <= 0:
        raise ValueError("old_file_id must be a positive integer")

    async with AsyncSessionLocal() as db:
        # Verify access to old file
        old_file = await check_file_access(db, old_file_id, owner_id)

        # Soft-delete old entry
        old_file.deleted = True
        old_file.deleted_at = datetime.now(timezone.utc)

        # Create new file entry
        if new_content or new_bytes_b64:
            ext = (new_filename.rsplit(".", 1)[-1] if "." in new_filename else old_file.extension or "").lower()
            name_no_ext = new_filename.rsplit(".", 1)[0] if "." in new_filename else new_filename or old_file.name
            if new_bytes_b64:
                import base64
                file_bytes = base64.b64decode(new_bytes_b64)
            else:
                file_bytes = new_content.encode("utf-8")

            result = await upload_file(
                db, _io.BytesIO(file_bytes), f"{name_no_ext}.{ext}",
                owner_id, old_file.folder_id,
            )
        else:
            # No new content: just re-enable old file with same name
            old_file.deleted = False
            old_file.deleted_at = None
            result = {"id": old_file.id, "name": old_file.name, "extension": old_file.extension,
                       "size": old_file.size, "mime_type": old_file.mime_type}

        await db.commit()

    return {
        "old_file_id": old_file_id,
        "new_file_id": result["id"],
        "new_name": result["name"],
        "new_extension": result.get("extension"),
        "new_size": result.get("size"),
        "old_file_retained_on_disk": True,
    }


# =====================================================================
# Capability: desktop:refresh
# =====================================================================
async def _refresh_desktop(params: dict, caller: str) -> dict:
    """Trigger desktop file list refresh.
    
    The frontend listens for this event and reloads the desktop file grid.
    """
    return {"refreshed": True}


register_capability(
    "desktop-tools", "replace_file", _replace_file,
    brief="替换桌面文件",
    description="Soft-delete old file entry and create new one. Physical file stays on disk. "
                "Use this to update a previously generated file on the desktop.",
    parameters={
        "type": "object",
        "properties": {
            "old_file_id": {"type": "integer", "description": "Existing file ID to replace"},
            "new_filename": {"type": "string", "description": "New file name (with extension)", "default": ""},
            "new_content": {"type": "string", "description": "New file content as plain text", "default": ""},
            "new_bytes_base64": {"type": "string", "description": "New file content as base64-encoded bytes (for binary files)", "default": ""},
        },
        "required": ["old_file_id"],
    },
    min_role="editor",
)

register_capability(
    "desktop-tools", "refresh", _refresh_desktop,
    brief="刷新桌面",
    description="Trigger desktop file list reload. Call this after generating or replacing files "
                "to ensure the desktop shows the latest files.",
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
