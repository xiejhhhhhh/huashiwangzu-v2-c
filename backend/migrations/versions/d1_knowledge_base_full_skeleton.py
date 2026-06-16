"""D1 - knowledge base full table skeleton (19 tables)

Revision ID: d10000000001
Revises: 9a8b7c6d5e4f
Create Date: 2026-06-15 06:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = "d10000000001"
down_revision: Union[str, Sequence[str], None] = "9a8b7c6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Extend existing catalogs (no cross-dependency) ──
    op.add_column("catalogs", sa.Column("file_hash", sa.String(64), nullable=True, comment="MD5 hash for dedup"))
    op.add_column("catalogs", sa.Column("channel_type", sa.String(32), nullable=False, server_default="auto", comment="ingestion channel: auto/upload/import/api"))
    op.create_unique_constraint("uq_catalogs_file_hash", "catalogs", ["file_hash"])
    op.create_index("ix_catalogs_file_hash", "catalogs", ["file_hash"])
    op.create_index("ix_catalogs_status", "catalogs", ["status"])
    op.create_index("ix_catalogs_owner_id", "catalogs", ["owner_id"])
    op.create_index("ix_catalogs_channel_type", "catalogs", ["channel_type"])

    # ── All new tables created before extending chunks (FK to page_fusions) ──
    # ── knowledge_page_sources ──
    op.create_table("knowledge_page_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False, comment="script/ocr/vision/layout"),
        sa.Column("content", postgresql.JSONB, nullable=False, comment="Raw content JSON per source type"),
        sa.Column("screenshot_md5", sa.String(64), nullable=True, comment="Screenshot MD5 for dedup"),
        sa.Column("verify_status", sa.String(16), nullable=False, server_default="pending", comment="pending/verified/failed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", "page_num", "source_type", name="uq_page_source"),
    )
    op.create_index("ix_page_sources_catalog_id", "knowledge_page_sources", ["catalog_id"])
    op.create_index("ix_page_sources_catalog_page", "knowledge_page_sources", ["catalog_id", "page_num"])
    op.create_index("ix_page_sources_screenshot_md5", "knowledge_page_sources", ["screenshot_md5"])

    # ── knowledge_page_fusions ──
    op.create_table("knowledge_page_fusions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=False),
        sa.Column("fusion_text", sa.Text(), nullable=True, comment="Fused body text"),
        sa.Column("summary", sa.Text(), nullable=True, comment="Page summary"),
        sa.Column("attributes", postgresql.JSONB, nullable=True),
        sa.Column("labels", postgresql.JSONB, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        sa.Column("conflicts", postgresql.JSONB, nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", "page_num", name="uq_page_fusion"),
    )
    op.create_index("ix_page_fusions_catalog_id", "knowledge_page_fusions", ["catalog_id"])
    op.create_index("ix_page_fusions_catalog_page", "knowledge_page_fusions", ["catalog_id", "page_num"])

    # ── knowledge_chunk_vectors ──
    op.create_table("knowledge_chunk_vectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False, comment="e.g. bge-m3-v1"),
        sa.Column("dim", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("normalized", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunk_vectors_chunk_id", "knowledge_chunk_vectors", ["chunk_id"])
    op.create_index("ix_chunk_vectors_model_version", "knowledge_chunk_vectors", ["model_version"])

    # ── knowledge_entities ──
    op.create_table("knowledge_entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("standard_name", sa.String(256), nullable=False, comment="Canonical entity name"),
        sa.Column("entity_type", sa.String(64), nullable=False, comment="brand/product/ingredient/effect/organization"),
        sa.Column("confirm_status", sa.String(16), nullable=False, server_default="pending", comment="confirmed/pending/rejected"),
        sa.Column("pinyin", sa.String(512), nullable=True, comment="Pinyin for fuzzy matching"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entities_standard_name", "knowledge_entities", ["standard_name"])
    op.create_index("ix_entities_entity_type", "knowledge_entities", ["entity_type"])
    op.create_index("ix_entities_confirm_status", "knowledge_entities", ["confirm_status"])

    # ── knowledge_entity_aliases ──
    op.create_table("knowledge_entity_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(256), nullable=False),
        sa.Column("alias_type", sa.String(32), nullable=False, server_default="synonym", comment="synonym/abbreviation/typo/legacy"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_aliases_entity_id", "knowledge_entity_aliases", ["entity_id"])
    op.create_index("ix_entity_aliases_alias", "knowledge_entity_aliases", ["alias"])

    # ── knowledge_entity_merges ──
    op.create_table("knowledge_entity_merges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_entity_id", sa.Integer(), nullable=True),
        sa.Column("to_entity_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reverse_map", postgresql.JSONB, nullable=True, comment="Reverse mapping for rollback"),
        sa.Column("merged_at", sa.String(32), nullable=False, comment="ISO timestamp or version"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_entity_id"], ["knowledge_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_merges_from", "knowledge_entity_merges", ["from_entity_id"])
    op.create_index("ix_entity_merges_to", "knowledge_entity_merges", ["to_entity_id"])

    # ── knowledge_attributes ──
    op.create_table("knowledge_attributes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(256), nullable=False, comment="Subject entity or concept"),
        sa.Column("attr_name", sa.String(128), nullable=False),
        sa.Column("attr_value", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=True),
        sa.Column("vote_status", sa.String(16), nullable=False, server_default="unvoted", comment="unvoted/confirmed/rejected/conflict"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attributes_subject", "knowledge_attributes", ["subject"])
    op.create_index("ix_attributes_attr_name", "knowledge_attributes", ["attr_name"])
    op.create_index("ix_attributes_vote_status", "knowledge_attributes", ["vote_status"])

    # ── knowledge_extract_candidates ──
    op.create_table("knowledge_extract_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False, comment="Candidate content / value"),
        sa.Column("source", sa.String(256), nullable=True, comment="Source description"),
        sa.Column("evidence_page", sa.String(128), nullable=True, comment="Source page info"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("verdict_status", sa.Integer(), nullable=False, server_default="0", comment="0=pending/1=confirmed/2=ignored/3=archived"),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extract_candidates_verdict_status", "knowledge_extract_candidates", ["verdict_status"])
    op.create_index("ix_extract_candidates_content", "knowledge_extract_candidates", ["content"], postgresql_using="hash")

    # ── knowledge_disambig_candidates ──
    op.create_table("knowledge_disambig_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_a_id", sa.Integer(), nullable=False),
        sa.Column("entity_b_id", sa.Integer(), nullable=False),
        sa.Column("cooccurrence", sa.Integer(), nullable=False, server_default="0", comment="Co-occurrence frequency"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="pending", comment="pending/approved/rejected"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entity_a_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_b_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_disambig_candidates_pair", "knowledge_disambig_candidates", ["entity_a_id", "entity_b_id"])
    op.create_index("ix_disambig_candidates_review_status", "knowledge_disambig_candidates", ["review_status"])

    # ── knowledge_graph_nodes ──
    op.create_table("knowledge_graph_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.String(64), nullable=False, comment="entity/concept/category"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0", comment="For disambiguation"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["knowledge_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_nodes_entity_id", "knowledge_graph_nodes", ["entity_id"])
    op.create_index("ix_graph_nodes_node_type", "knowledge_graph_nodes", ["node_type"])

    # ── knowledge_graph_edges ──
    op.create_table("knowledge_graph_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(128), nullable=False),
        sa.Column("support_chunk_ids", postgresql.JSONB, nullable=True, comment="Chunk IDs for evidence trace"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["knowledge_graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_node_id"], ["knowledge_graph_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_edges_from", "knowledge_graph_edges", ["from_node_id"])
    op.create_index("ix_graph_edges_to", "knowledge_graph_edges", ["to_node_id"])
    op.create_index("ix_graph_edges_relation", "knowledge_graph_edges", ["relation"])

    # ── knowledge_semantic_roles ──
    op.create_table("knowledge_semantic_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("fusion_id", sa.Integer(), nullable=True),
        sa.Column("role_type", sa.String(64), nullable=False, comment="e.g. subject/predicate/object"),
        sa.Column("role_value", sa.Text(), nullable=False, comment="Role text value"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fusion_id"], ["knowledge_page_fusions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_roles_chunk_id", "knowledge_semantic_roles", ["chunk_id"])
    op.create_index("ix_semantic_roles_fusion_id", "knowledge_semantic_roles", ["fusion_id"])
    op.create_index("ix_semantic_roles_role_type", "knowledge_semantic_roles", ["role_type"])

    # ── knowledge_labels ──
    op.create_table("knowledge_labels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False, comment="file/entity/vision"),
        sa.Column("target_id", sa.Integer(), nullable=False, comment="ID of the target"),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("label_category", sa.String(64), nullable=True, comment="brand/product/effect etc."),
        sa.Column("passed_admission", sa.Boolean(), nullable=False, server_default=sa.text("false"), comment="Admission gate passed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_labels_target", "knowledge_labels", ["target_type", "target_id"])
    op.create_index("ix_labels_label", "knowledge_labels", ["label"])
    op.create_index("ix_labels_passed_admission", "knowledge_labels", ["passed_admission"])

    # ── knowledge_evidences ──
    op.create_table("knowledge_evidences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False, comment="script/ocr/vision/fusion"),
        sa.Column("source_id", sa.Integer(), nullable=False, comment="ID in the source table"),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cross_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidences_catalog_id", "knowledge_evidences", ["catalog_id"])
    op.create_index("ix_evidences_source", "knowledge_evidences", ["source_type", "source_id"])
    op.create_index("ix_evidences_cross_verified", "knowledge_evidences", ["cross_verified"])

    # ── knowledge_tasks ──
    op.create_table("knowledge_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False, comment="extract/fuse/chunk/vectorize/candidate/resolve"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", comment="pending/processing/done/failed"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0", comment="0-100"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_tasks_status_lease", "knowledge_tasks", ["status", "lease_until"])
    op.create_index("ix_knowledge_tasks_catalog_id", "knowledge_tasks", ["catalog_id"])
    op.create_index("ix_knowledge_tasks_task_type", "knowledge_tasks", ["task_type"])

    # ── knowledge_llm_logs ──
    op.create_table("knowledge_llm_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("caller", sa.String(128), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("user_input", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("parse_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_logs_caller", "knowledge_llm_logs", ["caller"])
    op.create_index("ix_llm_logs_model", "knowledge_llm_logs", ["model"])
    op.create_index("ix_llm_logs_created_at", "knowledge_llm_logs", ["created_at"])

    # ── knowledge_doc_profiles ──
    op.create_table("knowledge_doc_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(256), nullable=True, comment="Document topic"),
        sa.Column("doc_type", sa.String(64), nullable=True, comment="Material type"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_entities", postgresql.JSONB, nullable=True),
        sa.Column("core_conclusions", postgresql.JSONB, nullable=True),
        sa.Column("searchable_phrases", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["catalogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", name="uq_doc_profiles_catalog_id"),
    )
    op.create_index("ix_doc_profiles_catalog_id", "knowledge_doc_profiles", ["catalog_id"])
    op.create_index("ix_doc_profiles_topic", "knowledge_doc_profiles", ["topic"])
    op.create_index("ix_doc_profiles_doc_type", "knowledge_doc_profiles", ["doc_type"])

    # ── Extend existing chunks (after page_fusions table exists) ──
    op.add_column("chunks", sa.Column("content_hash", sa.String(64), nullable=True, comment="SHA256 for dedup"))
    op.add_column("chunks", sa.Column("page_num", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("char_offset", sa.BigInteger(), nullable=True, comment="Char offset in fusion text"))
    op.add_column("chunks", sa.Column("source_fusion_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_chunks_source_fusion_id", "chunks", "knowledge_page_fusions", ["source_fusion_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
    op.create_index("ix_chunks_catalog_id", "chunks", ["catalog_id"])
    op.create_index("ix_chunks_page_num", "chunks", ["page_num"])
    op.create_index("ix_chunks_source_fusion_id", "chunks", ["source_fusion_id"])


def downgrade() -> None:
    # Drop FK from chunks first (depends on page_fusions)
    op.drop_constraint("fk_chunks_source_fusion_id", "chunks", type_="foreignkey")
    op.drop_index("ix_chunks_content_hash", table_name="chunks")
    op.drop_index("ix_chunks_catalog_id", table_name="chunks")
    op.drop_index("ix_chunks_page_num", table_name="chunks")
    op.drop_index("ix_chunks_source_fusion_id", table_name="chunks")
    op.drop_column("chunks", "source_fusion_id")
    op.drop_column("chunks", "char_offset")
    op.drop_column("chunks", "page_num")
    op.drop_column("chunks", "content_hash")

    # Drop all new tables (reverse order of creation)
    op.drop_table("knowledge_doc_profiles")
    op.drop_table("knowledge_llm_logs")
    op.drop_table("knowledge_tasks")
    op.drop_table("knowledge_evidences")
    op.drop_table("knowledge_labels")
    op.drop_table("knowledge_semantic_roles")
    op.drop_table("knowledge_graph_edges")
    op.drop_table("knowledge_graph_nodes")
    op.drop_table("knowledge_disambig_candidates")
    op.drop_table("knowledge_extract_candidates")
    op.drop_table("knowledge_attributes")
    op.drop_table("knowledge_entity_merges")
    op.drop_table("knowledge_entity_aliases")
    op.drop_table("knowledge_entities")
    op.drop_table("knowledge_chunk_vectors")
    op.drop_table("knowledge_page_fusions")
    op.drop_table("knowledge_page_sources")

    # Drop columns from catalogs
    op.drop_index("ix_catalogs_file_hash", table_name="catalogs")
    op.drop_index("ix_catalogs_status", table_name="catalogs")
    op.drop_index("ix_catalogs_owner_id", table_name="catalogs")
    op.drop_index("ix_catalogs_channel_type", table_name="catalogs")
    op.drop_constraint("uq_catalogs_file_hash", "catalogs", type_="unique")
    op.drop_column("catalogs", "channel_type")
    op.drop_column("catalogs", "file_hash")
