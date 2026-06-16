"""
L4 跨文档消歧候选生成
扫描不同文档中出现的同名/近似名实体对, 计算共现频率与相似度, 写入 disambig_candidates
"""
import logging
import itertools

from rapidfuzz.distance import Levenshtein
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Entity, EntityAlias, DisambigCandidate

logger = logging.getLogger(__name__)


def _calc_similarity(name_a: str, name_b: str) -> float:
    """综合相似度: 精确相等=1.0, 子串包含=0.9, 其余用 Levenshtein"""
    na, nb = name_a.strip().lower(), name_b.strip().lower()
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    prefix_a = na[:4] if len(na) > 4 else na
    prefix_b = nb[:4] if len(nb) > 4 else nb
    return max(
        Levenshtein.normalized_similarity(na, nb),
        Levenshtein.normalized_similarity(prefix_a, prefix_b),
    )


class DisambiguationService:

    @staticmethod
    async def scan_candidates(db: AsyncSession) -> list[DisambigCandidate]:
        """扫所有已确认+待审核的实体, 两两计算相似度, 生成消歧候选"""
        result = await db.execute(
            select(Entity).where(Entity.confirm_status.in_(["confirmed", "pending"]))
        )
        entities = result.scalars().all()

        if len(entities) < 2:
            logger.info("Less than 2 entities, skipping disambiguation scan")
            return []

        seen_pairs: set[tuple[int, int]] = set()
        existing = await db.execute(
            select(DisambigCandidate.entity_a_id, DisambigCandidate.entity_b_id)
        )
        for row in existing.all():
            seen_pairs.add((row.entity_a_id, row.entity_b_id))

        # 批量加载实体别名（避免 N+1）
        alias_rows = await db.execute(
            select(EntityAlias.entity_id, EntityAlias.alias)
        )
        alias_map: dict[int, list[str]] = {}
        for row in alias_rows.all():
            alias_map.setdefault(row.entity_id, []).append(row.alias)

        # 构建 (实体ID → 所有名称列表) 映射
        name_map: dict[int, list[str]] = {
            e.id: [e.standard_name] + alias_map.get(e.id, []) for e in entities
        }

        pair_sim: dict[tuple[int, int], float] = {}
        for ea, eb in itertools.combinations(entities, 2):
            key = (ea.id, eb.id)
            if key in seen_pairs or (eb.id, ea.id) in seen_pairs:
                continue
            sim = _calc_similarity(ea.standard_name, eb.standard_name)
            if sim < 0.5:
                continue
            pair_sim[key] = sim

        if not pair_sim:
            return []

        # 单条 SQL 批量计算所有候选对的所有名称组合共现
        union_parts = []
        bind_idx = 0
        bind_params: dict[str, str] = {}
        idx_to_key: dict[int, tuple[int, int]] = {}

        for (eid_a, eid_b), sim in pair_sim.items():
            for name_a in name_map[eid_a]:
                for name_b in name_map[eid_b]:
                    p_na = f"na_{bind_idx}"
                    p_nb = f"nb_{bind_idx}"
                    union_parts.append(
                        f"SELECT COALESCE((SELECT COUNT(DISTINCT a.catalog_id) "
                        f"FROM knowledge_page_fusions a "
                        f"JOIN knowledge_page_fusions b ON a.catalog_id = b.catalog_id "
                        f"WHERE a.fusion_text ILIKE '%' || :{p_na} || '%' "
                        f"AND b.fusion_text ILIKE '%' || :{p_nb} || '%' "
                        f"AND a.id != b.id), 0) AS cnt"
                    )
                    bind_params[p_na] = name_a
                    bind_params[p_nb] = name_b
                    idx_to_key[bind_idx] = (eid_a, eid_b)
                    bind_idx += 1

        if not union_parts:
            return []

        batch_sql = sa_text(" UNION ALL ".join(union_parts))
        batch_result = await db.execute(batch_sql, bind_params)
        rows = batch_result.all()

        cooccur_map: dict[tuple[int, int], int] = {}
        for i, row in enumerate(rows):
            eid_a, eid_b = idx_to_key[i]
            cooccur_map[(eid_a, eid_b)] = cooccur_map.get((eid_a, eid_b), 0) + (row.cnt or 0)

        candidates: list[DisambigCandidate] = []
        for (eid_a, eid_b), sim in pair_sim.items():
            cooccur = cooccur_map.get((eid_a, eid_b), 0)
            confidence = min(sim * (1.0 + 0.1 * min(cooccur, 5)), 0.99)
            candidates.append(DisambigCandidate(
                entity_a_id=eid_a, entity_b_id=eid_b,
                cooccurrence=cooccur,
                confidence=round(confidence, 4),
                review_status="pending",
            ))

        if candidates:
            db.add_all(candidates)
            await db.commit()
            for c in candidates:
                await db.refresh(c)

        logger.info("Generated %d disambiguation candidates", len(candidates))
        return candidates

    @staticmethod
    async def _count_cooccurrence(db: AsyncSession, name_a: str, name_b: str) -> int:
        """统计两个实体名在同一文件不同页的共现次数"""
        sql = sa_text("""
            SELECT COUNT(DISTINCT a.catalog_id)
            FROM knowledge_page_fusions a
            JOIN knowledge_page_fusions b ON a.catalog_id = b.catalog_id
            WHERE a.fusion_text ILIKE :na AND b.fusion_text ILIKE :nb
              AND a.id != b.id
        """)
        result = await db.execute(sql, {"na": f"%{name_a}%", "nb": f"%{name_b}%"})
        return result.scalar() or 0
