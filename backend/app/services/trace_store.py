"""Span recording and trace query — stores to system_trace_spans table.

trace_id and parent_span_id flow through a contextvar (`_trace_ctx_var`)
that middleware (logging_middleware) initialises per-request and
call_capability / emit_module_event propagate as they create child spans.
"""

import uuid
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from dataclasses import dataclass

from app.database import AsyncSessionLocal
from app.models.system_trace import SystemTraceSpan
from sqlalchemy import select

logger = logging.getLogger("v2.trace_store")


@dataclass
class SpanContext:
    trace_id: str
    span_id: str | None = None  # None = root (no active span yet)


_trace_ctx_var: ContextVar[SpanContext | None] = ContextVar("_trace_ctx", default=None)


def get_trace_ctx() -> SpanContext | None:
    return _trace_ctx_var.get()


def set_trace_ctx(ctx: SpanContext | None):
    _trace_ctx_var.set(ctx)


def reset_trace_ctx(token):
    if token is not None:
        _trace_ctx_var.reset(token)


def make_span_id() -> str:
    return uuid.uuid4().hex[:12]


async def start_span(
    span_name: str,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    metadata: dict | None = None,
    owner_id: int = 0,
) -> str:
    """Create a new span record, return span_id.

    If trace_id is None, reads from current contextvar.
    If parent_span_id is None, reads current span_id from contextvar as parent.
    """
    ctx = get_trace_ctx()
    if trace_id is None:
        trace_id = ctx.trace_id if ctx else uuid.uuid4().hex[:16]
    if parent_span_id is None:
        parent_span_id = ctx.span_id if ctx else None

    span_id = make_span_id()
    now = datetime.now(timezone.utc)
    span = SystemTraceSpan(
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        span_name=span_name,
        start_ms=now,
        duration_ms=0,
        status="ok",
        span_metadata=metadata,
        owner_id=owner_id,
    )
    async with AsyncSessionLocal() as db:
        db.add(span)
        await db.commit()
        await db.refresh(span)
        db_span_id = span.id

    logger.debug("Span start: %s trace=%s parent=%s", span_name, trace_id, parent_span_id)
    return str(db_span_id)


async def end_span(
    span_id: str | int,
    status: str = "ok",
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Finalize a span — set duration_ms, status, error."""
    duration_ms = 0
    async with AsyncSessionLocal() as db:
        try:
            sid = int(span_id)
            span = await db.get(SystemTraceSpan, sid)
            if span:
                duration_ms = int((datetime.now(timezone.utc) - span.start_ms).total_seconds() * 1000)
                span.duration_ms = duration_ms
                span.status = status
                if error:
                    span.error = error
                if metadata:
                    span.span_metadata = metadata
                await db.commit()
        except (ValueError, SystemTraceSpan.__class__ is type):
            logger.warning("end_span: invalid span_id=%s", span_id)

    logger.debug("Span end: span=%s status=%s duration=%dms", span_id, status, duration_ms)


async def get_trace_tree(trace_id: str) -> list[dict]:
    """Return all spans for a trace_id, assembled into a parent-child tree."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(SystemTraceSpan)
            .where(SystemTraceSpan.trace_id == trace_id)
            .order_by(SystemTraceSpan.id)
        )
        spans = r.scalars().all()

    span_dict: dict[str, dict] = {}
    roots: list[dict] = []

    for s in spans:
        node = {
            "span_id": str(s.id),
            "parent_span_id": s.parent_span_id,
            "span_name": s.span_name,
            "start_ms": s.start_ms.isoformat() if s.start_ms else None,
            "duration_ms": s.duration_ms,
            "status": s.status,
            "error": s.error,
            "metadata": s.span_metadata,
            "owner_id": s.owner_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "children": [],
        }
        span_dict[str(s.id)] = node

    # Build tree by linking children to parents
    for sid, node in span_dict.items():
        pid = node["parent_span_id"]
        if pid and pid in span_dict:
            span_dict[pid]["children"].append(node)
        else:
            roots.append(node)

    return roots
