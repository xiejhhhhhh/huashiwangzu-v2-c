"""文档开放接口 facade module.

Implements a Tencent Docs-style OpenAPI with self-hosted token triple
(Client-Id, Open-Id, Access-Token) + REST endpoints + embeddable editor.

This module delegates to existing editors via framework public APIs
and registered capabilities. It does NOT rewrite any editor.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from app.database import get_db
from app.models.user import User
from app.models.file import File
from app.schemas.common import ApiResponse
from app.core.exceptions import NotFound, AppException, PermissionDenied, AuthError
from app.services.file_service import check_file_access as framework_check_file_access
from app.services.module_registry import register_capability
from app.config import get_settings

from .models import DocsOpenToken, ensure_tables
from .token_service import create_token, validate_token, check_doc_access

# Ensure tables exist at module load time
ensure_tables()

router = APIRouter(prefix="/api/docs", tags=["docs-open"])


# ── Schemas ──

class TokenRequest(BaseModel):
    client_id: str = "default"
    open_id: int | None = None
    scope: dict | None = None
    expiry_hours: int = 2


class OpenRequest(BaseModel):
    file_id: int
    mode: str = "view"


class CreateDocRequest(BaseModel):
    title: str
    doc_type: str = "txt"
    folder_id: int | None = None


class ContentWriteRequest(BaseModel):
    content: dict | list | str


class ExportRequest(BaseModel):
    target_format: str = "pdf"


# ── Document type mapping ──

DOC_TYPE_MAP = {
    "xlsx": {"category": "spreadsheet", "editor": "excel-engine", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "xls": {"category": "spreadsheet", "editor": "excel-engine", "mime": "application/vnd.ms-excel"},
    "csv": {"category": "spreadsheet", "editor": "excel-engine", "mime": "text/csv"},
    "txt": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "md": {"category": "text", "editor": "text-editor", "mime": "text/markdown"},
    "json": {"category": "text", "editor": "text-editor", "mime": "application/json"},
    "yaml": {"category": "text", "editor": "text-editor", "mime": "text/yaml"},
    "yml": {"category": "text", "editor": "text-editor", "mime": "text/yaml"},
    "xml": {"category": "text", "editor": "text-editor", "mime": "application/xml"},
    "ini": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "cfg": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "log": {"category": "text", "editor": "text-editor", "mime": "text/plain"},
    "pdf": {"category": "document", "editor": "pdf-viewer", "mime": "application/pdf"},
    "docx": {"category": "document", "editor": "doc-viewer", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "doc": {"category": "document", "editor": "doc-viewer", "mime": "application/msword"},
    "pptx": {"category": "presentation", "editor": "ppt-viewer", "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "ppt": {"category": "presentation", "editor": "ppt-viewer", "mime": "application/vnd.ms-powerpoint"},
    "png": {"category": "image", "editor": "image-viewer", "mime": "image/png"},
    "jpg": {"category": "image", "editor": "image-viewer", "mime": "image/jpeg"},
    "jpeg": {"category": "image", "editor": "image-viewer", "mime": "image/jpeg"},
    "gif": {"category": "image", "editor": "image-viewer", "mime": "image/gif"},
    "svg": {"category": "image", "editor": "image-viewer", "mime": "image/svg+xml"},
    "bmp": {"category": "image", "editor": "image-viewer", "mime": "image/bmp"},
    "webp": {"category": "image", "editor": "image-viewer", "mime": "image/webp"},
}

EMBED_URL_TEMPLATE = "/api/docs/embed/{file_id}?token={access_token}&client_id={client_id}&open_id={open_id}"


def _get_doc_type(extension: str) -> dict:
    ext = (extension or "").lower().lstrip(".")
    info = DOC_TYPE_MAP.get(ext, {"category": "unknown", "editor": None, "mime": "application/octet-stream"})
    return {**info, "extension": ext}


async def get_authenticated_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via token triple (X- headers) or JWT bearer.

    Token triple (仿腾讯文档三件套) takes precedence when all three
    X-Client-Id, X-Open-Id, X-Access-Token are present.
    Falls back to standard JWT Bearer token (Authorization header).
    """
    x_client_id = request.headers.get("X-Client-Id")
    x_open_id = request.headers.get("X-Open-Id")
    x_access_token = request.headers.get("X-Access-Token")

    if x_client_id and x_open_id and x_access_token:
        token_record = await validate_token(db, x_access_token, x_client_id, x_open_id)
        user = await db.get(User, int(x_open_id))
        if not user or not user.enabled:
            raise PermissionDenied("User not found or disabled")
        return user

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header[7:]
        from app.services.auth import decode_access_token, get_user_by_id as auth_get_user
        payload = decode_access_token(jwt_token)
        user_id = int(payload.get("sub", 0))
        token_sv = payload.get("sv", 0)
        user = await auth_get_user(db, user_id)
        if not user or not user.enabled:
            raise PermissionDenied("User not found or disabled")
        if token_sv != user.session_version:
            raise PermissionDenied("Session expired, please login again")
        return user

    raise AuthError("Authentication required")


