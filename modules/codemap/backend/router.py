"""FastAPI router for codemap module.

Provides HTTP endpoints and cross-module capabilities:
  codemap:get_file
  codemap:impact
  codemap:check_boundary
  codemap:module_map
  codemap:search
  codemap:stats
  codemap:rebuild
  codemap:acquire_lock
  codemap:check_lock
  codemap:release_lock
  codemap:list_locks

Index is built asynchronously on module import (not blocking startup).
Query returns "indexing" status while build is in progress.
"""

from __future__ import annotations

import logging
import threading

from app.core.exceptions import NotFound
from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .feedback_summary import build_empirical_accuracy_fields, build_feedback_list_metadata
from .graph.graph import get_graph, normalize_path
from .indexer import get_indexer
from .init_db import ensure_codemap_tables
from .locks import file_lock
from .models import CodemapFeedback
from .validation import validate_feedback_fields
from .watcher import get_watcher

logger = logging.getLogger("v2.codemap").getChild("router")

router = APIRouter(prefix="/api/codemap", tags=["codemap"])

# ── Start background build on module import ──────────────────────────────────

_initialized = False
_init_lock = threading.Lock()

def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        logger.info("Starting codemap background index build...")
        indexer = get_indexer()
        indexer.build_async()

        try:
            watcher = get_watcher()
            watcher.start()
        except Exception as exc:
            logger.warning("File watcher failed to start: %s", exc)

        # Ensure database table exists (best-effort, non-blocking)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_async_ensure_tables())
        except Exception as exc:
            logger.warning("Failed to ensure codemap tables: %s", exc)

        # Wire up reindex callback for /rebuild endpoint
        get_graph().set_reindex_callback(get_indexer().build_full)

        _initialized = True

async def _async_ensure_tables() -> None:
    """Create the codemap_feedback table if it doesn't exist."""
    try:
        async with AsyncSessionLocal() as db:
            await ensure_codemap_tables(db)
    except Exception as exc:
        logger.warning("async table ensure failed: %s", exc)

_ensure_initialized()

# ── Request models ───────────────────────────────────────────────────────────

class GetFileRequest(BaseModel):
    path: str

class ImpactRequest(BaseModel):
    path: str
    symbol: str | None = None

class CheckBoundaryRequest(BaseModel):
    path: str | None = None
    module_key: str | None = None

class ModuleMapRequest(BaseModel):
    module_key: str

class SearchRequest(BaseModel):
    keyword: str

class ReportInaccuracyRequest(BaseModel):
    path: str
    query_type: str  # "impact" | "get_file"
    codemap_said: str = ""
    actual: str = ""
    reason: str = ""
    agent_id: str = ""

class ListFeedbackRequest(BaseModel):
    path: str | None = None
    page: int = 1
    page_size: int = 50

# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_ready() -> dict | None:
    graph = get_graph()
    if graph.ready:
        return None
    stats = graph.stats()
    build_error = stats.get("build_error")
    if build_error:
        error = f"索引不可用: {build_error}"
    else:
        error = "索引构建中，请稍后重试"
    return {
        "success": False,
        "error": error,
        "data": {
            "status": stats.get("index_status", "building"),
            "build_error": build_error,
        },
    }


def _cap_ready_error() -> dict | None:
    not_ready = _check_ready()
    if not_ready:
        return {
            "success": False,
            "error": str(not_ready["error"]),
            "data": not_ready.get("data"),
        }
    return None

