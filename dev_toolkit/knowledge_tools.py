"""Knowledge-module operational diagnostics for the project toolkit."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from statistics import median
from typing import Any

from dev_toolkit.knowledge_source_gap import (
    normalize_extensions,
    normalize_int_list,
    normalize_string_list,
    source_gap_snapshot,
)
from dev_toolkit.knowledge_source_manifest_audit import source_manifest_import_audit_snapshot

TOOL_NAMES = {
    "knowledge_pipeline_snapshot",
    "knowledge_source_gap_snapshot",
    "knowledge_source_manifest_audit",
    "knowledge_source_manifest_summary",
    "knowledge_source_manifest_scan",
    "knowledge_source_manifest_enqueue",
}

_STAGE_METRIC_WINDOW = 500
_KEY_STAGE_METRICS = {
    "relation_vector_candidates",
    "vector_candidates",
    "entity_candidates",
    "merged_candidates",
    "vector_candidate_limit",
    "entity_candidate_limit",
    "db_commit_ms",
    "candidate_ms",
    "score_ms",
    "stage_wall_ms",
    "llm_ms",
    "embedding_ms",
    "db_write_ms",
    "fusion_model_wall_ms",
    "graph_write_ms",
    "task_wall_ms",
}


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="knowledge_pipeline_snapshot",
            description="汇总知识库管道阶段队列、DB连接状态、最近失败和模型调用日志，用于批量分析巡检。",
            inputSchema={
                "type": "object",
                "properties": {
                    "failed_limit": {"type": "integer", "description": "最近失败任务条数", "default": 20},
                    "log_lines": {
                        "type": "integer",
                        "description": "扫描 backend.log 尾部行数，默认1200；设0跳过日志摘要",
                        "default": 1200,
                    },
                },
            },
        ),
        Tool(
            name="knowledge_source_gap_snapshot",
            description="只读统计企业微盘/外盘等文件根目录还有多少文件未注册或未完成知识库分析。",
            inputSchema={
                "type": "object",
                "properties": {
                    "root_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要递归统计的文件夹根名称，默认企业微盘导入、新加卷、本地资料库导入",
                    },
                    "root_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "可选根文件夹 ID；传入后会和 root_names 合并统计",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "纳入知识库分析口径的后缀白名单；默认覆盖文档、表格、PPT、文本和常见图片",
                    },
                    "sample_limit": {
                        "type": "integer",
                        "description": "每个根目录返回多少个未分析大文件样本，默认 12",
                        "default": 12,
                    },
                },
            },
        ),
        Tool(
            name="knowledge_source_manifest_summary",
            description="汇总外部物理源 manifest 状态，查看哪些文件已发现、已排队、已导入、跳过或失败。",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_root": {"type": "string", "description": "可选源目录过滤，例如 /Volumes/新加卷"},
                    "owner_id": {"type": "integer", "description": "用户 ID，默认 1"},
                },
            },
        ),
        Tool(
            name="knowledge_source_manifest_audit",
            description=(
                "只读审计外部源 manifest 中 imported 行是否已落 framework_file_items、"
                "kb_documents、kb_chunks、kb_raw_data 和 kb_pipeline_stage_runs。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_root": {"type": "string", "description": "可选源目录过滤，例如 /Volumes/新加卷"},
                    "owner_id": {"type": "integer", "description": "用户 ID，默认 1"},
                    "limit": {"type": "integer", "description": "最多审计 imported manifest 行数，默认1000"},
                    "sample_limit": {"type": "integer", "description": "最多返回异常样本数，默认25"},
                    "stages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "关键 pipeline stage 列表；默认知识库 DAG stage",
                    },
                },
            },
        ),
        Tool(
            name="knowledge_source_manifest_scan",
            description="扫描外部物理源目录并落盘 manifest，不导入文件；后续可按 manifest 增量投递。",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_root": {"type": "string", "description": "源目录，例如 /Volumes/新加卷"},
                    "target_root_name": {"type": "string", "description": "后续导入目标根目录名"},
                    "extensions": {"type": "array", "items": {"type": "string"}, "description": "扩展名过滤"},
                    "limit": {"type": "integer", "description": "本次最多扫描文件数，默认10000"},
                    "mark_missing": {"type": "boolean", "description": "完整扫描时标记已消失文件"},
                    "owner_id": {"type": "integer", "description": "用户 ID，默认 1"},
                },
                "required": ["source_root"],
            },
        ),
        Tool(
            name="knowledge_source_manifest_enqueue",
            description="从已扫描 manifest 中投递未导入/变更/失败文件到现有企业源导入队列。",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_root": {"type": "string", "description": "源目录，例如 /Volumes/新加卷"},
                    "target_root_name": {"type": "string", "description": "导入目标根目录名"},
                    "extensions": {"type": "array", "items": {"type": "string"}, "description": "扩展名过滤"},
                    "limit": {"type": "integer", "description": "最多投递清单行数，默认1000"},
                    "priority": {"type": "integer", "description": "导入任务优先级，默认8"},
                    "skip_existing_md5": {"type": "boolean", "description": "是否复用同 MD5 内容，默认 true"},
                    "owner_id": {"type": "integer", "description": "用户 ID，默认 1"},
                },
                "required": ["source_root"],
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> str:
    if name == "knowledge_source_manifest_audit":
        result = await source_manifest_import_audit_snapshot(
            repo_root,
            owner_id=int(arguments.get("owner_id", 1) or 1),
            source_root=str(arguments.get("source_root", "") or ""),
            limit=int(arguments.get("limit", 1000) or 1000),
            sample_limit=int(arguments.get("sample_limit", 25) or 25),
            critical_stages=normalize_string_list(arguments.get("stages")),
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if name in {
        "knowledge_source_manifest_summary",
        "knowledge_source_manifest_scan",
        "knowledge_source_manifest_enqueue",
    }:
        result = await _source_manifest_tool(repo_root, name, arguments)
        return json.dumps(result, ensure_ascii=False, indent=2)
    if name == "knowledge_source_gap_snapshot":
        root_names = arguments.get("root_names")
        root_ids = arguments.get("root_ids")
        extensions = arguments.get("extensions")
        sample_limit = int(arguments.get("sample_limit", 12) or 12)
        snapshot = await source_gap_snapshot(
            repo_root,
            root_names=normalize_string_list(root_names) or [
                "企业微盘导入",
                "新加卷",
                "本地资料库导入",
            ],
            root_ids=normalize_int_list(root_ids),
            extensions=normalize_extensions(extensions),
            sample_limit=max(0, sample_limit),
        )
        return json.dumps(snapshot, ensure_ascii=False, indent=2)
    if name != "knowledge_pipeline_snapshot":
        raise ValueError(f"未知知识库工具: {name}")
    failed_limit = int(arguments.get("failed_limit", 20) or 20)
    log_lines = int(arguments.get("log_lines", 1200) or 0)
    snapshot = await _db_snapshot(repo_root, failed_limit=max(0, failed_limit))
    snapshot["log_summary"] = _log_summary(repo_root, max(0, log_lines))
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


async def _source_manifest_tool(repo_root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    action = name.removeprefix("knowledge_source_manifest_")
    script = f"""
