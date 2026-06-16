"""
L6 语义角色抽取服务
从融合正文/内容块中抽取 subject/predicate/object 三元组
"""
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import PageFusion, SemanticRole

logger = logging.getLogger(__name__)


class RoleExtractor:

    SIMPLE_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
        (re.compile(r"^(.+?)(是|属于|为|作为|构成)(.+)$"), "subject", "predicate", "object"),
        (re.compile(r"^(.+?)(包含|包括|有|含有|由)(.+)$"), "subject", "predicate", "object"),
        (re.compile(r"^(.+?)(生产|制造|研发|出品)(.+)$"), "subject", "predicate", "object"),
        (re.compile(r"^(.+?)(检测|检验|测试|实验)(.+)$"), "subject", "predicate", "object"),
        (re.compile(r"^(.+?)(注册|备案|申报)(.+)$"), "subject", "predicate", "object"),
    ]

    @staticmethod
    async def extract_from_fusion(db: AsyncSession, fusion_id: int | None = None) -> list[SemanticRole]:
        """从页级融合正文提取语义角色; fusion_id=None 则全量"""
        query = select(PageFusion)
        if fusion_id:
            query = query.where(PageFusion.id == fusion_id)
        result = await db.execute(query)
        fusions = result.scalars().all()

        roles: list[SemanticRole] = []
        for fusion in fusions:
            if not fusion.fusion_text:
                continue
            page_roles = RoleExtractor._parse(fusion.fusion_text, fusion_id=fusion.id)
            roles.extend(page_roles)

        if roles:
            db.add_all(roles)
            await db.commit()

        logger.info("Extracted %d semantic roles from %d fusions", len(roles), len(fusions))
        return roles

    @staticmethod
    def _parse(text: str, fusion_id: int | None = None) -> list[SemanticRole]:
        """用简单规则从文本中抽语义角色: subject + predicate + object"""
        roles: list[SemanticRole] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) > 200:
                continue

            for pattern, subj_type, pred_type, obj_type in RoleExtractor.SIMPLE_PATTERNS:
                m = pattern.match(line)
                if m:
                    subject_text = m.group(1).strip()
                    predicate_text = m.group(2).strip()
                    object_text = m.group(3).strip()
                    if subject_text:
                        roles.append(SemanticRole(
                            fusion_id=fusion_id, role_type=subj_type, role_value=subject_text[:200],
                        ))
                    if predicate_text:
                        roles.append(SemanticRole(
                            fusion_id=fusion_id, role_type=pred_type, role_value=predicate_text[:50],
                        ))
                    if object_text:
                        roles.append(SemanticRole(
                            fusion_id=fusion_id, role_type=obj_type, role_value=object_text[:200],
                        ))
                    break

        return roles

    @staticmethod
    async def get_roles_by_fusion(db: AsyncSession, fusion_id: int) -> list[SemanticRole]:
        result = await db.execute(
            select(SemanticRole).where(SemanticRole.fusion_id == fusion_id)
        )
        return list(result.scalars().all())
