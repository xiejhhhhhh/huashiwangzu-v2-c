import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.core.exceptions import NotFound, PermissionDenied, ValidationError, ConflictError
from app.services.module_registry import register_capability
from app.models.system import SystemTaskQueue

logger = logging.getLogger("v2.scheduler").getChild("router")

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class CreateSchedulerRequest(BaseModel):
    title: str
    scheduled_at: str | None = None
    recur: str | None = None
    action_description: str


class CancelSchedulerRequest(BaseModel):
    task_id: int


def _parse_user_id(caller: str) -> int:
    if caller and caller.startswith("user:"):
        return int(caller.split(":", 1)[1])
    return 0


@router.post("/create")
async def http_create(
    req: CreateSchedulerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    scheduled_dt = None
    if req.scheduled_at:
        try:
            scheduled_dt = datetime.fromisoformat(req.scheduled_at)
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValidationError("scheduled_at 格式无效，请使用 ISO 8601")

    if req.recur and req.recur not in ("hourly", "daily", "weekly"):
        if not req.recur.startswith("cron:"):
            raise ValidationError("recur 仅支持 hourly/daily/weekly 或 cron:HH:MM")

    task = SystemTaskQueue(
        task_type="scheduled_agent_job",
        parameters=json.dumps({
            "title": req.title,
            "action_description": req.action_description,
            "creator_id": current_user.id,
        }, ensure_ascii=False),
        status="pending",
        module="scheduler",
        creator_id=current_user.id,
        scheduled_at=scheduled_dt,
        recur=req.recur,
        next_run_at=scheduled_dt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return ApiResponse(data={"id": task.id, "status": "created"})


@router.get("/list")
async def http_list(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("viewer")),
):
    stmt = select(SystemTaskQueue).where(
        and_(
            SystemTaskQueue.module == "scheduler",
            SystemTaskQueue.creator_id == current_user.id,
        )
    ).order_by(SystemTaskQueue.created_at.desc())
    r = await db.execute(stmt)
    tasks = r.scalars().all()
    return ApiResponse(data=[{
        "id": t.id,
        "title": json.loads(t.parameters or "{}").get("title", "") if t.parameters else "",
        "action_description": json.loads(t.parameters or "{}").get("action_description", "") if t.parameters else "",
        "status": t.status,
        "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
        "recur": t.recur,
        "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
        "result": t.result,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in tasks])


@router.post("/cancel")
async def http_cancel(
    req: CancelSchedulerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    task = await db.get(SystemTaskQueue, req.task_id)
    if not task or task.module != "scheduler":
        raise NotFound("任务不存在")
    if task.creator_id != current_user.id:
        raise PermissionDenied("只能取消自己的任务")
    if task.status in ("completed", "failed"):
        raise ConflictError("任务已结束，无法取消")
    task.status = "cancelled"
    await db.commit()
    return ApiResponse(data={"id": task.id, "status": "cancelled"})


# ── Cross-module capability: handler for scheduled_agent_job ──────────────────

async def _cap_create(params: dict, caller: str) -> dict:
    title = params.get("title", "")
    action_desc = params.get("action_description", "")
    owner_id = _parse_user_id(caller)
    if not owner_id:
        return {"success": False, "error": "无法解析调用者身份"}
    scheduled_at_str = params.get("scheduled_at")
    scheduled_dt = None
    if scheduled_at_str:
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_at_str)
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return {"success": False, "error": "scheduled_at 格式无效"}
    recur = params.get("recur")
    async with AsyncSessionLocal() as db:
        task = SystemTaskQueue(
            task_type="scheduled_agent_job",
            parameters=json.dumps({
                "title": title,
                "action_description": action_desc,
                "creator_id": owner_id,
            }, ensure_ascii=False),
            status="pending",
            module="scheduler",
            creator_id=owner_id,
            scheduled_at=scheduled_dt,
            recur=recur,
            next_run_at=scheduled_dt,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
    return {"success": True, "data": {"id": task.id}}


async def _cap_list(params: dict, caller: str) -> dict:
    owner_id = _parse_user_id(caller)
    async with AsyncSessionLocal() as db:
        stmt = select(SystemTaskQueue).where(
            and_(
                SystemTaskQueue.module == "scheduler",
                SystemTaskQueue.creator_id == owner_id,
            )
        ).order_by(SystemTaskQueue.created_at.desc())
        r = await db.execute(stmt)
        tasks = r.scalars().all()
    return {"success": True, "data": [
        {"id": t.id, "title": json.loads(t.parameters or "{}").get("title", ""),
         "status": t.status, "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
         "recur": t.recur, "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
         "result": t.result, "error_message": t.error_message}
        for t in tasks
    ]}


async def _cap_cancel(params: dict, caller: str) -> dict:
    task_id = params.get("task_id")
    owner_id = _parse_user_id(caller)
    async with AsyncSessionLocal() as db:
        task = await db.get(SystemTaskQueue, task_id)
        if not task or task.module != "scheduler":
            return {"success": False, "error": "任务不存在"}
        if task.creator_id != owner_id:
            return {"success": False, "error": "只能取消自己的任务"}
        if task.status in ("completed", "failed"):
            return {"success": False, "error": "任务已结束"}
        task.status = "cancelled"
        await db.commit()
    return {"success": True, "data": {"id": task_id, "status": "cancelled"}}


async def _cap_scheduled_job_handler(params: dict) -> dict:
    """Handler for scheduled_agent_job tasks.

    Triggers a real Agent chat execution with the action_description,
    stores the result, and notifies the creator via IM.
    """
    title = params.get("title", "定时任务")
    action_desc = params.get("action_description", "")
    creator_id = params.get("creator_id", 0)

    result_text = f"定时任务「{title}」已触发。动作: {action_desc[:200]}"
    execute_result = ""

    # Try to actually execute via Agent chat if action_description looks like a user query
    if action_desc and len(action_desc) > 10:
        try:
            from app.services.module_registry import call_capability

            # Create a conversation session for this scheduled execution
            conv_result = await call_capability(
                "agent", "spawn_subagent",
                {
                    "task": f"执行定时任务：{action_desc}",
                    "track_trajectory": True,
                    "write_enabled": True,
                    "tools": [],
                },
                caller=f"scheduler:system",
                caller_role="admin",
            )
            if isinstance(conv_result, dict):
                data = conv_result.get("data", {}) if conv_result.get("success") else {}
                results = data.get("results", [])
                if results:
                    execute_result = results[0].get("conclusion", "")
                elif conv_result.get("data", {}).get("conclusion"):
                    execute_result = conv_result["data"]["conclusion"]
                elif conv_result.get("error"):
                    execute_result = f"执行错误: {conv_result['error']}"
                else:
                    execute_result = _j(conv_result)[:1000]
            else:
                execute_result = str(conv_result)[:1000]

        except Exception as agent_exc:
            logger.warning("Agent scheduled execution failed, falling back to notify: %s", agent_exc)
            execute_result = f"Agent 执行失败: {agent_exc}"

    if execute_result:
        result_text = f"定时任务「{title}」执行完成。\n\n动作: {action_desc[:200]}\n\n结果:\n{execute_result[:1500]}"
    else:
        result_text = f"定时任务「{title}」已触发。动作: {action_desc[:200]}"

    # Notify creator
    try:
        from app.services.module_registry import call_capability as _cc
        await _cc(
            "im", "notify",
            {"user_id": creator_id, "content": result_text, "title": title},
            caller=f"scheduler:system",
            caller_role="admin",
        )
    except Exception as exc:
        logger.warning("IM notify unavailable, falling back to log: %s", exc)

    return {"success": True, "result": result_text[:2000], "executed": bool(execute_result)}

register_capability(
    "scheduler", "create", _cap_create,
    description="创建定时任务：传入标题、时间/周期、动作描述，到期自动执行并推送结果到本人 IM",
    brief="创建定时任务",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "任务标题"},
            "action_description": {"type": "string", "description": "到点要执行的动作描述"},
            "scheduled_at": {"type": "string", "description": "ISO 8601 执行时间（可空=立即）"},
            "recur": {"type": "string", "description": "周期: daily/hourly/weekly/cron:HH:MM（可空=单次）"},
        },
        "required": ["title", "action_description"],
    },
    min_role="editor",
)

register_capability(
    "scheduler", "list", _cap_list,
    description="列出自己创建的定时任务",
    brief="列出我的定时任务",
    parameters={"type": "object", "properties": {}},
    min_role="viewer",
)

register_capability(
    "scheduler", "cancel", _cap_cancel,
    description="取消自己创建的定时任务",
    brief="取消定时任务",
    parameters={
        "type": "object",
        "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
        "required": ["task_id"],
    },
    min_role="editor",
)

# Register the task_type handler for scheduled_agent_job
from app.services.task_worker import register_task_handler

register_task_handler("scheduled_agent_job", _cap_scheduled_job_handler)