import asyncio
import json
from app.database import AsyncSessionLocal
from modules.knowledge.backend.services.source_manifest_service import (
    enqueue_source_manifest_import,
    scan_source_manifest,
    source_manifest_summary,
)

ARGS = json.loads({json.dumps(json.dumps(arguments, ensure_ascii=False))})
ACTION = {json.dumps(action)}

def _string_list(value):
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in raw if str(item).strip()]

async def main():
    owner_id = int(ARGS.get("owner_id", 1) or 1)
    source_root = str(ARGS.get("source_root", "") or "")
    async with AsyncSessionLocal() as db:
        if ACTION == "summary":
            return await source_manifest_summary(
                db,
                owner_id=owner_id,
                source_root=source_root.strip() or None,
            )
        if ACTION == "scan":
            return await scan_source_manifest(
                db,
                owner_id=owner_id,
                source_root=source_root,
                target_root_name=str(ARGS.get("target_root_name", "企业微盘导入") or "企业微盘导入"),
                extensions=_string_list(ARGS.get("extensions")),
                limit=int(ARGS.get("limit", 10000) or 10000),
                mark_missing=bool(ARGS.get("mark_missing", False)),
            )
        if ACTION == "enqueue":
            return await enqueue_source_manifest_import(
                db,
                owner_id=owner_id,
                source_root=source_root,
                target_root_name=str(ARGS.get("target_root_name", "企业微盘导入") or "企业微盘导入"),
                extensions=_string_list(ARGS.get("extensions")),
                limit=int(ARGS.get("limit", 1000) or 1000),
                priority=int(ARGS.get("priority", 8) or 8),
                skip_existing_md5=bool(ARGS.get("skip_existing_md5", True)),
            )
        raise ValueError(f"unknown source manifest action: {{ACTION}}")

