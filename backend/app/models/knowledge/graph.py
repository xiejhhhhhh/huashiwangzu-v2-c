from sqlalchemy import String, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base, TimestampMixin


class GraphNode(Base, TimestampMixin):
    __tablename__ = "knowledge_graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="entity/concept/category")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0, comment="For disambiguation")


class GraphEdge(Base, TimestampMixin):
    __tablename__ = "knowledge_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_graph_nodes.id", ondelete="CASCADE"), nullable=False)
    relation: Mapped[str] = mapped_column(String(128), nullable=False)
    support_chunk_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Chunk IDs for evidence trace")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
