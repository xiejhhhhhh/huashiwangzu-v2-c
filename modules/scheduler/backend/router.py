import json
import logging
from datetime import datetime, timezone

from app.core.exceptions import AppException, ConflictError, NotFound, PermissionDenied, ValidationError
from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.system import SystemTaskQueue
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.scheduler").getChild("router")

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])
_FAILURE_STATUSES = {"failed", "error"}
_ALLOWED_RECUR = {"hourly", "daily", "weekly"}
_CANCELLABLE_STATUSES = {"pending"}


class CreateSchedulerRequest(BaseModel):
    title: str
    scheduled_at: str | None = None
    recur: str | None = None
    action_description: str


class CancelSchedulerRequest(BaseModel):
    task_id: int


def _normalize_required_text(value: object, field_name: str, max_length: int = 256) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} 必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} 不能为空")
    if len(normalized) > max_length:
        raise ValidationError(f"{field_name} 不能超过 {max_length} 个字符")
    return normalized


def _parse_scheduled_at(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError("scheduled_at 必须是 ISO 8601 字符串")
    try:
        scheduled_dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError("scheduled_at 格式无效，请使用 ISO 8601") from None
    if scheduled_dt.tzinfo is None:
        scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
    return scheduled_dt.astimezone(timezone.utc)


def _validate_recur(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError("recur 必须是字符串")
    recur = value.strip().lower()
    if recur in _ALLOWED_RECUR:
        return recur
    if not recur.startswith("cron:"):
        raise ValidationError("recur 仅支持 hourly/daily/weekly 或 cron:HH:MM")
    parts = recur.split(":")
    if len(parts) != 3:
        raise ValidationError("cron 表达式必须是 cron:HH:MM")
    try:
        hour = int(parts[1])
        minute = int(parts[2])
    except ValueError:
        raise ValidationError("cron 表达式必须使用数字小时和分钟") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValidationError("cron 时间必须在 00:00 到 23:59 之间")
    return f"cron:{hour:02d}:{minute:02d}"


def _parse_positive_task_id(value: object) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValidationError("task_id 必须是正整数")
    return value


def _encode_task_parameters(title: str, action_description: str, creator_id: int) -> str:
    return json.dumps({
        "title": title,
        "action_description": action_description,
        "creator_id": creator_id,
    }, ensure_ascii=False)


def _decode_task_parameters(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid scheduler task parameters JSON ignored")
        return {}
    return value if isinstance(value, dict) else {}


def _task_to_dict(task: SystemTaskQueue) -> dict:
    params = _decode_task_parameters(task.parameters)
    return {
        "id": task.id,
        "title": params.get("title", ""),
        "action_description": params.get("action_description", ""),
        "status": task.status,
        "scheduled_at": task.scheduled_at.isoformat() if task.scheduled_at else None,
        "recur": task.recur,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "result": task.result,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


async def _create_scheduler_task(
    db: AsyncSession,
    *,
    title: object,
    action_description: object,
    creator_id: int,
    scheduled_at: object = None,
    recur: object = None,
) -> SystemTaskQueue:
    normalized_title = _normalize_required_text(title, "title")
    normalized_action = _normalize_required_text(
        action_description, "action_description", max_length=4000,
    )
    scheduled_dt = _parse_scheduled_at(scheduled_at)
    normalized_recur = _validate_recur(recur)
    task = SystemTaskQueue(
        task_type="scheduled_agent_job",
        parameters=_encode_task_parameters(normalized_title, normalized_action, creator_id),
        status="pending",
        module="scheduler",
        creator_id=creator_id,
        scheduled_at=scheduled_dt,
        recur=normalized_recur,
        next_run_at=scheduled_dt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/create")
async def http_create(
    req: CreateSchedulerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    task = await _create_scheduler_task(
        db,
        title=req.title,
        action_description=req.action_description,
        creator_id=current_user.id,
        scheduled_at=req.scheduled_at,
        recur=req.recur,
    )
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
    return ApiResponse(data=[_task_to_dict(t) for t in tasks])


@router.post("/cancel")
async def http_cancel(
    req: CancelSchedulerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("editor")),
):
    task_id = _parse_positive_task_id(req.task_id)
    task = await db.get(SystemTaskQueue, task_id)
    if not task or task.module != "scheduler":
        raise NotFound("任务不存在")
    if task.creator_id != current_user.id:
        raise PermissionDenied("只能取消自己的任务")
    if task.status not in _CANCELLABLE_STATUSES:
        raise ConflictError("只能取消 pending 状态的定时任务")
    task.status = "cancelled"
    await db.commit()
    return ApiResponse(data={"id": task.id, "status": "cancelled"})


# ── Cross-module capability: handler for scheduled_agent_job ──────────────────

async def _cap_create(params: dict, caller: str) -> dict:
    try:
        owner_id = resolve_caller_user_id(caller)
    except PermissionDenied:
        return {"success": False, "error": "无法解析调用者身份"}
    if not owner_id:
        return {"success": False, "error": "无法解析调用者身份"}
    async with AsyncSessionLocal() as db:
        try:
            task = await _create_scheduler_task(
                db,
                title=params.get("title"),
                action_description=params.get("action_description"),
                creator_id=owner_id,
                scheduled_at=params.get("scheduled_at"),
                recur=params.get("recur"),
            )
        except AppException as exc:
            return {"success": False, "error": str(exc)}
    return {"success": True, "data": {"id": task.id}}


async def _cap_list(params: dict, caller: str) -> dict:
    try:
        owner_id = resolve_caller_user_id(caller)
    except PermissionDenied as exc:
        return {"success": False, "error": str(exc) or "无法解析调用者身份"}
    if not owner_id:
        return {"success": False, "error": "无法解析调用者身份"}
    async with AsyncSessionLocal() as db:
        stmt = select(SystemTaskQueue).where(
            and_(
                SystemTaskQueue.module == "scheduler",
                SystemTaskQueue.creator_id == owner_id,
            )
        ).order_by(SystemTaskQueue.created_at.desc())
        r = await db.execute(stmt)
        tasks = r.scalars().all()
    return {"success": True, "data": [_task_to_dict(t) for t in tasks]}


def _stringify_error(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _agent_failure_message(result: object) -> str | None:
    if not isinstance(result, dict):
        return None

    if result.get("success") is False:
        return _stringify_error(result.get("error")) or "Agent capability returned success:false"

    status = str(result.get("status") or "").lower()
    if status in _FAILURE_STATUSES:
        return _stringify_error(result.get("error")) or f"Agent capability status={status}"

    if result.get("error"):
        return _stringify_error(result.get("error"))

    data = result.get("data")
    if isinstance(data, dict):
        data_status = str(data.get("status") or "").lower()
        if data_status in _FAILURE_STATUSES:
            return _stringify_error(data.get("error")) or f"Agent capability data.status={data_status}"
        if data.get("error"):
            return _stringify_error(data.get("error"))

        results = data.get("results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                item_status = str(item.get("status") or "").lower()
                if item_status in _FAILURE_STATUSES:
                    return _stringify_error(item.get("error")) or f"Agent result status={item_status}"
                if item.get("error"):
                    return _stringify_error(item.get("error"))

    return None


async def _cap_cancel(params: dict, caller: str) -> dict:
    try:
        task_id = _parse_positive_task_id(params.get("task_id"))
    except AppException as exc:
        return {"success": False, "error": str(exc)}
    try:
        owner_id = resolve_caller_user_id(caller)
    except PermissionDenied:
        return {"success": False, "error": "无法解析调用者身份"}
    async with AsyncSessionLocal() as db:
        task = await db.get(SystemTaskQueue, task_id)
        if not task or task.module != "scheduler":
            return {"success": False, "error": "任务不存在"}
        if task.creator_id != owner_id:
            return {"success": False, "error": "只能取消自己的任务"}
        if task.status not in _CANCELLABLE_STATUSES:
            return {"success": False, "error": "只能取消 pending 状态的定时任务"}
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
    if not creator_id:
        return {"success": False, "error": "Missing creator_id"}

    result_text = f"定时任务「{title}」已触发。动作: {action_desc[:200]}"
    execute_result = ""
    failure_error = ""

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
                caller=f"user:{creator_id}",
                caller_role="viewer",
            )
            if isinstance(conv_result, dict):
                failure_error = _agent_failure_message(conv_result) or ""
                if failure_error:
                    execute_result = f"执行错误: {failure_error}"
                else:
                    data = conv_result.get("data", {}) if conv_result.get("success") else {}
                    results = data.get("results", [])
                    if results:
                        execute_result = results[0].get("conclusion", "")
                    elif conv_result.get("data", {}).get("conclusion"):
                        execute_result = conv_result["data"]["conclusion"]
                    else:
                        execute_result = json.dumps(conv_result, ensure_ascii=False)[:1000]
            else:
                execute_result = str(conv_result)[:1000]

        except Exception as agent_exc:
            logger.warning("Agent scheduled execution failed: %s", agent_exc)
            failure_error = str(agent_exc)
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
            caller="system:task-worker",
            caller_role="viewer",
        )
    except Exception as exc:
        logger.warning("IM notify unavailable, falling back to log: %s", exc)

    if failure_error:
        return {
            "success": False,
            "status": "failed",
            "error": failure_error,
            "result": result_text[:2000],
            "executed": False,
        }

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
