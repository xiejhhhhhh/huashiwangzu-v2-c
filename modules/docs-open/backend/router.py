"""文档开放接口 facade module.

Implements a Tencent Docs-style OpenAPI with self-hosted token triple
(Client-Id, Open-Id, Access-Token) + REST endpoints + embeddable editor.

This module delegates to existing editors via framework public APIs
and registered capabilities. It does NOT rewrite any editor.
"""
from pathlib import Path
from urllib.parse import urlencode

from app.config import get_settings
from app.core.exceptions import AppException, NotFound, PermissionDenied
from app.database import get_db
from app.models.file import File
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_service import (
    check_file_access as framework_check_file_access,
)
from app.services.file_service import (
    check_file_write_access as framework_check_file_write_access,
)
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .handlers.auth import _get_base_url, get_bearer_authenticated_user, require_docs_permission
from .handlers.content import _read_content, _write_content
from .handlers.embed import _generate_embed_html, _get_doc_type
from .models import DocsOpenToken
from .token_service import check_doc_access, create_token, validate_token
from .validators import (
    access_mode_for_mode,
    normalize_client_id,
    normalize_doc_type,
    normalize_expiry_hours,
    normalize_mode,
    normalize_positive_int,
    normalize_title,
    normalize_token_scope,
)

router = APIRouter(prefix="/api/docs", tags=["docs-open"])


# ── Schemas ──

class TokenRequest(BaseModel):
    client_id: str = Field("default", min_length=1, max_length=64)
    open_id: int | None = None
    scope: dict | None = None
    expiry_hours: int = Field(2, ge=1, le=24)


class OpenRequest(BaseModel):
    file_id: int
    mode: str = "view"


class CreateDocRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    doc_type: str = Field("txt", max_length=16)
    folder_id: int | None = None


class ContentWriteRequest(BaseModel):
    content: dict | list | str


class ExportRequest(BaseModel):
    target_format: str = "pdf"


async def _require_file_access_for_request(
    request: Request,
    db: AsyncSession,
    file_id: int,
    user: User,
    mode: str = "read",
) -> File:
    x_client_id = request.headers.get("X-Client-Id")
    x_open_id = request.headers.get("X-Open-Id")
    x_access_token = request.headers.get("X-Access-Token")
    if x_client_id and x_open_id and x_access_token:
        token_record = await validate_token(db, x_access_token, x_client_id, x_open_id)
        if normalize_positive_int(x_open_id, "open_id") != user.id:
            raise PermissionDenied("Open-Id mismatch")
        if not check_doc_access(token_record, file_id, mode):
            raise PermissionDenied("Token does not have access to this document")

    if mode == "edit":
        return await framework_check_file_write_access(db, file_id, user.id)
    return await framework_check_file_access(db, file_id, user.id)


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
    if body.open_id is not None and body.open_id != user.id:
        raise PermissionDenied("open_id must match the authenticated user")

    client_id = normalize_client_id(body.client_id)
    scope = normalize_token_scope(body.scope)
    expiry_hours = normalize_expiry_hours(body.expiry_hours)

    for fid in scope.get("doc_ids", []):
        await framework_check_file_access(db, fid, user.id)
    for fid in scope.get("edit_doc_ids", []):
        await framework_check_file_write_access(db, fid, user.id)

    result = await create_token(
        db,
        client_id=client_id,
        open_id=user.id,
        scope=scope,
        expiry_hours=expiry_hours,
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
    mode = normalize_mode(body.mode)
    if mode == "edit":
        file = await framework_check_file_write_access(db, body.file_id, user.id)
        token_scope = {"doc_ids": [body.file_id], "edit_doc_ids": [body.file_id]}
    else:
        file = await framework_check_file_access(db, body.file_id, user.id)
        token_scope = {"doc_ids": [body.file_id]}
    ext = (file.extension or "").lower().lstrip(".")
    doc_info = _get_doc_type(ext)

    base = _get_base_url(request)

    issue_doc_token = await create_token(
        db,
        client_id="docs-open",
        open_id=user.id,
        scope=token_scope,
        expiry_hours=2,
    )

    embed_query = urlencode({
        "token": issue_doc_token["access_token"],
        "client_id": "docs-open",
        "open_id": str(user.id),
        "mode": mode,
    })
    embed_url = f"{base}/api/docs/embed/{body.file_id}?{embed_query}"

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
    title = normalize_title(body.title)
    ext = normalize_doc_type(body.doc_type)

    if ext in ("docx", "xlsx", "pptx", "pdf"):
        try:
            from app.services.module_registry import call_capability
            gen_params = {
                "filename": title,
                "content": [{"type": "paragraph", "text": ""}],
            }
            if ext == "xlsx":
                gen_params = {
                    "filename": title,
                    "sheets": [{"name": "Sheet1", "columns": ["A"], "rows": [[""]]}],
                }
            elif ext == "pptx":
                gen_params = {
                    "filename": title,
                    "slides": [{"title": title, "bullets": [""]}],
                }
            result = await call_capability(
                "office-gen", ext,
                gen_params,
                caller=f"user:{user.id}",
                caller_role=user.role,
            )
            file_id = result.get("file_id") or result.get("id")
        except Exception as e:
            raise AppException(f"Failed to create {ext}: {e}")
    else:
        from app.services import file_create_service
        result = await file_create_service.create_file(
            db, title, ext, user.id, body.folder_id,
        )
        file_id = result["id"]

    base = _get_base_url(request)
    issue_doc_token = await create_token(
        db, client_id="docs-open", open_id=user.id,
        scope={"doc_ids": [file_id], "edit_doc_ids": [file_id]}, expiry_hours=2,
    )
    embed_query = urlencode({
        "token": issue_doc_token["access_token"],
        "client_id": "docs-open",
        "open_id": str(user.id),
        "mode": "edit",
    })
    embed_url = f"{base}/api/docs/embed/{file_id}?{embed_query}"

    return ApiResponse(data={
        "id": str(file_id),
        "title": title,
        "type": ext,
        "embed_url": embed_url,
        "content_url": f"{base}/api/docs/{file_id}/content",
    })


# ── 4. Get content (JSON middle layer) ──

@router.get("/{file_id}/content")
async def get_content(
    file_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("viewer", allow_scoped_token=True)),
):
    """Get structured JSON content of a document.

    Routes to the appropriate parser/engine based on file type.
    Returns the same shape as the module's parser output.
    """
    file = await _require_file_access_for_request(request, db, file_id, user, "read")
    ext = (file.extension or "").lower().lstrip(".")

    result = await _read_content(db, file, ext, user.id, user.role)
    return ApiResponse(data=result)