async def _load_path_feedback(db: AsyncSession, path: str) -> tuple[int, str]:
    """Load feedback count and latest reason for a given path."""
    result = await db.execute(
        select(func.count(CodemapFeedback.id)).where(CodemapFeedback.path == path)
    )
    count = result.scalar() or 0
    latest_reason = ""
    if count > 0:
        result = await db.execute(
            select(CodemapFeedback.reason)
            .where(CodemapFeedback.path == path)
            .order_by(CodemapFeedback.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            latest_reason = row
    return count, latest_reason

async def _add_reliability_note(result: dict | None, path: str, db: AsyncSession) -> dict | None:
    """Add reliability_note to a get_file/impact result if the file has issues."""
    if result is None or isinstance(result, dict) and result.get("error"):
        return result
    graph = get_graph()
    feedback_count, latest_reason = await _load_path_feedback(db, path)
    note = graph.build_reliability_note(path, feedback_count, latest_reason)
    if note:
        result["reliability_note"] = note
    return result


def _graph_error(result: dict | None) -> str | None:
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    return None


def _graph_api_response(result: dict | None) -> ApiResponse:
    error = _graph_error(result)
    if error:
        return ApiResponse(success=False, data=result, error=error)
    return ApiResponse(data=result)

# ── Query count helpers (DB-persisted, cross-worker consistent) ───────────────

_tables_ensured = False
_tables_ensured_lock = threading.Lock()

async def _ensure_tables_once(db: AsyncSession) -> None:
    """Idempotent: ensure codemap_metrics table exists on first call.
    Handles the case where _async_ensure_tables() couldn't run at import time
    (no running event loop in the import thread)."""
    global _tables_ensured
    if _tables_ensured:
        return
    with _tables_ensured_lock:
        if _tables_ensured:
            return
        await ensure_codemap_tables(db)
        _tables_ensured = True

async def _increment_query_count(db: AsyncSession) -> None:
    """Atomically increment the global query counter in DB."""
    await _ensure_tables_once(db)
    await db.execute(
        text("UPDATE codemap_metrics SET query_count = query_count + 1 WHERE id = 1")
    )
    await db.commit()

async def _get_query_count(db: AsyncSession) -> int:
    """Read the persisted query counter from DB."""
    await _ensure_tables_once(db)
    result = await db.execute(
        text("SELECT query_count FROM codemap_metrics WHERE id = 1")
    )
    row = result.scalar_one_or_none()
    return row if row is not None else 0


async def _enrich_stats_with_db(stats: dict, db: AsyncSession) -> dict:
    """Attach persisted metrics and feedback summary to graph stats."""
    qc = await _get_query_count(db)
    stats["query_count"] = qc
    result = await db.execute(select(func.count(CodemapFeedback.id)))
    feedback_count = result.scalar() or 0
    stats["feedback_count"] = feedback_count
    stats.update(build_empirical_accuracy_fields(qc, feedback_count))
    if feedback_count > 0:
        result = await db.execute(
            select(CodemapFeedback)
            .order_by(CodemapFeedback.created_at.desc())
            .limit(5)
        )
        stats["recent_complaints"] = [
            {
                "path": r.path,
                "query_type": r.query_type,
                "reason": r.reason[:100],
                "created_at": str(r.created_at),
            }
            for r in result.scalars().all()
        ]
    return stats

# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/health")
async def health(_user=Depends(require_permission("viewer"))):
    graph = get_graph()
    stats = graph.stats()
    return ApiResponse(data={
        "module": "codemap",
        "status": "ok" if stats.get("index_status") != "unavailable" else "degraded",
        "index_ready": graph.ready,
        "index_status": stats.get("index_status"),
        "build_error": stats.get("build_error"),
        "file_count": len(graph._files),
    })

@router.get("/stats")
async def http_stats(db: AsyncSession = Depends(get_db), _user=Depends(require_permission("viewer"))):
    graph = get_graph()
    stats = graph.stats()
    return ApiResponse(data=await _enrich_stats_with_db(stats, db))

@router.post("/get-file")
async def http_get_file(
    body: GetFileRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("viewer")),
):
    not_ready = _check_ready()
    if not_ready:
        return ApiResponse(**not_ready)
    graph = get_graph()
    await _increment_query_count(db)
    path = normalize_path(body.path)
    result = graph.get_file(path)
    if result is None:
        raise NotFound(f"File not found: {path}")
    result = await _add_reliability_note(result, path, db)
    return ApiResponse(data=result)

@router.post("/impact")
async def http_impact(
    body: ImpactRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("viewer")),
):
    not_ready = _check_ready()
    if not_ready:
        return ApiResponse(**not_ready)
    graph = get_graph()
    await _increment_query_count(db)
    path = normalize_path(body.path)
    result = graph.impact(path, body.symbol)
    if _graph_error(result):
        return _graph_api_response(result)
    result = await _add_reliability_note(result, path, db)
    return _graph_api_response(result)

