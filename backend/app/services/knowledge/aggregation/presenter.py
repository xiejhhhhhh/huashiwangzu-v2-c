from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Attribute, DisambigCandidate, Entity, GraphEdge, GraphNode
from app.services.knowledge.governance_presenter import edge_dict, entity_dict


def attribute_dict(attr: Attribute) -> dict:
    return {
        "id": attr.id,
        "name": attr.attr_name,
        "value": attr.attr_value,
        "sourcePage": attr.source_page,
        "evidence": attr.evidence,
        "voteStatus": attr.vote_status,
    }


async def build_entity_aggregation(db: AsyncSession, entity_id: int) -> dict | None:
    entity = await db.get(Entity, entity_id)
    if not entity:
        return None

    attr_rows = await db.execute(
        select(Attribute).where(Attribute.subject == entity.standard_name)
    )
    node = (
        await db.execute(select(GraphNode).where(GraphNode.entity_id == entity_id))
    ).scalar_one_or_none()
    edges = []
    if node:
        edge_rows = await db.execute(
            select(GraphEdge).where(
                or_(GraphEdge.from_node_id == node.id, GraphEdge.to_node_id == node.id)
            )
        )
        edges = [edge_dict(edge) for edge in edge_rows.scalars().all()]

    merge_rows = await db.execute(
        select(DisambigCandidate)
        .where(
            or_(
                DisambigCandidate.entity_a_id == entity_id,
                DisambigCandidate.entity_b_id == entity_id,
            ),
            DisambigCandidate.review_status == "pending",
        )
        .order_by(DisambigCandidate.confidence.desc())
    )
    attrs = [attribute_dict(attr) for attr in attr_rows.scalars().all()]
    return {
        "实体": entity_dict(entity),
        "属性聚合": attrs,
        "关系聚合": edges,
        "合并建议": [
            {
                "id": item.id,
                "entityAId": item.entity_a_id,
                "entityBId": item.entity_b_id,
                "cooccurrence": item.cooccurrence,
                "confidence": item.confidence,
                "reviewStatus": item.review_status,
            }
            for item in merge_rows.scalars().all()
        ],
        "冲突建议": [attr for attr in attrs if attr["voteStatus"] == "conflict"],
    }