def require_docs_permission(min_role: str = "viewer"):
    """Dependency factory: auth + role check for docs-open endpoints."""
    role_level = {"admin": 3, "editor": 2, "viewer": 1}

    async def _check(user: User = Depends(get_authenticated_user)) -> User:
        if role_level.get(user.role, 0) < role_level.get(min_role, 0):
            raise PermissionDenied(
                f"Requires at least '{min_role}' role, got '{user.role}'"
            )
        return user

    return _check


def _get_base_url(request: Request) -> str:
    """Build the base URL from the request."""
    forwarded = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("X-Forwarded-Host", request.url.hostname)
    port = request.url.port
    if port and port not in (80, 443):
        return f"{forwarded}://{host}:{port}"
    return f"{forwarded}://{host}"


# ── 1. Token endpoint ──

@router.post("/token")
async def issue_token(
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("viewer")),
):
    """Issue a document-scoped access token (仿腾讯文档三件套).

    Forced to current user: open_id cannot be specified by the client.
    scope.doc_ids are validated one by one via framework_check_file_access.
    """
    scope = body.scope or {}
    doc_ids = scope.get("doc_ids")
    if doc_ids is not None:
        if not isinstance(doc_ids, list):
            raise PermissionDenied("scope.doc_ids must be a list")
        for fid in doc_ids:
            await framework_check_file_access(db, int(fid), user.id)

    result = await create_token(
        db,
        client_id=body.client_id,
        open_id=user.id,
        scope=scope,
        expiry_hours=body.expiry_hours,
    )
    return ApiResponse(data=result)


# ── 2. Open document ──

@router.post("/open")
async def open_document(
    body: OpenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("viewer")),
):
    """Open a document. Returns id, title, type, embed_url, content_url.
    
    Simulates Tencent Docs /openapi/drive/v2/files endpoint shape.
    """
    file = await framework_check_file_access(db, body.file_id, user.id)
    ext = (file.extension or "").lower().lstrip(".")
    doc_info = _get_doc_type(ext)

    base = _get_base_url(request)

    issue_doc_token = await create_token(
        db,
        client_id="docs-open",
        open_id=user.id,
        scope={"doc_ids": [body.file_id]},
        expiry_hours=2,
    )

    embed_url = f"{base}/api/docs/embed/{body.file_id}"
    embed_url += f"?token={issue_doc_token['access_token']}"
    embed_url += f"&client_id=docs-open&open_id={user.id}"
    embed_url += f"&mode={body.mode}"

    content_url = f"{base}/api/docs/{body.file_id}/content"

    return ApiResponse(data={
        "id": str(file.id),
        "title": file.name,
        "type": ext,
        "category": doc_info.get("category", "unknown"),
        "embed_url": embed_url,
        "content_url": content_url,
        "editor": doc_info.get("editor"),
        "mime": doc_info.get("mime", "application/octet-stream"),
        "size": file.size,
        "createTime": file.created_at.isoformat() if file.created_at else None,
    })


