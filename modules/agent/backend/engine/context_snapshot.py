"""Context snapshot for replayable and auditable conversation state.
Provides take/restore/list/retention operations on agent_context_snapshots.
Snapshots are auxiliary — all failures are logged without propagation.
"""
import logging

from sqlalchemy import select, desc, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ContextSnapshot, AgentEvent
from .event_store import record_event
from .budget_allocator import estimate_tokens as _budget_estimate_tokens

logger = logging.getLogger("v2.agent").getChild("engine.context_snapshot")

# Retention limits
MAX_PERIODIC_PER_CONVERSATION = 15
MAX_COMPRESS_PAIRS = 10  # keep this many pre/post_compress pairs


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token count estimation (~chars/1.5)."""
    return _budget_estimate_tokens(messages)


async def take_snapshot(
    db: AsyncSession,
    conversation_id: int,
    snapshot_type: str,
    messages: list[dict],
    events: list[AgentEvent],
    summary: str | None = None,
) -> ContextSnapshot | None:
    """Create a ContextSnapshot record.

    Args:
        db: Database session.
        conversation_id: The conversation to snapshot.
        snapshot_type: ``"pre_compress"``, ``"post_compress"``, or ``"periodic"``.
        messages: The projected messages at this point.
        events: List of AgentEvent objects for determining event_id boundaries.
        summary: Optional summary text (used for post_compress summaries).

    Returns:
        The created ContextSnapshot record, or None on failure.
    """
    try:
        last_event_id = events[-1].id if events else None
        token_est = estimate_tokens(messages)
        msg_count = len(messages)

        if snapshot_type == "pre_compress":
            snapshot = ContextSnapshot(
                conversation_id=conversation_id,
                snapshot_type=snapshot_type,
                event_id_before=last_event_id,
                event_id_after=None,
                message_count_before=msg_count,
                message_count_after=0,
                token_estimate_before=token_est,
                token_estimate_after=0,
                summary=summary,
                snapshot_data=messages,
                compression_ratio=None,
                restored_from=None,
            )
        elif snapshot_type == "post_compress":
            snapshot = ContextSnapshot(
                conversation_id=conversation_id,
                snapshot_type=snapshot_type,
                event_id_before=None,
                event_id_after=last_event_id,
                message_count_before=0,
                message_count_after=msg_count,
                token_estimate_before=0,
                token_estimate_after=token_est,
                summary=summary,
                snapshot_data=messages,
                compression_ratio=None,
                restored_from=None,
            )
        elif snapshot_type == "periodic":
            snapshot = ContextSnapshot(
                conversation_id=conversation_id,
                snapshot_type=snapshot_type,
                event_id_before=last_event_id,
                event_id_after=last_event_id,
                message_count_before=msg_count,
                message_count_after=msg_count,
                token_estimate_before=token_est,
                token_estimate_after=token_est,
                summary=summary,
                snapshot_data=messages,
                compression_ratio=None,
                restored_from=None,
            )
        else:
            logger.warning("Unknown snapshot_type '%s' for conversation %s", snapshot_type, conversation_id)
            return None

        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        logger.info(
            "Snapshot taken: conversation=%s type=%s id=%s msgs=%s tokens=%s",
            conversation_id, snapshot_type, snapshot.id, msg_count, token_est,
        )
        return snapshot
    except Exception:
        await db.rollback()
        logger.exception("Failed to take %s snapshot for conversation %s", snapshot_type, conversation_id)
        return None


async def get_latest_snapshot(
    db: AsyncSession,
    conversation_id: int,
    snapshot_type: str | None = None,
) -> ContextSnapshot | None:
    """Get the most recent snapshot for a conversation.

    Args:
        db: Database session.
        conversation_id: The conversation to query.
        snapshot_type: Optional filter by snapshot type.

    Returns:
        The latest ContextSnapshot record, or None.
    """
    try:
        stmt = select(ContextSnapshot).where(
            ContextSnapshot.conversation_id == conversation_id
        )
        if snapshot_type:
            stmt = stmt.where(ContextSnapshot.snapshot_type == snapshot_type)
        stmt = stmt.order_by(desc(ContextSnapshot.id)).limit(1)
        r = await db.execute(stmt)
        return r.scalar_one_or_none()
    except Exception:
        logger.exception(
            "Failed to get latest snapshot for conversation %s", conversation_id
        )
        return None


async def restore_snapshot(
    db: AsyncSession,
    snapshot_id: int,
) -> list[dict]:
    """Restore context messages from a snapshot, recording restore provenance.

    Args:
        db: Database session.
        snapshot_id: The snapshot id to restore from.

    Returns:
        The saved messages list, or empty list on failure / missing data.
    """
    try:
        r = await db.execute(
            select(ContextSnapshot).where(ContextSnapshot.id == snapshot_id)
        )
        snapshot = r.scalar_one_or_none()
        if snapshot is None:
            logger.warning("Snapshot %s not found for restore", snapshot_id)
            return []

        data = snapshot.snapshot_data
        if not isinstance(data, list):
            logger.warning("Snapshot %s has no valid snapshot_data", snapshot_id)
            return []

        # Record restore provenance for audit trail
        await record_restore_provenance(db, snapshot)

        logger.info(
            "Restored snapshot %s: conversation=%s type=%s msgs=%s",
            snapshot_id, snapshot.conversation_id, snapshot.snapshot_type, len(data),
        )
        return data
    except Exception:
        logger.exception("Failed to restore snapshot %s", snapshot_id)
        return []


async def record_restore_provenance(
    db: AsyncSession,
    snapshot: ContextSnapshot,
) -> None:
    """Record that a snapshot was used for restore via an append-only event."""
    try:
        await record_event(
            db,
            snapshot.conversation_id,
            "snapshot_restore",
            {
                "snapshot_id": snapshot.id,
                "snapshot_type": snapshot.snapshot_type,
                "event_id_before": snapshot.event_id_before,
                "event_id_after": snapshot.event_id_after,
            },
            llm_response_id=None,
        )
    except Exception:
        logger.exception("Failed to record restore provenance")


async def list_snapshots(
    db: AsyncSession,
    conversation_id: int,
    limit: int = 20,
) -> list[ContextSnapshot]:
    """List recent snapshots for audit / replay.

    Args:
        db: Database session.
        conversation_id: The conversation to query.
        limit: Maximum number of snapshots to return (newest first).

    Returns:
        List of ContextSnapshot records.
    """
    try:
        r = await db.execute(
            select(ContextSnapshot)
            .where(ContextSnapshot.conversation_id == conversation_id)
            .order_by(desc(ContextSnapshot.id))
            .limit(limit)
        )
        return list(r.scalars().all())
    except Exception:
        logger.exception(
            "Failed to list snapshots for conversation %s", conversation_id
        )
        return []


async def enforce_retention(
    db: AsyncSession,
    conversation_id: int,
) -> dict:
    """Enforce retention policy: prune excess periodic and compress snapshots.

    Keeps:
    - Last ``MAX_PERIODIC_PER_CONVERSATION`` periodic snapshots.
    - Last ``MAX_COMPRESS_PAIRS`` pre/post_compress pairs.

    Returns:
        Dict with ``pruned`` count.
    """
    pruned = 0
    try:
        for snap_type, max_keep in [
            ("periodic", MAX_PERIODIC_PER_CONVERSATION),
        ]:
            r = await db.execute(
                select(ContextSnapshot.id)
                .where(
                    ContextSnapshot.conversation_id == conversation_id,
                    ContextSnapshot.snapshot_type == snap_type,
                )
                .order_by(desc(ContextSnapshot.id))
                .offset(max_keep)
            )
            stale_ids = [row[0] for row in r.all()]
            if stale_ids:
                ids_str = ",".join(str(i) for i in stale_ids)
                await db.execute(
                    text(f"DELETE FROM agent_context_snapshots WHERE id IN ({ids_str})")
                )
                pruned += len(stale_ids)

        # Prune excess pre/post_compress pairs
        for snap_type in ("pre_compress", "post_compress"):
            r = await db.execute(
                select(ContextSnapshot.id)
                .where(
                    ContextSnapshot.conversation_id == conversation_id,
                    ContextSnapshot.snapshot_type == snap_type,
                )
                .order_by(desc(ContextSnapshot.id))
                .offset(MAX_COMPRESS_PAIRS)
            )
            stale_ids = [row[0] for row in r.all()]
            if stale_ids:
                ids_str = ",".join(str(i) for i in stale_ids)
                await db.execute(
                    text(f"DELETE FROM agent_context_snapshots WHERE id IN ({ids_str})")
                )
                pruned += len(stale_ids)

        if pruned:
            await db.commit()
            logger.info(
                "Retention enforced for conv=%s: pruned %d snapshots",
                conversation_id, pruned,
            )
    except Exception:
        await db.rollback()
        logger.exception("Failed to enforce retention for conversation %s", conversation_id)
    return {"pruned": pruned}


async def get_compress_pair(
    db: AsyncSession,
    conversation_id: int,
) -> tuple[ContextSnapshot | None, ContextSnapshot | None]:
    """Get the most recent pre/post_compress snapshot pair for a conversation.

    Returns:
        ``(pre_snapshot, post_snapshot)`` tuple, either may be None.
    """
    try:
        post = await get_latest_snapshot(db, conversation_id, "post_compress")
        if not post:
            return await get_latest_snapshot(db, conversation_id, "pre_compress"), None

        r = await db.execute(
            select(ContextSnapshot)
            .where(
                ContextSnapshot.conversation_id == conversation_id,
                ContextSnapshot.snapshot_type == "pre_compress",
                ContextSnapshot.id < post.id,
            )
            .order_by(desc(ContextSnapshot.id))
            .limit(1)
        )
        pre = r.scalar_one_or_none()
        return pre, post
    except Exception:
        logger.exception("Failed to get compress pair for conversation %s", conversation_id)
        return None, None


async def count_snapshots(
    db: AsyncSession,
    conversation_id: int,
) -> int:
    """Count total snapshots for a conversation (for diagnostics)."""
    try:
        r = await db.execute(
            select(func.count()).select_from(ContextSnapshot)
            .where(ContextSnapshot.conversation_id == conversation_id)
        )
        return r.scalar() or 0
    except Exception:
        return 0
