"""知识库治理服务：候选治理、质量审计、实体合并、歧义处理、抽取校准、证据链审查。"""
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.knowledge").getChild("governance")


async def list_governance_candidates(
    db: AsyncSession,
    owner_id: int,
    audit_status: str = "pending",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """列出治理候选条目，支持按状态筛选。"""
    from ..models import KbGovernanceCandidate

    stmt = select(KbGovernanceCandidate).where(KbGovernanceCandidate.audit_status == audit_status)
    total_stmt = select(func.count(KbGovernanceCandidate.id)).where(KbGovernanceCandidate.audit_status == audit_status)
    if owner_id:
        stmt = stmt.where(KbGovernanceCandidate.owner_id == owner_id)
        total_stmt = total_stmt.where(KbGovernanceCandidate.owner_id == owner_id)
    stmt = stmt.order_by(KbGovernanceCandidate.confidence.asc(), KbGovernanceCandidate.created_at.desc())
    total_r = await db.execute(total_stmt)
    total = total_r.scalar() or 0

    offset = (page - 1) * page_size
    r = await db.execute(stmt.offset(offset).limit(page_size))
    candidates = r.scalars().all()

    return {
        "items": [
            {
                "id": c.id,
                "document_id": c.document_id,
                "entity_name": c.entity_name,
                "category": c.category,
                "excerpt": c.excerpt,
                "confidence": c.confidence,
                "audit_status": c.audit_status,
                "created_at": c.created_at,
            }
            for c in candidates
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def approve_candidate(db: AsyncSession, candidate_id: int, user_id: int) -> bool:
    """审批通过治理候选 → 标记 confirmed。"""
    from ..models import KbEntityDictionary, KbGovernanceCandidate

    c_r = await db.execute(
        select(KbGovernanceCandidate).where(KbGovernanceCandidate.id == candidate_id)
    )
    c = c_r.scalar_one_or_none()
    if not c:
        return False

    c.audit_status = "approved"
    c.reviewed_by = user_id
    c.reviewed_at = datetime.now(timezone.utc)

    # 同步更新实体词典状态
    ent_r = await db.execute(
        select(KbEntityDictionary).where(
            KbEntityDictionary.name == c.entity_name,
            KbEntityDictionary.owner_id == c.owner_id,
        ).limit(1)
    )
    ent = ent_r.scalars().first()
    if ent:
        ent.status = "confirmed"

    await db.commit()
    logger.info("Approved governance candidate %d: %s", candidate_id, c.entity_name)
    return True


async def reject_candidate(db: AsyncSession, candidate_id: int, user_id: int) -> bool:
    """驳回治理候选 → 标记 rejected。"""
    from ..models import KbEntityDictionary, KbGovernanceCandidate

    c_r = await db.execute(
        select(KbGovernanceCandidate).where(KbGovernanceCandidate.id == candidate_id)
    )
    c = c_r.scalar_one_or_none()
    if not c:
        return False

    c.audit_status = "rejected"
    c.reviewed_by = user_id
    c.reviewed_at = datetime.now(timezone.utc)

    # 同时归档实体词典条目
    ent_r = await db.execute(
        select(KbEntityDictionary).where(
            KbEntityDictionary.name == c.entity_name,
            KbEntityDictionary.owner_id == c.owner_id,
        ).limit(1)
    )
    ent = ent_r.scalars().first()
    if ent:
        ent.status = "archived"

    await db.commit()
    logger.info("Rejected governance candidate %d: %s", candidate_id, c.entity_name)
    return True


async def merge_entities(
    db: AsyncSession,
    source_entity_ids: list[int],
    target_entity_id: int,
    user_id: int,
    reason: str = "",
) -> bool:
    """合并实体：源实体 → 目标实体。"""
    from ..models import (
        KbChunkEntity,
        KbEntityAlias,
        KbEntityDictionary,
        KbEntityMergeLog,
        KbEvidence,
    )

    target_r = await db.execute(
        select(KbEntityDictionary).where(KbEntityDictionary.id == target_entity_id)
    )
    target = target_r.scalar_one_or_none()
    if not target:
        return False

    for src_id in source_entity_ids:
        if src_id == target_entity_id:
            continue
        src_r = await db.execute(
            select(KbEntityDictionary).where(KbEntityDictionary.id == src_id)
        )
        src = src_r.scalar_one_or_none()
        if not src:
            continue

        # 源名称 → 目标别名
        existing_alias = await db.execute(
            select(KbEntityAlias).where(
                KbEntityAlias.entity_id == target_entity_id,
                KbEntityAlias.alias == src.name,
            )
        )
        if not existing_alias.scalar_one_or_none():
            alias = KbEntityAlias(owner_id=target.owner_id, entity_id=target_entity_id, alias=src.name)
            db.add(alias)

        # 迁移 chunk-entity 关联
        ce_r = await db.execute(
            select(KbChunkEntity).where(KbChunkEntity.entity_id == src_id)
        )
        for ce in ce_r.scalars().all():
            existing_ce = await db.execute(
                select(KbChunkEntity).where(
                    KbChunkEntity.chunk_id == ce.chunk_id,
                    KbChunkEntity.entity_id == target_entity_id,
                )
            )
            if not existing_ce.scalar_one_or_none():
                ce.entity_id = target_entity_id

        # 迁移证据
        ev_r = await db.execute(
            select(KbEvidence).where(KbEvidence.entity_id == src_id)
        )
        for ev in ev_r.scalars().all():
            ev.entity_id = target_entity_id

        # 标记源为 merged
        src.status = "merged"

    # 记录合并操作
    log = KbEntityMergeLog(
        owner_id=target.owner_id,
        source_entity_ids=source_entity_ids,
        target_entity_id=target_entity_id,
        merged_by=user_id,
        reason=reason or "人工合并",
    )
    db.add(log)
    await db.commit()
    logger.info("Merged %d entities into entity_id=%d", len(source_entity_ids), target_entity_id)
    return True


async def get_pending_count(db: AsyncSession, owner_id: int | None = None) -> int:
    """获取待确认的治理候选数量。"""
    from ..models import KbGovernanceCandidate

    stmt = select(func.count(KbGovernanceCandidate.id)).where(KbGovernanceCandidate.audit_status == "pending")
    if owner_id is not None:
        stmt = stmt.where(KbGovernanceCandidate.owner_id == owner_id)
    r = await db.execute(stmt)
    return r.scalar() or 0


async def get_evidence_detail(db: AsyncSession, owner_id: int, entity_id: int) -> list[dict]:
    """查询某实体的证据详情。"""
    from ..models import KbEvidence

    r = await db.execute(
        select(KbEvidence)
        .where(KbEvidence.entity_id == entity_id, KbEvidence.owner_id == owner_id)
        .order_by(KbEvidence.page, KbEvidence.created_at)
    )
    evidences = r.scalars().all()
    return [
        {
            "id": e.id,
            "entity_id": e.entity_id,
            "document_id": e.document_id,
            "chunk_id": e.chunk_id,
            "page": e.page,
            "excerpt": e.excerpt,
            "confidence": e.confidence,
            "status": e.status,
        }
        for e in evidences
    ]


async def calibrate_extraction(
    db: AsyncSession,
    candidate_id: int,
    new_name: str | None = None,
    new_category: str | None = None,
    user_id: int | None = None,
) -> bool:
    """校准抽取结果：修改实体名或类别。"""
    from ..models import KbEntityDictionary, KbGovernanceCandidate

    c_r = await db.execute(
        select(KbGovernanceCandidate).where(KbGovernanceCandidate.id == candidate_id)
    )
    c = c_r.scalar_one_or_none()
    if not c:
        return False

    if new_name:
        c.entity_name = new_name
    if new_category:
        c.category = new_category

    # 同步更新实体词典
    ent_r = await db.execute(
        select(KbEntityDictionary).where(
            KbEntityDictionary.name == c.entity_name,
            KbEntityDictionary.owner_id == c.owner_id,
        )
    )
    for ent in ent_r.scalars().all():
        if new_name:
            ent.name = new_name
        if new_category:
            ent.category = new_category

    await db.commit()
    return True
