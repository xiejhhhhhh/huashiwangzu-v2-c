"""Post-turn hook chain for agent conversation loop.

Runs asynchronously after each conversation turn without blocking
the main conversation flow. All hooks fire via create_task so the
caller returns immediately.

## Hook chain (fixed order, each is non-blocking)

1. **memory_distill** — Extract facts from the current turn → save to memory.
2. **profile_evolve** — Submit a profile evolution task to SystemTaskQueue.
3. **prompt_suggestion** — Analyse turn for prompt improvement opportunities.
4. **context_snapshot** — Take a periodic snapshot every N turns.
5. **cleanup_archive** — Prune stale periodic snapshots beyond retention.

Each hook is individually wrapped in try/except so a single failure
never cascades to other hooks or the main conversation flow.

Background maintenance (``setup_global_hooks``) runs on a fixed 5-min
interval to enforce retention policies across all conversations.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentEvent, ContextSnapshot, AgentHookRun
from .context_snapshot import take_snapshot

logger = logging.getLogger("v2.agent").getChild("engine.post_turn_hooks")

# Periodic snapshot: take a snapshot every N turns per conversation.
EVERY_N_TURNS = 3

# How many periodic snapshots to keep per conversation (newest retained).
MAX_PERIODIC_SNAPSHOTS = 10

# Background maintenance interval (seconds)
_BACKGROUND_MAINTENANCE_INTERVAL = 300  # 5 minutes

# Background maintenance lifecycle tracking
_background_maintenance_task: asyncio.Task | None = None
_background_maintenance_started_at: float = 0.0
_background_maintenance_run_count: int = 0

# ── Hook lifecycle governance (persisted via DB) ──────────────────────
_HOOK_LIFECYCLE_STATE: dict[str, str] = {
    "maintenance_status": "stopped",
}
_HOOK_RUN_HISTORY_MAX = 200


async def _read_hook_runs(db: AsyncSession, owner_id: int | None = None) -> list[dict]:
    q = select(AgentHookRun)
    if owner_id is not None and owner_id > 0:
        q = q.where(AgentHookRun.owner_id == owner_id)
    q = q.order_by(desc(AgentHookRun.created_at)).limit(_HOOK_RUN_HISTORY_MAX)
    r = await db.execute(q)
    return [
        {
            "hook_name": row.hook_name,
            "success": row.success,
            "duration_ms": row.duration_ms,
            "detail": row.detail or "",
            "timestamp": row.created_at.timestamp() if row.created_at else 0,
            "conversation_id": row.conversation_id,
        }
        for row in r.scalars().all()
    ]


async def _append_hook_run(
    db: AsyncSession, owner_id: int, conversation_id: int | None, record: dict,
) -> None:
    db.add(AgentHookRun(
        owner_id=owner_id,
        conversation_id=conversation_id,
        hook_name=record.get("hook_name", ""),
        success=record.get("success", False),
        duration_ms=record.get("duration_ms", 0.0),
        detail=record.get("detail", "")[:500],
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()


async def get_hook_lifecycle_state(db: AsyncSession, owner_id: int | None = None) -> dict:
    """Return observable hook lifecycle state for admin health check."""
    global _HOOK_LIFECYCLE_STATE
    state = dict(_HOOK_LIFECYCLE_STATE)
    state["maintenance_task_running"] = (
        _background_maintenance_task is not None and not _background_maintenance_task.done()
    )
    state["maintenance_started_at"] = _background_maintenance_started_at
    state["maintenance_run_count"] = _background_maintenance_run_count
    all_runs = await _read_hook_runs(db, owner_id)
    state["recent_hook_runs"] = all_runs[-20:]
    state["hook_names"] = ["memory_distill", "profile_evolve", "context_snapshot", "cleanup_archive", "prompt_suggestion"]
    return state


async def _record_hook_run(
    db: AsyncSession, owner_id: int, conversation_id: int | None,
    name: str, success: bool, duration_ms: float, detail: str = "",
) -> None:
    """Record a hook run for lifecycle observability (persisted via DB)."""
    await _append_hook_run(db, owner_id, conversation_id, {
        "hook_name": name,
        "success": success,
        "duration_ms": round(duration_ms, 1),
        "detail": detail[:200],
    })


async def _get_turn_count(db: AsyncSession, conversation_id: int) -> int:
    """Count assistant_msg events as a deterministic turn counter (cross-worker safe)."""
    r = await db.execute(
        select(func.count()).select_from(AgentEvent)
        .where(
            AgentEvent.conversation_id == conversation_id,
            AgentEvent.event_type == "assistant_msg",
        )
    )
    return r.scalar() or 0


class PostTurnHooks:
    """Fixed hook chain that runs after each conversation turn.

    Hooks are executed as fire-and-forget tasks via ``asyncio.create_task``.
    Each hook is individually wrapped in try/except so a single failure
    never cascades to other hooks or the main conversation flow.
    """

    async def run_hooks(
        self,
        db: AsyncSession,
        conversation_id: int,
        owner_id: int,
        messages: list[dict],
        tool_events: list[dict] | None = None,
        timeline: list[dict] | None = None,
    ) -> dict:
        """Run all post-turn hooks as fire-and-forget tasks.

        Returns a summary dict immediately without awaiting the hooks.
        The ``db`` session is **not** reused by the spawned tasks —
        each hook opens its own database session to avoid use-after-close
        on the caller's session.
        """
        tool_events = tool_events or []
        timeline = timeline or []

        summary: dict = {"hooks_run": [], "errors": {}}

        async def _safe_run(name: str, coro):
            _t0 = time.time()
            try:
                await coro
                _t1 = time.time()
                summary["hooks_run"].append(name)
                from app.database import AsyncSessionLocal as _ASL
                async with _ASL() as _db:
                    await _record_hook_run(_db, owner_id, conversation_id, name, True, (_t1 - _t0) * 1000)
            except Exception as exc:
                _t1 = time.time()
                logger.exception("Post-turn hook '%s' failed (non-fatal): %s", name, exc)
                summary["errors"][name] = str(exc)
                from app.database import AsyncSessionLocal as _ASL
                async with _ASL() as _db:
                    await _record_hook_run(_db, owner_id, conversation_id, name, False, (_t1 - _t0) * 1000, str(exc)[:200])
                from .failure_diagnostics import record_failure
                await record_failure("hook", f"run_{name}", type(exc).__name__, str(exc), conversation_id, owner_id)

        asyncio.create_task(
            _safe_run("memory_distill", self._hook_memory_distill(
                conversation_id, owner_id, messages, tool_events,
            ))
        )

        asyncio.create_task(
            _safe_run("profile_evolve", self._hook_profile_evolve(
                conversation_id, owner_id, messages,
            ))
        )

        asyncio.create_task(
            _safe_run("context_snapshot", self._hook_context_snapshot(
                conversation_id, owner_id, messages,
            ))
        )

        asyncio.create_task(
            _safe_run("cleanup_archive", self._hook_cleanup_archive(
                conversation_id,
            ))
        )

        asyncio.create_task(
            _safe_run("prompt_suggestion", self._hook_prompt_suggestion(
                conversation_id, owner_id, messages,
            ))
        )

        return summary

    async def _hook_memory_distill(
        self,
        conversation_id: int,
        owner_id: int,
        messages: list[dict],
        tool_events: list[dict],
    ) -> dict:
        """Extract facts from the recent conversation turn and save to memory.

        Delegates to ``engine.record_turn`` which handles extraction and
        persistence via the layered memory store.
        """
        logger.debug("memory_distill: conv=%s owner=%s", conversation_id, owner_id)

        from app.database import AsyncSessionLocal
        from .engine import record_turn

        async with AsyncSessionLocal() as session:
            result = await record_turn(session, conversation_id, owner_id, messages)
            return result

    async def _hook_profile_evolve(
        self,
        conversation_id: int,
        owner_id: int,
        messages: list[dict],
    ) -> None:
        """Submit a profile evolution task to ``SystemTaskQueue``.

        The ``profile_evolve`` task handler runs asynchronously and decides
        whether the latest turn warrants an update to the user's profile.
        Throttling (cooldown) is handled inside the task handler itself.
        """
        logger.debug("profile_evolve: conv=%s owner=%s", conversation_id, owner_id)

        from app.database import AsyncSessionLocal
        from app.models.system import SystemTaskQueue

        async with AsyncSessionLocal() as session:
            task = SystemTaskQueue(
                task_type="profile_evolve",
                parameters=json.dumps({
                    "conversation_id": conversation_id,
                    "owner_id": owner_id,
                }),
                status="pending",
                priority=0,
                module="agent",
                creator_id=owner_id,
            )
            session.add(task)
            await session.commit()

    async def _hook_prompt_suggestion(
        self,
        conversation_id: int,
        owner_id: int,
        messages: list[dict],
    ) -> None:
        """Record a lightweight suggestion when the assistant reply is too thin."""
        from app.database import AsyncSessionLocal
        from .event_store import record_event

        assistant_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                assistant_text = str(msg.get("content", "") or "").strip()
                break

        if not assistant_text or len(assistant_text) >= 120:
            return

        async with AsyncSessionLocal() as session:
            await record_event(
                session,
                conversation_id,
                "hook_prompt_suggestion",
                {
                    "owner_id": owner_id,
                    "assistant_length": len(assistant_text),
                    "suggestion": "assistant_reply_too_short",
                },
                llm_response_id=None,
            )

    async def _hook_context_snapshot(
        self,
        conversation_id: int,
        owner_id: int,
        messages: list[dict],
    ) -> None:
        """Take a periodic snapshot every ``EVERY_N_TURNS`` turns.

        Snapshots provide a recoverable checkpoint for replay and audit
        without incurring I/O overhead on every turn.
        Uses DB-backed assistant_msg count as turn counter (cross-worker safe).
        """
        from app.database import AsyncSessionLocal
        from .event_store import read_events

        async with AsyncSessionLocal() as session:
            counter = await _get_turn_count(session, conversation_id)
            if counter % EVERY_N_TURNS != 0:
                logger.debug(
                    "context_snapshot skipped (turn %s/%s): conv=%s",
                    counter, EVERY_N_TURNS, conversation_id,
                )
                return

            logger.debug("context_snapshot: conv=%s turn=%s", conversation_id, counter)
            events = await read_events(session, conversation_id)
            await take_snapshot(
                db=session,
                conversation_id=conversation_id,
                snapshot_type="periodic",
                messages=messages,
                events=events,
                summary=f"Periodic snapshot at turn {counter}",
            )

    async def _hook_cleanup_archive(
        self,
        conversation_id: int,
    ) -> None:
        """Clean up stale periodic snapshots beyond retention limit.

        Removes the oldest periodic snapshots when the count exceeds
        ``MAX_PERIODIC_SNAPSHOTS`` per conversation.
        """
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                r = await session.execute(
                    select(ContextSnapshot.id)
                    .where(
                        ContextSnapshot.conversation_id == conversation_id,
                        ContextSnapshot.snapshot_type == "periodic",
                    )
                    .order_by(desc(ContextSnapshot.id))
                    .offset(MAX_PERIODIC_SNAPSHOTS)
                )
                stale_ids = [row[0] for row in r.all()]
                if stale_ids:
                    await session.execute(
                        delete(ContextSnapshot).where(ContextSnapshot.id.in_(stale_ids))
                    )
                    await session.commit()
                    logger.info(
                        "cleanup_archive: removed %d stale periodic snapshots for conv=%s",
                        len(stale_ids), conversation_id,
                    )
            except Exception as exc:
                await session.rollback()
                logger.warning("cleanup_archive failed (non-fatal): %s", exc)


_MAINTENANCE_INTERVAL = 300  # 5 minutes, must be > 0


def setup_global_hooks() -> None:
    """Register startup hooks for the post-turn system.

    Starts a background maintenance task that periodically enforces
    snapshot retention across all conversations.  The task runs on
    a fixed interval (``_MAINTENANCE_INTERVAL`` seconds) and is
    wrapped in try/except so a single failure never kills the loop.

    Lifecycle:
    - Tracks ``_background_maintenance_started_at`` timestamp.
    - Counts ``_background_maintenance_run_count`` iterations.
    - On cancellation, logs the total runtime and run count.
    - On exception, logs the error and continues (self-healing).
    """
    global _background_maintenance_task, _background_maintenance_started_at, _background_maintenance_run_count  # noqa: PLW0603
    _HOOK_LIFECYCLE_STATE["maintenance_status"] = "starting"

    if _background_maintenance_task is not None:
        if not _background_maintenance_task.done():
            logger.debug("setup_global_hooks: background task already running")
            _HOOK_LIFECYCLE_STATE["maintenance_status"] = "running"
            return
        logger.warning("setup_global_hooks: previous background task finished, restarting")

    async def _maintenance_loop() -> None:
        global _background_maintenance_run_count  # noqa: PLW0603
        logger.info(
            "Maintenance loop started (interval=%ss, EVERY_N_TURNS=%s, MAX_PERIODIC_SNAPSHOTS=%s)",
            _MAINTENANCE_INTERVAL, EVERY_N_TURNS, MAX_PERIODIC_SNAPSHOTS,
        )
        while True:
            try:
                await asyncio.sleep(_MAINTENANCE_INTERVAL)
                result = await _run_global_retention()
                _background_maintenance_run_count += 1
                _HOOK_LIFECYCLE_STATE["maintenance_status"] = "running"
                if result.get("total_pruned", 0) > 0:
                    logger.info(
                        "Maintenance iteration %d: pruned %d snapshots",
                        _background_maintenance_run_count, result["total_pruned"],
                    )
            except asyncio.CancelledError:
                logger.info(
                    "Maintenance loop cancelled after %d iterations (%.1fs runtime)",
                    _background_maintenance_run_count,
                    time.time() - _background_maintenance_started_at,
                )
                _HOOK_LIFECYCLE_STATE["maintenance_status"] = "cancelled"
                break
            except Exception:
                logger.exception("Maintenance loop iteration failed (will retry)")

    _background_maintenance_task = asyncio.create_task(_maintenance_loop(), name="agent-hooks-maintenance")
    _background_maintenance_started_at = time.time()
    _background_maintenance_run_count = 0
    _HOOK_LIFECYCLE_STATE["maintenance_status"] = "running"
    logger.info(
        "setup_global_hooks: post-turn hooks ready (EVERY_N_TURNS=%s, MAX_PERIODIC_SNAPSHOTS=%s)",
        EVERY_N_TURNS, MAX_PERIODIC_SNAPSHOTS,
    )


async def _run_global_retention() -> dict:
    """Enforce snapshot retention for all conversations that have snapshots.

    Queries ``agent_context_snapshots`` for distinct conversation IDs,
    then runs the retention policy on each.  Failures are non-fatal
    (logged per conversation).
    """
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    stats = {"conversations_checked": 0, "total_pruned": 0, "errors": 0}
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                text("SELECT DISTINCT conversation_id FROM agent_context_snapshots")
            )
            conv_ids = [row[0] for row in r.all()]
    except Exception as exc:
        logger.warning("Global retention: failed to query conversation IDs: %s", exc)
        return {"error": str(exc)}

    for conv_id in conv_ids:
        try:
            from .context_snapshot import enforce_retention
            async with AsyncSessionLocal() as db:
                result = await enforce_retention(db, conv_id)
            stats["conversations_checked"] += 1
            stats["total_pruned"] += result.get("pruned", 0)
        except Exception as exc:
            stats["errors"] += 1
            logger.warning("Global retention: conv=%s failed: %s", conv_id, exc)

    if stats["total_pruned"] > 0:
        logger.info(
            "Global retention: checked %d conversations, pruned %d snapshots",
            stats["conversations_checked"], stats["total_pruned"],
        )
    return stats
