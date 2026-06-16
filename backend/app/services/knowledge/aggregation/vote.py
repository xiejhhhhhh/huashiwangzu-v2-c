"""
L4 跨文件属性投票
同实体同属性名的不同值跨文件统计:
- 多数一致 >60% → 采用多数值, 标记 "majority_consistent"(原设计 v2 常用 confirmed 同义)
- 严重分歧 → 全部保留, 标记 "conflict"
"""
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Attribute

logger = logging.getLogger(__name__)

MAJORITY_THRESHOLD = 0.6


class VoteService:

    @staticmethod
    async def run_vote(db: AsyncSession, subject: str | None = None) -> dict:
        """对 subject 下所有未投票的属性执行投票; subject=None 则全量"""
        query = select(Attribute).where(Attribute.vote_status == "unvoted")
        if subject:
            query = query.where(Attribute.subject == subject)

        result = await db.execute(query)
        attributes = result.scalars().all()

        if not attributes:
            return {"processed": 0, "majority_consistent": 0, "conflict": 0}

        groups: dict[tuple[str, str], list[Attribute]] = {}
        for attr in attributes:
            key = (attr.subject, attr.attr_name)
            groups.setdefault(key, []).append(attr)

        majority_count = 0
        conflict_count = 0

        for key, group in groups.items():
            values = [a.attr_value.strip().lower() for a in group]
            counter = Counter(values)
            top_value, top_count = counter.most_common(1)[0]
            ratio = top_count / len(values)

            if ratio >= MAJORITY_THRESHOLD:
                majority_value = next(a.attr_value for a in group if a.attr_value.strip().lower() == top_value)

                for attr in group:
                    attr.vote_status = "majority_consistent"
                    attr.attr_value = majority_value
                majority_count += 1
                logger.info("Vote majority for %s.%s: %s (%.0f%%)", key[0], key[1], majority_value, ratio * 100)
            else:
                for attr in group:
                    attr.vote_status = "conflict"
                conflict_count += 1
                logger.warning("Vote conflict for %s.%s: values=%s", key[0], key[1], list(set(values)))

        await db.commit()
        return {
            "processed": len(attributes),
            "majority_consistent": majority_count,
            "conflict": conflict_count,
        }
