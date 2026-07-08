"""Framework-level background task worker.

Consumes SystemTaskQueue (framework_system_task_queues). Concurrency-safe via
FOR UPDATE SKIP LOCKED. Modules register handlers by task_type.
"""
import asyncio
import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

from sqlalchemy import and_, func, not_, or_, select, text, update

from app.database import AsyncSessionLocal, engine
from app.models.system import SystemTaskQueue
from app.services.module_registry import semantic_failure_reason

logger = logging.getLogger("v2.task_worker")

POLL_INTERVAL_SECONDS = 2.0
RUNNING_TIMEOUT_SECONDS = 1200  # running 超过 20 分钟视为死任务，回收重排
CONFIG_RELOAD_SECONDS = 5.0
DEFAULT_MAX_LANES_PER_PROCESS = 16
ABSOLUTE_MAX_LANES_PER_PROCESS = 256
CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "task_worker.json"
WORKER_LEADER_LOCK_KEY = 94022025
WORKER_CLAIM_LOCK_KEY = 94022026
WORKER_PROCESS_SLOT_LOCK_BASE = 94022100
WORKER_STAGE_CLAIM_LOCK_BASE = 94022200


@dataclass(frozen=True)
class StageConcurrencyRule:
    stage_max_running: dict[str, int] | None = None


@dataclass(frozen=True)
class ClaimedTask:
    id: int
    task_type: str
    parameters: str | None = None
    document_id: int | None = None
    stage_key: str | None = None
    lane_key: str | None = None
    dependency_key: str | None = None


@dataclass(frozen=True)
class _ClaimCandidate:
    id: int
    task_type: str
    stage_key: str
    lane_key: str
    priority: int
    created_at: datetime | None
    running_count: int
    running_limit: int
    lane_running_count: int = 0
    lane_running_limit: int = 0
    dispatch_rank: int = 1_000_000


@dataclass(frozen=True)
class WorkerConfig:
    worker_lanes_per_process: int = 1
    max_lanes_per_process: int = DEFAULT_MAX_LANES_PER_PROCESS
    worker_process_mode: str = "leader"
    worker_process_slots: int = 1
    claim_lock_scope: str = "process"
    claim_candidate_scan_limit: int = 100
    serialize_claims: bool = True
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS
    running_timeout_seconds: int = RUNNING_TIMEOUT_SECONDS
    stale_recovery_interval_seconds: float = 10.0
    config_reload_seconds: float = CONFIG_RELOAD_SECONDS
    reclaim_running_on_startup: bool = False
    startup_reclaim_min_age_seconds: int = 10
    stage_concurrency: dict[str, StageConcurrencyRule] | None = None
    lane_concurrency: dict[str, dict[str, int]] | None = None
    stage_dispatch_order: dict[str, dict[str, int]] | None = None
    paused_task_types: set[str] | None = None
    paused_stages: dict[str, set[str]] | None = None
    paused_lanes: dict[str, set[str]] | None = None

# task_type -> async handler(parameters: dict) -> dict | None
TaskHandler = Callable[[dict], Awaitable[dict | None]]
_HANDLERS: dict[str, TaskHandler] = {}

_worker_task: asyncio.Task | None = None
_lane_tasks: dict[int, asyncio.Task] = {}
_lane_current_task_ids: dict[int, int] = {}
_retiring_lane_ids: set[int] = set()
_next_lane_id = 1
_stop_flag = False
_last_active: datetime | None = None
_runtime_config = WorkerConfig()
_config_mtime: float | None = None
_worker_is_leader = False
_claim_lock = asyncio.Lock()
_stale_recovery_lock = asyncio.Lock()
_last_stale_recovery_at: datetime | None = None


def register_task_handler(task_type: str, handler: TaskHandler) -> None:
    """模块调用此函数注册自己的任务处理器。"""
    _HANDLERS[task_type] = handler
    logger.info("Registered task handler: %s", task_type)


def has_task_handler(task_type: str) -> bool:
    return task_type in _HANDLERS


async def _echo_handler(parameters: dict) -> dict:
    """内置自检处理器，用于验证 worker 链路。"""
    return {"echo": parameters}


_HANDLERS["_echo"] = _echo_handler


def _clamp_int(value: object, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _clamp_float(value: object, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _coerce_choice(value: object, default: str, choices: set[str]) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in choices:
            return lowered
    return default


def _parse_stage_concurrency(raw: object) -> dict[str, StageConcurrencyRule]:
    if not isinstance(raw, dict):
        return {}
    rules: dict[str, StageConcurrencyRule] = {}
    for task_type, rule_raw in raw.items():
        task_type_key = str(task_type or "").strip()
        if not task_type_key or not isinstance(rule_raw, dict):
            continue
        stage_limits: dict[str, int] = {}
        for stage, limit in rule_raw.items():
            stage_key = str(stage or "").strip()
            if not stage_key:
                continue
            parsed_limit = _clamp_int(limit, 0, 0, ABSOLUTE_MAX_LANES_PER_PROCESS)
            if parsed_limit > 0:
                stage_limits[stage_key] = parsed_limit
        if stage_limits:
            rules[task_type_key] = StageConcurrencyRule(stage_max_running=stage_limits)
    return rules


def _parse_lane_concurrency(raw: object) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict):
        return {}
    rules: dict[str, dict[str, int]] = {}
    for task_type, rule_raw in raw.items():
        task_type_key = str(task_type or "").strip()
        if not task_type_key or not isinstance(rule_raw, dict):
            continue
        lane_limits: dict[str, int] = {}
        for lane, limit in rule_raw.items():
            lane_key = str(lane or "").strip()
            if not lane_key:
                continue
            parsed_limit = _clamp_int(limit, 0, 0, ABSOLUTE_MAX_LANES_PER_PROCESS)
            if parsed_limit > 0:
                lane_limits[lane_key] = parsed_limit
        if lane_limits:
            rules[task_type_key] = lane_limits
    return rules


def _parse_stage_dispatch_order(raw: object) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict):
        return {}
    rules: dict[str, dict[str, int]] = {}
    for task_type, rule_raw in raw.items():
        task_type_key = str(task_type or "").strip()
        if not task_type_key:
            continue
        order: dict[str, int] = {}
        if isinstance(rule_raw, list):
            for idx, stage in enumerate(rule_raw):
                stage_key = str(stage or "").strip()
                if stage_key:
                    order[stage_key] = idx
        elif isinstance(rule_raw, dict):
            for stage, rank in rule_raw.items():
                stage_key = str(stage or "").strip()
                if not stage_key:
                    continue
                order[stage_key] = _clamp_int(rank, 1_000_000, 0, 1_000_000)
        if order:
            rules[task_type_key] = order
    return rules