@router.post("/{file_id}/content")
async def write_content(
    file_id: int,
    body: ContentWriteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("editor", allow_scoped_token=True)),
):
    """Write structured JSON content back to a document.

    Routes to the appropriate engine based on file type.
    """
    file = await _require_file_access_for_request(request, db, file_id, user, "edit")
    ext = (file.extension or "").lower().lstrip(".")

    await _write_content(db, file, ext, body.content, user.id, user.role)
    return ApiResponse(data={"message": "Content saved"})


# ── 5. Export document ──

@router.post("/{file_id}/export")
async def export_document(
    file_id: int,
    body: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_docs_permission("editor")),
):
    """Export a document to a different format.

    Uses office-gen's convert capability for office files.
    For text files, returns the raw content.
    """
    file = await framework_check_file_write_access(db, file_id, user.id)
    ext = (file.extension or "").lower().lstrip(".")
    target = normalize_doc_type(body.target_format)

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
            raise AppException(f"Export failed: {e}")

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
    mode = normalize_mode(mode)
    token_record = await validate_token(db, token, client_id, open_id)
    access_mode = access_mode_for_mode(mode)
    if not check_doc_access(token_record, file_id, access_mode):
        raise PermissionDenied("Token does not have access to this document")

    if access_mode == "edit":
        file = await framework_check_file_write_access(db, file_id, int(open_id))
    else:
        file = await framework_check_file_access(db, file_id, int(open_id))

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
    has_token_part = bool(token or client_id or open_id)
    if has_token_part:
        if not (token and client_id and open_id):
            raise PermissionDenied("Incomplete token triple")
        token_record = await validate_token(db, token, client_id, open_id)
        if not check_doc_access(token_record, file_id, "read"):
            raise PermissionDenied("Token does not have access to this document")
        file = await framework_check_file_access(db, file_id, normalize_positive_int(open_id, "open_id"))
    else:
        user = await get_bearer_authenticated_user(request, db)
        file = await framework_check_file_access(db, file_id, user.id)

    settings = get_settings()
    storage_root = Path(settings.UPLOAD_DIR).resolve()
    full_path = (storage_root / file.storage_path).resolve()
    import os
    if os.path.commonpath([str(storage_root), str(full_path)]) != str(storage_root) or not full_path.exists():
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
    """Revoke active tokens owned by the current user for this file."""
    await framework_check_file_write_access(db, file_id, user.id)
    from sqlalchemy import select

    result = await db.execute(
        select(DocsOpenToken).where(
            DocsOpenToken.open_id == user.id,
            DocsOpenToken.is_revoked.is_(False),
        )
    )
    revoked_count = 0
    for token_record in result.scalars().all():
        if check_doc_access(token_record, file_id, "read"):
            token_record.is_revoked = True
            revoked_count += 1
    await db.commit()
    return ApiResponse(data={"message": "Tokens revoked", "revoked": revoked_count})


# ── Import capabilities to register them at module load ──

# noinspection PyUnresolvedReferences
from .handlers import capabilities  # noqa: F401, E402
