"""Single-leader database dispatcher for framework background tasks.

The existing task queue remains the durable source of truth.  This module owns
claiming, lease renewal, executor process supervision and resource accounting;
business handlers remain registered by their modules.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable
from uuid import uuid4

import psutil
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.system import SystemTaskQueue, TaskAttemptMetric
from app.services.event_bus import append_event_in_transaction
from app.services.process_registry import 注册进程, 注销进程

logger = logging.getLogger("v2.task_dispatcher")

DISPATCHER_LEADER_LOCK_KEY = 94022025
DEFAULT_IDLE_POLL_SECONDS = 5.0
DEFAULT_ACTIVE_POLL_SECONDS = 1.0
DEFAULT_LEASE_SECONDS = 30
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_MAX_EXECUTORS = 8
DEFAULT_EXECUTOR_RSS_MB = 512


@dataclass(frozen=True)
class TaskDefinition:
    """Scheduling metadata for a registered handler.

    Definitions are intentionally small. Existing handlers can use the default
    definition while they are migrated; Knowledge supplies stage/lane metadata
    through its persisted queue fields.
    """

    task_type: str
    default_lane: str = "general"
    rss_estimate_mb: int = DEFAULT_EXECUTOR_RSS_MB
    timeout_seconds: int = 1200
    cloud: bool = False
    cpu_cores: float = 0.25
    gpu_memory_mb: int = 0
    provider_key: str | None = None


@dataclass(frozen=True)
class DispatcherConfig:
    idle_poll_seconds: float = DEFAULT_IDLE_POLL_SECONDS
    active_poll_seconds: float = DEFAULT_ACTIVE_POLL_SECONDS
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS
    max_executors: int = DEFAULT_MAX_EXECUTORS
    memory_caution_percent: float = 80.0
    memory_emergency_percent: float = 90.0
    memory_reserve_mb: int = 1024
    cpu_caution_percent: float = 80.0
    gpu_caution_percent: float = 80.0
    gpu_emergency_percent: float = 90.0
    lane_limits: dict[str, int] = field(default_factory=dict)
    provider_limits: dict[str, int] = field(default_factory=dict)
    stage_timeouts_seconds: dict[str, dict[str, int]] = field(default_factory=dict)
    reconcile_seconds: float = 60.0
    paused_task_types: frozenset[str] = frozenset()
    paused_stages: dict[str, frozenset[str]] = field(default_factory=dict)
    paused_lanes: dict[str, frozenset[str]] = field(default_factory=dict)
    allowed_task_types: frozenset[str] | None = None
    allowed_document_ids: frozenset[int] | None = None


@dataclass(frozen=True)
class ClaimedLease:
    task_id: int
    lease_token: str
    task_type: str
    lane_key: str
    stage_key: str
    attempt: int
    timeout_seconds: int = 1200


@dataclass
class ExecutorState:
    claim: ClaimedLease
    process: asyncio.subprocess.Process
    started_at: datetime
    started_perf: float
    rss_start_mb: float | None
    rss_peak_mb: float | None
    cpu_start_seconds: float | None
    io_start: tuple[int, int] | None
    last_heartbeat: datetime
    reg_id: int | None = None


_definitions: dict[str, TaskDefinition] = {}
_dispatcher_task: asyncio.Task[None] | None = None
_dispatcher_stop = False
_dispatcher_is_leader = False
_active_executors: dict[int, ExecutorState] = {}
TaskSettlementHandler = Callable[[AsyncSession, SystemTaskQueue, dict[str, Any]], Awaitable[None]]
_settlement_handlers: dict[str, TaskSettlementHandler] = {}
TaskReconciler = Callable[[AsyncSession], Awaitable[None]]
_reconcilers: dict[str, TaskReconciler] = {}


def register_task_definition(definition: TaskDefinition) -> None:
    _definitions[definition.task_type] = definition


def ensure_task_definition(task_type: str, *, lane_key: str | None = None) -> TaskDefinition:
    existing = _definitions.get(task_type)
    if existing is not None:
        return existing
    definition = TaskDefinition(task_type=task_type, default_lane=lane_key or "general")
    _definitions[task_type] = definition
    return definition


def task_definitions() -> dict[str, TaskDefinition]:
    return dict(_definitions)


def register_task_settlement_handler(task_type: str, handler: TaskSettlementHandler) -> None:
    """Register module-owned downstream publication after a task settles.

    The dispatcher invokes this inside its fenced settlement transaction.  A
    handler may create dependent rows but must not commit the supplied session.
    """
    _settlement_handlers[task_type] = handler


def register_dispatcher_reconciler(name: str, reconciler: TaskReconciler) -> None:
    """Register low-frequency durable-state repair work owned by Dispatcher."""
    _reconcilers[name] = reconciler


def build_task_envelope(
    *,
    task_type: str,
    module: str,
    owner_id: int | None,
    lane_key: str | None,
    requested_by: str,
    trigger: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_type": task_type,
        "module": module,
        "owner_id": owner_id,
        "lane_key": lane_key or "general",
        "requested_by": requested_by,
        "trigger": trigger,
        "body": body,
    }


def _contains_physical_path(value: Any, *, key: str = "") -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in {"physical_path", "file_path", "full_path", "absolute_path"}:
        return True
    if isinstance(value, dict):
        return any(_contains_physical_path(child, key=str(child_key)) for child_key, child in value.items())
    if isinstance(value, list):
        return any(_contains_physical_path(child) for child in value)
    return False


async def publish_task(
    db: AsyncSession,
    *,
    task_type: str,
    module: str,
    owner_id: int | None,
    body: dict[str, Any],
    requested_by: str,
    trigger: str,
    priority: int = 0,
    max_retries: int = 3,
    document_id: int | None = None,
    stage_key: str | None = None,
    lane_key: str | None = None,
    dependency_key: str | None = None,
    ready_status: str = "ready",
    resource_profile: dict[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    recur: str | None = None,
    next_run_at: datetime | None = None,
) -> SystemTaskQueue:
    """Create one durable task through the sole publication contract.

    It deliberately does not commit: callers can atomically persist their
    domain change, its follow-up work and an outbox event in one transaction.
    Disk paths are rejected; handlers receive durable IDs and resolve files via
    framework access checks at execution time.
    """
    if not task_type or not module:
        raise ValueError("task_type and module are required")
    if not isinstance(body, dict):
        raise ValueError("task body must be an object")
    if _contains_physical_path(body):
        raise ValueError("task body must not contain a physical file path; pass file_id instead")
    definition = ensure_task_definition(task_type, lane_key=lane_key)
    resolved_lane = lane_key or definition.default_lane
    envelope = build_task_envelope(
        task_type=task_type,
        module=module,
        owner_id=owner_id,
        lane_key=resolved_lane,
        requested_by=requested_by,
        trigger=trigger,
        body=body,
    )
    profile = {
        "cpu_cores": definition.cpu_cores,
        "rss_estimate_mb": definition.rss_estimate_mb,
        "gpu_memory_mb": definition.gpu_memory_mb,
        "cloud": definition.cloud,
        "provider_key": definition.provider_key,
        **(resource_profile or {}),
    }
    task = SystemTaskQueue(
        task_type=task_type,
        module=module,
        parameters=json.dumps(envelope, ensure_ascii=False),
        priority=int(priority),
        status="pending",
        creator_id=owner_id,
        max_retries=max(0, int(max_retries)),
        document_id=document_id,
        stage_key=stage_key,
        lane_key=resolved_lane,
        ready_status=ready_status,
        dependency_key=dependency_key,
        resource_profile=profile,
        scheduled_at=scheduled_at,
        recur=recur,
        next_run_at=next_run_at,
    )
    db.add(task)
    await db.flush()
    await db.execute(
        text("SELECT pg_notify('framework_task_dispatch', :payload)"),
        {"payload": str(task.id)},
    )
    return task


def unpack_task_parameters(raw_parameters: str | None) -> dict[str, Any]:
    """Return handler parameters, accepting durable envelopes and old rows."""
    try:
        decoded = json.loads(raw_parameters or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid parameters JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Invalid parameters JSON: root must be an object")
    body = decoded.get("body")
    if decoded.get("schema_version") == 1 and isinstance(body, dict):
        return dict(body)
    return dict(decoded)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dispatcher_config() -> DispatcherConfig:
    raw: dict[str, Any] = {}
    try:
        raw = json.loads((Path(__file__).resolve().parents[2] / "data" / "config" / "task_worker.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    dispatch = raw.get("dispatcher") if isinstance(raw.get("dispatcher"), dict) else {}

    def int_mapping(value: Any) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, int] = {}
        for key, item in value.items():
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                result[str(key)] = min(parsed, 1024)
        return result

    def number(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(dispatch.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))

    def paused_mapping(value: Any) -> dict[str, frozenset[str]]:
        if not isinstance(value, dict):
            return {}
        return {
            str(task_type): frozenset(str(item) for item in values if str(item))
            for task_type, values in value.items()
            if isinstance(values, list)
        }

    def stage_timeout_mapping(value: Any) -> dict[str, dict[str, int]]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, dict[str, int]] = {}
        for task_type, stages in value.items():
            if not isinstance(stages, dict):
                continue
            parsed_stages: dict[str, int] = {}
            for stage, seconds in stages.items():
                try:
                    parsed = int(seconds)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    parsed_stages[str(stage)] = max(30, min(parsed, 14_400))
            if parsed_stages:
                result[str(task_type)] = parsed_stages
        return result

    def env_set(name: str, *, numeric: bool = False) -> frozenset[Any] | None:
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return None
        values: set[Any] = set()
        for item in raw_value.split(","):
            candidate = item.strip()
            if not candidate:
                continue
            if numeric:
                try:
                    values.add(int(candidate))
                except ValueError:
                    logger.warning("Ignoring invalid %s item: %s", name, candidate)
            else:
                values.add(candidate)
        return frozenset(values) if values else None

    legacy_lane_limits: dict[str, int] = {}
    for value in (raw.get("lane_concurrency") or {}).values():
        for lane, limit in int_mapping(value).items():
            legacy_lane_limits[lane] = max(legacy_lane_limits.get(lane, 0), limit)
    lane_limits = int_mapping(dispatch.get("lane_limits")) or legacy_lane_limits
    paused_stages = paused_mapping(raw.get("paused_stages"))
    paused_lanes = paused_mapping(raw.get("paused_lanes"))
    return DispatcherConfig(
        idle_poll_seconds=number("idle_poll_seconds", DEFAULT_IDLE_POLL_SECONDS, 1.0, 60.0),
        active_poll_seconds=number("active_poll_seconds", DEFAULT_ACTIVE_POLL_SECONDS, 0.2, 10.0),
        lease_seconds=int(number("lease_seconds", DEFAULT_LEASE_SECONDS, 15.0, 3600.0)),
        heartbeat_seconds=number("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS, 1.0, 60.0),
        max_executors=int(number("max_executors", DEFAULT_MAX_EXECUTORS, 1.0, 256.0)),
        memory_caution_percent=number("memory_caution_percent", 80.0, 40.0, 95.0),
        memory_emergency_percent=number("memory_emergency_percent", 90.0, 50.0, 99.0),
        memory_reserve_mb=int(number("memory_reserve_mb", 1024.0, 128.0, 1024.0 * 1024.0)),
        cpu_caution_percent=number("cpu_caution_percent", 80.0, 20.0, 99.0),
        gpu_caution_percent=number("gpu_caution_percent", 80.0, 20.0, 99.0),
        gpu_emergency_percent=number("gpu_emergency_percent", 90.0, 30.0, 99.0),
        lane_limits=lane_limits,
        provider_limits=int_mapping(dispatch.get("provider_limits")),
        stage_timeouts_seconds=stage_timeout_mapping(dispatch.get("stage_timeouts_seconds")),
        reconcile_seconds=number("reconcile_seconds", 60.0, 10.0, 3600.0),
        paused_task_types=frozenset(str(item) for item in (raw.get("paused_task_types") or []) if str(item)),
        paused_stages=paused_stages,
        paused_lanes=paused_lanes,
        allowed_task_types=env_set("TASK_DISPATCHER_ALLOWED_TASK_TYPES"),
        allowed_document_ids=env_set("TASK_DISPATCHER_ALLOWED_DOCUMENT_IDS", numeric=True),
    )


def _task_is_paused(task: SystemTaskQueue, config: DispatcherConfig) -> bool:
    if task.task_type in config.paused_task_types:
        return True
    stage = str(task.stage_key or "")
    lane = str(task.lane_key or "")
    return stage in config.paused_stages.get(task.task_type, frozenset()) or lane in config.paused_lanes.get(task.task_type, frozenset())


def _task_lane(task: SystemTaskQueue) -> str:
    if task.lane_key:
        return str(task.lane_key)
    return ensure_task_definition(task.task_type).default_lane


def _task_stage(task: SystemTaskQueue) -> str:
    return str(task.stage_key or task.task_type)


def _resource_snapshot() -> dict[str, Any]:
    """整机资源:读资源底座缓存(毫秒,含GPU)。缓存无则 psutil 兜底(不卡在macmon)。"""
    try:
        from app.services.resource_monitor import 读缓存
        snap = 读缓存(默认现采=False)
        cpu = snap.get("cpu_percent")
        if cpu is not None:
            gpu_src = snap.get("gpu_source")
            return {
                "cpu_percent": float(cpu),
                "memory_percent": float(snap.get("memory_percent") or 0.0),
                "memory_available_mb": float(snap.get("memory_available_mb") or 0.0),
                "gpu_memory_percent": snap.get("gpu_ram_percent"),
                "gpu_confidence": "macmon" if gpu_src == "macmon" else "unknown",
            }
    except Exception:  # noqa: BLE001 缓存不可用退回现采
        pass
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    return {
        "cpu_percent": float(cpu_percent),
        "memory_percent": float(memory.percent),
        "memory_available_mb": round(memory.available / (1024 * 1024), 2),
        "gpu_memory_percent": None,
        "gpu_confidence": "unknown",
    }


def _task_profile(task: SystemTaskQueue) -> dict[str, Any]:
    definition = ensure_task_definition(task.task_type, lane_key=task.lane_key)
    stored = task.resource_profile if isinstance(task.resource_profile, dict) else {}
    return {
        "rss_estimate_mb": max(1, int(stored.get("rss_estimate_mb", definition.rss_estimate_mb) or definition.rss_estimate_mb)),
        "cpu_cores": max(0.0, float(stored.get("cpu_cores", definition.cpu_cores) or definition.cpu_cores)),
        "gpu_memory_mb": max(0, int(stored.get("gpu_memory_mb", definition.gpu_memory_mb) or definition.gpu_memory_mb)),
        "cloud": bool(stored.get("cloud", definition.cloud)),
        "provider_key": stored.get("provider_key") or definition.provider_key,
        "timeout_seconds": max(30, min(int(stored.get("timeout_seconds", definition.timeout_seconds) or definition.timeout_seconds), 14_400)),
    }


def _task_timeout_seconds(task: SystemTaskQueue, config: DispatcherConfig) -> int:
    stage = _task_stage(task)
    configured = config.stage_timeouts_seconds.get(task.task_type, {}).get(stage)
    if configured is not None:
        return configured
    return int(_task_profile(task)["timeout_seconds"])


async def _running_counts(db: AsyncSession) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    rows = await db.execute(
        select(SystemTaskQueue.lane_key, SystemTaskQueue.task_type, SystemTaskQueue.stage_key, func.count(SystemTaskQueue.id))
        .where(SystemTaskQueue.status == "running")
        .group_by(SystemTaskQueue.lane_key, SystemTaskQueue.task_type, SystemTaskQueue.stage_key)
    )
    by_lane: dict[str, int] = defaultdict(int)
    by_stage: dict[tuple[str, str], int] = defaultdict(int)
    for lane, task_type, stage, count in rows.all():
        lane_key = str(lane or ensure_task_definition(str(task_type)).default_lane)
        count_value = int(count or 0)
        by_lane[lane_key] += count_value
        by_stage[(str(task_type), str(stage or task_type))] += count_value
    return dict(by_lane), dict(by_stage)


async def _provider_running_counts(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(
        select(SystemTaskQueue.resource_profile)
        .where(SystemTaskQueue.status == "running")
    )
    counts: dict[str, int] = defaultdict(int)
    for (profile,) in rows.all():
        if isinstance(profile, dict) and profile.get("provider_key"):
            counts[str(profile["provider_key"])] += 1
    return dict(counts)


def _lane_capacity(
    lane: str,
    *,
    config: DispatcherConfig,
    snapshot: dict[str, Any],
) -> int:
    configured = int(config.lane_limits.get(lane, config.max_executors))
    configured = max(1, min(configured, config.max_executors))
    if snapshot["memory_percent"] >= config.memory_emergency_percent:
        return 0
    if lane in {"local_preprocess", "derived_index", "relation_build"} and snapshot["memory_percent"] >= config.memory_caution_percent:
        return 0
    return configured


def _resource_allows_task(
    task: SystemTaskQueue,
    *,
    config: DispatcherConfig,
    snapshot: dict[str, Any],
    provider_running: dict[str, int],
) -> bool:
    profile = _task_profile(task)
    if not profile["cloud"] and snapshot["cpu_percent"] >= config.cpu_caution_percent:
        return False
    estimated_available = int(snapshot["memory_available_mb"])
    if not profile["cloud"] and estimated_available < config.memory_reserve_mb + int(profile["rss_estimate_mb"]):
        return False
    gpu_percent = snapshot.get("gpu_memory_percent")
    if profile["gpu_memory_mb"]:
        # Unknown GPU telemetry is intentionally conservative: a configured
        # lane cap is still required and we do not invent a "95% accurate" read.
        if gpu_percent is not None and float(gpu_percent) >= config.gpu_caution_percent:
            return False
    provider = profile.get("provider_key")
    if provider and config.provider_limits.get(str(provider), config.max_executors) <= provider_running.get(str(provider), 0):
        return False
    return True


async def _select_dispatch_candidate(
    db: AsyncSession,
    *,
    config: DispatcherConfig,
    snapshot: dict[str, Any],
) -> SystemTaskQueue | None:
    now = _now()
    allowed_filter = (
        [SystemTaskQueue.task_type.in_(tuple(sorted(config.allowed_task_types)))]
        if config.allowed_task_types is not None
        else []
    )
    document_filter = (
        [SystemTaskQueue.document_id.in_(tuple(sorted(config.allowed_document_ids)))]
        if config.allowed_document_ids is not None
        else []
    )
    stage_rank = func.row_number().over(
        partition_by=(
            SystemTaskQueue.task_type,
            SystemTaskQueue.lane_key,
            SystemTaskQueue.stage_key,
        ),
        order_by=(SystemTaskQueue.priority.desc(), SystemTaskQueue.id),
    ).label("stage_rank")
    ranked_candidates = (
        select(SystemTaskQueue.id.label("task_id"), stage_rank)
        .where(
            SystemTaskQueue.status == "pending",
            SystemTaskQueue.ready_status.in_((None, "", "ready")),
            (SystemTaskQueue.scheduled_at.is_(None) | (SystemTaskQueue.scheduled_at <= now)),
            (SystemTaskQueue.retry_at.is_(None) | (SystemTaskQueue.retry_at <= now)),
            *allowed_filter,
            *document_filter,
        )
        .subquery("ranked_task_candidates")
    )
    candidate_ids = [
        int(task_id)
        for task_id in (
            await db.execute(
                select(ranked_candidates.c.task_id)
                .where(ranked_candidates.c.stage_rank <= 64)
                .order_by(ranked_candidates.c.task_id)
            )
        ).scalars().all()
    ]
    if not candidate_ids:
        return None
    rows = await db.execute(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.id.in_(candidate_ids),
            SystemTaskQueue.status == "pending",
        )
        .order_by(SystemTaskQueue.priority.desc(), SystemTaskQueue.id)
        .with_for_update(skip_locked=True)
    )
    from app.services.task_worker import has_task_handler

    candidates = [
        task for task in rows.scalars().all()
        if not _task_is_paused(task, config)
        and has_task_handler(task.task_type)
        and (config.allowed_task_types is None or task.task_type in config.allowed_task_types)
    ]
    if not candidates:
        return None
    running_by_lane, running_by_stage = await _running_counts(db)
    provider_running = await _provider_running_counts(db)
    backlog_by_lane_stage: dict[tuple[str, str, str], int] = defaultdict(int)
    for task in candidates:
        backlog_by_lane_stage[(task.task_type, _task_lane(task), _task_stage(task))] += 1

    scored: list[tuple[tuple[int, float, int, int], SystemTaskQueue]] = []
    for task in candidates:
        lane = _task_lane(task)
        lane_capacity = _lane_capacity(lane, config=config, snapshot=snapshot)
        if running_by_lane.get(lane, 0) >= lane_capacity:
            continue
        if not _resource_allows_task(task, config=config, snapshot=snapshot, provider_running=provider_running):
            continue
        active = [
            (task_type, stage, count)
            for (task_type, candidate_lane, stage), count in backlog_by_lane_stage.items()
            if candidate_lane == lane and count > 0
        ]
        total_backlog = sum(count for _, _, count in active)
        stage_backlog = backlog_by_lane_stage[(task.task_type, lane, _task_stage(task))]
        floor = 1 if lane_capacity >= len(active) else 0
        remaining = max(0, lane_capacity - len(active) * floor)
        target = floor + (remaining * stage_backlog / max(1, total_backlog))
        running = running_by_stage.get((task.task_type, _task_stage(task)), 0)
        deficit = target - running
        if deficit <= 0 and any(
            running_by_stage.get((candidate_type, candidate_stage), 0) < 1
            for candidate_type, candidate_stage, _ in active
        ):
            continue
        # Higher deficit first, then queue priority, then older task id.
        scored.append(((-int(deficit * 1000), -float(task.priority or 0), int(task.id), len(active)), task))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


async def claim_next_task(
    db: AsyncSession,
    *,
    owner: str,
    config: DispatcherConfig,
) -> ClaimedLease | None:
    from app.services.maintenance_service import get_maintenance_state

    maintenance = await get_maintenance_state(db)
    if maintenance.get("status") in {"draining", "restarting"} and maintenance.get("restart_requested"):
        await db.rollback()
        return None
    snapshot = _resource_snapshot()
    task = await _select_dispatch_candidate(db, config=config, snapshot=snapshot)
    if task is None:
        await db.rollback()
        return None
    lane = _task_lane(task)
    timeout_seconds = _task_timeout_seconds(task, config)
    token = uuid4().hex
    now = _now()
    expires_at = now + timedelta(seconds=config.lease_seconds)
    result = await db.execute(
        update(SystemTaskQueue)
        .where(SystemTaskQueue.id == task.id, SystemTaskQueue.status == "pending")
        .values(
            status="running",
            lane_key=lane,
            started_at=now,
            completed_at=None,
            error_message=None,
            result=None,
            lease_token=token,
            lease_owner=owner,
            lease_expires_at=expires_at,
            heartbeat_at=now,
            executor_pid=None,
            attempt=SystemTaskQueue.attempt + 1,
        )
        .returning(
            SystemTaskQueue.id,
            SystemTaskQueue.task_type,
            SystemTaskQueue.lane_key,
            SystemTaskQueue.stage_key,
            SystemTaskQueue.attempt,
        )
    )
    claimed = result.one_or_none()
    if claimed is None:
        await db.rollback()
        return None
    await db.commit()
    return ClaimedLease(
        task_id=int(claimed.id),
        lease_token=token,
        task_type=str(claimed.task_type),
        lane_key=str(claimed.lane_key or lane),
        stage_key=str(claimed.stage_key or claimed.task_type),
        attempt=int(claimed.attempt),
        timeout_seconds=timeout_seconds,
    )


async def _renew_lease(db: AsyncSession, state: ExecutorState, config: DispatcherConfig) -> bool:
    now = _now()
    result = await db.execute(
        update(SystemTaskQueue)
        .where(
            SystemTaskQueue.id == state.claim.task_id,
            SystemTaskQueue.status == "running",
            SystemTaskQueue.lease_token == state.claim.lease_token,
        )
        .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=config.lease_seconds))
    )
    await db.commit()
    if int(result.rowcount or 0) == 1:
        state.last_heartbeat = now
        return True
    return False


def _process_observation(pid: int) -> tuple[float | None, float | None, tuple[int, int] | None]:
    try:
        process = psutil.Process(pid)
        memory = process.memory_info().rss / (1024 * 1024)
        cpu = sum(process.cpu_times()[:2])
        io_counters = getattr(process, "io_counters", None)
        io = io_counters() if callable(io_counters) else None
        io_values = (int(io.read_bytes), int(io.write_bytes)) if io is not None else None
        return float(memory), float(cpu), io_values
    except (psutil.Error, OSError, AttributeError):
        return None, None, None


async def _record_attempt_metric(
    db: AsyncSession,
    state: ExecutorState,
    *,
    status: str,
    exit_code: int | None,
) -> None:
    existing = await db.scalar(
        select(TaskAttemptMetric.id).where(
            TaskAttemptMetric.task_id == state.claim.task_id,
            TaskAttemptMetric.attempt == state.claim.attempt,
            TaskAttemptMetric.lease_token == state.claim.lease_token,
        )
    )
    if existing is not None:
        return
    rss_end, cpu_end, io_end = _process_observation(state.process.pid)
    rss_peak = state.rss_peak_mb
    if rss_end is not None:
        rss_peak = max(rss_peak or 0.0, rss_end)
    duration_ms = round((perf_counter() - state.started_perf) * 1000)
    cpu_seconds = None
    if state.cpu_start_seconds is not None and cpu_end is not None:
        cpu_seconds = max(0.0, cpu_end - state.cpu_start_seconds)
    read_bytes = write_bytes = None
    if state.io_start is not None and io_end is not None:
        read_bytes = max(0, io_end[0] - state.io_start[0])
        write_bytes = max(0, io_end[1] - state.io_start[1])
    db.add(TaskAttemptMetric(
        task_id=state.claim.task_id,
        attempt=state.claim.attempt,
        lease_token=state.claim.lease_token,
        task_type=state.claim.task_type,
        stage_key=state.claim.stage_key,
        lane_key=state.claim.lane_key,
        executor_pid=state.process.pid,
        exit_code=exit_code,
        status=status,
        started_at=state.started_at,
        completed_at=_now(),
        duration_ms=duration_ms,
        cpu_seconds=cpu_seconds,
        rss_start_mb=state.rss_start_mb,
        rss_peak_mb=rss_peak,
        rss_end_mb=rss_end,
        io_read_bytes=read_bytes,
        io_write_bytes=write_bytes,
        observation_confidence="process",
        metrics_json={"gpu_confidence": "unknown"},
    ))


async def _mark_executor_exit(db: AsyncSession, state: ExecutorState, exit_code: int | None) -> None:
    now = _now()
    error = f"Executor process exited before fenced completion (exit_code={exit_code})"
    result = await db.execute(
        update(SystemTaskQueue)
        .where(
            SystemTaskQueue.id == state.claim.task_id,
            SystemTaskQueue.status == "running",
            SystemTaskQueue.lease_token == state.claim.lease_token,
        )
        .values(
            status="pending",
            retry_count=SystemTaskQueue.retry_count + 1,
            retry_at=now + timedelta(seconds=5),
            started_at=None,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            executor_pid=None,
            failure_class="resource" if exit_code not in (0, None) else "internal",
            error_message=error,
        )
    )
    if int(result.rowcount or 0) == 1:
        metric_status = "executor_exit"
    else:
        final_status = await db.scalar(select(SystemTaskQueue.status).where(SystemTaskQueue.id == state.claim.task_id))
        metric_status = str(final_status or "fenced")
    await _record_attempt_metric(db, state, status=metric_status, exit_code=exit_code)
    await db.commit()


async def recover_expired_leases(db: AsyncSession) -> int:
    now = _now()
    rows = await db.execute(
        select(SystemTaskQueue)
        .where(
            SystemTaskQueue.status == "running",
            (
                SystemTaskQueue.lease_expires_at.is_(None)
                | (SystemTaskQueue.lease_expires_at < now)
            ),
        )
        .with_for_update(skip_locked=True)
    )
    recovered = 0
    for task in rows.scalars().all():
        next_retry = int(task.retry_count or 0) + 1
        terminal = next_retry >= int(task.max_retries or 3)
        task.retry_count = next_retry
        task.failure_class = "timeout"
        task.error_message = "Dispatcher lease expired; task released for retry"
        task.lease_token = None
        task.lease_owner = None
        task.lease_expires_at = None
        task.heartbeat_at = None
        task.executor_pid = None
        if terminal:
            task.status = "failed"
            task.completed_at = now
        else:
            task.status = "pending"
            task.started_at = None
            task.retry_at = now + timedelta(seconds=5)
        recovered += 1
    if recovered:
        await db.commit()
    else:
        await db.rollback()
    return recovered


async def release_running_lease_for_shutdown(
    db: AsyncSession,
    *,
    task_id: int,
    lease_token: str,
) -> bool:
    """Return a fenced running task to pending without consuming retry budget."""
    result = await db.execute(
        update(SystemTaskQueue)
        .where(
            SystemTaskQueue.id == int(task_id),
            SystemTaskQueue.status == "running",
            SystemTaskQueue.lease_token == lease_token,
        )
        .values(
            status="pending",
            retry_at=_now(),
            started_at=None,
            completed_at=None,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            executor_pid=None,
            failure_class=None,
            error_message=None,
            blocked_reason="dispatcher_shutdown_requeue",
        )
    )
    return int(result.rowcount or 0) == 1


async def execute_claimed_task(task_id: int, lease_token: str) -> int:
    """Run one leased handler inside the disposable executor process."""
    from app.services import task_worker

    async with AsyncSessionLocal() as db:
        task = await db.scalar(
            select(SystemTaskQueue).where(
                SystemTaskQueue.id == task_id,
                SystemTaskQueue.status == "running",
                SystemTaskQueue.lease_token == lease_token,
            )
        )
        if task is None:
            return 2
        task.executor_pid = os.getpid()
        await db.commit()
        ok, result, error = await task_worker._run_handler(task)
        now = _now()
        settlement = _settlement_handlers.get(task.task_type)
        if ok and settlement is not None:
            try:
                await settlement(db, task, result or {})
            except Exception:
                logger.exception("Task settlement callback failed task_id=%d type=%s", task_id, task.task_type)
                await db.rollback()
                return 4
        if ok:
            values: dict[str, Any] = {
                "status": "completed",
                "result": json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                "error_message": None,
                "completed_at": now,
                "lease_expires_at": None,
                "heartbeat_at": now,
                "executor_pid": os.getpid(),
                "lease_token": None,
                "lease_owner": None,
            }
            outcome = "completed"
        else:
            retry_count = int(task.retry_count or 0) + 1
            terminal = retry_count >= int(task.max_retries or 3)
            values = {
                "status": "failed" if terminal else "pending",
                "retry_count": retry_count,
                "retry_at": None if terminal else now + timedelta(seconds=5),
                "started_at": None if not terminal else task.started_at,
                "completed_at": now if terminal else None,
                "error_message": error,
                "failure_class": "internal",
                "lease_expires_at": None,
                "heartbeat_at": None,
                "executor_pid": None,
                "lease_token": None,
                "lease_owner": None,
            }
            outcome = "failed" if terminal else "retrying"
        update_result = await db.execute(
            update(SystemTaskQueue)
            .where(
                SystemTaskQueue.id == task_id,
                SystemTaskQueue.status == "running",
                SystemTaskQueue.lease_token == lease_token,
            )
            .values(**values)
        )
        if int(update_result.rowcount or 0) != 1:
            await db.rollback()
            return 3
        await append_event_in_transaction(
            db,
            event_name="task.settled",
            payload={"task_id": task_id, "task_type": task.task_type, "outcome": outcome},
            caller="system:task-dispatcher",
            caller_role="admin",
            dedup_key=f"task-settled:{task_id}:{lease_token}",
        )
        await db.commit()
    return 0 if ok else 1


class TaskDispatcher:
    def __init__(self, config_override: DispatcherConfig | None = None) -> None:
        self.owner = f"dispatcher:{os.getpid()}:{uuid4().hex[:12]}"
        self._leader_connection = None
        self._last_reconcile_at: datetime | None = None
        self._config_override = config_override

    async def run(self) -> None:
        global _dispatcher_is_leader
        self._leader_connection = await engine.connect()
        try:
            acquired = await self._leader_connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": DISPATCHER_LEADER_LOCK_KEY},
            )
            await self._leader_connection.commit()
            if not acquired:
                return
            _dispatcher_is_leader = True
            while not _dispatcher_stop:
                config = self._config_override or _dispatcher_config()
                await self._tick(config)
                delay = config.active_poll_seconds if _active_executors else config.idle_poll_seconds
                await asyncio.sleep(delay)
        finally:
            _dispatcher_is_leader = False
            if self._leader_connection is not None:
                try:
                    await self._leader_connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": DISPATCHER_LEADER_LOCK_KEY},
                    )
                    await self._leader_connection.commit()
                finally:
                    await self._leader_connection.close()

    async def _tick(self, config: DispatcherConfig) -> None:
        await self._reap_and_heartbeat(config)
        async with AsyncSessionLocal() as db:
            await recover_expired_leases(db)
        if self._last_reconcile_at is None or (_now() - self._last_reconcile_at).total_seconds() >= config.reconcile_seconds:
            await self._run_reconcilers()
            self._last_reconcile_at = _now()
        while len(_active_executors) < config.max_executors and not _dispatcher_stop:
            async with AsyncSessionLocal() as db:
                claim = await claim_next_task(db, owner=self.owner, config=config)
            if claim is None:
                break
            await self._spawn_executor(claim)

    async def _run_reconcilers(self) -> None:
        for name, reconciler in _reconcilers.items():
            try:
                async with AsyncSessionLocal() as db:
                    await reconciler(db)
                    await db.commit()
            except Exception:
                logger.exception("Dispatcher reconciler failed: %s", name)

    async def _spawn_executor(self, claim: ClaimedLease) -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.task_worker_main",
            "--executor-task-id",
            str(claim.task_id),
            "--lease-token",
            claim.lease_token,
            cwd=str(Path(__file__).resolve().parents[2]),
            start_new_session=True,
        )
        rss, cpu, io = _process_observation(process.pid)
        now = _now()
        state = ExecutorState(
            claim=claim,
            process=process,
            started_at=now,
            started_perf=perf_counter(),
            rss_start_mb=rss,
            rss_peak_mb=rss,
            cpu_start_seconds=cpu,
            io_start=io,
            last_heartbeat=now,
        )
        _active_executors[claim.task_id] = state
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(SystemTaskQueue)
                .where(
                    SystemTaskQueue.id == claim.task_id,
                    SystemTaskQueue.lease_token == claim.lease_token,
                )
                .values(executor_pid=process.pid)
            )
            await db.commit()
        reg = await 注册进程(
            label=f"queue-{claim.task_type}-{claim.stage_key}",
            pid=process.pid,
            kind="queue",
            source="task_dispatcher",
            ref_id=claim.task_id,
            command="app.task_worker_main --executor-task-id",
        )
        state.reg_id = reg.get("reg_id") if reg else None

    async def _reap_and_heartbeat(self, config: DispatcherConfig) -> None:
        now = _now()
        for task_id, state in list(_active_executors.items()):
            rss, _, _ = _process_observation(state.process.pid)
            if rss is not None:
                state.rss_peak_mb = max(state.rss_peak_mb or 0.0, rss)
            return_code = state.process.returncode
            if return_code is not None:
                async with AsyncSessionLocal() as db:
                    await _mark_executor_exit(db, state, return_code)
                await 注销进程(reg_id=state.reg_id, pid=state.process.pid, exit_code=return_code)
                _active_executors.pop(task_id, None)
                continue
            if (now - state.started_at).total_seconds() >= state.claim.timeout_seconds:
                logger.error(
                    "Executor exceeded task timeout task_id=%d type=%s timeout=%ds",
                    task_id,
                    state.claim.task_type,
                    state.claim.timeout_seconds,
                )
                await self._terminate_executor(state)
                async with AsyncSessionLocal() as db:
                    await _mark_executor_exit(db, state, 124)
                await 注销进程(reg_id=state.reg_id, pid=state.process.pid, status="killed", exit_code=124)
                _active_executors.pop(task_id, None)
                continue
            if (now - state.last_heartbeat).total_seconds() >= config.heartbeat_seconds:
                async with AsyncSessionLocal() as db:
                    task = await db.get(SystemTaskQueue, state.claim.task_id)
                    paused = task is not None and _task_is_paused(task, config)
                    renewed = False if paused else await _renew_lease(db, state, config)
                    if paused:
                        await db.execute(
                            update(SystemTaskQueue)
                            .where(
                                SystemTaskQueue.id == state.claim.task_id,
                                SystemTaskQueue.status == "running",
                                SystemTaskQueue.lease_token == state.claim.lease_token,
                            )
                            .values(
                                status="pending",
                                started_at=None,
                                retry_at=None,
                                blocked_reason="paused_by_config",
                                lease_token=None,
                                lease_owner=None,
                                lease_expires_at=None,
                                heartbeat_at=None,
                                executor_pid=None,
                            )
                        )
                        await db.commit()
                if not renewed:
                    await self._terminate_executor(state)
                    await 注销进程(reg_id=state.reg_id, pid=state.process.pid, status="killed")
                    _active_executors.pop(task_id, None)

    async def _terminate_executor(self, state: ExecutorState) -> None:
        try:
            os.killpg(state.process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
        try:
            await asyncio.wait_for(state.process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            try:
                os.killpg(state.process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass


def start_dispatcher() -> None:
    global _dispatcher_task, _dispatcher_stop
    if _dispatcher_task is not None and not _dispatcher_task.done():
        return
    _dispatcher_stop = False
    _dispatcher_task = asyncio.create_task(TaskDispatcher().run())


async def stop_dispatcher() -> None:
    global _dispatcher_stop
    _dispatcher_stop = True
    if _dispatcher_task is not None:
        try:
            await asyncio.wait_for(_dispatcher_task, timeout=10.0)
        except asyncio.TimeoutError:
            _dispatcher_task.cancel()
            await asyncio.gather(_dispatcher_task, return_exceptions=True)
    dispatcher = TaskDispatcher()
    states = list(_active_executors.values())
    await asyncio.gather(
        *(dispatcher._terminate_executor(state) for state in states),
        return_exceptions=True,
    )
    if states:
        async with AsyncSessionLocal() as db:
            for state in states:
                released = await release_running_lease_for_shutdown(
                    db,
                    task_id=state.claim.task_id,
                    lease_token=state.claim.lease_token,
                )
                await _record_attempt_metric(
                    db,
                    state,
                    status="shutdown_requeue" if released else "fenced",
                    exit_code=state.process.returncode,
                )
                await 注销进程(reg_id=state.reg_id, pid=state.process.pid, status="killed",
                             exit_code=state.process.returncode)
            await db.commit()
    _active_executors.clear()


def dispatcher_health() -> dict[str, Any]:
    return {
        "running": _dispatcher_task is not None and not _dispatcher_task.done(),
        "is_leader": _dispatcher_is_leader,
        "owner": None if not _dispatcher_is_leader else f"dispatcher:{os.getpid()}",
        "active_executors": [
            {
                "task_id": state.claim.task_id,
                "task_type": state.claim.task_type,
                "pid": state.process.pid,
                "attempt": state.claim.attempt,
                "rss_peak_mb": state.rss_peak_mb,
            }
            for state in _active_executors.values()
        ],
        "definitions": sorted(_definitions),
        "resource": _resource_snapshot(),
    }
