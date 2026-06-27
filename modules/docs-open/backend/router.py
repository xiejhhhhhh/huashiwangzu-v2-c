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
from app.core.exceptions import NotFound, AppException, PermissionDenied
from app.services.file_service import check_file_access as framework_check_file_access
from app.config import get_settings

from .models import DocsOpenToken
from .token_service import create_token, validate_token, check_doc_access
from .handlers.auth import get_authenticated_user, require_docs_permission, _get_base_url
from .handlers.embed import _generate_embed_html, _get_doc_type
from .handlers.content import _read_content, _write_content

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
            raise AppException(f"Failed to create {ext}: {e}")
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
    token_info = await validate_token(db, token, client_id, open_id)
    token_record = token_info
    if not check_doc_access(token_record, file_id):
        raise PermissionDenied("Token does not have access to this document")

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


# ── Import capabilities to register them at module load ──

# noinspection PyUnresolvedReferences
from .handlers import capabilities  # noqa: F401, E402