@router.post("/check-boundary")
async def http_check_boundary(
    body: CheckBoundaryRequest,
    _user=Depends(require_permission("viewer")),
):
    not_ready = _check_ready()
    if not_ready:
        return ApiResponse(**not_ready)
    graph = get_graph()
    result = graph.check_boundary(path=body.path, module_key=body.module_key)
    return _graph_api_response(result)

@router.post("/module-map")
async def http_module_map(
    body: ModuleMapRequest,
    _user=Depends(require_permission("viewer")),
):
    not_ready = _check_ready()
    if not_ready:
        return ApiResponse(**not_ready)
    graph = get_graph()
    result = graph.module_map(body.module_key)
    return _graph_api_response(result)

@router.post("/search")
async def http_search(
    body: SearchRequest,
    _user=Depends(require_permission("viewer")),
):
    not_ready = _check_ready()
    if not_ready:
        return ApiResponse(**not_ready)
    graph = get_graph()
    if not body.keyword.strip():
        return ApiResponse(success=False, error="keyword is required", data={"keyword": body.keyword})
    result = graph.search(body.keyword)
    return ApiResponse(data=result)

# ── Rebuild endpoint ─────────────────────────────────────────────────────────

@router.post("/rebuild")
async def http_rebuild(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission("admin")),
):
    graph = get_graph()
    if not graph.reindex_now():
        return ApiResponse(success=False, error="rebuild callback is not registered", data=graph.stats())
    stats = graph.stats()
    stats["rebuild_triggered"] = True
    stats["rebuild_scope"] = "current_worker"
    return ApiResponse(data=await _enrich_stats_with_db(stats, db))


# ── Cross-module capability handlers ───────────────────────────────────────

async def _cap_get_file(params: dict, caller: str) -> dict:
    not_ready = _cap_ready_error()
    if not_ready:
        return not_ready
    graph = get_graph()
    path = normalize_path(params.get("path", ""))
    result = graph.get_file(path)
    if result is None:
        return {"success": False, "error": f"File not found: {path}"}
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
    not_ready = _cap_ready_error()
    if not_ready:
        return not_ready
    graph = get_graph()
    path = normalize_path(params.get("path", ""))
    symbol = params.get("symbol")
    result = graph.impact(path, symbol)
    error = _graph_error(result)
    if error:
        return {"success": False, "error": error, "data": result}
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
    not_ready = _cap_ready_error()
    if not_ready:
        return not_ready
    graph = get_graph()
    result = graph.check_boundary(path=params.get("path"), module_key=params.get("module_key"))
    error = _graph_error(result)
    if error:
        return {"success": False, "error": error, "data": result}
    return {"success": True, "data": result}


async def _cap_module_map(params: dict, caller: str) -> dict:
    not_ready = _cap_ready_error()
    if not_ready:
        return not_ready
    graph = get_graph()
    result = graph.module_map(params.get("module_key", ""))
    error = _graph_error(result)
    if error:
        return {"success": False, "error": error, "data": result}
    return {"success": True, "data": result}


async def _cap_search(params: dict, caller: str) -> dict:
    not_ready = _cap_ready_error()
    if not_ready:
        return not_ready
    graph = get_graph()
    keyword = str(params.get("keyword", ""))
    if not keyword.strip():
        return {"success": False, "error": "keyword is required"}
    return {"success": True, "data": graph.search(keyword)}


async def _cap_stats(params: dict, caller: str) -> dict:
    graph = get_graph()
    stats = graph.stats()
    try:
        async with AsyncSessionLocal() as db:
            stats = await _enrich_stats_with_db(stats, db)
    except Exception:
        pass
    return {"success": True, "data": stats}


