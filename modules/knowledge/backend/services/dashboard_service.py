"""Knowledge dashboard stats service.

Pure service layer: accepts db + user_id, returns dict.
Router layer is responsible for ApiResponse wrapping and auth.
"""
import logging

from app.models.file import File
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbDocument,
    KbEntityDictionary,
    KbFileRelation,
    KbGraphEdge,
)

logger = logging.getLogger("v2.knowledge").getChild("dashboard_service")

DEEP_STAGE_FIELDS = (
    KbDocument.raw_status,
    KbDocument.fusion_status,
    KbDocument.profile_status,
    KbDocument.graph_status,
    KbDocument.relation_status,
)


async def get_dashboard_stats(db: AsyncSession, user_id: int) -> dict:
    live_source_clause = exists(
        select(File.id).where(
            File.id == KbDocument.file_id,
            File.deleted.is_(False),
        )
    )
    unavailable_source_clause = ~live_source_clause

    total = (await db.execute(
        select(func.count(KbDocument.id)).where(KbDocument.deleted.is_(False), KbDocument.owner_id == user_id)
    )).scalar() or 0

    completed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            KbDocument.raw_status == "done",
            KbDocument.fusion_status == "done",
            KbDocument.profile_status == "done",
            KbDocument.graph_status == "done",
            KbDocument.relation_status == "done",
        )
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            or_(*(field.in_(("failed", "error")) for field in DEEP_STAGE_FIELDS)),
        )
    )).scalar() or 0

    partial = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            or_(*(field.in_(("degraded", "paused")) for field in DEEP_STAGE_FIELDS)),
            ~or_(*(field.in_(("failed", "error")) for field in DEEP_STAGE_FIELDS)),
        )
    )).scalar() or 0

    pending = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            and_(*(field == "pending" for field in DEEP_STAGE_FIELDS)),
        )
    )).scalar() or 0

    source_unavailable = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            unavailable_source_clause,
        )
    )).scalar() or 0

    running = max(0, total - completed - failed - partial - pending - source_unavailable)

    entity_count = (await db.execute(
        select(func.count(KbEntityDictionary.id)).where(KbEntityDictionary.owner_id == user_id)
    )).scalar() or 0

    relation_count = (await db.execute(
        select(func.count(KbGraphEdge.id)).where(KbGraphEdge.owner_id == user_id)
    )).scalar() or 0

    file_relation_count = (await db.execute(
        select(func.count(KbFileRelation.id)).where(KbFileRelation.owner_id == user_id)
    )).scalar() or 0

    duplicate_entities = 0
    dup_rows = await db.execute(
        select(KbEntityDictionary.name, func.count(KbEntityDictionary.id))
        .where(KbEntityDictionary.owner_id == user_id, KbEntityDictionary.status != "merged")
        .group_by(KbEntityDictionary.name)
        .having(func.count(KbEntityDictionary.id) > 1)
    )
    dup_groups = dup_rows.all()
    duplicate_entities = sum(cnt for _, cnt in dup_groups)

    cat_rows = await db.execute(
        select(KbEntityDictionary.category, func.count(KbEntityDictionary.id))
        .where(KbEntityDictionary.owner_id == user_id)
        .group_by(KbEntityDictionary.category)
        .order_by(func.count(KbEntityDictionary.id).desc())
    )
    entity_category_distribution = {cat: cnt for cat, cnt in cat_rows.all()}

    all_docs = await db.execute(
        select(KbDocument).where(KbDocument.deleted.is_(False), KbDocument.owner_id == user_id)
        .order_by(KbDocument.id.desc())
    )
    doc_progresses = []
    stuck_docs = []
    for d in all_docs.scalars().all():
        source_available = await db.scalar(
            select(
                exists(
                    select(File.id).where(
                        File.id == d.file_id,
                        File.deleted.is_(False),
                    )
                )
            )
        )
        source_state = "available" if source_available else (
            "source_file_deleted_or_missing" if d.file_id else "source_file_missing"
        )
        entry = {
            "id": d.id, "filename": d.filename, "total_pages": d.total_pages,
            "raw_status": d.raw_status, "fusion_status": d.fusion_status,
            "profile_status": getattr(d, "profile_status", "pending"),
            "graph_status": getattr(d, "graph_status", "pending"),
            "relation_status": getattr(d, "relation_status", "pending"),
            "parse_status": d.parse_status, "created_at": str(d.created_at or ""),
            "source_available": bool(source_available), "source_state": source_state,
        }
        doc_progresses.append(entry)
        if source_available and any(
            (getattr(d, attr, "pending") or "pending") in {"failed", "error"}
            for attr in ("raw_status", "fusion_status", "profile_status", "graph_status", "relation_status")
        ):
            stuck_docs.append(entry)

    recent = (await db.execute(
        select(KbDocument).where(
            KbDocument.deleted.is_(False), KbDocument.owner_id == user_id,
            live_source_clause,
            KbDocument.raw_status == "done",
            KbDocument.fusion_status == "done",
            KbDocument.profile_status == "done",
            KbDocument.graph_status == "done",
            KbDocument.relation_status == "done",
        )
        .order_by(KbDocument.updated_at.desc().nullslast())
        .limit(10)
    )).scalars().all()
    recent_completions = [
        {"id": d.id, "filename": d.filename, "completed_at": str(d.updated_at or "")}
        for d in recent
    ]

    return {
        "total_documents": total,
        "completed_documents": completed,
        "partial_documents": partial,
        "running_documents": running,
        "failed_documents": failed,
        "source_unavailable_documents": source_unavailable,
        "total_entities": entity_count,
        "total_graph_relations": relation_count,
        "total_file_relations": file_relation_count,
        "duplicate_entity_count": duplicate_entities,
        "duplicate_entity_groups": [{"name": name, "count": cnt} for name, cnt in dup_groups],
        "entity_category_distribution": entity_category_distribution,
        "document_progresses": doc_progresses,
        "stuck_documents": stuck_docs,
        "recent_completions": recent_completions,
    }