def _parse_paused_task_types(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {str(item or "").strip() for item in raw if str(item or "").strip()}


def _parse_paused_dimension(raw: object) -> dict[str, set[str]]:
    if not isinstance(raw, dict):
        return {}
    rules: dict[str, set[str]] = {}
    for task_type, values in raw.items():
        task_type_key = str(task_type or "").strip()
        if not task_type_key:
            continue
        if isinstance(values, list):
            parsed = {str(item or "").strip() for item in values if str(item or "").strip()}
        else:
            parsed = {str(values or "").strip()} if str(values or "").strip() else set()
        if parsed:
            rules[task_type_key] = parsed
    return rules


def _parse_worker_config(raw: dict | None) -> WorkerConfig:
    raw = raw or {}
    max_lanes_per_process = _clamp_int(
        raw.get("max_lanes_per_process"),
        WorkerConfig.max_lanes_per_process,
        1,
        ABSOLUTE_MAX_LANES_PER_PROCESS,
    )
    serialize_claims = _coerce_bool(
        raw.get("serialize_claims"),
        WorkerConfig.serialize_claims,
    )
    claim_lock_scope = _coerce_choice(
        raw.get("claim_lock_scope"),
        "process" if serialize_claims else "none",
        {"none", "process", "database"},
    )
    return WorkerConfig(
        worker_lanes_per_process=_clamp_int(
            raw.get("worker_lanes_per_process"),
            WorkerConfig.worker_lanes_per_process,
            0,
            max_lanes_per_process,
        ),
        max_lanes_per_process=max_lanes_per_process,
        worker_process_mode=_coerce_choice(
            raw.get("worker_process_mode"),
            WorkerConfig.worker_process_mode,
            {"leader", "all"},
        ),
        worker_process_slots=_clamp_int(
            raw.get("worker_process_slots"),
            WorkerConfig.worker_process_slots,
            1,
            64,
        ),
        claim_lock_scope=claim_lock_scope,
        claim_candidate_scan_limit=_clamp_int(
            raw.get("claim_candidate_scan_limit"),
            WorkerConfig.claim_candidate_scan_limit,
            1,
            5000,
        ),
        serialize_claims=serialize_claims,
        poll_interval_seconds=_clamp_float(
            raw.get("poll_interval_seconds"),
            WorkerConfig.poll_interval_seconds,
            0.2,
            60.0,
        ),
        running_timeout_seconds=_clamp_int(
            raw.get("running_timeout_seconds"),
            WorkerConfig.running_timeout_seconds,
            60,
            24 * 60 * 60,
        ),
        stale_recovery_interval_seconds=_clamp_float(
            raw.get("stale_recovery_interval_seconds"),
            WorkerConfig.stale_recovery_interval_seconds,
            1.0,
            300.0,
        ),
        config_reload_seconds=_clamp_float(
            raw.get("config_reload_seconds"),
            WorkerConfig.config_reload_seconds,
            1.0,
            300.0,
        ),
        reclaim_running_on_startup=_coerce_bool(
            raw.get("reclaim_running_on_startup"),
            WorkerConfig.reclaim_running_on_startup,
        ),
        startup_reclaim_min_age_seconds=_clamp_int(
            raw.get("startup_reclaim_min_age_seconds"),
            WorkerConfig.startup_reclaim_min_age_seconds,
            0,
            3600,
        ),
        stage_concurrency=_parse_stage_concurrency(raw.get("stage_concurrency")),
        lane_concurrency=_parse_lane_concurrency(raw.get("lane_concurrency")),
        stage_dispatch_order=_parse_stage_dispatch_order(raw.get("stage_dispatch_order")),
        paused_task_types=_parse_paused_task_types(raw.get("paused_task_types")),
        paused_stages=_parse_paused_dimension(raw.get("paused_stages")),
        paused_lanes=_parse_paused_dimension(raw.get("paused_lanes")),
    )


def _load_worker_config(force: bool = False) -> WorkerConfig:
    global _config_mtime, _runtime_config
    try:
        stat = CONFIG_PATH.stat()
    except FileNotFoundError:
        if force:
            _runtime_config = WorkerConfig()
        return _runtime_config
    except OSError as exc:
        logger.warning("Task worker config stat failed: %s", exc)
        return _runtime_config

    if not force and _config_mtime == stat.st_mtime:
        return _runtime_config

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root must be an object")
    except Exception as exc:
        logger.warning("Task worker config load failed: %s", exc)
        return _runtime_config

    next_config = _parse_worker_config(raw)
    if next_config != _runtime_config:
        logger.info("Task worker config loaded: %s", next_config)
    _runtime_config = next_config
    _config_mtime = stat.st_mtime
    return _runtime_config


async def _reconcile_one_orphan(task: SystemTaskQueue, now: datetime) -> None:
    """Increment retry_count on an orphan task and fail it if over limit."""
    task.retry_count = (task.retry_count or 0) + 1
    if task.retry_count >= (task.max_retries or 3):
        task.status = "failed"
        task.error_message = "Orphan task exceeded max retries on startup recovery"
        task.completed_at = now
    else:
        task.status = "pending"
        task.started_at = None


async def _recover_stale_tasks(db, running_timeout_seconds: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    timeout = running_timeout_seconds or _runtime_config.running_timeout_seconds
    cutoff = now - timedelta(seconds=timeout)

    # Phase 1: timeout-reclaim — running tasks older than cutoff
    result = await db.execute(
        select(SystemTaskQueue)
        .where(SystemTaskQueue.status == "running", SystemTaskQueue.started_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    stale = list(result.scalars().all())
    reclaimed_count = 0
    for task in stale:
        retry_count = (task.retry_count or 0) + 1
        if retry_count >= (task.max_retries or 3):
            values = {
                "retry_count": retry_count,
                "status": "failed",
                "error_message": "Task timed out and exceeded max retries",
                "completed_at": now,
            }
        else:
            values = {
                "retry_count": retry_count,
                "status": "pending",
                "started_at": None,
            }
        update_result = await db.execute(
            update(SystemTaskQueue)
            .where(
                SystemTaskQueue.id == task.id,
                SystemTaskQueue.status == "running",
                SystemTaskQueue.started_at == task.started_at,
            )
            .values(**values)
        )
        reclaimed_count += int(update_result.rowcount or 0)
    if reclaimed_count:
        logger.info("Timeout recovery: reclaimed %d stale tasks", reclaimed_count)
    await db.commit()


async def _recover_stale_tasks_if_due(db, config: WorkerConfig) -> None:
    """Run stale-task recovery at most once per configured interval per process."""
    global _last_stale_recovery_at
    now = datetime.now(timezone.utc)
    interval = max(1.0, float(config.stale_recovery_interval_seconds or 1.0))
    if _last_stale_recovery_at is not None:
        if (now - _last_stale_recovery_at).total_seconds() < interval:
            return

    async with _stale_recovery_lock:
        now = datetime.now(timezone.utc)
        if _last_stale_recovery_at is not None:
            if (now - _last_stale_recovery_at).total_seconds() < interval:
                return
        await _recover_stale_tasks(db, config.running_timeout_seconds)
        _last_stale_recovery_at = now


async def _recover_orphan_running_tasks() -> None:
    """Startup recovery: reclaim only timed-out running tasks.

    In multi-worker deployments another worker may legitimately be executing a
    fresh ``running`` task while this worker starts. Treating every running task
    as orphaned causes duplicate retries, so startup recovery uses the same
    timeout + row-lock path as periodic stale recovery.
    """
    try:
        async with AsyncSessionLocal() as db:
            await _recover_stale_tasks(db, _runtime_config.running_timeout_seconds)
    except Exception as exc:
        logger.error("Orphan recovery failed: %s", exc)


async def _acquire_worker_leader_connection():
    conn = await engine.connect()
    try:
        result = await conn.execute(
            text("select pg_try_advisory_lock(:lock_key)"),
            {"lock_key": WORKER_LEADER_LOCK_KEY},
        )
        acquired = bool(result.scalar())
        await conn.commit()
        if acquired:
            return conn
        await conn.close()
        return None
    except Exception as exc:
        logger.warning("Task worker leader lock acquire failed: %s", exc)
        await conn.close()
        return None


async def _release_worker_leader_connection(conn) -> None:
    try:
        await conn.execute(
            text("select pg_advisory_unlock(:lock_key)"),
            {"lock_key": WORKER_LEADER_LOCK_KEY},
        )
        await conn.commit()
    except Exception as exc:
        logger.warning("Task worker leader lock release failed: %s", exc)
    finally:
        await conn.close()


async def _acquire_worker_slot_connection(slot_count: int):
    slot_count = max(1, int(slot_count or 1))
    for slot_id in range(slot_count):
        conn = await engine.connect()
        try:
            lock_key = WORKER_PROCESS_SLOT_LOCK_BASE + slot_id
            result = await conn.execute(
                text("select pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            acquired = bool(result.scalar())
            await conn.commit()
            if acquired:
                return conn, slot_id
            await conn.close()
        except Exception as exc:
            logger.warning("Task worker process slot acquire failed: %s", exc)
            await conn.close()
    return None, None


async def _release_worker_slot_connection(conn, slot_id: int | None) -> None:
    try:
        lock_key = WORKER_PROCESS_SLOT_LOCK_BASE + int(slot_id or 0)
        await conn.execute(
            text("select pg_advisory_unlock(:lock_key)"),
            {"lock_key": lock_key},
        )
        await conn.commit()
    except Exception as exc:
        logger.warning("Task worker process slot release failed: %s", exc)
    finally:
        await conn.close()


async def _reclaim_running_tasks_on_startup(min_age_seconds: int = 10) -> None:
    """Release DB-running tasks when this deployment restarts as a single owner.

    This is intentionally config-gated. The default timeout recovery is safer
    for multi-instance deployments; local enterprise imports prefer immediate
    restart recovery because the queue is DB-persisted and the watchdog restarts
    the only backend owner.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(0, int(min_age_seconds or 0)))
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(SystemTaskQueue)
                .where(
                    SystemTaskQueue.status == "running",
                    SystemTaskQueue.started_at < cutoff,
                )
                .values(
                    status="pending",
                    started_at=None,
                    error_message="Task reclaimed on worker startup; released for retry",
                    updated_at=now,
                )
            )
            await db.commit()
            reclaimed = int(result.rowcount or 0)
            if reclaimed:
                logger.info(
                    "Startup recovery: reclaimed %d running task(s) older than %ss",
                    reclaimed,
                    min_age_seconds,
                )
    except Exception as exc:
        logger.error("Startup running-task reclaim failed: %s", exc)


def _result_is_semantic_failure(result: dict | None) -> tuple[bool, str | None]:
    """Return whether a handler result is a business failure contract."""
    reason = semantic_failure_reason(result)
    return reason is not None, reason


def _task_stage_key(task: SystemTaskQueue) -> str:
    return str(task.stage_key or "").strip()


def _task_lane_key(task: SystemTaskQueue) -> str:
    return str(task.lane_key or "").strip()


def _stage_running_counts(
    running_tasks: list[SystemTaskQueue],
    rules: dict[str, StageConcurrencyRule],
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for task in running_tasks:
        task_type = str(task.task_type or "")
        rule = rules.get(task_type)
        if rule is None:
            continue
        stage_key = _task_stage_key(task)
        if stage_key:
            counts[(task_type, stage_key)] = counts.get((task_type, stage_key), 0) + 1
    return counts


def _lane_running_counts(
    running_tasks: list[SystemTaskQueue],
    rules: dict[str, dict[str, int]],
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for task in running_tasks:
        task_type = str(task.task_type or "")
        rule = rules.get(task_type)
        if rule is None:
            continue
        lane_key = _task_lane_key(task)
        if lane_key:
            counts[(task_type, lane_key)] = counts.get((task_type, lane_key), 0) + 1
    return counts


@asynccontextmanager
async def _claim_gate(db, config: WorkerConfig):
    if config.claim_lock_scope in {"process", "database"}:
        async with _claim_lock:
            if config.claim_lock_scope == "database":
                await db.execute(
                    text("select pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": WORKER_CLAIM_LOCK_KEY},
                )
            yield
        return
    yield


def _stage_allowed_by_stage_concurrency(
    task_type: str,
    stage_key: str,
    *,
    running_counts: dict[tuple[str, str], int],
    config: WorkerConfig,
) -> bool:
    rules = config.stage_concurrency or {}
    rule = rules.get(str(task_type or ""))
    if rule is None:
        return True

    stage_limits = rule.stage_max_running or {}
    limit = stage_limits.get(stage_key)
    if limit is None:
        return False
    return running_counts.get((task_type, stage_key), 0) < limit


def _task_allowed_by_stage_concurrency(
    task: SystemTaskQueue,
    *,
    running_counts: dict[tuple[str, str], int],
    config: WorkerConfig,
) -> bool:
    return _stage_allowed_by_stage_concurrency(
        str(task.task_type or ""),
        _task_stage_key(task),
        running_counts=running_counts,
        config=config,
    )


def _lane_allowed_by_lane_concurrency(
    task_type: str,
    lane_key: str,
    *,
    lane_running_counts: dict[tuple[str, str], int],
    config: WorkerConfig,
) -> bool:
    rules = config.lane_concurrency or {}
    task_rules = rules.get(str(task_type or ""))
    if task_rules is None:
        return True
    limit = task_rules.get(lane_key)
    if limit is None:
        return False
    return lane_running_counts.get((task_type, lane_key), 0) < limit


def _task_allowed_by_lane_concurrency(
    task: SystemTaskQueue,
    *,
    lane_running_counts: dict[tuple[str, str], int],
    config: WorkerConfig,
) -> bool:
    return _lane_allowed_by_lane_concurrency(
        str(task.task_type or ""),
        _task_lane_key(task),
        lane_running_counts=lane_running_counts,
        config=config,
    )


def _concurrency_sql_filters(
    *,
    rules: dict[str, StageConcurrencyRule],
    running_counts: dict[tuple[str, str], int],
) -> list:
    filters = []
    for task_type, rule in rules.items():
        stage_limits = rule.stage_max_running or {}
        if not stage_limits:
            continue
        allowed_stages = tuple(stage_limits.keys())
        filters.append(
            not_(
                and_(
                    SystemTaskQueue.task_type == task_type,
                    or_(
                        SystemTaskQueue.stage_key.is_(None),
                        SystemTaskQueue.stage_key.not_in(allowed_stages),
                    ),
                )
            )
        )
        for stage_key, limit in stage_limits.items():
            if running_counts.get((task_type, stage_key), 0) >= limit:
                filters.append(
                    not_(
                        and_(
                            SystemTaskQueue.task_type == task_type,
                            SystemTaskQueue.stage_key == stage_key,
                        )
                    )
                )
    return filters


def _choose_stage_fair_candidate(candidates: list[_ClaimCandidate]) -> _ClaimCandidate | None:
    if not candidates:
        return None

    def score(candidate: _ClaimCandidate) -> tuple[float, int, int, float, int]:
        running_limit = max(1, int(candidate.running_limit or 1))
        available_slots = max(0, running_limit - int(candidate.running_count or 0))
        available_ratio = available_slots / running_limit
        if candidate.lane_running_limit > 0:
            lane_limit = max(1, int(candidate.lane_running_limit))
            lane_available_slots = max(0, lane_limit - int(candidate.lane_running_count or 0))
            lane_available_ratio = lane_available_slots / lane_limit
            available_ratio = min(available_ratio, lane_available_ratio)
            available_slots = min(available_slots, lane_available_slots)
        created_at = candidate.created_at
        created_ts = created_at.timestamp() if created_at is not None else 0.0
        return (available_ratio, -int(candidate.dispatch_rank), available_slots, -created_ts, -candidate.id)

    return max(candidates, key=score)


def _claim_group_lock_key(task_type: str, stage_key: str, lane_key: str = "") -> int:
    raw = f"{task_type}:{stage_key}:{lane_key}".encode("utf-8")
    digest = hashlib.blake2b(raw, digest_size=4).digest()
    offset = int.from_bytes(digest, "big") % 1_000_000
    return WORKER_STAGE_CLAIM_LOCK_BASE + offset


async def _try_claim_group_lock(db, task_type: str, stage_key: str, lane_key: str = "") -> bool:
    return bool(
        await db.scalar(
            text("select pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": _claim_group_lock_key(task_type, stage_key, lane_key)},
        )
    )


def _task_paused(task_type: str, stage_key: str = "", lane_key: str = "", config: WorkerConfig | None = None) -> bool:
    config = config or _runtime_config
    task_type_key = str(task_type or "")
    stage = str(stage_key or "")
    lane = str(lane_key or "")
    if task_type_key in (config.paused_task_types or set()):
        return True
    paused_stages = config.paused_stages or {}
    if stage and stage in (paused_stages.get(task_type_key) or set()):
        return True
    paused_lanes = config.paused_lanes or {}
    return bool(lane and lane in (paused_lanes.get(task_type_key) or set()))


async def _select_stage_fair_task_id(
    db,
    *,
    now: datetime,
    rules: dict[str, StageConcurrencyRule],
    running_counts: dict[tuple[str, str], int],
    lane_running_counts: dict[tuple[str, str], int],
    config: WorkerConfig,
) -> int | None:
    candidates: list[_ClaimCandidate] = []
    dispatch_order = config.stage_dispatch_order or {}
    ready_filter = and_(
        SystemTaskQueue.status == "pending",
        or_(
            SystemTaskQueue.ready_status.is_(None),
            SystemTaskQueue.ready_status == "ready",
        ),
        or_(
            SystemTaskQueue.scheduled_at.is_(None),
            SystemTaskQueue.scheduled_at <= now,
        ),
    )

    for task_type, rule in sorted(rules.items()):
        stage_limits = rule.stage_max_running or {}
        for stage_key, limit in sorted(stage_limits.items()):
            if _task_paused(task_type, stage_key, config=config):
                continue
            if config.claim_lock_scope == "none" and not await _try_claim_group_lock(db, task_type, stage_key):
                continue
            running_count = running_counts.get((task_type, stage_key), 0)
            if running_count >= limit:
                continue
            row = await db.execute(
                select(
                    SystemTaskQueue.id,
                    SystemTaskQueue.task_type,
                    SystemTaskQueue.stage_key,
                    SystemTaskQueue.lane_key,
                    SystemTaskQueue.priority,
                    SystemTaskQueue.created_at,
                )
                .where(
                    ready_filter,
                    SystemTaskQueue.task_type == task_type,
                    SystemTaskQueue.stage_key == stage_key,
                )
                .order_by(SystemTaskQueue.priority.desc(), SystemTaskQueue.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            candidate = row.first()
            if candidate is None:
                continue
            lane_key = str(candidate.lane_key or "")
            if _task_paused(str(candidate.task_type or ""), stage_key, lane_key, config=config):
                continue
            lane_rules = (config.lane_concurrency or {}).get(str(candidate.task_type or "")) or {}
            lane_limit = int(lane_rules.get(lane_key) or 0)
            lane_running_count = lane_running_counts.get((str(candidate.task_type or ""), lane_key), 0)
            if lane_limit > 0 and lane_running_count >= lane_limit:
                continue
            candidates.append(
                _ClaimCandidate(
                    id=int(candidate.id),
                    task_type=str(candidate.task_type or ""),
                    stage_key=str(candidate.stage_key or ""),
                    lane_key=lane_key,
                    priority=int(candidate.priority or 0),
                    created_at=candidate.created_at,
                    running_count=running_count,
                    running_limit=int(limit),
                    lane_running_count=lane_running_count,
                    lane_running_limit=lane_limit,
                    dispatch_rank=(dispatch_order.get(str(candidate.task_type or "")) or {}).get(stage_key, 1_000_000),
                )
            )

    unmanaged_row = await db.execute(
        select(
            SystemTaskQueue.id,
            SystemTaskQueue.task_type,
            SystemTaskQueue.stage_key,
            SystemTaskQueue.lane_key,
            SystemTaskQueue.priority,
            SystemTaskQueue.created_at,
        )
        .where(
            ready_filter,
            SystemTaskQueue.task_type.not_in(tuple(rules.keys())),
            SystemTaskQueue.task_type.not_in(tuple(config.paused_task_types or set())),
        )
        .order_by(SystemTaskQueue.priority.desc(), SystemTaskQueue.id)
        .limit(config.claim_candidate_scan_limit)
        .with_for_update(skip_locked=True)
    )
    unmanaged_candidate = unmanaged_row.first()
    if unmanaged_candidate is not None:
        if _task_paused(
            str(unmanaged_candidate.task_type or ""),
            str(unmanaged_candidate.stage_key or ""),
            str(unmanaged_candidate.lane_key or ""),
            config=config,
        ):
            unmanaged_candidate = None
    if unmanaged_candidate is not None:
        candidates.append(
            _ClaimCandidate(
                id=int(unmanaged_candidate.id),
                task_type=str(unmanaged_candidate.task_type or ""),
                stage_key=str(unmanaged_candidate.stage_key or ""),
                lane_key=str(unmanaged_candidate.lane_key or ""),
                priority=int(unmanaged_candidate.priority or 0),
                created_at=unmanaged_candidate.created_at,
                running_count=0,
                running_limit=max(1, min(config.worker_lanes_per_process or 1, 8)),
                dispatch_rank=(dispatch_order.get(str(unmanaged_candidate.task_type or "")) or {}).get(
                    str(unmanaged_candidate.stage_key or ""),
                    1_000_000,
                ),
            )
        )

    chosen = _choose_stage_fair_candidate(candidates)
    return chosen.id if chosen is not None else None


async def _claim_one_task(db, config: WorkerConfig | None = None) -> ClaimedTask | None:
    """原子抢占一条 pending 任务（FOR UPDATE SKIP LOCKED 防多 worker 抢同一条）。

    即时任务(scheduled_at IS NULL)照旧立即执行；
    定时任务(scheduled_at <= now())到点才被取。
    """
    config = config or _runtime_config
    now = datetime.now(timezone.utc)
    async with _claim_gate(db, config):
        running_counts: dict[tuple[str, str], int] = {}
        lane_running_counts: dict[tuple[str, str], int] = {}
        rules = config.stage_concurrency or {}
        lane_rules = config.lane_concurrency or {}
        counted_task_types = tuple(sorted(set(rules.keys()) | set(lane_rules.keys())))
        if counted_task_types:
            running_result = await db.execute(
                select(
                    SystemTaskQueue.task_type,
                    SystemTaskQueue.stage_key,
                    SystemTaskQueue.lane_key,
                    func.count(SystemTaskQueue.id),
                )
                .where(
                    SystemTaskQueue.status == "running",
                    SystemTaskQueue.task_type.in_(counted_task_types),
                )
                .group_by(
                    SystemTaskQueue.task_type,
                    SystemTaskQueue.stage_key,
                    SystemTaskQueue.lane_key,
                )
            )
            for task_type, stage_key, lane_key, count in running_result.all():
                task_type_key = str(task_type or "")
                if stage_key:
                    running_counts[(task_type_key, str(stage_key or ""))] = int(count or 0)
                if lane_key:
                    lane_running_counts[(task_type_key, str(lane_key or ""))] = (
                        lane_running_counts.get((task_type_key, str(lane_key or "")), 0)
                        + int(count or 0)
                    )
        if rules:
            task_id = await _select_stage_fair_task_id(
                db,
                now=now,
                rules=rules,
                running_counts=running_counts,
                lane_running_counts=lane_running_counts,
                config=config,
            )
        else:
            concurrency_filters = _concurrency_sql_filters(rules=rules, running_counts=running_counts)
            paused_task_types = tuple(config.paused_task_types or set())
            row = await db.execute(
                select(
                    SystemTaskQueue.id,
                    SystemTaskQueue.task_type,
                    SystemTaskQueue.stage_key,
                    SystemTaskQueue.lane_key,
                )
                .where(
                    and_(
                        SystemTaskQueue.status == "pending",
                        or_(
                            SystemTaskQueue.ready_status.is_(None),
                            SystemTaskQueue.ready_status == "ready",
                        ),
                        or_(
                            SystemTaskQueue.scheduled_at.is_(None),
                            SystemTaskQueue.scheduled_at <= now,
                        ),
                        *(
                            [SystemTaskQueue.task_type.not_in(paused_task_types)]
                            if paused_task_types
                            else []
                        ),
                        *concurrency_filters,
                    ),
                )
                .order_by(SystemTaskQueue.priority.desc(), SystemTaskQueue.id)
                .limit(config.claim_candidate_scan_limit)
                .with_for_update(skip_locked=True)
            )
            candidates = row.all()
            task_id = next(
                (
                    int(candidate_id)
                    for candidate_id, task_type, stage_key, lane_key in candidates
                    if not _task_paused(
                        str(task_type or ""),
                        str(stage_key or ""),
                        str(lane_key or ""),
                        config=config,
                    )
                    and _stage_allowed_by_stage_concurrency(
                        str(task_type or ""),
                        str(stage_key or ""),
                        running_counts=running_counts,
                        config=config,
                    )
                    and _lane_allowed_by_lane_concurrency(
                        str(task_type or ""),
                        str(lane_key or ""),
                        lane_running_counts=lane_running_counts,
                        config=config,
                    )
                ),
                None,
            )
        if task_id is None:
            await db.rollback()
            return None
        update_result = await db.execute(
            update(SystemTaskQueue)
            .where(
                SystemTaskQueue.id == task_id,
                SystemTaskQueue.status == "pending",
            )
            .values(
                status="running",
                started_at=datetime.now(timezone.utc),
                completed_at=None,
                error_message=None,
                result=None,
            )
            .returning(
                SystemTaskQueue.id,
                SystemTaskQueue.task_type,
                SystemTaskQueue.parameters,
                SystemTaskQueue.document_id,
                SystemTaskQueue.stage_key,
                SystemTaskQueue.lane_key,
                SystemTaskQueue.dependency_key,
            )
        )
        claimed = update_result.one_or_none()
        if claimed is None:
            await db.rollback()
            return None
        await db.commit()
        return ClaimedTask(
            id=int(claimed.id),
            task_type=str(claimed.task_type or ""),
            parameters=claimed.parameters,
            document_id=int(claimed.document_id) if claimed.document_id is not None else None,
            stage_key=claimed.stage_key,
            lane_key=claimed.lane_key,
            dependency_key=claimed.dependency_key,
        )


async def _run_handler(task: SystemTaskQueue | ClaimedTask) -> tuple[bool, dict | None, str | None]:
    handler = _HANDLERS.get(task.task_type)
    if not handler:
        return False, None, f"No handler registered for task_type '{task.task_type}'"
    try:
        params = json.loads(task.parameters) if task.parameters else {}
    except Exception as exc:
        return False, None, f"Invalid parameters JSON: {exc}"
    if not isinstance(params, dict):
        return False, None, "Invalid parameters JSON: root must be an object"
    params["task_id"] = int(task.id)
    if task.document_id is not None:
        params["document_id"] = int(task.document_id)
    if task.stage_key:
        params["stage"] = str(task.stage_key)
    if task.lane_key:
        params["lane"] = str(task.lane_key)
    if task.dependency_key:
        params["dependency_key"] = str(task.dependency_key)
    try:
        result = await handler(params)
        failed, error = _result_is_semantic_failure(result)
        if failed:
            return False, result, error
        return True, result, None
    except Exception as exc:
        logger.error(
            "Task %s (%s) handler failed: %r",
            task.id,
            task.task_type,
            exc,
            exc_info=True,
        )
        return False, None, str(exc)


def _compute_next_recur(recur: str, ref_time: datetime) -> datetime | None:
    """根据周期表达计算下一次运行时间。"""
    ref = ref_time.astimezone(timezone.utc)
    if recur == "hourly":
        return ref + timedelta(hours=1)
    elif recur == "daily":
        return ref + timedelta(days=1)
    elif recur == "weekly":
        return ref + timedelta(weeks=1)
    elif recur.startswith("cron:"):
        # Minimal cron: "cron:HH:MM" daily at that UTC time
        parts = recur.split(":")
        if len(parts) >= 3:
            hour, minute = int(parts[1]), int(parts[2])
            next_time = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_time <= ref:
                next_time += timedelta(days=1)
            return next_time
    return None


def _serialize_task_result(result: dict | None) -> str | None:
    return json.dumps(result, ensure_ascii=False, default=str) if result is not None else None


async def _finish_task(db, task_id: int, ok: bool, result: dict | None, error: str | None) -> None:
    task = await db.get(SystemTaskQueue, task_id)
    if not task:
        return
    now = datetime.now(timezone.utc)
    if ok:
        task.status = "completed"
        task.result = _serialize_task_result(result)
        task.error_message = None
        task.completed_at = now
        # 周期任务: 完成后自动重排下一次
        if task.recur:
            next_time = _compute_next_recur(task.recur, now)
            if next_time:
                task.status = "pending"
                task.scheduled_at = next_time
                task.next_run_at = next_time
                task.started_at = None
                task.retry_count = 0
                task.completed_at = None
    else:
        task.retry_count = (task.retry_count or 0) + 1
        task.error_message = error
        if task.retry_count >= (task.max_retries or 3):
            task.status = "failed"
            task.completed_at = now
        else:
            task.status = "pending"  # 重排重试
            task.started_at = None
    await db.commit()


def _active_task_ids_snapshot() -> list[int]:
    return sorted(set(_lane_current_task_ids.values()))


async def _release_active_tasks_on_shutdown(task_ids: list[int] | None = None) -> None:
    """Return tasks owned by this process to the DB queue during graceful restart.

    Startup recovery only reclaims timed-out tasks because multiple uvicorn
    workers may be alive at once. During process shutdown, however, this process
    knows exactly which task IDs its lanes claimed, so releasing only those tasks
    avoids both duplicate execution and 20-minute stale waits after a restart.
    """
    task_ids = sorted(set(task_ids or _active_task_ids_snapshot()))
    if not task_ids:
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(SystemTaskQueue)
                .where(
                    SystemTaskQueue.id.in_(task_ids),
                    SystemTaskQueue.status == "running",
                )
                .values(
                    status="pending",
                    started_at=None,
                    error_message="Task interrupted by worker shutdown; released for retry",
                )
            )
            await db.commit()
            released = int(result.rowcount or 0)
            if released:
                logger.info("Released %d running task(s) during worker shutdown", released)
    except Exception as exc:
        logger.error("Failed to release running tasks during worker shutdown: %s", exc)


async def _rollback_idle_worker_transaction(db) -> None:
    """Return a polling session to the pool without an open transaction."""
    try:
        if db.in_transaction():
            await db.rollback()
    except Exception as exc:
        logger.warning("Task worker idle transaction rollback failed: %s", exc)


async def _worker_lane_loop(lane_id: int) -> None:
    global _last_active
    logger.info("Task worker lane %s started", lane_id)
    while not _stop_flag and lane_id not in _retiring_lane_ids:
        config = _runtime_config
        try:
            async with AsyncSessionLocal() as db:
                await _recover_stale_tasks_if_due(db, config)
                task = await _claim_one_task(db, config)
                await _rollback_idle_worker_transaction(db)
            if task is None:
                await asyncio.sleep(config.poll_interval_seconds)
                continue
            _last_active = datetime.now(timezone.utc)
            _lane_current_task_ids[lane_id] = int(task.id)
            try:
                ok, result, error = await _run_handler(task)
                async with AsyncSessionLocal() as db:
                    await _finish_task(db, task.id, ok, result, error)
            finally:
                _lane_current_task_ids.pop(lane_id, None)
        except Exception as exc:
            logger.error("Task worker lane %s error: %r", lane_id, exc, exc_info=True)
            await asyncio.sleep(config.poll_interval_seconds)
    logger.info("Task worker lane %s stopped", lane_id)


def _start_lane() -> None:
    global _next_lane_id
    lane_id = _next_lane_id
    _next_lane_id += 1
    _lane_tasks[lane_id] = asyncio.create_task(_worker_lane_loop(lane_id))


def _reconcile_lanes(target_count: int) -> None:
    for lane_id, task in list(_lane_tasks.items()):
        if task.done():
            _lane_tasks.pop(lane_id, None)
            _retiring_lane_ids.discard(lane_id)

    active_count = len(_lane_tasks)
    if active_count <= target_count:
        _retiring_lane_ids.clear()

    while active_count < target_count:
        _start_lane()
        active_count += 1

    if active_count > target_count:
        active_lane_ids = sorted(_lane_tasks.keys(), reverse=True)
        for lane_id in active_lane_ids[: active_count - target_count]:
            _retiring_lane_ids.add(lane_id)


async def _worker_supervisor_loop() -> None:
    global _worker_is_leader
    logger.info("Task worker supervisor started")
    _load_worker_config(force=True)
    while not _stop_flag:
        config = _load_worker_config()
        leader_conn = None
        slot_conn = None
        slot_id = None
        try:
            leader_conn = await _acquire_worker_leader_connection()
            if leader_conn is None and config.worker_process_mode == "leader":
                _worker_is_leader = False
                _reconcile_lanes(0)
                await asyncio.sleep(config.config_reload_seconds)
                continue
            if config.worker_process_mode == "all":
                slot_conn, slot_id = await _acquire_worker_slot_connection(config.worker_process_slots)
                if slot_conn is None:
                    _worker_is_leader = leader_conn is not None
                    _reconcile_lanes(0)
                    await asyncio.sleep(config.config_reload_seconds)
                    continue

            _worker_is_leader = leader_conn is not None
            if leader_conn is not None:
                logger.info("Task worker leader lock acquired by pid=%s", os.getpid())
                if config.reclaim_running_on_startup:
                    await _reclaim_running_tasks_on_startup(config.startup_reclaim_min_age_seconds)
                else:
                    await _recover_orphan_running_tasks()
            elif config.worker_process_mode == "all":
                logger.info("Task worker process pid=%s joining without leader lock", os.getpid())
            if slot_conn is not None:
                logger.info("Task worker process slot %s acquired by pid=%s", slot_id, os.getpid())

            while not _stop_flag:
                config = _load_worker_config()
                async with AsyncSessionLocal() as db:
                    await _recover_stale_tasks_if_due(db, config)
                    await _rollback_idle_worker_transaction(db)
                _reconcile_lanes(config.worker_lanes_per_process)
                await asyncio.sleep(config.config_reload_seconds)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Task worker supervisor error: %s", exc)
            _worker_is_leader = False
            _reconcile_lanes(0)
            await asyncio.sleep(config.config_reload_seconds)
        finally:
            _reconcile_lanes(0)
            if _lane_tasks:
                await asyncio.gather(*_lane_tasks.values(), return_exceptions=True)
            if leader_conn is not None:
                await _release_worker_leader_connection(leader_conn)
            if slot_conn is not None:
                await _release_worker_slot_connection(slot_conn, slot_id)

    _worker_is_leader = False
    _reconcile_lanes(0)
    if _lane_tasks:
        await asyncio.gather(*_lane_tasks.values(), return_exceptions=True)
    logger.info("Task worker supervisor stopped")


def start_worker() -> None:
    global _worker_task, _stop_flag
    if _worker_task is not None and not _worker_task.done():
        return
    _stop_flag = False
    _worker_task = asyncio.create_task(_worker_supervisor_loop())


async def stop_worker() -> None:
    global _stop_flag
    _stop_flag = True
    if _worker_task:
        active_task_ids = _active_task_ids_snapshot()
        try:
            timeout = _runtime_config.poll_interval_seconds + _runtime_config.config_reload_seconds + 1
            await asyncio.wait_for(_worker_task, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _worker_task.cancel()
            for lane_task in _lane_tasks.values():
                lane_task.cancel()
            if _lane_tasks:
                await asyncio.gather(*_lane_tasks.values(), return_exceptions=True)
        finally:
            await _release_active_tasks_on_shutdown(active_task_ids)


def worker_health() -> dict:
    stage_concurrency = {
        task_type: dict(rule.stage_max_running or {})
        for task_type, rule in (_runtime_config.stage_concurrency or {}).items()
    }
    lane_concurrency = {
        task_type: dict(rule or {})
        for task_type, rule in (_runtime_config.lane_concurrency or {}).items()
    }
    paused_stages = {
        task_type: sorted(values)
        for task_type, values in (_runtime_config.paused_stages or {}).items()
    }
    paused_lanes = {
        task_type: sorted(values)
        for task_type, values in (_runtime_config.paused_lanes or {}).items()
    }
    return {
        "running": _worker_task is not None and not _worker_task.done(),
        "configured_lanes_per_process": _runtime_config.worker_lanes_per_process,
        "max_lanes_per_process": _runtime_config.max_lanes_per_process,
        "worker_process_mode": _runtime_config.worker_process_mode,
        "worker_process_slots": _runtime_config.worker_process_slots,
        "claim_lock_scope": _runtime_config.claim_lock_scope,
        "claim_candidate_scan_limit": _runtime_config.claim_candidate_scan_limit,
        "serialize_claims": _runtime_config.serialize_claims,
        "active_lanes": len([task for task in _lane_tasks.values() if not task.done()]),
        "active_task_ids": _active_task_ids_snapshot(),
        "retiring_lanes": sorted(_retiring_lane_ids),
        "config_path": str(CONFIG_PATH),
        "config_reload_seconds": _runtime_config.config_reload_seconds,
        "stale_recovery_interval_seconds": _runtime_config.stale_recovery_interval_seconds,
        "reclaim_running_on_startup": _runtime_config.reclaim_running_on_startup,
        "startup_reclaim_min_age_seconds": _runtime_config.startup_reclaim_min_age_seconds,
        "is_leader": _worker_is_leader,
        "leader_lock_key": WORKER_LEADER_LOCK_KEY,
        "claim_lock_key": WORKER_CLAIM_LOCK_KEY,
        "worker_process_slot_lock_base": WORKER_PROCESS_SLOT_LOCK_BASE,
        "registered_handlers": sorted(_HANDLERS.keys()),
        "stage_concurrency": stage_concurrency,
        "lane_concurrency": lane_concurrency,
        "paused_task_types": sorted(_runtime_config.paused_task_types or set()),
        "paused_stages": paused_stages,
        "paused_lanes": paused_lanes,
        "last_active": _last_active.isoformat() if _last_active else None,
        "process_local": True,
        "pid": os.getpid(),
        "last_active_scope": "process",
    }