async def _cap_rebuild(params: dict, caller: str) -> dict:
    graph = get_graph()
    if not graph.reindex_now():
        return {"success": False, "error": "rebuild callback is not registered", "data": graph.stats()}
    stats = graph.stats()
    stats["rebuild_triggered"] = True
    stats["rebuild_scope"] = "current_worker"
    try:
        async with AsyncSessionLocal() as db:
            stats = await _enrich_stats_with_db(stats, db)
    except Exception:
        pass
    return {"success": True, "data": stats}


async def _cap_acquire_lock(params: dict, caller: str) -> dict:
    return file_lock.acquire_lock(
        params.get("path", ""),
        params.get("agent_id", caller),
        params.get("ttl", 600),
    )


async def _cap_check_lock(params: dict, caller: str) -> dict:
    return file_lock.check_lock(params.get("path", ""))


async def _cap_release_lock(params: dict, caller: str) -> dict:
    return file_lock.release_lock(params.get("path", ""))


async def _cap_list_locks(params: dict, caller: str) -> dict:
    return file_lock.list_locks()


async def _cap_report_inaccuracy(params: dict, caller: str) -> dict:
    try:
        path, query_type = validate_feedback_fields(params.get("path", ""), params.get("query_type", ""))
        async with AsyncSessionLocal() as db:
            await _ensure_tables_once(db)
            feedback = CodemapFeedback(
                path=path,
                query_type=query_type,
                codemap_said=params.get("codemap_said", ""),
                actual=params.get("actual", ""),
                reason=params.get("reason", ""),
                agent_id=params.get("agent_id", caller),
            )
            db.add(feedback)
            await db.flush()
            feedback_id = feedback.id
            await db.commit()
            return {"success": True, "data": {"id": feedback_id, "message": "反馈已记录"}}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _cap_list_feedback(params: dict, caller: str) -> dict:
    try:
        path = params.get("path")
        page = params.get("page", 1)
        page_size = params.get("page_size", 50)
        page = max(int(page or 1), 1)
        page_size = max(int(page_size or 50), 1)
        async with AsyncSessionLocal() as db:
            await _ensure_tables_once(db)
            if path:
                path = normalize_path(path)
                total_result = await db.execute(
                    select(func.count(CodemapFeedback.id)).where(CodemapFeedback.path == path)
                )
                feedback_count = total_result.scalar() or 0
                result = await db.execute(
                    select(CodemapFeedback)
                    .where(CodemapFeedback.path == path)
                    .order_by(CodemapFeedback.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                items = [
                    {
                        "id": f.id,
                        "path": f.path,
                        "query_type": f.query_type,
                        "codemap_said": f.codemap_said,
                        "actual": f.actual,
                        "reason": f.reason,
                        "agent_id": f.agent_id,
                        "created_at": str(f.created_at),
                    }
                    for f in result.scalars().all()
                ]
                return {
                    "success": True,
                    "data": {
                        "items": items,
                        **build_feedback_list_metadata(
                            feedback_count=feedback_count,
                            page=page,
                            page_size=page_size,
                            aggregated_by_path=False,
                            path=path,
                        ),
                    },
                }
            total_result = await db.execute(select(func.count(CodemapFeedback.id)))
            feedback_count = total_result.scalar() or 0
            path_count_result = await db.execute(select(func.count(func.distinct(CodemapFeedback.path))))
            path_count = path_count_result.scalar() or 0
            result = await db.execute(
                select(CodemapFeedback.path, func.count(CodemapFeedback.id).label("count"))
                .group_by(CodemapFeedback.path)
                .order_by(desc("count"))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return {
                "success": True,
                "data": {
                    "items": [{"path": row[0], "complaint_count": row[1]} for row in result.all()],
                    **build_feedback_list_metadata(
                        feedback_count=feedback_count,
                        page=page,
                        page_size=page_size,
                        aggregated_by_path=True,
                        path_count=path_count,
                    ),
                },
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

register_capability(
    "codemap", "get_file", _cap_get_file,
    description="查询文件的代码地图信息：所属层/模块、语言、符号清单、依赖与被依赖、注册/调用的能力、涉及的表",
    brief="查询文件代码地图",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "文件路径（相对项目根目录）"}},
        "required": ["path"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "impact", _cap_impact,
    description="查询影响面：正向+反向传递闭包，返回波及的文件、模块、跨模块能力清单和风险等级(high/medium/low)",
    brief="查询改动影响面",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "symbol": {"type": "string", "description": "符号名（可选，限定影响范围）"},
        },
        "required": ["path"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "check_boundary", _cap_check_boundary,
    description="检查文件或模块的边界合规性，返回违反铁律17-20的引用清单",
    brief="检查边界合规性",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "module_key": {"type": "string", "description": "模块 key（与 path 二选一）"},
        },
    },
    min_role="viewer",
)

register_capability(
    "codemap", "module_map", _cap_module_map,
    description="查询模块的对外能力、依赖的外部能力、边界健康状态",
    brief="查询模块地图",
    parameters={
        "type": "object",
        "properties": {"module_key": {"type": "string", "description": "模块 key"}},
        "required": ["module_key"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "search", _cap_search,
    description="按关键词模糊搜索文件和符号",
    brief="搜索文件和符号",
    parameters={
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "搜索关键词"}},
        "required": ["keyword"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "stats", _cap_stats,
    description="返回索引规模、构建耗时、最后更新时间、是否就绪、新鲜度与可信度",
    brief="查看代码地图统计",
    parameters={"type": "object", "properties": {}},
    min_role="viewer",
)

register_capability(
    "codemap", "rebuild", _cap_rebuild,
    description="全量重建代码索引，返回重建后的 stats",
    brief="重建代码索引",
    parameters={"type": "object", "properties": {}},
    min_role="admin",
)

register_capability(
    "codemap", "acquire_lock", _cap_acquire_lock,
    description="获取文件锁（跨 worker 持久化，租约式 TTL）",
    brief="获取文件锁",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件或资源路径"},
            "agent_id": {"type": "string", "description": "锁主标识"},
            "ttl": {"type": "integer", "description": "租约秒数（默认 600）"},
        },
        "required": ["path", "agent_id"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "check_lock", _cap_check_lock,
    description="检查文件锁状态",
    brief="检查文件锁状态",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "文件或资源路径"}},
        "required": ["path"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "release_lock", _cap_release_lock,
    description="释放文件锁",
    brief="释放文件锁",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "文件或资源路径"}},
        "required": ["path"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "list_locks", _cap_list_locks,
    description="列出所有活跃文件锁",
    brief="列出活跃文件锁",
    parameters={"type": "object", "properties": {}},
    min_role="viewer",
)

register_capability(
    "codemap", "report_inaccuracy", _cap_report_inaccuracy,
    description="报告 codemap 查询结果与实际不符：提交文件路径、codemap 说的、实际情况、原因。Agent 实读验证后发现不准时调用",
    brief="报告 codemap 不准",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "有问题的文件路径"},
            "query_type": {"type": "string", "description": "查询类型: impact / get_file"},
            "codemap_said": {"type": "string", "description": "codemap 返回的内容摘要"},
            "actual": {"type": "string", "description": "实际内容或影响"},
            "reason": {"type": "string", "description": "为什么不准"},
            "agent_id": {"type": "string", "description": "反馈来源 agent（可选）"},
        },
        "required": ["path", "query_type"],
    },
    min_role="viewer",
)

register_capability(
    "codemap", "list_feedback", _cap_list_feedback,
    description="列出 codemap 的反馈记录。可按 path 过滤，按投诉频次排序。仅管理员。维修 codemap 前先查此接口定解析缺陷",
    brief="查看 codemap 反馈",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "按路径过滤（可选）"},
            "page": {"type": "integer", "description": "页码", "default": 1},
            "page_size": {"type": "integer", "description": "每页条数", "default": 50},
        },
    },
    min_role="admin",
)


# Mount lock/feedback HTTP endpoints. Cross-module capabilities are registered
# in this file only; lock_router stays HTTP-only to avoid duplicate registry.
from .locks import lock_router

router.include_router(lock_router.router)