# ── 3. Create document ──

@router.post("")
async def create_document(
    body: CreateDocRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("editor")),
):
    """Create a new empty document.
    
    Delegates to office-gen for office files, or creates a plain text file.
    """
    ext = body.doc_type.lower().lstrip(".")
    doc_info = _get_doc_type(ext)

    if ext in ("docx", "xlsx", "pptx", "pdf"):
        try:
            from app.services.module_registry import call_capability
            gen_params = {
                "filename": body.title,
                "content": [{"type": "paragraph", "text": ""}],
            }
            if ext == "xlsx":
                gen_params = {
                    "filename": body.title,
                    "sheets": [{"name": "Sheet1", "columns": ["A"], "rows": [[""]]}],
                }
            elif ext == "pptx":
                gen_params = {
                    "filename": body.title,
                    "slides": [{"title": body.title, "bullets": [""]}],
                }
            result = await call_capability(
                "office-gen", ext,
                gen_params,
                caller=f"user:{user.id}",
                caller_role=user.role,
            )
            file_id = result.get("file_id") or result.get("id")
        except Exception as e:
            return ApiResponse(success=False, error=f"Failed to create {ext}: {e}")
    else:
        from app.services import file_create_service
        result = await file_create_service.create_file(
            db, body.title, ext, user.id, body.folder_id,
        )
        file_id = result["id"]

    base = _get_base_url(request)
    issue_doc_token = await create_token(
        db, client_id="docs-open", open_id=user.id,
        scope={"doc_ids": [file_id]}, expiry_hours=2,
    )
    embed_url = f"{base}/api/docs/embed/{file_id}?token={issue_doc_token['access_token']}&client_id=docs-open&open_id={user.id}&mode=edit"

    return ApiResponse(data={
        "id": str(file_id),
        "title": body.title,
        "type": ext,
        "embed_url": embed_url,
        "content_url": f"{base}/api/docs/{file_id}/content",
    })


# ── 4. Get content (JSON middle layer) ──

@router.get("/{file_id}/content")
async def get_content(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("viewer")),
):
    """Get structured JSON content of a document.
    
    Routes to the appropriate parser/engine based on file type.
    Returns the same shape as the module's parser output.
    """
    file = await framework_check_file_access(db, file_id, user.id)
    ext = (file.extension or "").lower().lstrip(".")

    result = await _read_content(db, file, ext, user.role)
    return ApiResponse(data=result)


@router.post("/{file_id}/content")
async def write_content(
    file_id: int,
    body: ContentWriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("editor")),
):
    """Write structured JSON content back to a document.
    
    Routes to the appropriate engine based on file type.
    """
    file = await framework_check_file_access(db, file_id, user.id)
    ext = (file.extension or "").lower().lstrip(".")

    await _write_content(db, file, ext, body.content, user.role)
    return ApiResponse(data={"message": "Content saved"})


# ── 5. Export document ──

@router.post("/{file_id}/export")
async def export_document(
    file_id: int,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("viewer")),
):
    """Export a document to a different format.
    
    Uses office-gen's convert capability for office files.
    For text files, returns the raw content.
    """
    file = await framework_check_file_access(db, file_id, user.id)
    ext = (file.extension or "").lower().lstrip(".")
    target = body.target_format.lower().lstrip(".")

    if ext in ("docx", "xlsx", "pptx", "pdf") or target in ("pdf", "docx", "xlsx", "pptx"):
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "office-gen", "convert",
                {"file_id": file_id, "target_format": target},
                caller=f"user:{user.id}",
                caller_role=user.role,
            )
            return ApiResponse(data=result)
        except Exception as e:
            return ApiResponse(success=False, error=f"Export failed: {e}")

    return ApiResponse(data={
        "id": file_id,
        "format": ext,
        "message": "Raw content available via GET /content",
    })


