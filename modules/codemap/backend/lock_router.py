"""File lock and feedback endpoints.

Extracted from router.py to follow size guidelines.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability

from . import file_lock
from .models import CodemapFeedback

import logging
logger = logging.getLogger("v2.codemap").getChild("lock_router")

router = APIRouter(prefix="/api/codemap", tags=["codemap"])


# ── File lock endpoints ──────────────────────────────────────────────────────

class AcquireLockRequest(BaseModel):
    path: str
    agent_id: str
    ttl: int = 600


class LockPathRequest(BaseModel):
    path: str


@router.post("/acquire-lock")
async def http_acquire_lock(
    body: AcquireLockRequest,
    _user=Depends(require_permission("viewer")),
):
    return ApiResponse(data=file_lock.acquire_lock(body.path, body.agent_id, body.ttl))


@router.post("/check-lock")
async def http_check_lock(
    body: LockPathRequest,
    _user=Depends(require_permission("viewer")),
):
    return ApiResponse(data=file_lock.check_lock(body.path))


@router.post("/release-lock")
async def http_release_lock(
    body: LockPathRequest,
    _user=Depends(require_permission("viewer")),
):
    return ApiResponse(data=file_lock.release_lock(body.path))


@router.get("/list-locks")
async def http_list_locks(_user=Depends(require_permission("viewer"))):
    return ApiResponse(data=file_lock.list_locks())


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
    feedback = CodemapFeedback(
        path=body.path,
        query_type=body.query_type,
        codemap_said=body.codemap_said,
        actual=body.actual,
        reason=body.reason,
        agent_id=body.agent_id or "anonymous",
    )
    db.add(feedback)
    await db.commit()
    logger.info("Feedback recorded: path=%s type=%s reason=%s", body.path, body.query_type, body.reason[:80])
    return ApiResponse(data={"id": feedback.id, "message": "反馈已记录"})


@router.get("/list-feedback")
async def http_list_feedback(
    path: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("admin")),
):
    """列出 codemap 反馈记录。仅 admin。可按 path 过滤、按频次排序。"""
    if path:
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


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-module capabilities (registered with framework registry)
# ═══════════════════════════════════════════════════════════════════════════════

async def _cap_get_file(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.ready:
        return {"success": False, "error": "索引构建中"}
    path = params.get("path", "")
    result = graph.get_file(path)
    if result is None:
        return {"success": False, "error": f"File not found: {path}"}
    # Add reliability note + persistent query count increment
    try:
        async with AsyncSessionLocal() as db:
            feedback_count, latest_reason = await _load_path_feedback(db, path)
            note = graph.build_reliability_note(path, feedback_count, latest_reason)
            if note:
                result["reliability_note"] = note
            await _increment_query_count(db)
    except Exception:
        pass
    return {"success": True, "data": result}


async def _cap_impact(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.ready:
        return {"success": False, "error": "索引构建中"}
    path = params.get("path", "")
    symbol = params.get("symbol")
    result = graph.impact(path, symbol)
    # Add reliability note + persistent query count increment
    try:
        async with AsyncSessionLocal() as db:
            feedback_count, latest_reason = await _load_path_feedback(db, path)
            note = graph.build_reliability_note(path, feedback_count, latest_reason)
            if note:
                result["reliability_note"] = note
            await _increment_query_count(db)
    except Exception:
        pass
    return {"success": True, "data": result}


async def _cap_check_boundary(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.ready:
        return {"success": False, "error": "索引构建中"}
    path = params.get("path")
    module_key = params.get("module_key")
    return {"success": True, "data": graph.check_boundary(path=path, module_key=module_key)}


async def _cap_module_map(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.ready:
        return {"success": False, "error": "索引构建中"}
    module_key = params.get("module_key", "")
    return {"success": True, "data": graph.module_map(module_key)}


async def _cap_search(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.ready:
        return {"success": False, "error": "索引构建中"}
    keyword = params.get("keyword", "")
    return {"success": True, "data": graph.search(keyword)}


async def _cap_stats(params: dict, caller: str) -> dict:
    graph = get_graph()
    stats = graph.stats()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count(CodemapFeedback.id)))
            feedback_count = result.scalar() or 0
            qc = await _get_query_count(db)
            stats["query_count"] = qc
            stats["feedback_count"] = feedback_count
            stats["empirical_accuracy"] = max(0, 100 - int(feedback_count * 100 / max(qc, 1))) if qc > 0 else 100
            if feedback_count > 0:
                result = await db.execute(
                    select(CodemapFeedback)
                    .order_by(CodemapFeedback.created_at.desc())
                    .limit(5)
                )
                stats["recent_complaints"] = [
                    {"path": r.path, "query_type": r.query_type, "reason": r.reason[:100], "created_at": str(r.created_at)}
                    for r in result.scalars().all()
                ]
    except Exception:
        pass
    return {"success": True, "data": stats}


async def _cap_rebuild(params: dict, caller: str) -> dict:
    graph = get_graph()
    graph.reindex_now()
    return {"success": True, "data": graph.stats()}


async def _cap_acquire_lock(params: dict, caller: str) -> dict:
    path = params.get("path", "")
    agent_id = params.get("agent_id", caller)
    ttl = params.get("ttl", 600)
    return file_lock.acquire_lock(path, agent_id, ttl)


async def _cap_check_lock(params: dict, caller: str) -> dict:
    return file_lock.check_lock(params.get("path", ""))


async def _cap_release_lock(params: dict, caller: str) -> dict:
    return file_lock.release_lock(params.get("path", ""))


async def _cap_list_locks(params: dict, caller: str) -> dict:
    return file_lock.list_locks()


# ── Feedback capability handlers ─────────────────────────────────────────────

async def _cap_report_inaccuracy(params: dict, caller: str) -> dict:
    """Report codemap inaccuracy feedback."""
    path = params.get("path", "")
    query_type = params.get("query_type", "")
    codemap_said = params.get("codemap_said", "")
    actual = params.get("actual", "")
    reason = params.get("reason", "")
    agent_id = params.get("agent_id", caller)
    try:
        async with AsyncSessionLocal() as db:
            feedback = CodemapFeedback(
                path=path, query_type=query_type, codemap_said=codemap_said,
                actual=actual, reason=reason, agent_id=agent_id,
            )
            db.add(feedback)
            await db.commit()
            return {"success": True, "data": {"id": feedback.id, "message": "反馈已记录"}}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _cap_list_feedback(params: dict, caller: str) -> dict:
    """List feedback (admin only, enforced by capability min_role)."""
    path = params.get("path")
    page = params.get("page", 1)
    page_size = params.get("page_size", 50)
    try:
        async with AsyncSessionLocal() as db:
            if path:
                result = await db.execute(
                    select(CodemapFeedback)
                    .where(CodemapFeedback.path == path)
                    .order_by(CodemapFeedback.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                items = [
                    {"id": f.id, "path": f.path, "query_type": f.query_type,
                     "reason": f.reason, "agent_id": f.agent_id, "created_at": str(f.created_at)}
                    for f in result.scalars().all()
                ]
                return {"success": True, "data": {"items": items}}
            else:
                result = await db.execute(
                    select(CodemapFeedback.path, func.count(CodemapFeedback.id).label("count"))
                    .group_by(CodemapFeedback.path)
                    .order_by(desc("count"))
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                rows = result.all()
                aggregated = [{"path": r[0], "complaint_count": r[1]} for r in rows]
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
                return {"success": True, "data": {"items": aggregated, "aggregated_by_path": True}}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# Register all capabilities