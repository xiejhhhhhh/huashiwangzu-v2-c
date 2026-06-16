"""
L7 标签管理服务
- 创建/查询/更新标签
- 标签始终走准入门
"""
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models.knowledge import Catalog, Label, PageFusion
from app.services.knowledge.label.admission import AdmissionGate
from app.services.knowledge.label.candidates import (
    catalog_label_candidates,
    dedupe_candidates,
    fusion_label_candidates,
)

logger = logging.getLogger(__name__)


class LabelService:

    @staticmethod
    async def create_label(
        db: AsyncSession,
        target_type: str,
        target_id: int,
        label: str,
        category: str | None = None,
    ) -> tuple[Label | None, str]:
        """创建标签, 走准入门, 已存在则跳过. 返回 (Label or None, reason)"""
        label_stripped = label.strip()
        existing = await db.execute(
            select(Label).where(
                and_(Label.target_type == target_type, Label.target_id == target_id, Label.label == label_stripped)
            )
        )
        if existing.scalar_one_or_none():
            return None, "skipped: already exists"

        passed, reason = AdmissionGate.check(label, category)
        label_obj = Label(
            target_type=target_type,
            target_id=target_id,
            label=label_stripped,
            label_category=category,
            passed_admission=passed,
        )
        db.add(label_obj)
        await db.commit()
        await db.refresh(label_obj)
        return label_obj, reason

    @staticmethod
    async def bulk_create(
        db: AsyncSession,
        target_type: str,
        target_id: int,
        labels: list[str],
        category: str | None = None,
    ) -> list[dict]:
        """批量创建标签, 返回 {label, passed, reason}；跳过已存在的标签"""
        existing = await db.execute(
            select(Label.label).where(
                and_(Label.target_type == target_type, Label.target_id == target_id)
            )
        )
        existing_labels = {r[0] for r in existing.all()}

        items = [{"label": l, "category_hint": category} for l in labels if l.strip() not in existing_labels]
        checks = AdmissionGate.batch_check(items)
        created = []
        for check in checks:
            label_obj = Label(
                target_type=target_type,
                target_id=target_id,
                label=check["label"],
                label_category=category,
                passed_admission=check["passed"],
            )
            db.add(label_obj)
            created.append({
                "label": check["label"],
                "passed": check["passed"],
                "reason": check["reason"],
            })
        await db.commit()
        return created

    @staticmethod
    async def get_labels(
        db: AsyncSession,
        target_type: str | None = None,
        target_id: int | None = None,
        only_admitted: bool = False,
    ) -> list[Label]:
        query = select(Label)
        if target_type:
            query = query.where(Label.target_type == target_type)
        if target_id:
            query = query.where(Label.target_id == target_id)
        if only_admitted:
            query = query.where(Label.passed_admission == True)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_labels_by_target(
        db: AsyncSession, target_type: str, target_id: int
    ) -> list[Label]:
        result = await db.execute(
            select(Label).where(
                and_(Label.target_type == target_type, Label.target_id == target_id)
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_label(db: AsyncSession, label_id: int) -> bool:
        label = await db.get(Label, label_id)
        if not label:
            return False
        await db.delete(label)
        await db.commit()
        return True

    @staticmethod
    async def index_file_labels(db: AsyncSession, catalog_id: int) -> dict:
        catalog = await db.get(Catalog, catalog_id)
        if not catalog:
            raise NotFound(f"Catalog {catalog_id} not found")
        candidates = catalog_label_candidates(catalog)
        result = await db.execute(
            select(PageFusion).where(PageFusion.catalog_id == catalog_id).order_by(PageFusion.page_num)
        )
        for fusion in result.scalars().all():
            candidates.extend(fusion_label_candidates(fusion))
        labels = dedupe_candidates(candidates)
        created = await LabelService.bulk_create(db, "file", catalog_id, labels)
        admitted = sum(1 for item in created if item["passed"])
        return {
            "catalogId": catalog_id,
            "candidateCount": len(labels),
            "createdCount": len(created),
            "admittedCount": admitted,
            "items": created,
        }
