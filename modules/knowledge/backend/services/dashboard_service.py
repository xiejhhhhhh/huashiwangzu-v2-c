"""Knowledge dashboard stats service.

Pure service layer: accepts db + user_id, returns dict.
Router layer is responsible for ApiResponse wrapping and auth.
"""
import logging
from sqlalchemy import select, func, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbDocument, KbEntityDictionary, KbGraphEdge,
    KbFileRelation, KbGovernanceCandidate, KbDocumentProfile,
)

logger = logging.getLogger("v2.knowledge").getChild("dashboard_service")


async def get_dashboard_stats(db: AsyncSession, user_id: int) -> dict:
    total = (await db.execute(
        select(func.count(KbDocument.id)).where(KbDocument.deleted == False, KbDocument.owner_id == user_id)
    )).scalar() or 0

    completed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user_id,
            KbDocument.fusion_status == "done",
            exists(
                select(KbDocumentProfile.id).where(
                    KbDocumentProfile.document_id == KbDocument.id
                )
            ),
        )
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user_id,
            or_(KbDocument.raw_status == "failed", KbDocument.fusion_status == "failed"),
        )
    )).scalar() or 0

    pending = (await db.execute(
        select(func.count(KbDocument.id)).where(
            KbDocument.deleted == False, KbDocument.owner_id == user_id,
            KbDocument.raw_status == "pending", KbDocument.fusion_status == "pending",
        )
    )).scalar() or 0

    running = total - completed - failed - pending

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
        select(KbDocument).where(KbDocument.deleted == False, KbDocument.owner_id == user_id)
        .order_by(KbDocument.id.desc())
    )
    doc_progresses = []
    stuck_docs = []
    for d in all_docs.scalars().all():
        entry = {
            "id": d.id, "filename": d.filename, "total_pages": d.total_pages,
            "raw_status": d.raw_status, "fusion_status": d.fusion_status,
            "parse_status": d.parse_status, "created_at": str(d.created_at or ""),
        }
        doc_progresses.append(entry)
        if d.raw_status == "failed" or d.fusion_status == "failed":
            stuck_docs.append(entry)

    recent = (await db.execute(
        select(KbDocument).where(
            KbDocument.deleted == False, KbDocument.owner_id == user_id,
            KbDocument.fusion_status == "done",
            exists(
                select(KbDocumentProfile.id).where(
                    KbDocumentProfile.document_id == KbDocument.id
                )
            ),
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
        "running_documents": running,
        "failed_documents": failed,
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
