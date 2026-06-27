"""Unified failure diagnostic recording for Agent engine.

Records structured failure events to ``agent_failure_diagnostics`` table
so that all exception degradation paths have a queryable audit trail."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentFailureDiagnostic as FDModel

logger = logging.getLogger("v2.agent").getChild("engine.failure_diagnostics")


async def record_failure(
    source: str,
    operation: str,
    error_type: str,
    error_message: str,
    conversation_id: int | None = None,
    owner_id: int | None = None,
    extra: dict | None = None,
) -> None:
    """Append a structured failure diagnostic record to DB.

    Args:
        source: Origin label (e.g. ``"hook"``, ``"chat"``, ``"memory"``).
        operation: What was being done (e.g. ``"run_hook"``, ``"write_recall_quality"``).
        error_type: Exception type name.
        error_message: Human-readable error description.
        conversation_id: Optional conversation context.
        owner_id: Optional user context.
        extra: Optional additional structured data.
    """
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            db.add(FDModel(
                owner_id=owner_id,
                conversation_id=conversation_id,
                source=source,
                operation=operation,
                error_type=error_type,
                error_message=str(error_message)[:500],
                extra_data=extra or {},
                created_at=datetime.now(timezone.utc),
            ))
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to record failure diagnostic: %s", exc)


async def read_failure_diagnostics(
    limit: int = 50,
    owner_id: int | None = None,
) -> list[dict]:
    """Read the most recent N diagnostic records from DB.

    Args:
        limit: Maximum number of records to return (newest first).
        owner_id: If set, filter by owner.

    Returns:
        List of diagnostic dicts in reverse chronological order.
    """
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            q = select(FDModel)
            if owner_id is not None and owner_id > 0:
                q = q.where(FDModel.owner_id == owner_id)
            q = q.order_by(desc(FDModel.created_at)).limit(limit)
            r = await db.execute(q)
            rows = r.scalars().all()
            return [
                {
                    "timestamp": row.created_at.timestamp() if row.created_at else 0,
                    "source": row.source,
                    "operation": row.operation,
                    "error_type": row.error_type,
                    "error_message": row.error_message,
                    "conversation_id": row.conversation_id,
                    "owner_id": row.owner_id,
                    "extra": row.extra_data or {},
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning("Failed to read failure diagnostics: %s", exc)
        return []
