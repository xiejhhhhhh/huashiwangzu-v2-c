"""Attribute service — write attributes with source, evidence, and vote status."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.attribute import Attribute


async def create_attribute(
    db: AsyncSession,
    subject: str,
    attr_name: str,
    attr_value: str,
    source_page: int | None = None,
    evidence: dict | None = None,
    vote_status: str = "unvoted",
) -> Attribute:
    attr = Attribute(
        subject=subject,
        attr_name=attr_name,
        attr_value=attr_value,
        source_page=source_page,
        evidence=evidence or {},
        vote_status=vote_status,
    )
    db.add(attr)
    await db.flush()
    return attr


async def find_attributes_by_subject(
    db: AsyncSession,
    subject: str,
    attr_name: str | None = None,
) -> list[Attribute]:
    stmt = select(Attribute).where(Attribute.subject == subject)
    if attr_name:
        stmt = stmt.where(Attribute.attr_name == attr_name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def upsert_attribute(
    db: AsyncSession,
    subject: str,
    attr_name: str,
    attr_value: str,
    source_page: int | None = None,
    evidence: dict | None = None,
) -> Attribute:
    existing_list = await find_attributes_by_subject(db, subject, attr_name)
    for existing in existing_list:
        if existing.attr_value == attr_value:
            existing.vote_status = "confirmed"
            return existing

    return await create_attribute(
        db, subject, attr_name, attr_value,
        source_page, evidence, "unvoted",
    )


async def create_attribute_from_candidate(
    db: AsyncSession,
    subject: str,
    attr_name: str,
    attr_value: str,
    source_page: int | None = None,
    evidence_text: str = "",
) -> Attribute:
    evidence = {}
    if evidence_text:
        evidence["source"] = evidence_text
    if source_page:
        evidence["page"] = source_page

    return await upsert_attribute(
        db, subject, attr_name, attr_value,
        source_page, evidence,
    )