print(json.dumps(asyncio.run(main()), ensure_ascii=False, default=str))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = ".:backend"
    proc = await asyncio.create_subprocess_exec(
        _project_python(repo_root),
        "-c",
        script,
        cwd=repo_root,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return {
            "success": False,
            "error": stderr.decode("utf-8", errors="replace")[-4000:],
        }
    return json.loads(stdout.decode("utf-8"))


async def _db_snapshot(repo_root: Path, *, failed_limit: int) -> dict[str, Any]:
    script = """
import asyncio
import json
from sqlalchemy import text
from app.database import AsyncSessionLocal

NAMES = {
    "source_validate": "源文件校验",
    "parse_index": "基础解析/索引",
    "page_render": "页面截图/压缩资产",
    "raw_text": "原始文本采集",
    "raw_ocr": "视觉 OCR",
    "raw_vision": "VLM 看图理解",
    "fusion": "LLM 融合交叉印证",
    "profile": "文档画像/标签",
    "cognitive_index": "V3 认知派生索引",
    "graph": "实体图谱抽取",
    "relations": "关系/联动构建",
}
ORDER = list(NAMES)

async def main():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text('''
            select stage_key, max(lane_key) lane_key,
                   count(*) filter (where status='pending') pending,
                   count(*) filter (where status='pending' and coalesce(ready_status,'ready')='ready') ready,
                   count(*) filter (where status='running') running,
                   count(*) filter (where status='failed') failed,
                   count(*) filter (where status='completed') completed,
                   count(*) total
            from framework_system_task_queues
            where task_type='kb_pipeline_stage'
            group by stage_key
        '''))).mappings().all()
        pending_breakdown = (await db.execute(text('''
            select stage_key,
                   coalesce(lane_key,'') lane_key,
                   coalesce(ready_status,'ready') ready_status,
                   priority,
                   count(*) count
            from framework_system_task_queues
            where task_type='kb_pipeline_stage' and status='pending'
            group by stage_key, lane_key, ready_status, priority
            order by stage_key, ready_status, priority desc
        '''))).mappings().all()
        lane_running = (await db.execute(text('''
            select coalesce(lane_key,'') lane_key, count(*) running
            from framework_system_task_queues
            where task_type='kb_pipeline_stage' and status='running'
            group by lane_key
        '''))).mappings().all()
        db_states = (await db.execute(text('''
            select coalesce(state,'null') state,
                   coalesce(wait_event_type,'null') wait_event_type,
                   coalesce(wait_event,'null') wait_event,
                   count(*) count
            from pg_stat_activity
            where datname=current_database()
            group by state, wait_event_type, wait_event
            order by count(*) desc
        '''))).mappings().all()
        lock_waits = (await db.execute(text('''
            select state,
                   wait_event_type,
                   wait_event,
                   round(extract(epoch from now() - query_start))::int query_age_s,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 240) query,
                   count(*) count
            from pg_stat_activity
            where datname=current_database()
              and wait_event_type = 'Lock'
            group by state, wait_event_type, wait_event, query_age_s, query
            order by count(*) desc, query_age_s desc
            limit 20
        '''))).mappings().all()
        long_transactions = (await db.execute(text('''
            select pid,
                   state,
                   wait_event_type,
                   wait_event,
                   round(extract(epoch from now() - xact_start))::int xact_age_s,
                   round(extract(epoch from now() - query_start))::int query_age_s,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 240) query
            from pg_stat_activity
            where datname=current_database()
              and xact_start is not null
              and (state = 'idle in transaction' or now() - xact_start > interval '20 seconds')
            order by xact_start nulls last
            limit 30
        '''))).mappings().all()
        failures = (await db.execute(text('''
            select id, document_id, stage_key, retry_count, max_retries,
                   left(coalesce(error_message,''), 360) error_message, updated_at
            from framework_system_task_queues
            where task_type='kb_pipeline_stage' and status='failed'
            order by updated_at desc
            limit :limit
        '''), {"limit": FAILED_LIMIT})).mappings().all()
        stage_metric_rows = (await db.execute(text('''
            select source,
                   stage,
                   status,
                   model_profile,
                   model_used,
                   duration_ms,
                   metrics_json,
                   completed_at,
                   updated_at
            from (
                select 'stage_run' as source,
                       stage,
                       status,
                       null::text as model_profile,
                       null::text as model_used,
                       duration_ms,
                       metrics_json,
                       completed_at,
                       updated_at,
                       id
                from kb_pipeline_stage_runs
                union all
                select 'artifact' as source,
                       stage,
                       status,
                       model_profile,
                       model_used,
                       duration_ms,
                       metrics_json,
                       completed_at,
                       updated_at,
                       id
                from kb_analysis_artifacts
            ) recent_metrics
            order by coalesce(completed_at, updated_at) desc nulls last, source, id desc
            limit :limit
        '''), {"limit": STAGE_METRIC_WINDOW})).mappings().all()

    by_stage = {row["stage_key"]: row for row in rows}
    totals = {"pending": 0, "ready": 0, "running": 0, "failed": 0, "completed": 0, "total": 0}
    stages = []
    for stage in ORDER:
        row = by_stage.get(stage)
        if not row:
            continue
        item = {
            "stage": stage,
            "name": NAMES[stage],
            "lane": row["lane_key"],
            "pending": int(row["pending"]),
            "ready": int(row["ready"]),
            "running": int(row["running"]),
            "failed": int(row["failed"]),
            "completed": int(row["completed"]),
            "total": int(row["total"]),
        }
        item["remaining"] = item["pending"] + item["running"] + item["failed"]
        item["rate"] = round(item["completed"] / item["total"] * 100, 1) if item["total"] else 0.0
        for key in totals:
            totals[key] += item[key]
        stages.append(item)
    totals["remaining"] = totals["pending"] + totals["running"] + totals["failed"]
    totals["rate"] = round(totals["completed"] / totals["total"] * 100, 1) if totals["total"] else 0.0
    print(json.dumps({
        "success": True,
        "stages": stages,
        "totals": totals,
        "pending_breakdown": [dict(row) for row in pending_breakdown],
        "lane_running": [dict(row) for row in lane_running],
        "db_states": [dict(row) for row in db_states],
        "db_pressure": {
            "lock_wait_count": sum(int(row["count"]) for row in lock_waits),
            "idle_in_transaction_count": sum(
                int(row["count"])
                for row in db_states
                if row["state"] == "idle in transaction"
            ),
            "long_transaction_count": len(long_transactions),
            "lock_waits": [dict(row) for row in lock_waits],
            "long_transactions": [dict(row) for row in long_transactions],
        },
        "recent_failures": [{**dict(row), "updated_at": str(row["updated_at"])} for row in failures],
        "recent_stage_metric_rows": [
            {
                **dict(row),
                "completed_at": str(row["completed_at"]) if row["completed_at"] else None,
                "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            }
            for row in stage_metric_rows
        ],
    }, ensure_ascii=False, default=str))

asyncio.run(main())
""".replace("FAILED_LIMIT", str(failed_limit)).replace("STAGE_METRIC_WINDOW", str(_STAGE_METRIC_WINDOW))
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    proc = await asyncio.create_subprocess_exec(
        _project_python(repo_root),
        "-c",
        script,
        cwd=repo_root,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return {
            "success": False,
            "error": stderr.decode("utf-8", errors="replace")[-4000:],
        }
    snapshot = json.loads(stdout.decode("utf-8"))
    metric_rows = snapshot.pop("recent_stage_metric_rows", [])
    snapshot["recent_stage_metrics"] = _summarize_stage_metrics(metric_rows)
    worker_config = _load_worker_config(repo_root)
    snapshot["worker_config"] = worker_config
    _annotate_queue_limits(snapshot, worker_config)
    return snapshot


def _summarize_stage_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    duration_by_stage: dict[str, list[float]] = {}
    duration_by_model: dict[str, list[float]] = {}
    key_values: dict[str, list[float]] = {}
    status_counts: dict[str, int] = {}
    model_counts: dict[str, int] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        stage = str(row.get("stage") or "unknown")
        status = str(row.get("status") or "unknown")
        model = str(row.get("model_used") or row.get("model_profile") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        model_counts[model] = model_counts.get(model, 0) + 1

        duration = _number(row.get("duration_ms"))
        if duration is not None:
            duration_by_stage.setdefault(stage, []).append(duration)
            duration_by_model.setdefault(model, []).append(duration)

        metrics = row.get("metrics_json")
        if isinstance(metrics, dict):
            for key, value in _flatten_metrics(metrics).items():
                if key not in _KEY_STAGE_METRICS:
                    continue
                number = _number(value)
                if number is not None:
                    key_values.setdefault(key, []).append(number)

    return {
        "window_size": len(rows),
        "status_counts": status_counts,
        "model_counts": model_counts,
        "duration_ms_by_stage": {
            key: _number_summary(values)
            for key, values in sorted(duration_by_stage.items())
        },
        "duration_ms_by_model": {
            key: _number_summary(values)
            for key, values in sorted(duration_by_model.items())
        },
        "key_metrics": {
            key: _number_summary(values)
            for key, values in sorted(key_values.items())
        },
    }


def _flatten_metrics(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        clean_key = str(key)
        nested_key = f"{prefix}.{clean_key}" if prefix else clean_key
        flattened[nested_key] = item
        flattened[clean_key] = item
        if isinstance(item, dict):
            flattened.update(_flatten_metrics(item, nested_key))
    return flattened


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number_summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": _round_number(median(ordered)) if ordered else None,
        "p90": _round_number(_percentile_number(ordered, 0.9)) if ordered else None,
        "max": _round_number(max(ordered)) if ordered else None,
    }


def _percentile_number(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return sorted(values)[index]


def _round_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    if float(value).is_integer():
        return int(value)
    return round(value, 2)


def _load_worker_config(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "backend" / "data" / "config" / "task_worker.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"loaded": False, "path": str(path), "error": str(exc)}
    return {
        "loaded": True,
        "path": str(path),
        "worker_lanes_per_process": data.get("worker_lanes_per_process"),
        "worker_process_slots": data.get("worker_process_slots"),
        "max_lanes_per_process": data.get("max_lanes_per_process"),
        "poll_interval_seconds": data.get("poll_interval_seconds"),
        "stage_concurrency": (data.get("stage_concurrency") or {}).get("kb_pipeline_stage", {}),
        "lane_concurrency": (data.get("lane_concurrency") or {}).get("kb_pipeline_stage", {}),
        "paused_stages": (data.get("paused_stages") or {}).get("kb_pipeline_stage", []),
        "paused_lanes": (data.get("paused_lanes") or {}).get("kb_pipeline_stage", []),
    }


def _annotate_queue_limits(snapshot: dict[str, Any], worker_config: dict[str, Any]) -> None:
    stages = snapshot.get("stages") or []
    lane_running = {
        row.get("lane_key") or "": int(row.get("running") or 0)
        for row in snapshot.get("lane_running") or []
        if isinstance(row, dict)
    }
    stage_limits = worker_config.get("stage_concurrency") or {}
    lane_limits = worker_config.get("lane_concurrency") or {}
    paused_stages = {
        str(stage)
        for stage in (worker_config.get("paused_stages") or [])
        if str(stage).strip()
    }
    paused_lanes = {
        str(lane)
        for lane in (worker_config.get("paused_lanes") or [])
        if str(lane).strip()
    }
    reasons: dict[str, int] = {}
    for item in stages:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or "")
        lane = str(item.get("lane") or "")
        ready = int(item.get("ready") or 0)
        pending = int(item.get("pending") or 0)
        running = int(item.get("running") or 0)
        stage_limit = _optional_positive_int(stage_limits.get(stage))
        lane_limit = _optional_positive_int(lane_limits.get(lane))
        current_lane_running = lane_running.get(lane, 0)
        if pending <= 0:
            reason = "no_pending"
        elif stage in paused_stages:
            reason = "paused_by_config"
        elif lane in paused_lanes:
            reason = "lane_paused_by_config"
        elif ready <= 0:
            reason = "blocked_not_ready"
        elif stage_limit is not None and running >= stage_limit:
            reason = "stage_concurrency_full"
        elif lane_limit is not None and current_lane_running >= lane_limit:
            reason = "lane_concurrency_full"
        else:
            reason = "ready_waiting_for_worker_poll_or_free_worker"
        item["configured_stage_concurrency"] = stage_limit
        item["configured_lane_concurrency"] = lane_limit
        item["lane_running"] = current_lane_running
        item["pending_diagnosis"] = reason
        reasons[reason] = reasons.get(reason, 0) + pending
    snapshot["pending_diagnosis_summary"] = reasons


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _project_python(repo_root: Path) -> str:
    candidate = repo_root / "backend" / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else "python3"


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0 or not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return []


def _log_summary(repo_root: Path, log_lines: int) -> dict[str, Any]:
    lines = _tail_lines(repo_root / "backend" / "logs" / "backend.log", log_lines)
    durations: list[int] = []
    summary: dict[str, Any] = {
        "scanned_lines": len(lines),
        "gpt55_success": 0,
        "read_timeout": 0,
        "fallback_succeeded": 0,
        "degraded": 0,
        "vision_failed": 0,
        "errors": 0,
        "recent_error_samples": [],
    }
    for line in lines:
        if "model=gpt-5.5-knowledge" in line and "[USAGE]" in line and "error=" not in line:
            summary["gpt55_success"] += 1
        if "ReadTimeout" in line:
            summary["read_timeout"] += 1
        if "fallback succeeded" in line:
            summary["fallback_succeeded"] += 1
        if "LLM_CALL_DEGRADED" in line or "model_degraded=True" in line:
            summary["degraded"] += 1
        if "Vision model" in line and "failed" in line:
            summary["vision_failed"] += 1
        if " ERROR " in line or "Traceback" in line:
            summary["errors"] += 1
            if len(summary["recent_error_samples"]) < 12:
                summary["recent_error_samples"].append(line[-500:])
        match = re.search(r"duration=(\\d+)ms", line)
        if match:
            durations.append(int(match.group(1)))
    summary["model_duration_ms"] = {
        "count": len(durations),
        "median": int(median(durations)) if durations else None,
        "p90": _percentile(durations, 0.9),
        "max": max(durations) if durations else None,
    }
    return summary


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]
