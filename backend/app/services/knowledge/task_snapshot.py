import json
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, KnowledgeTask

STATUS_MAP = {
    "pending": "待执行",
    "processing": "执行中",
    "done": "已完成",
    "failed": "失败",
}


def _progress(task: KnowledgeTask) -> dict:
    return {
        "百分比": task.progress or 0,
        "当前步骤": task.task_type,
        "块数": 0,
        "候选数": 0,
        "证据数": 0,
        "阶段列表": [{"名称": task.task_type, "状态": STATUS_MAP.get(task.status, task.status)}],
    }


def _task_item(task: KnowledgeTask, catalog: Catalog | None) -> dict:
    created = task.created_at.isoformat() if task.created_at else ""
    return {
        "任务ID": task.id,
        "文件ID": task.catalog_id,
        "文件名": catalog.file_name if catalog else None,
        "通道": catalog.channel_type if catalog else None,
        "优先级": 0,
        "状态": STATUS_MAP.get(task.status, task.status),
        "入队时间": created,
        "开始时间": task.heartbeat.isoformat() if task.heartbeat else None,
        "结束时间": task.updated_at.isoformat() if task.status in {"done", "failed"} and task.updated_at else None,
        "错误信息": task.error,
        "进度": _progress(task),
    }


async def build_task_snapshot(db: AsyncSession) -> dict:
    result = await db.execute(select(KnowledgeTask).order_by(desc(KnowledgeTask.id)).limit(50))
    tasks = result.scalars().all()
    catalog_ids = {task.catalog_id for task in tasks}
    catalogs: dict[int, Catalog] = {}
    if catalog_ids:
        catalog_result = await db.execute(select(Catalog).where(Catalog.id.in_(catalog_ids)))
        catalogs = {catalog.id: catalog for catalog in catalog_result.scalars().all()}
    items = [_task_item(task, catalogs.get(task.catalog_id)) for task in tasks]
    now = datetime.now(timezone.utc).isoformat()
    active = [item for item in items if item["状态"] in {"待执行", "执行中"}]
    realtime = [{
        "时间": now,
        "文件ID": item["文件ID"],
        "文件名": item["文件名"] or f"文件 {item['文件ID']}",
        "状态": item["状态"],
        "当前步骤": item["进度"]["当前步骤"],
        "百分比": item["进度"]["百分比"],
    } for item in active[:20]]
    return {"任务列表": items, "实时动态": realtime}


def sse_payload(snapshot: dict) -> str:
    return "data: " + json.dumps(snapshot, ensure_ascii=False) + "\n\n"
