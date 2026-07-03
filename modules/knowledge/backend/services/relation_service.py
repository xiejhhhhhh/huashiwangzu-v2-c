"""第7层 跨文件动态关联服务（★华哥最看重）。

新文件入库 → 自动跟已有文件建立关联边：文件画像向量相似度 + 实体共现度 → kb_file_relations。
增量计算：只算新文件与已有文件的关联，不全量重算。
逐边 commit，幂等可重入（已有边跳过，中断只丢当前边）。
"""
import logging

from app.database import AsyncSessionLocal
from app.services.task_worker import register_task_handler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbChunkEntity, KbDocument, KbDocumentProfile, KbEntityDictionary, KbFileRelation

logger = logging.getLogger("v2.knowledge").getChild("relation")


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """余弦相似度。"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _get_document_entity_ids(db: AsyncSession, document_id: int) -> set[int]:
    """获取文档关联的实体 ID 集合。"""
    r = await db.execute(
        select(KbChunkEntity.entity_id).where(KbChunkEntity.document_id == document_id)
    )
    return {row[0] for row in r.all()}


def _entity_overlap_score(entities_a: set[int], entities_b: set[int]) -> float:
    """实体共现 Jaccard 相似度。"""
    if not entities_a or not entities_b:
        return 0.0
    intersection = len(entities_a & entities_b)
    union = len(entities_a | entities_b)
    return intersection / union if union > 0 else 0.0


async def compute_file_relations(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict:
    """为新文件计算与已有文件的关联边（增量，逐边 commit，幂等可重入）。

    基于：文件画像向量余弦相似度(0.6权重) + 实体共现 Jaccard(0.4权重)。
    已有边（同 source/target）跳过，中断只丢当前边。
    """
    # 获取新文件画像
    r = await db.execute(
        select(KbDocumentProfile).where(KbDocumentProfile.document_id == document_id)
    )
    new_profile = r.scalar_one_or_none()
    if not new_profile or not new_profile.profile_embedding:
        logger.warning("No profile/embedding for document_id=%d, skipping relations", document_id)
        return {"document_id": document_id, "relations_created": 0}

    # 获取新文件的实体集合
    new_entities = await _get_document_entity_ids(db, document_id)

    # 获取已有关联边（幂等：正反两向都加载，跳过已存在的对）
    r = await db.execute(
        select(KbFileRelation.source_document_id, KbFileRelation.target_document_id)
        .where(
            (KbFileRelation.source_document_id == document_id)
            | (KbFileRelation.target_document_id == document_id)
        )
    )
    existing_edges = {(row[0], row[1]) for row in r.all()}

    # 获取所有已有文件画像（排除本文件）
    r = await db.execute(
        select(KbDocumentProfile).where(
            KbDocumentProfile.document_id != document_id,
            KbDocumentProfile.profile_embedding.isnot(None),
        )
    )
    existing_profiles = r.scalars().all()

    relations_created = 0
    for existing in existing_profiles:
        if not existing.profile_embedding:
            continue

        # 幂等：双向边成对创建,正向已存在即跳过整对
        fwd_edge = (document_id, existing.document_id)
        rev_edge = (existing.document_id, document_id)
        if fwd_edge in existing_edges or rev_edge in existing_edges:
            continue

        # 向量相似度
        vec_sim = _cosine_similarity(new_profile.profile_embedding, existing.profile_embedding)

        # 实体共现度
        existing_entities = await _get_document_entity_ids(db, existing.document_id)
        entity_sim = _entity_overlap_score(new_entities, existing_entities)

        # 综合分数（向量 0.6 + 实体 0.4）
        combined_score = round(vec_sim * 0.6 + entity_sim * 0.4, 4)

        # 阈值：综合 >0.15 才建边
        if combined_score < 0.15:
            continue

        # 确定关系类型
        if entity_sim > 0.3:
            relation_type = "entity_overlap"
        elif vec_sim > 0.8:
            relation_type = "semantic_similar"
        else:
            relation_type = "reference"

        # 共同实体名称
        shared_entity_names = []
        if new_entities and existing_entities:
            common = new_entities & existing_entities
            if common:
                ent_r = await db.execute(
                    select(KbEntityDictionary.name).where(
                        KbEntityDictionary.id.in_(list(common)[:10])
                    )
                )
                shared_entity_names = [row[0] for row in ent_r.all()]

        # 创建双向边
        for (src_id, tgt_id) in [(document_id, existing.document_id), (existing.document_id, document_id)]:
            relation = KbFileRelation(
                owner_id=owner_id,
                source_document_id=src_id,
                target_document_id=tgt_id,
                relation_type=relation_type,
                similarity_score=combined_score,
                shared_entities=shared_entity_names if src_id == document_id else None,
                evidence=f"向量相似度={vec_sim:.3f}, 实体共现={entity_sim:.3f}" if src_id == document_id else None,
                weight=combined_score,
            )
            db.add(relation)
            relations_created += 1

        # 逐对 commit：中断只丢当前边
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    logger.info("Created %d file relations for document_id=%d", relations_created, document_id)
    return {"document_id": document_id, "relations_created": relations_created}


async def get_file_relations(
    db: AsyncSession, document_id: int,
) -> list[dict]:
    """查询文件的关联边列表。"""
    r = await db.execute(
        select(KbFileRelation).where(KbFileRelation.source_document_id == document_id)
        .order_by(KbFileRelation.similarity_score.desc())
        .limit(50)
    )
    relations = r.scalars().all()

    # 补充目标文件名
    target_ids = list({rel.target_document_id for rel in relations})
    doc_names: dict[int, str] = {}
    if target_ids:
        doc_r = await db.execute(
            select(KbDocument.id, KbDocument.filename).where(KbDocument.id.in_(target_ids))
        )
        doc_names = {row[0]: row[1] for row in doc_r.all()}

    return [
        {
            "id": rel.id,
            "source_document_id": rel.source_document_id,
            "target_document_id": rel.target_document_id,
            "target_filename": doc_names.get(rel.target_document_id, ""),
            "relation_type": rel.relation_type,
            "similarity_score": rel.similarity_score,
            "shared_entities": rel.shared_entities,
            "evidence": rel.evidence,
            "weight": rel.weight,
            "created_at": rel.created_at.isoformat() if rel.created_at else None,
        }
        for rel in relations
    ]


async def get_relation_graph(db: AsyncSession, owner_id: int) -> dict:
    """获取知识网络全景（所有文件关联边的图结构）。"""
    r = await db.execute(
        select(KbFileRelation).where(KbFileRelation.owner_id == owner_id)
        .order_by(KbFileRelation.similarity_score.desc())
        .limit(200)
    )
    relations = r.scalars().all()

    # 收集文件
    doc_ids = set()
    for rel in relations:
        doc_ids.add(rel.source_document_id)
        doc_ids.add(rel.target_document_id)

    doc_r = await db.execute(
        select(KbDocument.id, KbDocument.filename).where(KbDocument.id.in_(doc_ids))
    )
    doc_names = {row[0]: row[1] for row in doc_r.all()}

    nodes = [{"id": did, "label": doc_names.get(did, f"Doc#{did}"), "type": "document"} for did in doc_ids]
    edges = [
        {
            "source": rel.source_document_id,
            "target": rel.target_document_id,
            "relation_type": rel.relation_type,
            "weight": rel.weight,
        }
        for rel in relations
    ]

    return {"nodes": nodes, "edges": edges}


# ── 框架任务 handler ────────────────────────────────


async def _relation_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_relation 任务。"""
    document_id = int(params.get("document_id", 0))
    if document_id <= 0:
        return {"error": "document_id required", "status": "failed"}

    async with AsyncSessionLocal() as db:
        df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = df.scalar_one_or_none()
        if not doc:
            return {"error": f"Document {document_id} not found", "status": "failed"}

        owner_id = doc.owner_id
        try:
            result = await compute_file_relations(db, document_id, owner_id)
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Relation handler failed for document_id=%d: %s", document_id, e)
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_relation", _relation_handler)