# ── 6. Embed page (核心: rendered HTML) ──

@router.get("/embed/{file_id}", response_class=HTMLResponse)
async def embed_document(
    file_id: int,
    request: Request,
    token: str = Query(...),
    client_id: str = Query("docs-open"),
    open_id: str = Query(...),
    mode: str = Query("view"),
    db: AsyncSession = Depends(get_db),
):
    """Serve the embeddable document editor page (无桌面壳, full-page).
    
    Validates the token triple, then serves an HTML page that:
    - Routes to the correct editor based on document format
    - Can be iframed into any internal page/dashboard/Agent card
    """
    token_info = await validate_token(db, token, client_id, open_id)
    token_record = token_info
    if not check_doc_access(token_record, file_id):
        raise PermissionDenied("Token does not have access to this document")

    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")

    await framework_check_file_access(db, file_id, int(open_id))

    ext = (file.extension or "").lower().lstrip(".")
    doc_info = _get_doc_type(ext)
    base = _get_base_url(request)
    is_edit = mode == "edit"

    html = _generate_embed_html(
        file_id=file_id,
        file_name=file.name or "untitled",
        extension=ext,
        doc_info=doc_info,
        base_url=base,
        token=token,
        client_id=client_id,
        open_id=open_id,
        is_editable=is_edit and doc_info.get("category") in ("text", "spreadsheet"),
    )
    return HTMLResponse(content=html, status_code=200)


# ── 7. Raw file access (for embed viewers) ──

