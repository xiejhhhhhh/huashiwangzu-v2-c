"""File lock and feedback endpoints.

Extracted from router.py to follow size guidelines.
"""
import logging

from app.database import get_db
from app.middleware.auth import require_permission
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..graph.graph import normalize_path
from ..init_db import ensure_codemap_tables
from ..models import CodemapFeedback
from ..validation import validate_feedback_fields
from . import file_lock

logger = logging.getLogger("v2.codemap").getChild("lock_router")

router = APIRouter(tags=["codemap"])


def _operation_response(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(success=False, data=result, error=str(result.get("error") or "operation failed"))
    return ApiResponse(data=result)


# ── File lock endpoints ──────────────────────────────────────────────────────

class AcquireLockRequest(BaseModel):
    path: str
    agent_id: str
    ttl: int = 600


class LockPathRequest(BaseModel):
    path: str


class ReportInaccuracyRequest(BaseModel):
    path: str
    query_type: str
    codemap_said: str = ""
    actual: str = ""
    reason: str = ""
    agent_id: str = ""


@router.post("/acquire-lock")
async def http_acquire_lock(
    body: AcquireLockRequest,
    _user=Depends(require_permission("viewer")),
):
    return _operation_response(file_lock.acquire_lock(body.path, body.agent_id, body.ttl))


@router.post("/check-lock")
async def http_check_lock(
    body: LockPathRequest,
    _user=Depends(require_permission("viewer")),
):
    return _operation_response(file_lock.check_lock(body.path))


@router.post("/release-lock")
async def http_release_lock(
    body: LockPathRequest,
    _user=Depends(require_permission("viewer")),
):
    return _operation_response(file_lock.release_lock(body.path))


@router.get("/list-locks")
async def http_list_locks(_user=Depends(require_permission("viewer"))):
    return _operation_response(file_lock.list_locks())


# ═══════════════════════════════════════════════════════════════════════════════
# Feedback & Maintenance Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/report-inaccuracy")
async def http_report_inaccuracy(
    body: ReportInaccuracyRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("viewer")),
):
    """Agent 实读验证后发现 codemap 不准时，调用此接口记录一条反馈。"""
    try:
        path, query_type = validate_feedback_fields(body.path, body.query_type)
    except ValueError as exc:
        return ApiResponse(success=False, error=str(exc), data={"path": body.path, "query_type": body.query_type})
    await ensure_codemap_tables(db)
    feedback = CodemapFeedback(
        path=path,
        query_type=query_type,
        codemap_said=body.codemap_said,
        actual=body.actual,
        reason=body.reason,
        agent_id=body.agent_id or "anonymous",
    )
    db.add(feedback)
    await db.flush()
    feedback_id = feedback.id
    await db.commit()
    logger.info("Feedback recorded: path=%s type=%s reason=%s", body.path, body.query_type, body.reason[:80])
    return ApiResponse(data={"id": feedback_id, "message": "反馈已记录"})


@router.get("/list-feedback")
async def http_list_feedback(
    path: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("admin")),
):
    """列出 codemap 反馈记录。仅 admin。可按 path 过滤、按频次排序。"""
    await ensure_codemap_tables(db)
    if path:
        path = normalize_path(path)
        # Filter by path, ordered by recency
        result = await db.execute(
            select(CodemapFeedback)
            .where(CodemapFeedback.path == path)
            .order_by(CodemapFeedback.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = result.scalars().all()
    else:
        # Aggregate by path, sorted by complaint count desc
        result = await db.execute(
            select(
                CodemapFeedback.path,
                func.count(CodemapFeedback.id).label("count"),
            )
            .group_by(CodemapFeedback.path)
            .order_by(desc("count"))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = result.all()
        aggregated = [{"path": r[0], "complaint_count": r[1]} for r in rows]
        # For each path, get the latest reason
        for entry in aggregated:
            r = await db.execute(
                select(CodemapFeedback.reason)
                .where(CodemapFeedback.path == entry["path"])
                .order_by(CodemapFeedback.created_at.desc())
                .limit(1)
            )
            row = r.scalar_one_or_none()
            if row:
                entry["latest_reason"] = row
        return ApiResponse(data={
            "items": aggregated,
            "aggregated_by_path": True,
            "page": page,
            "page_size": page_size,
        })

    return ApiResponse(data={
        "items": [
            {
                "id": f.id,
                "path": f.path,
                "query_type": f.query_type,
                "codemap_said": f.codemap_said[:200],
                "actual": f.actual[:200],
                "reason": f.reason,
                "agent_id": f.agent_id,
                "created_at": str(f.created_at),
            }
            for f in items
        ],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    })