@router.get("/{file_id}/file")
async def get_file_raw(
    file_id: int,
    request: Request,
    token: str | None = Query(None),
    client_id: str | None = Query(None),
    open_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get raw file for embedding (pdf, images, etc.).

    Supports two auth modes:
    1. Query-parameter token triple (?token=&client_id=&open_id=) for iframe src
    2. JWT Bearer header (from desktop shell, via get_authenticated_user)
    """
    if token and client_id and open_id:
        await validate_token(db, token, client_id, open_id)
        await framework_check_file_access(db, file_id, int(open_id))
    else:
        user = await get_authenticated_user(request, db)
        await framework_check_file_access(db, file_id, user.id)

    file = await db.get(File, file_id)
    if not file or file.deleted:
        raise NotFound("File not found")

    settings = get_settings()
    storage_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (storage_root / file.storage_path).resolve()
    if not str(full_path).startswith(str(storage_root)) or not full_path.exists():
        raise NotFound("File not found on disk")
    ext = (file.extension or "").lower()
    mime = _get_doc_type(ext).get("mime", "application/octet-stream")
    return FileResponse(
        path=str(full_path),
        media_type=mime,
        filename=f"{file.name}.{file.extension}" if file.extension else file.name,
    )


@router.post("/{file_id}/revoke-tokens")
async def revoke_doc_tokens(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("editor")),
):
    """Revoke all tokens owned by the current user (security measure)."""
    await framework_check_file_access(db, file_id, user.id)
    from sqlalchemy import update as sql_update
    stmt = (
        sql_update(DocsOpenToken)
        .where(
            DocsOpenToken.open_id == user.id,
            DocsOpenToken.is_revoked == False,
        )
        .values(is_revoked=True)
    )
    await db.execute(stmt)
    await db.commit()
    return ApiResponse(data={"message": "All active tokens revoked"})


# ── Internal helpers ──

async def _read_content(db: AsyncSession, file: File, ext: str, user_role: str = "editor") -> dict:
    """Read document content as structured JSON based on type."""
    settings = get_settings()
    storage_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (storage_root / file.storage_path).resolve()

    if ext in ("txt", "md", "json", "yaml", "yml", "xml", "ini", "cfg", "log"):
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return {"content": text, "format": "text", "extension": ext}

    if ext in ("xlsx", "xls"):
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "excel-engine", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "excel-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse xlsx: {e}", "format": "error", "extension": ext}

    if ext == "csv":
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        import csv, io
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        return {"content": rows, "format": "csv-json", "extension": ext}

    if ext == "pdf":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pdf-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse pdf: {e}", "format": "error", "extension": ext}

    if ext == "docx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "docx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse docx: {e}", "format": "error", "extension": ext}

    if ext == "pptx":
        try:
            from app.services.module_registry import call_capability
            result = await call_capability(
                "pptx-parser", "parse",
                {"file_id": file.id},
                caller=f"user:{file.owner_id}",
                caller_role=user_role,
            )
            return {"content": result, "format": "parsed-json", "extension": ext}
        except Exception as e:
            return {"error": f"Failed to parse pptx: {e}", "format": "error", "extension": ext}

    return {"content": None, "format": "binary", "extension": ext}


async def _write_content(db: AsyncSession, file: File, ext: str, content: dict | list | str, user_role: str = "editor") -> None:
    """Write structured content back to a document.

    Uses framework replace_file_content (content-addressed) instead of
    direct disk overwrite to preserve content-addressable dedup integrity.
    """
    from app.services.file_upload_service import replace_file_content

    if ext in ("txt", "md", "json", "yaml", "yml", "xml", "ini", "cfg", "log"):
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, file.owner_id, text.encode("utf-8"))

    elif ext in ("xlsx", "xls"):
        try:
            from app.services.module_registry import call_capability
            json_str = __import__("json").dumps(content, ensure_ascii=False)
            await call_capability(
                "office-gen", "xlsx",
                {"filename": file.name, "content": json_str},
                caller=f"user:{file.owner_id}",
                caller_role="admin",
            )
        except Exception as e:
            raise AppException(f"Failed to write xlsx: {e}", status_code=500)

    elif ext in ("docx",):
        try:
            from app.services.module_registry import call_capability
            await call_capability(
                "office-gen", "docx",
                {"filename": file.name, "content": content},
                caller=f"user:{file.owner_id}",
                caller_role="admin",
            )
        except Exception as e:
            raise AppException(f"Failed to write docx: {e}", status_code=500)

    elif ext == "csv":
        text = content if isinstance(content, str) else str(content)
        await replace_file_content(db, file.id, file.owner_id, text.encode("utf-8"))

    else:
        raise AppException(f"Writing to {ext} is not supported yet", status_code=400)


# ── Embed HTML generator ──

def _generate_embed_html(
    file_id: int,
    file_name: str,
    extension: str,
    doc_info: dict,
    base_url: str,
    token: str,
    client_id: str,
    open_id: str,
    is_editable: bool,
) -> str:
    category = doc_info.get("category", "unknown")
    editor = doc_info.get("editor", "")

    api_base = base_url.rstrip("/")

    if category == "spreadsheet" and extension in ("xlsx", "xls"):
        return _spreadsheet_embed_html(file_id, file_name, api_base, token, client_id, open_id, is_editable)
    elif extension == "csv":
        return _csv_embed_html(file_id, file_name, api_base, token, client_id, open_id, is_editable)
    elif category == "text":
        return _text_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id, is_editable)
    elif extension == "pdf":
        return _pdf_embed_html(file_id, file_name, api_base, token, client_id, open_id)
    elif category == "document":
        return _doc_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    elif category == "presentation":
        return _presentation_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    elif category == "image":
        return _image_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)
    else:
        return _fallback_embed_html(file_id, file_name, extension, api_base, token, client_id, open_id)


def _spreadsheet_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - 文档</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed;flex-shrink:0}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
.table-wrap{{overflow:auto;border:1px solid #e4e7ed;border-radius:4px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #e4e7ed;padding:4px 8px;text-align:left;white-space:nowrap;min-width:60px}}
th{{background:#f5f7fa;font-weight:500;color:#606266;position:sticky;top:0;z-index:1}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399;font-size:14px}}
.error{{display:flex;align-items:center;justify-content:center;height:100%;color:#f56c6c;font-size:14px;padding:20px;text-align:center}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">{"可编辑" if editable else "只读"}</span></div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  try{{
    const r=await fetch('{base}/api/docs/{file_id}/content',{{
      headers:{{'X-Client-Id':'{cid}','X-Open-Id':'{oid}','X-Access-Token':'{token}'}}
    }})
    if(!r.ok)throw new Error('HTTP '+r.status)
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const data=body.data||{{}}
    let cells=data.content||data.cells||{{}}
    if(data.content?.sheet_set){{
      const ss=data.content.sheet_set
      const first=Object.keys(ss)[0]
      if(first)cells=ss[first].cells||{{}}
    }}
    if(data.sheet_set){{
      const ss=data.sheet_set
      const first=Object.keys(ss)[0]
      if(first)cells=ss[first].cells||{{}}
    }}
    const addrs=Object.keys(cells).sort((a,b)=>{{
      const ca=a.match(/^([A-Z]+)(\d+)$/),cb=b.match(/^([A-Z]+)(\d+)$/)
      if(!ca||!cb)return a.localeCompare(b)
      const colA=ca[1].length*26+ca[1].charCodeAt(0)-64,colB=cb[1].length*26+cb[1].charCodeAt(0)-64
      return parseInt(ca[2])-parseInt(cb[2])||colA-colB
    }})
    if(addrs.length===0){{app.innerHTML='<div class="loading">空表格</div>';return}}
    const rows={{}},cols=new Set
    for(const addr of addrs){{
      const m=addr.match(/^([A-Z]+)(\d+)$/)
      if(!m)continue
      const col=m[1],row=parseInt(m[2])
      if(!rows[row])rows[row]={{}};
      (rows[row])[col]=cells[addr]?.value??''
      cols.add(col)
    }}
    const sortedCols=[...cols].sort((a,b)=>a.length-b.length||a.localeCompare(b));
    const sortedRows=Object.keys(rows).sort((a,b)=>parseInt(a)-parseInt(b))
    let html='<div class="table-wrap"><table><thead><tr><th></th>'+sortedCols.map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'
    for(const r of sortedRows){{
      html+='<tr><th>'+r+'</th>'
      for(const c of sortedCols){{
        const val=(rows[r]?.[c]||'')
        html+='<td>'+(typeof val==='string'?val.replace(/</g,'&lt;').replace(/>/g,'&gt;'):String(val))+'</td>'
      }}
      html+='</tr>'
    }}
    html+='</tbody></table></div>'
    app.innerHTML=html
  }}catch(e){{
    app.innerHTML='<div class="error">加载失败: '+e.message+'</div>'
  }}
}})()
</script>
</body></html>"""


def _csv_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - CSV</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
textarea{{width:100%;height:100%;border:1px solid #e4e7ed;border-radius:4px;padding:12px;font-family:monospace;font-size:13px;resize:none;outline:none}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">{"可编辑" if editable else "只读"}</span></div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  try{{
    const r=await fetch('{base}/api/docs/{file_id}/content',{{
      headers:{{'X-Client-Id':'{cid}','X-Open-Id':'{oid}','X-Access-Token':'{token}'}}
    }})
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const text=body.data?.content||''
    if({str(editable).lower()} && 'content' in (body.data||{{}})){{
      app.innerHTML='<textarea id="editor">'+text.replace(/</g,'&lt;')+'</textarea><div style="margin-top:8px;text-align:right"><button onclick="saveCsv()" style="padding:6px 16px;background:#2395bc;color:#fff;border:none;border-radius:4px;cursor:pointer">保存</button></div>'
      window.saveCsv=async function(){{
        const val=document.getElementById('editor').value
        const r=await fetch('{base}/api/docs/{file_id}/content',{{
          method:'POST',headers:{{'Content-Type':'application/json','X-Client-Id':'{cid}','X-Open-Id':'{oid}','X-Access-Token':'{token}'}},
          body:JSON.stringify({{content:val}})
        }})
        const b=await r.json()
        alert(b.success?'✅ 保存成功':'❌ '+b.error)
      }}
    }}else{{
      app.innerHTML='<textarea readonly>'+text.replace(/</g,'&lt;')+'</textarea>'
    }}
  }}catch(e){{
    app.innerHTML='<div class="loading">加载失败: '+e.message+'</div>'
  }}
}})()
</script>
</body></html>"""


def _text_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str, editable: bool) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - 文本</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;font-family:苹方,"微软雅黑",宋体,sans-serif;background:#fff;color:#333}}
.toolbar{{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:#f8f9fa;border-bottom:1px solid #e4e7ed;flex-shrink:0}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.toolbar .save-btn{{padding:6px 16px;background:#2395bc;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px;display:none}}
.toolbar .save-btn:hover{{background:#31A1C6}}
.content{{padding:16px;overflow:auto;height:calc(100% - 45px)}}
textarea{{width:100%;height:100%;border:1px solid #e4e7ed;border-radius:4px;padding:12px;font-family:monospace;font-size:13px;line-height:1.6;resize:none;outline:none}}
textarea:focus{{border-color:#2395bc}}
.loading{{display:flex;align-items:center;justify-content:center;height:100%;color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2>
<span class="badge">{ext.upper()} {"可编辑" if editable else "只读"}</span>
<button class="save-btn" id="saveBtn" onclick="saveText()" style="display:none">保存</button>
</div>
<div class="content" id="app"><div class="loading">加载中…</div></div>
<script>
(async function(){{
  const app=document.getElementById('app')
  try{{
    const r=await fetch('{base}/api/docs/{file_id}/content',{{
      headers:{{'X-Client-Id':'{cid}','X-Open-Id':'{oid}','X-Access-Token':'{token}'}}
    }})
    const body=await r.json()
    if(!body.success)throw new Error(body.error||'加载失败')
    const text=body.data?.content||''
    const canEdit={'true' if editable else 'false'}
    if(canEdit==='true'){{
      app.innerHTML='<textarea id="editor">'+text.replace(/</g,'&lt;')+'</textarea>'
      document.getElementById('saveBtn').style.display='inline-block'
    }}else{{
      app.innerHTML='<textarea readonly>'+text.replace(/</g,'&lt;')+'</textarea>'
    }}
  }}catch(e){{
    app.innerHTML='<div class="loading">加载失败: '+e.message+'</div>'
  }}
}})()
window.saveText=async function(){{
  const val=document.getElementById('editor').value
  const r=await fetch('{base}/api/docs/{file_id}/content',{{
    method:'POST',headers:{{'Content-Type':'application/json','X-Client-Id':'{cid}','X-Open-Id':'{oid}','X-Access-Token':'{token}'}},
    body:JSON.stringify({{content:val}})
  }})
  const b=await r.json()
  if(b.success){{document.getElementById('saveBtn').textContent='✅ 已保存';setTimeout(()=>document.getElementById('saveBtn').textContent='保存',2000)}}else{{alert('❌ '+b.error)}}
}}
</script>
</body></html>"""


def _pdf_embed_html(file_id: int, name: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = f"{base}/api/docs/{file_id}/file?token={token}&client_id={cid}&open_id={oid}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - PDF</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">PDF</span></div>
<div class="content">
<iframe src="{file_url}" title="{__import__("html").escape(name)}"></iframe>
</div>
</body></html>"""


def _doc_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = f"{base}/api/docs/{file_id}/file?token={token}&client_id={cid}&open_id={oid}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - 文档</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">{ext.upper()}</span></div>
<div class="content">
<iframe src="{file_url}" title="{__import__("html").escape(name)}"></iframe>
</div>
</body></html>"""


def _presentation_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    file_url = f"{base}/api/docs/{file_id}/file?token={token}&client_id={cid}&open_id={oid}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - 演示</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px}}
iframe{{width:100%;height:100%;border:none;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.loading{{color:#909399;font-size:14px}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">{ext.upper()}</span></div>
<div class="content">
<iframe src="{file_url}" title="{__import__("html").escape(name)}"></iframe>
</div>
</body></html>"""


def _image_embed_html(file_id: int, name: str, ext: str, base: str, token: str, cid: str, oid: str) -> str:
    img_url = f"{base}/api/docs/{file_id}/file?token={token}&client_id={cid}&open_id={oid}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)} - 图片</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#f0f2f5;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.toolbar{{display:flex;align-items:center;padding:8px 16px;background:#fff;border-bottom:1px solid #e4e7ed}}
.toolbar h2{{font-size:15px;font-weight:600;color:#303133}}
.toolbar .badge{{margin-left:12px;font-size:11px;padding:2px 8px;border-radius:3px;background:#e6f7ff;color:#2395bc}}
.content{{height:calc(100% - 45px);display:flex;align-items:center;justify-content:center;padding:16px;overflow:auto}}
img{{max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
</style></head>
<body>
<div class="toolbar"><h2>{__import__("html").escape(name)}</h2><span class="badge">{ext.upper()}</span></div>
<div class="content">
<img src="{img_url}" alt="{__import__("html").escape(name)}" />
</div>
</body></html>"""


def _fallback_embed_html(file_id: int, name: str, ext: str, base: str = "", token: str = "", cid: str = "", oid: str = "") -> str:
    file_url = f"{base}/api/docs/{file_id}/file?token={token}&client_id={cid}&open_id={oid}" if base and token else f"/api/docs/{file_id}/file"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{__import__("html").escape(name)}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%;background:#fff;font-family:苹方,"微软雅黑",宋体,sans-serif}}
.content{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#909399;gap:12px}}
.icon{{font-size:48px}}
</style></head>
<body>
<div class="content">
<div class="icon">📄</div>
<h3>{__import__("html").escape(name)}</h3>
<p>格式 .{ext} 暂不支持在线预览</p>
<p style="font-size:13px"><a href="{file_url}" style="color:#2395bc">下载文件</a></p>
</div>
</body></html>"""


# ── Register capability ──

async def _open_capability(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    mode = params.get("mode", "view")
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.database import AsyncSessionLocal
    from app.models.file import File
    from app.services.file_service import check_file_access

    user_id = _resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower().lstrip(".")
        doc_info = _get_doc_type(ext)
        return {
            "id": str(file.id),
            "title": file.name,
            "type": ext,
            "category": doc_info.get("category"),
            "editor": doc_info.get("editor"),
            "mime": doc_info.get("mime"),
        }


async def _get_content_capability(params: dict, caller: str) -> dict:
    file_id = int(params.get("file_id", 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.database import AsyncSessionLocal
    from app.models.file import File
    from app.services.file_service import check_file_access

    user_id = _resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower().lstrip(".")
        return await _read_content(db, file, ext)


async def _create_doc_capability(params: dict, caller: str) -> dict:
    title = params.get("title", "untitled")
    doc_type = params.get("type", "txt")
    from app.database import AsyncSessionLocal
    user_id = _resolve_caller_user_id(caller)
    async with AsyncSessionLocal() as db:
        from app.services import file_create_service
        result = await file_create_service.create_file(db, title, doc_type, user_id, None)
        return {"id": str(result["id"]), "title": title, "type": doc_type}


def _resolve_caller_user_id(caller: str) -> int:
    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


register_capability(
    "docs-open", "open", _open_capability,
    description="Open a document by file_id, returns metadata and editor info",
    brief="打开文档",
    parameters={"file_id": {"type": "int"}, "mode": {"type": "string"}},
    min_role="viewer",
)

register_capability(
    "docs-open", "get_content", _get_content_capability,
    description="Get structured JSON content of a document by file_id",
    brief="获取文档内容",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)

register_capability(
    "docs-open", "create_doc", _create_doc_capability,
    description="Create a new empty document",
    brief="创建文档",
    parameters={"title": {"type": "string"}, "type": {"type": "string"}},
    min_role="editor",
)



